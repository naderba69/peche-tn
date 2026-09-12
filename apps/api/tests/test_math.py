from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.enums import TideState, WaveIncidence, WindRelation
from spotdata.domain.math import (
    alongshore_wave_proxy,
    alongshore_wave_signed_proxy,
    circular_difference_deg,
    classify_wave,
    classify_wind,
    deep_water_wave_steepness,
    deep_water_wavelength_m,
    dispersion_wavenumber,
    gust_factor,
    incoming_direction_components,
    incoming_direction_signed_components,
    kmh_to_knots,
    kmh_to_mps,
    knots_to_kmh,
    near_bottom_orbital_velocity_ms,
    neutral_wind_drag_coefficient,
    project_current,
    sea_level_rates,
    secondary_wave_energy_share,
    signed_difference_deg,
    tide_states,
    wave_energy_proxy,
    weighted_directional_coherence,
    wind_stress_pa,
    wind_stress_signed_components,
)
from spotdata.domain.models import ForecastHour

TZ = ZoneInfo("Africa/Tunis")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(10, 350, 20), (350, 10, 20), (90, 270, 180), (45, 45, 0)],
)
def test_circular_difference(a: float, b: float, expected: float) -> None:
    assert circular_difference_deg(a, b) == expected


def test_signed_difference_wraps() -> None:
    assert signed_difference_deg(10, 350) == 20
    assert signed_difference_deg(350, 10) == -20


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (90, WindRelation.ONSHORE),
        (270, WindRelation.OFFSHORE),
        (145, WindRelation.CROSS_ONSHORE),
        (210, WindRelation.CROSS_OFFSHORE),
        (None, WindRelation.UNKNOWN),
    ],
)
def test_wind_direction_uses_from_convention(
    direction: float | None, expected: WindRelation
) -> None:
    relation, _ = classify_wind(direction, 90)
    assert relation == expected


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (90, WaveIncidence.DIRECT),
        (140, WaveIncidence.OBLIQUE),
        (175, WaveIncidence.ALONGSHORE),
        (270, WaveIncidence.INCONSISTENT),
        (None, WaveIncidence.UNKNOWN),
    ],
)
def test_wave_incidence(direction: float | None, expected: WaveIncidence) -> None:
    relation, _ = classify_wave(direction, 90)
    assert relation == expected


@pytest.mark.parametrize("orientation", [0.0, 45.0, 90.0, 180.0, 270.0, 359.0])
def test_incoming_from_convention_is_rotation_invariant(orientation: float) -> None:
    """The outward normal itself is sea-origin; its opposite is land-origin."""
    from_sea = orientation % 360
    from_land = (orientation + 180) % 360
    assert classify_wind(from_sea, orientation)[0] == WindRelation.ONSHORE
    assert classify_wind(from_land, orientation)[0] == WindRelation.OFFSHORE
    assert classify_wave(from_sea, orientation)[0] == WaveIncidence.DIRECT
    assert classify_wave(from_land, orientation)[0] == WaveIncidence.INCONSISTENT


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (0.0, WindRelation.ONSHORE),
        (30.0, WindRelation.ONSHORE),
        (30.001, WindRelation.CROSS_ONSHORE),
        (79.999, WindRelation.CROSS_ONSHORE),
        (80.0, WindRelation.ALONGSHORE),
        (90.0, WindRelation.ALONGSHORE),
        (100.0, WindRelation.ALONGSHORE),
        (100.001, WindRelation.CROSS_OFFSHORE),
        (149.999, WindRelation.CROSS_OFFSHORE),
        (150.0, WindRelation.OFFSHORE),
        (180.0, WindRelation.OFFSHORE),
    ],
)
def test_wind_sector_boundaries(offset: float, expected: WindRelation) -> None:
    relation, _ = classify_wind((350.0 + offset) % 360.0, 350.0)
    assert relation == expected


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (0.0, WaveIncidence.DIRECT),
        (25.0, WaveIncidence.DIRECT),
        (25.001, WaveIncidence.OBLIQUE),
        (69.999, WaveIncidence.OBLIQUE),
        (70.0, WaveIncidence.OBLIQUE),
        (70.001, WaveIncidence.ALONGSHORE),
        (90.0, WaveIncidence.ALONGSHORE),
        (110.0, WaveIncidence.ALONGSHORE),
        (110.001, WaveIncidence.INCONSISTENT),
        (180.0, WaveIncidence.INCONSISTENT),
    ],
)
def test_wave_sector_boundaries(offset: float, expected: WaveIncidence) -> None:
    incidence, _ = classify_wave((350.0 + offset) % 360.0, 350.0)
    assert incidence == expected


def test_incoming_components_preserve_physical_sign_and_magnitude() -> None:
    shoreward, alongshore = incoming_direction_components(10.0, 90.0, 90.0)
    assert shoreward == pytest.approx(10.0)
    assert alongshore == pytest.approx(0.0)

    shoreward, alongshore = incoming_direction_components(10.0, 270.0, 90.0)
    assert shoreward == pytest.approx(-10.0)
    assert alongshore == pytest.approx(0.0, abs=1e-9)

    shoreward, alongshore = incoming_direction_components(10.0, 0.0, 90.0)
    assert shoreward == pytest.approx(0.0, abs=1e-9)
    assert alongshore == pytest.approx(10.0)

    shoreward, alongshore = incoming_direction_components(10.0, 135.0, 90.0)
    assert shoreward == pytest.approx(10.0 / 2**0.5)
    assert alongshore == pytest.approx(10.0 / 2**0.5)
    assert incoming_direction_components(None, 90.0, 90.0) == (None, None)
    assert incoming_direction_components(10.0, None, 90.0) == (None, None)


def test_signed_incoming_component_uses_declared_positive_tangent() -> None:
    # S=90° makes the positive alongshore axis 180° (south). A source at 93°
    # travels slightly north of west and therefore has a negative tangent component.
    shoreward, alongshore = incoming_direction_signed_components(16.0, 93.0, 90.0)
    assert shoreward == pytest.approx(15.978, abs=0.001)
    assert alongshore == pytest.approx(-0.837, abs=0.001)
    assert incoming_direction_signed_components(None, 93.0, 90.0) == (None, None)


def test_wave_metrics_use_exact_deep_water_relation_and_energy_flux_proxy() -> None:
    assert wave_energy_proxy(1.0, 8.0) == 8.0
    assert wave_energy_proxy(1.0, 4.0) == 4.0
    wavelength = 9.80665 * 4.0**2 / (2.0 * 3.141592653589793)
    assert deep_water_wavelength_m(4.0) == pytest.approx(wavelength)
    assert deep_water_wave_steepness(1.0, 4.0) == pytest.approx(1 / wavelength)
    assert deep_water_wave_steepness(1.0, 0.0) is None
    assert deep_water_wavelength_m(None) is None


def test_gust_factor_is_guarded_near_calm_conditions() -> None:
    assert gust_factor(10.0, 18.0) == pytest.approx(1.8)
    assert gust_factor(4.99, 20.0) is None
    assert gust_factor(0.0, 0.0) is None
    assert gust_factor(None, 20.0) is None


def test_wind_unit_conversions_are_reversible() -> None:
    assert knots_to_kmh(25.0) == pytest.approx(46.3)
    assert kmh_to_knots(46.3) == pytest.approx(25.0)
    assert kmh_to_mps(36.0) == pytest.approx(10.0)


def test_wind_stress_uses_documented_drag_relation_and_signed_projection() -> None:
    assert neutral_wind_drag_coefficient(0.0) == pytest.approx(1.2e-3)
    assert neutral_wind_drag_coefficient(10.0) == pytest.approx(1.2e-3)
    assert neutral_wind_drag_coefficient(20.0) == pytest.approx(1.79e-3)
    assert neutral_wind_drag_coefficient(30.0) == pytest.approx(2.115e-3)
    assert wind_stress_pa(36.0) == pytest.approx(1.225 * 1.2e-3 * 10.0**2)
    stress, shoreward, alongshore = wind_stress_signed_components(36.0, 135.0, 90.0)
    assert stress == pytest.approx(0.147)
    assert shoreward == pytest.approx(stress / 2**0.5)
    assert alongshore == pytest.approx(-stress / 2**0.5)
    assert wind_stress_signed_components(None, 90.0, 90.0) == (None, None, None)


def test_weighted_directional_coherence_is_circular_and_excludes_calm() -> None:
    aligned, count = weighted_directional_coherence(
        [(10.0, 359.0), (10.0, 0.0), (10.0, 1.0), (2.0, 180.0)]
    )
    assert count == 3
    assert aligned == pytest.approx(0.9999, abs=0.0001)
    cancelled, count = weighted_directional_coherence([(10.0, 0.0), (10.0, 120.0), (10.0, 240.0)])
    assert count == 3
    assert cancelled == pytest.approx(0.0, abs=1e-12)
    insufficient, count = weighted_directional_coherence([(10.0, 0.0), (4.9, 30.0)])
    assert insufficient is None
    assert count == 1


def test_alongshore_proxy_is_zero_for_direct_waves() -> None:
    assert alongshore_wave_proxy(1.0, 6.0, 90.0, 90.0) == pytest.approx(0)
    assert alongshore_wave_proxy(1.0, 6.0, 135.0, 90.0) == pytest.approx(6.0)
    assert alongshore_wave_signed_proxy(1.0, 6.0, 135.0, 90.0) == pytest.approx(-6.0)
    assert alongshore_wave_signed_proxy(1.0, 6.0, 45.0, 90.0) == pytest.approx(6.0)
    assert alongshore_wave_proxy(1.0, 6.0, 270.0, 90.0) is None


def test_secondary_wave_energy_share_is_separate_and_bounded() -> None:
    assert secondary_wave_energy_share(1.0, 2.0) == pytest.approx(0.2)
    assert secondary_wave_energy_share(1.0, 1.0) == pytest.approx(0.5)
    assert secondary_wave_energy_share(0.0, 0.0) is None
    assert secondary_wave_energy_share(None, 1.0) is None


def test_current_projection_uses_towards_convention() -> None:
    along, cross = project_current(1.0, 90.0, 90.0)
    assert along == pytest.approx(0)
    assert cross == pytest.approx(1)
    along, cross = project_current(1.0, 0.0, 90.0)
    assert along == pytest.approx(-1.0)
    assert cross == pytest.approx(0, abs=1e-9)
    along, cross = project_current(1.0, 180.0, 90.0)
    assert along == pytest.approx(1.0)
    assert cross == pytest.approx(0, abs=1e-9)


def test_sea_level_rate_and_state_come_from_values() -> None:
    levels = [0.0, 0.1, 0.2, 0.1, 0.0]
    hours = [
        ForecastHour(
            time=datetime(2026, 9, 7, index, tzinfo=TZ),
            sea_level_height_msl_m=level,
        )
        for index, level in enumerate(levels)
    ]
    rates = sea_level_rates(hours)
    assert rates[1] == pytest.approx(0.1)
    assert rates[3] == pytest.approx(-0.1)
    states = tide_states(hours, hours[0].time.date())
    assert states[1][0] == TideState.RISING
    assert states[3][0] == TideState.FALLING
    assert states[2][0] == TideState.SLACK


def test_dispersion_wavenumber_solves_for_known_orders() -> None:
    # The solver must satisfy omega^2 = g k tanh(k h) to high precision across
    # deep, intermediate and shallow water rather than matching limit formulas.
    import math as _math

    g = 9.80665
    for period, depth in ((8.0, 200.0), (8.0, 5.0), (8.0, 0.5), (12.0, 1.5)):
        omega = 2.0 * _math.pi / period
        k = dispersion_wavenumber(omega, depth)
        assert k is not None and k > 0
        residual = g * k * _math.tanh(k * depth) - omega**2
        assert abs(residual) < 1e-9 * omega**2


def test_dispersion_wavenumber_rejects_invalid_inputs() -> None:
    assert dispersion_wavenumber(None, 5.0) is None
    assert dispersion_wavenumber(0.5, None) is None
    assert dispersion_wavenumber(0.0, 5.0) is None
    assert dispersion_wavenumber(0.5, 0.0) is None
    assert dispersion_wavenumber(-1.0, 5.0) is None


def test_near_bottom_orbital_velocity_grows_towards_shallow_water() -> None:
    shallow = near_bottom_orbital_velocity_ms(1.0, 8.0, 1.5)
    deep = near_bottom_orbital_velocity_ms(1.0, 8.0, 5.0)
    assert shallow is not None and deep is not None
    assert shallow > deep
    # Sanity: a 1 m / 8 s wave must not produce absurd near-bed speeds at 5 m depth.
    assert deep < 1.0


def test_near_bottom_orbital_velocity_rejects_invalid_inputs() -> None:
    assert near_bottom_orbital_velocity_ms(None, 8.0, 5.0) is None
    assert near_bottom_orbital_velocity_ms(1.0, 0.0, 5.0) is None
    assert near_bottom_orbital_velocity_ms(1.0, 8.0, -1.0) is None


def test_spring_neap_classification_from_actual_range() -> None:
    from spotdata.domain.math import classify_spring_neap, in_gabes_zone

    assert classify_spring_neap(1.0, [0.5, 0.6, 0.55]) == ("spring", 1.82, 0.55)
    assert classify_spring_neap(0.3, [0.5, 0.6, 0.55]) == ("neap", 0.55, 0.55)
    assert classify_spring_neap(0.55, [0.5, 0.6, 0.55])[0] == "intermediate"
    assert classify_spring_neap(None, []) == ("unknown", None, None)
    assert in_gabes_zone(33.9, 10.5) is True
    assert in_gabes_zone(36.8, 11.1) is False
