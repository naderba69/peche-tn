from collections.abc import Callable
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import (
    DecisionLevel,
    DecisionReasonCode,
    ForceMajeureKind,
)
from spotdata.domain.models import (
    AnglerProfile,
    Coordinates,
    ForecastDataset,
    OfficialWarning,
    RankSpotsRequest,
    SpotCandidate,
    SpotProfile,
)
from spotdata.main import app

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")


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
    response = engine.rank_spots(
        [(good_spot, good), (bad_spot, bad)], good.target_date
    )
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


def test_official_warning_overrides_go_to_no_go(
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
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.OFFICIAL_WARNING
    assert result.force_majeure_kind == ForceMajeureKind.ACCESS_LEGAL
    assert result.recommended_windows == []


def test_rank_spots_endpoint(
    dataset_factory: Callable[..., ForecastDataset],
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
    with TestClient(app) as client:
        app.state.open_meteo.forecast_dataset = AsyncMock(side_effect=[good, bad])
        response = client.post("/api/v1/decisions/rank-spots", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["target_date"] == today.isoformat()
    assert [spot["spot_id"] for spot in body["ranked"]] == ["good", "bad"]
    assert body["ranked"][0]["decision"] == "go"
    assert body["ranked"][0]["best_window_start"] is not None
    assert isinstance(body["ranked"][0]["species_axes_summary"], list)
    assert body["ranked"][1]["force_majeure_kind"] == "safety"
