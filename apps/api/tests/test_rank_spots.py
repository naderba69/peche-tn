from collections.abc import Callable
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import (
    DecisionLevel,
    DecisionReasonCode,
    ForceMajeureKind,
    InmCheckStatus,
)
from spotdata.domain.models import (
    AnglerProfile,
    AutomatedShoreProfile,
    AutoOrientationResponse,
    Coordinates,
    ForecastDataset,
    InmWarningAudit,
    OfficialWarning,
    OrientationEvidence,
    RankSpotsRequest,
    SpotCandidate,
    SpotProfile,
)
from spotdata.main import app

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")


def _unverified_inm_audit() -> InmWarningAudit:
    return InmWarningAudit(
        status=InmCheckStatus.UNVERIFIED,
        checked_at=datetime.now(TZ),
        coverage_status="unknown",
        coverage_ar="unknown",
        reason_code="synthetic_unverified",
        explanation_ar="INM test source was not verifiable.",
    )


def _candidate(
    spot_id: str, name: str, latitude: float, longitude: float, shore: str = "sandy"
) -> SpotCandidate:
    return SpotCandidate(
        spot_id=spot_id,
        name_ar=name,
        location=Coordinates(latitude=latitude, longitude=longitude, name=name),
        spot=SpotProfile(
            seaward_orientation_deg=90,
            orientation_source="manual",
            shore_type=shore,  # type: ignore[arg-type]
            exposure="open",
        ),
    )


def test_rank_spots_orders_go_first(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    good = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    bad = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"wind_speed_kmh": 60.0, "wind_gust_kmh": 75.0, "wave_height_m": 3.5},
    )
    good_spot = _candidate("good", "البقعة الجيدة", 36.8, 10.3)
    bad_spot = _candidate("bad", "البقعة الخطرة", 37.2, 10.0)
    response = engine.rank_spots([(good_spot, good), (bad_spot, bad)], good.target_date)
    assert [spot.spot_id for spot in response.ranked] == ["good", "bad"]
    assert response.ranked[0].decision == DecisionLevel.GO
    assert response.ranked[0].best_window_start is not None
    assert response.ranked[0].species_label_ar == "صيد عام"
    assert response.ranked[1].decision == DecisionLevel.NO_GO
    assert response.ranked[1].force_majeure_kind == ForceMajeureKind.SAFETY


def test_rank_spots_keeps_failed_fetch_last(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    good = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    response = engine.rank_spots(
        [
            (_candidate("ok", "بقعة سليمة", 36.8, 10.3), good),
            (_candidate("dead", "بقعة بلا بيانات", 35.0, 11.0), None),
        ],
        good.target_date,
    )
    assert response.ranked[0].spot_id == "ok"
    assert response.ranked[0].decision == DecisionLevel.GO
    assert response.ranked[1].spot_id == "dead"
    assert response.ranked[1].decision == DecisionLevel.NO_GO
    assert response.ranked[1].decision_reason_code == DecisionReasonCode.CRITICAL_DATA_MISSING
    assert response.ranked[1].error_ar


def test_official_warning_input_is_ignored_by_the_engine(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    warned = base.model_copy(
        update={
            "official_warning": OfficialWarning(
                source="inm",
                kind="strong_wind",
                level="warning",
                issued_at=base.fetched_at,
                text_ar="نشرة المعهد: رياح قوية قرب السواحل.",
            )
        }
    )
    result = engine.evaluate(warned)
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert result.force_majeure_kind != ForceMajeureKind.ACCESS_LEGAL
    assert result.recommended_windows
    assert any("GO النهائي يتطلب تحققاً آلياً حديثاً" in item for item in result.limitations_ar)


def test_rank_spots_endpoint_returns_no_go_without_automated_spot_profile(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    bad = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"wind_speed_kmh": 60.0, "wind_gust_kmh": 75.0, "wave_height_m": 3.5},
    )
    today = datetime.now(TZ).date()
    payload = RankSpotsRequest(
        target_date=today,
        angler=AnglerProfile(),
        spots=[
            _candidate("good", "البقعة الجيدة", 36.8, 10.3),
            _candidate("bad", "البقعة الخطرة", 37.2, 10.0),
        ],
    ).model_dump(mode="json")
    payload.update(
        {
            "field_reports": [
                {
                    "kind": "fouling",
                    "severity": "dense",
                    "source": "official",
                    "reported_at": datetime.now(TZ).isoformat(),
                }
            ],
            "test_cast": {"cast_at": datetime.now(TZ).isoformat(), "hooked": True},
            "official_warning": {
                "source": "inm",
                "kind": "strong_wind",
                "level": "alert",
                "issued_at": datetime.now(TZ).isoformat(),
            },
        }
    )
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.coast_orientation,
            "resolve",
            AsyncMock(
                return_value=AutoOrientationResponse(
                    status="unavailable",
                    reasons_ar=["synthetic unavailable map profile"],
                )
            ),
        )
        mock_fetch = AsyncMock(side_effect=[good, bad])
        app.state.open_meteo.forecast_dataset = mock_fetch
        response = client.post("/api/v1/decisions/rank-spots", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["target_date"] == today.isoformat()
    assert [spot["spot_id"] for spot in body["ranked"]] == ["good", "bad"]
    assert [spot["decision"] for spot in body["ranked"]] == ["no_go", "no_go"]
    assert all(spot["decision_reason_code"] == "critical_data_missing" for spot in body["ranked"])
    assert all(spot["best_window_start"] is None for spot in body["ranked"])
    assert all(spot["opportunity_score"] is None for spot in body["ranked"])
    assert all("اتجاه الساحل" in spot["error_ar"] for spot in body["ranked"])
    mock_fetch.assert_not_awaited()


def test_rank_spots_fails_closed_when_inm_warning_coverage_is_unverified(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(TZ)
    evidence = OrientationEvidence(
        orientation_deg=90,
        coastline_tangent_deg=0,
        coastline_distance_m=35,
        search_radius_m=3000,
        segments_used=4,
        confidence="high",
        provider="OpenStreetMap Overpass",
        server="https://overpass.test/api",
        calculated_at=now,
        limitations_ar=["test evidence"],
    )
    shore = AutomatedShoreProfile(
        status="resolved",
        retrieved_at=now,
        shore_type="sandy",
        exposure=None,
        evidence_feature_id=123,
        evidence_feature_version=1,
        evidence_feature_timestamp=now,
        feature_distance_m=10,
        raw_tags={"natural": "beach", "surface": "sand"},
        confidence="high",
        limitations_ar=["test shore tags"],
    )
    profile = AutoOrientationResponse(
        status="resolved",
        orientation_deg=90,
        evidence=evidence,
        shore_profile=shore,
        reasons_ar=["test profile"],
    )
    payload = RankSpotsRequest(
        target_date=now.date(),
        angler=AnglerProfile(experience="intermediate", session_hours=24),
        spots=[_candidate("one", "بقعة", 36.8, 10.3)],
    ).model_dump(mode="json")
    dataset = dataset_factory(
        target_date=now.date(),
        count=96,
        start_at=datetime.combine(now.date(), datetime.min.time(), TZ),
    )
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.coast_orientation, "resolve", AsyncMock(return_value=profile))
        forecast_mock = AsyncMock(return_value=dataset)
        monkeypatch.setattr(app.state.open_meteo, "forecast_dataset", forecast_mock)
        inm_mock = AsyncMock(return_value=_unverified_inm_audit())
        monkeypatch.setattr(app.state.inm_warnings, "check", inm_mock)
        response = client.post("/api/v1/decisions/rank-spots", json=payload)
    assert response.status_code == 200
    body = response.json()
    spot = body["ranked"][0]
    assert spot["decision"] == "no_go"
    assert spot["decision_reason_code"] == "official_warning_unverified"
    assert "تعذر إثبات خلو نشرة INM" in spot["summary_ar"]
    assert body["official_warning_check"]["status"] == "unverified"
    forecast_mock.assert_awaited_once()
    inm_mock.assert_awaited_once()


def test_rank_spots_accepts_every_preset_spot() -> None:
    """انحدار: صفحة الولايات ترسل كل البقع المعروفة (21) دفعة واحدة.

    الحد القديم (12) كان يرد 422 ويظهر للمستخدم كـ«تعذر ترتيب البقع».
    """
    spots = [
        _candidate(f"spot-{index}", f"بقعة {index}", 36.0 + index * 0.05, 10.0)
        for index in range(21)
    ]
    request = RankSpotsRequest(target_date=datetime(2026, 9, 14, tzinfo=TZ).date(), spots=spots)
    assert len(request.spots) == 21


def test_rank_spots_rejects_above_documented_ceiling() -> None:
    """السقف 24 يبقى مُطبَّقاً حتى لا يُخنق المزوّد بمسح غير محدود."""
    import pytest
    from pydantic import ValidationError

    spots = [
        _candidate(f"spot-{index}", f"بقعة {index}", 36.0 + index * 0.05, 10.0)
        for index in range(25)
    ]
    with pytest.raises(ValidationError):
        RankSpotsRequest(target_date=datetime(2026, 9, 14, tzinfo=TZ).date(), spots=spots)
