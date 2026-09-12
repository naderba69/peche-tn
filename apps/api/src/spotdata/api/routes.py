from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request, status

from spotdata import __version__
from spotdata.domain.engine import ENGINE_VERSION, DecisionEngine, InsufficientDataError
from spotdata.domain.factor_catalog import factor_catalog_summary, serialized_factor_catalog
from spotdata.domain.models import (
    SCHEMA_VERSION,
    AutoOrientationRequest,
    AutoOrientationResponse,
    CoastalWaterContext,
    DecisionResponse,
    ForecastDataset,
    ForecastDecisionRequest,
    GeminiKeyVerificationResponse,
    GeminiReportRequest,
    GeminiReportResponse,
    RankSpotsRequest,
    RankSpotsResponse,
    SourceMetadata,
    SpotCandidate,
)
from spotdata.services.coast_orientation import CoastOrientationClient
from spotdata.services.copernicus_water import CopernicusWaterClient, unavailable_water_context
from spotdata.services.gemini import GeminiClient, GeminiServiceError
from spotdata.services.open_meteo import OpenMeteoClient, UpstreamDataError

router = APIRouter()
engine = DecisionEngine()
LOGGER = logging.getLogger(__name__)
TUNIS_TZ = ZoneInfo("Africa/Tunis")
OPTIONAL_WATER_TIMEOUT_SECONDS = 8.0
GeminiApiKey = Annotated[
    str,
    Header(
        alias="X-Gemini-API-Key",
        description="Runtime-only Google AI Studio key; never persisted by the API",
    ),
]


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
            "the opportunity score is not a catch probability",
            "weed/debris, turbidity and rip-current fields are low-confidence proxies, not observations",
            "tide and current use model values, not synthetic lunar times",
            "pressure, lunar and solunar claims do not receive automatic catch weights without validation",
            "all decisions include factor provenance, confidence and limitations",
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
    response_model=DecisionResponse,
    tags=["decisions"],
    summary="Fetch free forecasts plus a current station observation and issue an explainable Tunisia surfcasting decision",
)
async def forecast_decision(payload: ForecastDecisionRequest, request: Request) -> DecisionResponse:
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
    client: OpenMeteoClient = request.app.state.open_meteo
    water_client: CopernicusWaterClient = request.app.state.copernicus_water

    async def optional_water_context() -> CoastalWaterContext:
        try:
            return await asyncio.wait_for(
                water_client.coastal_context(payload.location, payload.spot),
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
            client.forecast_dataset(payload),
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
                        "TUR محفوظة بوحدة FNU ولا تتحول إلى NTU؛ CHL لا تشخّص ازدهاراً ضاراً أو نشاط السمك، والقيم لا تغير السلامة أو التنفيذ أو الفرصة أو الثقة.",
                    ],
                )
            )
        dataset = dataset.model_copy(
            update={"coastal_water_context": water_context, "sources": sources}
        )
        return engine.evaluate(dataset)
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
    summary="Analyze several known spots for one day and rank them best-to-weakest",
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
    client: OpenMeteoClient = request.app.state.open_meteo

    async def dataset_for(candidate: SpotCandidate) -> ForecastDataset:
        single = ForecastDecisionRequest(
            location=candidate.location,
            target_date=payload.target_date,
            spot=candidate.spot,
            angler=payload.angler,
            field_reports=payload.field_reports,
            test_cast=payload.test_cast,
            official_warning=payload.official_warning,
        )
        return await client.forecast_dataset(single)

    outcomes = await asyncio.gather(
        *(dataset_for(candidate) for candidate in payload.spots),
        return_exceptions=True,
    )
    datasets: list[tuple[SpotCandidate, ForecastDataset | None]] = [
        (candidate, outcome if isinstance(outcome, ForecastDataset) else None)
        for candidate, outcome in zip(payload.spots, outcomes, strict=True)
    ]
    return engine.rank_spots(datasets, payload.target_date)


@router.post(
    "/v1/decisions/evaluate",
    response_model=DecisionResponse,
    tags=["decisions"],
    summary="Evaluate a supplied forecast dataset without any network call",
)
async def evaluate_dataset(payload: ForecastDataset) -> DecisionResponse:
    try:
        return engine.evaluate(payload)
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "insufficient_forecast_data",
                "message_ar": str(exc),
            },
        ) from exc
