from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request, status

from spotdata import __version__
from spotdata.domain.engine import ENGINE_VERSION, DecisionEngine, InsufficientDataError
from spotdata.domain.enums import (
    DecisionLevel,
    DecisionReasonCode,
    FieldFeasibilityLevel,
    ForceMajeureKind,
    InmCheckStatus,
    OrientationSource,
    PotentialLevel,
    ShoreType,
    SourceDataKind,
)
from spotdata.domain.factor_catalog import factor_catalog_summary, serialized_factor_catalog
from spotdata.domain.models import (
    SCHEMA_VERSION,
    AnglerProfile,
    AutoOrientationRequest,
    AutoOrientationResponse,
    CoastalWaterContext,
    DecisionPreflightNoGo,
    DecisionResponse,
    ForecastDataset,
    ForecastDecisionRequest,
    GeminiKeyVerificationResponse,
    GeminiReportRequest,
    GeminiReportResponse,
    InmWarningAudit,
    RankedSpot,
    RankSpotsRequest,
    RankSpotsResponse,
    SourceMetadata,
    SpotCandidate,
    SpotProfile,
)
from spotdata.services.coast_orientation import CoastOrientationClient
from spotdata.services.copernicus_water import CopernicusWaterClient, unavailable_water_context
from spotdata.services.gemini import GeminiClient, GeminiServiceError
from spotdata.services.inm_warnings import InmWarningClient
from spotdata.services.open_meteo import OpenMeteoClient, UpstreamDataError

router = APIRouter()
engine = DecisionEngine()
LOGGER = logging.getLogger(__name__)
TUNIS_TZ = ZoneInfo("Africa/Tunis")
OPTIONAL_WATER_TIMEOUT_SECONDS = 8.0
# عدد البقع التي تُجلب بياناتها في آن واحد داخل مسح الولايات.
RANK_SPOTS_CONCURRENCY = 6
GeminiApiKey = Annotated[
    str,
    Header(
        alias="X-Gemini-API-Key",
        description="Runtime-only Google AI Studio key; never persisted by the API",
    ),
]


async def _safe_inm_check(
    request: Request,
    windows: list[tuple[datetime, datetime]],
) -> InmWarningAudit:
    request_id = getattr(request.state, "request_id", None)
    try:
        checker: InmWarningClient = request.app.state.inm_warnings
        return await checker.check(windows, request_id=request_id)
    except Exception as exc:
        LOGGER.exception(
            "INM verification failed closed request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )
        return InmWarningAudit(
            status=InmCheckStatus.UNVERIFIED,
            request_id=request_id,
            checked_at=datetime.now(UTC),
            coverage_status="unknown",
            coverage_ar="تعذر إثبات نطاق التغطية.",
            reason_code="verifier_internal_error",
            explanation_ar="تعطل محلل تحقق INM داخلياً؛ بقي القرار NO_GO احترازياً.",
        )


def _missing_automated_spot_context(profile: AutoOrientationResponse) -> list[str]:
    missing: list[str] = []
    if profile.status != "resolved" or profile.orientation_deg is None or profile.evidence is None:
        missing.append("اتجاه الساحل: لم يُحسب من هندسة OSM صالحة قرب البقعة.")
    elif (
        profile.evidence.confidence != "high"
        or profile.evidence.coastline_distance_m > 500.0
        or profile.evidence.segments_used < 3
    ):
        missing.append(
            "اتجاه الساحل: الدليل الآلي لا يحقق شرط الثقة العالية (≤500م وثلاثة مقاطع على الأقل)؛ بقي Unknown."
        )
    return missing


def _full_day_angler_profile(angler: AnglerProfile) -> AnglerProfile:
    """Experience is not a decision input; this product always analyzes 24 hours."""
    return angler.model_copy(update={"experience": None, "session_hours": 24})


def _effective_shore_type(
    original: SpotProfile, profile: AutoOrientationResponse
) -> tuple[ShoreType | None, str]:
    """Prefer an explicit user selection; otherwise use only server-verified OSM tags."""
    if original.shore_type is not None and original.shore_type_source == "user":
        return original.shore_type, "user"
    shore = profile.shore_profile
    if shore is not None and shore.status == "resolved" and shore.shore_type is not None:
        return shore.shore_type, "overpass"
    return None, "unknown"


def _server_spot_profile(original: SpotProfile, profile: AutoOrientationResponse) -> SpotProfile:
    has_orientation = (
        profile.status == "resolved"
        and profile.orientation_deg is not None
        and profile.evidence is not None
    )
    shore_type, shore_type_source = _effective_shore_type(original, profile)
    return original.model_copy(
        update={
            "seaward_orientation_deg": profile.orientation_deg if has_orientation else None,
            "orientation_source": OrientationSource.OVERPASS
            if has_orientation
            else OrientationSource.ESTIMATED,
            "orientation_evidence": profile.evidence if has_orientation else None,
            "shore_type": shore_type,
            "shore_type_source": shore_type_source,
            "exposure": None,
        }
    )


def _preflight_no_go(
    missing_context_ar: list[str],
    automated_profile: AutoOrientationResponse | None = None,
    *,
    reason_code: DecisionReasonCode = DecisionReasonCode.CRITICAL_DATA_MISSING,
) -> DecisionPreflightNoGo:
    sources: list[SourceMetadata] = []
    if automated_profile is not None and automated_profile.evidence is not None:
        sources.append(
            SourceMetadata(
                provider="OpenStreetMap Overpass",
                product="OSM coastline geometry / seaward normal",
                data_kind=SourceDataKind.MAP_DATA,
                variables=["natural=coastline", "orientation_deg", "coastline_tangent_deg"],
                retrieved_at=automated_profile.evidence.calculated_at,
                limitations_ar=list(automated_profile.evidence.limitations_ar),
            )
        )
    if automated_profile is not None and automated_profile.shore_profile is not None:
        shore = automated_profile.shore_profile
        sources.append(
            SourceMetadata(
                provider="OpenStreetMap Overpass",
                product=(
                    f"OSM way/{shore.evidence_feature_id}"
                    if shore.evidence_feature_id is not None
                    else "OSM nearby shore-tag query"
                ),
                data_kind=SourceDataKind.MAP_DATA,
                variables=sorted(shore.raw_tags),
                retrieved_at=shore.retrieved_at,
                limitations_ar=list(shore.limitations_ar),
            )
        )
    return DecisionPreflightNoGo(
        decision_reason_code=reason_code,
        summary_ar=(
            "لا تذهب: تعذر التحقق الآلي من حداثة تحذيرات INM ونطاق تغطيتها؛ "
            "لا يُسمح بإصدار GO حتى ينجح هذا الفحص."
            if reason_code == DecisionReasonCode.OFFICIAL_WARNING_UNVERIFIED
            else "لا تذهب: اتجاه الساحل أو بيانات 24 ساعة غير مكتملة؛ لم يصدر المحرك GO."
        ),
        missing_context_ar=missing_context_ar,
        automated_orientation=automated_profile,
        sources=sources,
        generated_at=datetime.now(UTC),
    )


@router.get("", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "name": "Peche TN Decision API",
        "version": __version__,
        "docs": "/api/docs",
        "methodology": "/api/methodology",
    }


@router.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, object]:
    client: OpenMeteoClient = request.app.state.open_meteo
    water_client: CopernicusWaterClient = request.app.state.copernicus_water
    return {
        "status": "ok",
        "version": __version__,
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "time": datetime.now(TUNIS_TZ).isoformat(),
        "upstream_cache": {
            "entries": client.cache.size,
            "hits": client.cache.hits,
            "misses": client.cache.misses,
            "scope": "process_memory",
        },
        "satellite_cache": {
            "entries": water_client.cache.size,
            "hits": water_client.cache.hits,
            "misses": water_client.cache.misses,
            "scope": "process_memory",
        },
    }


@router.get("/methodology", tags=["system"])
async def methodology() -> dict[str, object]:
    return {
        "principles": [
            "safety, field feasibility, fishing opportunity and confidence are separate axes",
            "the safety gate cannot be overridden by the other axes",
            "missing values never become zero/calm conditions",
            "choose a spot: verified shoreline geometry is fetched automatically; forecasts are analyzed for a fixed 24-hour period without experience/session settings; if shore type is undocumented, the report is still computed with the most conservative known wave threshold but final decision remains NO_GO; coast exposure remains Unknown",
            "the opportunity score is not a catch probability",
            "weed/debris, turbidity and rip-current fields are low-confidence proxies, not observations",
            "tide and current use model values, not synthetic lunar times",
            "pressure, lunar and solunar claims do not receive automatic catch weights without validation",
            "all decisions include factor provenance, confidence and limitations",
            "the API fetches forecasts and exposes a request-scoped INM BMS audit; GO requires a fresh uncached official response, explicit clear state, verified national coastal coverage and no conflict; warning, stale data, parser conflict or unavailable source remain NO_GO; manual acknowledgement never substitutes",
            "user-entered field reports, test casts and warning claims are excluded from decisions",
            "fresh METAR values are direct airport-station observations and are never relabelled as spot observations",
            "station/model reconciliation is distance- and age-gated; divergence lowers confidence without spatially copying the station value",
            "spot orientation points from shore to open sea; wind and wave bearings are source/from directions, while current bearing is towards",
            "signed alongshore diagnostics use the positive bearing (seaward orientation + 90 degrees) modulo 360",
            "wind stress, circular directional coherence and wave-component crossing diagnostics are context-only and have no invented decision threshold",
            "Sentinel-2 TUR/SPM/CHL is intermittent remote-sensing context, never a field measurement, hourly forecast or fishing-opportunity input",
        ],
        "free_data_providers": [
            "Open-Meteo model forecasts",
            "AviationWeather.gov METAR direct station observations",
            "OpenStreetMap Overpass coastline geometry",
            "Copernicus Marine public WMTS Sentinel-2 ocean-colour retrievals",
            "INM Tunisia official BMS marine-warning page (strict fail-closed parser)",
        ],
        "optional_writer": "Google Gemini structured prose with a transient user key",
        "factor_coverage": factor_catalog_summary().model_dump(mode="json"),
        "factor_catalog": "/api/methodology/factors",
        "llm_in_decision_path": False,
    }


@router.get("/methodology/factors", tags=["system"])
async def methodology_factors() -> dict[str, object]:
    return {
        "coverage": factor_catalog_summary().model_dump(mode="json"),
        "factors": serialized_factor_catalog(),
    }


@router.post(
    "/v1/spots/orientation",
    response_model=AutoOrientationResponse,
    tags=["spots"],
    summary="Calculate a corrected Overpass coastline normal for a Tunisian spot",
)
async def auto_orientation(
    payload: AutoOrientationRequest, request: Request
) -> AutoOrientationResponse:
    client: CoastOrientationClient = request.app.state.coast_orientation
    return await client.resolve(payload.latitude, payload.longitude)


@router.post(
    "/v1/gemini/verify",
    response_model=GeminiKeyVerificationResponse,
    tags=["reports"],
    summary="Verify a runtime-only Google Gemini key without storing it",
)
async def verify_gemini_key(
    request: Request, gemini_api_key: GeminiApiKey
) -> GeminiKeyVerificationResponse:
    client: GeminiClient = request.app.state.gemini
    try:
        return await client.verify_key(gemini_api_key)
    except GeminiServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message_ar": exc.message_ar},
        ) from exc


@router.post(
    "/v1/reports/gemini",
    response_model=GeminiReportResponse,
    tags=["reports"],
    summary="Generate a schema-validated narrative without changing engine facts",
)
async def generate_gemini_report(
    payload: GeminiReportRequest,
    request: Request,
    gemini_api_key: GeminiApiKey,
) -> GeminiReportResponse:
    if payload.decision.engine_version != ENGINE_VERSION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "stale_engine_result",
                "message_ar": "أعد تحليل البقعة بالمحرك الحالي قبل توليد تقرير Gemini.",
            },
        )
    client: GeminiClient = request.app.state.gemini
    try:
        return await client.generate_report(
            gemini_api_key,
            payload.request,
            payload.decision,
        )
    except GeminiServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message_ar": exc.message_ar},
        ) from exc


@router.post(
    "/v1/decisions/forecast",
    response_model=DecisionResponse | DecisionPreflightNoGo,
    tags=["decisions"],
    summary="Fetch a spot's verified shore direction and analyze a fixed 24-hour forecast",
)
async def forecast_decision(
    payload: ForecastDecisionRequest, request: Request
) -> DecisionResponse | DecisionPreflightNoGo:
    today = datetime.now(TUNIS_TZ).date()
    if payload.target_date < today or payload.target_date > today + timedelta(days=7):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "target_date_out_of_range",
                "message_ar": "التاريخ يجب أن يكون بين اليوم وسبعة أيام قادمة.",
                "details": {
                    "min": today.isoformat(),
                    "max": (today + timedelta(days=7)).isoformat(),
                },
            },
        )
    coast_client: CoastOrientationClient = request.app.state.coast_orientation
    automated_profile = await coast_client.resolve(
        payload.location.latitude,
        payload.location.longitude,
    )
    missing_context = _missing_automated_spot_context(automated_profile)
    if missing_context:
        return _preflight_no_go(missing_context, automated_profile)

    assert automated_profile.orientation_deg is not None
    assert automated_profile.evidence is not None
    shore_type, shore_type_source = _effective_shore_type(payload.spot, automated_profile)
    verified_spot = payload.spot.model_copy(
        update={
            "seaward_orientation_deg": automated_profile.orientation_deg,
            "orientation_source": OrientationSource.OVERPASS,
            "orientation_evidence": automated_profile.evidence,
            "shore_type": shore_type,
            "shore_type_source": shore_type_source,
            "exposure": None,
        }
    )
    verified_payload = payload.model_copy(
        update={"spot": verified_spot, "angler": _full_day_angler_profile(payload.angler)}
    )

    client: OpenMeteoClient = request.app.state.open_meteo
    water_client: CopernicusWaterClient = request.app.state.copernicus_water

    async def optional_water_context() -> CoastalWaterContext:
        try:
            return await asyncio.wait_for(
                water_client.coastal_context(verified_payload.location, verified_payload.spot),
                timeout=OPTIONAL_WATER_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            # Satellite context is explicitly outside the decision path. An upstream,
            # parsing, timeout or schema failure must never suppress the deterministic forecast.
            LOGGER.warning(
                "Optional Copernicus coastal-water context unavailable (%s): %s",
                type(exc).__name__,
                exc,
            )
            return unavailable_water_context(
                payload.location,
                payload.spot,
                "تعذر إكمال استرجاع Copernicus الاختياري ضمن المهلة؛ بقيت القيم Unknown ولم يتأثر القرار.",
            )

    try:
        dataset, water_context = await asyncio.gather(
            client.forecast_dataset(verified_payload),
            optional_water_context(),
        )
        sources = list(dataset.sources)
        if water_context.availability == "available":
            variables = [
                name
                for name, value in (
                    ("turbidity_fnu", water_context.turbidity_fnu),
                    (
                        "suspended_particulate_matter_g_m3",
                        water_context.suspended_particulate_matter_g_m3,
                    ),
                    ("chlorophyll_a_mg_m3", water_context.chlorophyll_a_mg_m3),
                )
                if value is not None
            ]
            sources.append(
                SourceMetadata(
                    provider="Copernicus Marine Service / Sentinel-2",
                    product=(
                        "Mediterranean daily 100 m ocean-colour TUR/SPM/CHL mosaic "
                        "(OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205)"
                    ),
                    data_kind="remote_sensing_estimate",
                    variables=variables,
                    horizontal_resolution_km=0.1,
                    retrieved_at=water_context.retrieved_at,
                    limitations_ar=[
                        "استعادة أقمار صناعية سياقية عند بكسل بحري ثابت، وليست قياساً ميدانياً داخل البقعة أو توقعاً لساعات الرحلة.",
                        "السحب والظل والوهج وقرب الساحل قد تجعل البكسل Unknown؛ لا يملأ Peche TN الفجوات ولا يبحث جانبياً عن قيمة ملائمة.",
                        "TUR محفوظة بوحدة FNU ولا تتحول إلى NTU؛ CHL لا تشخّص ازدهاراً ضاراً أو نشاط السمك. الاستثناء الوحيد: CHL كثيف حديث (≤48 ساعة) مع بروكسي نقل مرتفع قد يسبب منعاً احترازياً؛ لا يغيّر ذلك السلامة أو قابلية التنفيذ أو الفرصة أو الثقة.",
                    ],
                )
            )
        shore_profile = automated_profile.shore_profile
        if shore_profile is not None:
            sources.append(
                SourceMetadata(
                    provider="OpenStreetMap Overpass",
                    product=(
                        f"OSM way/{shore_profile.evidence_feature_id} + nearby coastline geometry"
                        if shore_profile.evidence_feature_id is not None
                        else "OSM nearby shore tags + coastline geometry"
                    ),
                    data_kind=SourceDataKind.MAP_DATA,
                    variables=sorted(shore_profile.raw_tags),
                    retrieved_at=shore_profile.retrieved_at,
                    limitations_ar=[
                        *shore_profile.limitations_ar,
                        *(
                            [
                                f"ميزة التصنيف تبعد {shore_profile.feature_distance_m:.1f} م عن الإحداثيات المطلوبة."
                            ]
                            if shore_profile.feature_distance_m is not None
                            else []
                        ),
                        "اتجاه الساحل محسوب من هندسة OSM؛ لا يمثل مسحاً ميدانياً أو تحذيراً رسمياً.",
                    ],
                )
            )
        dataset = dataset.model_copy(
            update={"coastal_water_context": water_context, "sources": sources}
        )
        decision = engine.evaluate(dataset)
        inm_audit = await _safe_inm_check(
            request,
            [(window.start, window.end) for window in decision.recommended_windows]
            if decision.decision == DecisionLevel.GO
            else [],
        )
        decision = engine.apply_official_warning_check(dataset, decision, inm_audit)
        return decision.model_copy(
            update={
                "spot_profile": verified_spot,
                "automated_shore_profile": shore_profile,
            }
        )
    except UpstreamDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "upstream_data_error",
                "message_ar": exc.message_ar,
                "details": exc.details,
            },
        ) from exc
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "insufficient_forecast_data",
                "message_ar": str(exc),
            },
        ) from exc


@router.post(
    "/v1/decisions/rank-spots",
    response_model=RankSpotsResponse,
    tags=["decisions"],
    summary="Compare spots over a fixed 24-hour forecast after verifying each shore direction",
)
async def rank_spots(payload: RankSpotsRequest, request: Request) -> RankSpotsResponse:
    today = datetime.now(TUNIS_TZ).date()
    if payload.target_date < today or payload.target_date > today + timedelta(days=7):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "target_date_out_of_range",
                "message_ar": "التاريخ يجب أن يكون بين اليوم وسبعة أيام قادمة.",
                "details": {
                    "min": today.isoformat(),
                    "max": (today + timedelta(days=7)).isoformat(),
                },
            },
        )
    coast_client: CoastOrientationClient = request.app.state.coast_orientation
    profile_gate = asyncio.Semaphore(RANK_SPOTS_CONCURRENCY)

    async def profile_for(candidate: SpotCandidate) -> AutoOrientationResponse:
        async with profile_gate:
            return await coast_client.resolve(
                candidate.location.latitude,
                candidate.location.longitude,
            )

    profiles = await asyncio.gather(*(profile_for(candidate) for candidate in payload.spots))
    missing_by_spot = [
        (
            candidate,
            profile,
            _missing_automated_spot_context(profile),
        )
        for candidate, profile in zip(payload.spots, profiles, strict=True)
    ]
    if any(missing for _, _, missing in missing_by_spot):
        ranked = [
            RankedSpot(
                spot_id=candidate.spot_id,
                name_ar=candidate.name_ar,
                spot_profile=_server_spot_profile(candidate.spot, profile),
                automated_shore_profile=profile.shore_profile,
                decision=DecisionLevel.NO_GO,
                decision_reason_code=DecisionReasonCode.CRITICAL_DATA_MISSING,
                force_majeure_kind=ForceMajeureKind.DATA,
                best_window_start=None,
                best_window_end=None,
                opportunity_score=None,
                field_status=FieldFeasibilityLevel.UNKNOWN,
                holding_difficulty=PotentialLevel.UNKNOWN,
                summary_ar="لا تذهب: ملف الساحل الآلي غير مكتمل.",
                error_ar=" ".join(missing),
            )
            for candidate, profile, missing in missing_by_spot
        ]
        return RankSpotsResponse(
            target_date=payload.target_date,
            generated_at=datetime.now(UTC),
            ranked=ranked,
            notes_ar=[
                "كل البقع تُحجب احترازياً حتى تتوفر خصائص ساحل آلية ذات مصدر مكاني موثق؛ القيم التي يرسلها العميل لا تُعد إثباتاً.",
                "مؤشر الفرصة غير متاح عند نقص ملف الساحل، وليس صفراً ولا احتمال مصيد.",
            ],
        )

    client: OpenMeteoClient = request.app.state.open_meteo
    verified_candidates: list[SpotCandidate] = []
    profile_by_spot_id: dict[str, AutoOrientationResponse] = {}
    for candidate, profile, _missing in missing_by_spot:
        assert profile.orientation_deg is not None
        assert profile.evidence is not None
        shore_type, shore_type_source = _effective_shore_type(candidate.spot, profile)
        verified_spot = candidate.spot.model_copy(
            update={
                "seaward_orientation_deg": profile.orientation_deg,
                "orientation_source": OrientationSource.OVERPASS,
                "orientation_evidence": profile.evidence,
                "shore_type": shore_type,
                "shore_type_source": shore_type_source,
                "exposure": None,
            }
        )
        verified_candidates.append(candidate.model_copy(update={"spot": verified_spot}))
        profile_by_spot_id[candidate.spot_id] = profile

    # حدّ التزامن: ترتيب كل الولايات قد يعني 24 بقعة في عدة مزوّدين دفعةً واحدة،
    # وهو ما يستنزف حصص Open-Meteo ويُبطئ Render. ننفّذ على دفعات متوازية محدودة.
    gate = asyncio.Semaphore(RANK_SPOTS_CONCURRENCY)

    async def dataset_for(candidate: SpotCandidate) -> ForecastDataset:
        single = ForecastDecisionRequest(
            location=candidate.location,
            target_date=payload.target_date,
            spot=candidate.spot,
            angler=_full_day_angler_profile(payload.angler),
        )
        async with gate:
            dataset = await client.forecast_dataset(single)
        profile = profile_by_spot_id[candidate.spot_id].shore_profile
        if profile is None:
            return dataset
        source = SourceMetadata(
            provider="OpenStreetMap Overpass",
            product=(
                f"OSM way/{profile.evidence_feature_id} + nearby coastline geometry"
                if profile.evidence_feature_id is not None
                else "OSM nearby shore tags + coastline geometry"
            ),
            data_kind=SourceDataKind.MAP_DATA,
            variables=sorted(profile.raw_tags),
            retrieved_at=profile.retrieved_at,
            limitations_ar=[
                *profile.limitations_ar,
                *(
                    [
                        f"ميزة التصنيف تبعد {profile.feature_distance_m:.1f} م عن الإحداثيات المطلوبة."
                    ]
                    if profile.feature_distance_m is not None
                    else []
                ),
                "اتجاه الساحل محسوب من هندسة OSM؛ لا يمثل مسحاً ميدانياً أو تحذيراً رسمياً.",
            ],
        )
        return dataset.model_copy(update={"sources": [*dataset.sources, source]})

    outcomes = await asyncio.gather(
        *(dataset_for(candidate) for candidate in verified_candidates),
        return_exceptions=True,
    )
    datasets: list[tuple[SpotCandidate, ForecastDataset | None]] = [
        (candidate, outcome if isinstance(outcome, ForecastDataset) else None)
        for candidate, outcome in zip(verified_candidates, outcomes, strict=True)
    ]
    preliminary = engine.rank_spots(datasets, payload.target_date)
    candidate_windows = [
        (item.best_window_start, item.best_window_end)
        for item in preliminary.ranked
        if item.decision == DecisionLevel.GO
        and item.best_window_start is not None
        and item.best_window_end is not None
    ]
    inm_audit = await _safe_inm_check(request, candidate_windows)
    response = (
        engine.rank_spots(
            datasets,
            payload.target_date,
            official_warning_check=inm_audit,
        )
        if candidate_windows
        else preliminary.model_copy(update={"official_warning_check": inm_audit})
    )
    enriched_ranked = [
        item.model_copy(
            update={
                "spot_profile": next(
                    (
                        candidate.spot
                        for candidate in verified_candidates
                        if candidate.spot_id == item.spot_id
                    ),
                    None,
                ),
                "automated_shore_profile": profile_by_spot_id[item.spot_id].shore_profile,
            }
        )
        for item in response.ranked
    ]
    return response.model_copy(update={"ranked": enriched_ranked})
