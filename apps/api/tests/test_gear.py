from spotdata.domain.enums import LeadShape, MontageClass, PotentialLevel
from spotdata.domain.gear import (
    CATALOG,
    recommend_gear,
    scenario_weight_band,
    weight_band_for,
)
from spotdata.domain.models import HoldingBreakdown


def _breakdown(dominant: str, confidence: int = 26) -> HoldingBreakdown:
    return HoldingBreakdown(
        longshore_current=PotentialLevel.MODERATE,
        orbital_motion=PotentialLevel.LOW,
        return_flow=PotentialLevel.LOW,
        tidal_current=PotentialLevel.LOW,
        dominant=dominant,  # type: ignore[arg-type]
        confidence=confidence,
        orbital_velocity_band_ms="0.10 إلى 0.30",
        reasons_ar=["اختبار."],
    )


def test_catalog_contains_five_lead_types() -> None:
    assert len(CATALOG) == 5
    assert {item.shape for item in CATALOG} == set(LeadShape)


def test_weight_band_rises_with_holding_difficulty() -> None:
    assert weight_band_for(PotentialLevel.LOW)[1][0] == 60
    assert weight_band_for(PotentialLevel.MODERATE)[1][0] == 100
    assert weight_band_for(PotentialLevel.HIGH)[1][0] == 150


def test_alternative_scenario_never_heavier_than_primary() -> None:
    primary = scenario_weight_band(0, PotentialLevel.HIGH)[1]
    alternative = scenario_weight_band(1, PotentialLevel.HIGH)[1]
    assert alternative[0] <= primary[0]
    assert alternative[1] <= primary[1]


def test_recommendation_is_always_multi_scenario() -> None:
    recommendation = recommend_gear(
        holding=PotentialLevel.HIGH,
        breakdown=_breakdown("longshore_current"),
        fouling=PotentialLevel.MODERATE,
        wave_height_m=1.2,
        wind_speed_kmh=24.0,
    )
    assert 1 <= len(recommendation.scenarios) <= 3
    assert all(
        scenario.weight_min_g <= scenario.weight_max_g for scenario in recommendation.scenarios
    )
    assert all(
        scenario.montage_class in {MontageClass.LOW, MontageClass.MEDIUM, MontageClass.HIGH}
        for scenario in recommendation.scenarios
    )
    # A longshore-dominant case must prefer grapnel-class holds in the first slot.
    assert recommendation.scenarios[0].shape == LeadShape.BREAKAWAY_GRAPNEL


def test_recommendation_rocky_scenario_always_last() -> None:
    recommendation = recommend_gear(
        holding=PotentialLevel.MODERATE,
        breakdown=_breakdown("none"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.6,
        wind_speed_kmh=12.0,
    )
    assert recommendation.scenarios[-1].shape == LeadShape.ROCKY


def test_recommendation_carries_rod_rating_condition() -> None:
    recommendation = recommend_gear(
        holding=PotentialLevel.LOW,
        breakdown=_breakdown("none"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.4,
        wind_speed_kmh=10.0,
    )
    assert "القصبة" in recommendation.required_rod_rating_note_ar
    assert recommendation.confidence <= 30


def test_recommendation_lowers_confidence_on_missing_forcing() -> None:
    full = recommend_gear(
        holding=PotentialLevel.HIGH,
        breakdown=_breakdown("tidal_current", confidence=26),
        fouling=PotentialLevel.LOW,
        wave_height_m=1.0,
        wind_speed_kmh=20.0,
    )
    missing = recommend_gear(
        holding=PotentialLevel.HIGH,
        breakdown=_breakdown("tidal_current", confidence=26),
        fouling=PotentialLevel.LOW,
        wave_height_m=None,
        wind_speed_kmh=None,
    )
    assert missing.confidence <= full.confidence
