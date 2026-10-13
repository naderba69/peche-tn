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


def test_high_holding_with_large_waves_reaches_the_heavy_band() -> None:
    # The extreme band is reachable only for HIGH holding with wave >= 1.5 m
    # (audit 2026-09-14, item C4); otherwise the catalog stays at 150-200 g.
    assert weight_band_for(PotentialLevel.HIGH)[0] == "heavy"
    assert weight_band_for(PotentialLevel.HIGH, 1.4)[0] == "heavy"
    assert weight_band_for(PotentialLevel.HIGH, 1.5)[0] == "extreme"
    assert weight_band_for(PotentialLevel.HIGH, 2.0)[0] == "extreme"
    # Alternatives must never be heavier than the primary scenario.
    primary = scenario_weight_band(0, PotentialLevel.HIGH, 1.6)[1]
    alternative = scenario_weight_band(1, PotentialLevel.HIGH, 1.6)[1]
    assert alternative[1] <= primary[1]


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


def test_orbital_velocity_selects_the_weight_band() -> None:
    from spotdata.domain.gear import ROD_CAP_G, band_from_orbital_velocity

    assert band_from_orbital_velocity(0.10) == "light"
    assert band_from_orbital_velocity(0.26) == "light"
    assert band_from_orbital_velocity(0.27) == "medium"
    assert band_from_orbital_velocity(0.45) == "heavy"
    assert band_from_orbital_velocity(0.60) is None
    assert ROD_CAP_G == 150


def test_recommendation_follows_bottom_load_and_respects_rod_cap() -> None:
    calm = recommend_gear(
        holding=PotentialLevel.HIGH,
        breakdown=_breakdown("none"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.6,
        wind_speed_kmh=10.0,
        orbital_velocity_ms=0.10,
    )
    assert calm.scenarios[0].weight_max_g <= 90

    rough = recommend_gear(
        holding=PotentialLevel.LOW,
        breakdown=_breakdown("none"),
        fouling=PotentialLevel.LOW,
        wave_height_m=1.2,
        wind_speed_kmh=20.0,
        orbital_velocity_ms=0.40,
    )
    # Holding says LOW, but the bottom load wins: the lead must not be light.
    assert rough.scenarios[0].weight_min_g >= 100
    assert all(scenario.weight_max_g <= 150 for scenario in rough.scenarios)

    beyond = recommend_gear(
        holding=PotentialLevel.HIGH,
        breakdown=_breakdown("longshore_current"),
        fouling=PotentialLevel.LOW,
        wave_height_m=2.5,
        wind_speed_kmh=30.0,
        orbital_velocity_ms=0.80,
    )
    assert all(scenario.weight_max_g <= 150 for scenario in beyond.scenarios)
    assert "لا تنصب" in beyond.casting_advice_ar


def test_longshore_current_can_raise_the_load_but_never_lower_it() -> None:
    calm_wave = recommend_gear(
        holding=PotentialLevel.LOW,
        breakdown=_breakdown("longshore_current"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.5,
        wind_speed_kmh=12.0,
        orbital_velocity_ms=0.10,
    )
    strong_current = recommend_gear(
        holding=PotentialLevel.LOW,
        breakdown=_breakdown("longshore_current"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.5,
        wind_speed_kmh=12.0,
        orbital_velocity_ms=0.10,
        longshore_current_ms=0.35,
    )
    assert calm_wave.scenarios[0].weight_max_g <= 90
    assert strong_current.scenarios[0].weight_min_g >= 100
    # A weak current must not lower a heavier wave-driven load.
    weak_current = recommend_gear(
        holding=PotentialLevel.LOW,
        breakdown=_breakdown("longshore_current"),
        fouling=PotentialLevel.LOW,
        wave_height_m=0.5,
        wind_speed_kmh=12.0,
        orbital_velocity_ms=0.40,
        longshore_current_ms=0.05,
    )
    assert weak_current.scenarios[0].weight_min_g >= 150
