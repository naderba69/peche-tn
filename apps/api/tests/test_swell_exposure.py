from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionLevel, FactorImpact, WaveIncidence
from spotdata.domain.models import (
    Coordinates,
    ForecastDataset,
    SpotCandidate,
    SpotProfile,
)

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")


def _codes(hour) -> set[str]:
    return {factor.code for factor in hour.factors}


def test_swell_incidence_derived_and_exposure_context(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    exposed = dataset_factory(
        hour_updates={"swell_height_m": 1.2, "swell_direction_deg": 90.0},
    )
    result = engine.evaluate(exposed)
    hour = result.hourly[0]
    assert hour.derived.swell_incidence == WaveIncidence.DIRECT
    assert "direct_swell_exposure" in _codes(hour)
    factor = next(f for f in hour.factors if f.code == "direct_swell_exposure")
    assert factor.impact == FactorImpact.NEUTRAL
    assert factor.severity.value == "info"


def test_swell_from_land_side_marks_spot_sheltered(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    sheltered = dataset_factory(
        hour_updates={"swell_height_m": 1.2, "swell_direction_deg": 270.0},
    )
    result = engine.evaluate(sheltered)
    hour = result.hourly[0]
    assert hour.derived.swell_incidence == WaveIncidence.INCONSISTENT
    assert "sheltered_from_swell" in _codes(hour)
    factor = next(f for f in hour.factors if f.code == "sheltered_from_swell")
    assert factor.impact == FactorImpact.NEUTRAL
    assert factor.severity.value == "info"


def test_swell_exposure_is_context_only_and_never_changes_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    baseline = dataset_factory()
    exposed = dataset_factory(
        hour_updates={"swell_height_m": 1.2, "swell_direction_deg": 90.0},
    )
    base = engine.evaluate(baseline)
    with_swell = engine.evaluate(exposed)
    assert with_swell.decision == base.decision
    assert with_swell.decision_reason_code == base.decision_reason_code
    assert with_swell.opportunity_score == base.opportunity_score


def test_rank_spots_surfaces_swell_exposure(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    start = datetime(2026, 9, 4, 0, tzinfo=TZ)
    exposed = dataset_factory(
        count=96,
        start_at=start,
        hour_updates={"swell_height_m": 1.2, "swell_direction_deg": 90.0},
    )
    sheltered = dataset_factory(
        count=96,
        start_at=start,
        hour_updates={"swell_height_m": 1.2, "swell_direction_deg": 270.0},
    )
    calm = dataset_factory(count=96, start_at=start)

    def candidate(spot_id: str, name: str, seaward: float) -> SpotCandidate:
        return SpotCandidate(
            spot_id=spot_id,
            name_ar=name,
            location=Coordinates(latitude=36.8, longitude=10.3, name=name),
            spot=SpotProfile(
                seaward_orientation_deg=seaward,
                orientation_source="manual",
                shore_type="sandy",  # type: ignore[arg-type]
                exposure="open",
            ),
        )

    response = engine.rank_spots(
        [
            (candidate("exposed", "مكشوفة", 90.0), exposed),
            (candidate("sheltered", "محمية", 270.0), sheltered),
            (candidate("calm", "هادئة", 90.0), calm),
        ],
        exposed.target_date,
    )
    by_id = {spot.spot_id: spot for spot in response.ranked}
    assert by_id["exposed"].swell_exposure == WaveIncidence.DIRECT
    assert by_id["sheltered"].swell_exposure == WaveIncidence.INCONSISTENT
    assert by_id["calm"].swell_exposure is None
    assert by_id["exposed"].decision in {DecisionLevel.GO, DecisionLevel.NO_GO}
