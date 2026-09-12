from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from pydantic import ValidationError

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.models import Factor, ForecastDataset, WeatherStationObservation


def _with_observation(
    dataset: ForecastDataset,
    *,
    distance_km: float = 10.0,
    age_minutes: int = 30,
    wind_speed_kmh: float = 13.0,
    wind_gust_kmh: float = 18.0,
    wind_direction_deg: float = 90.0,
    air_temperature_c: float = 24.0,
    pressure_hpa: float = 1014.0,
    raw_report: str = "DTTA 062330Z 09007KT 9999 FEW020 24/17 Q1014",
) -> ForecastDataset:
    observation = WeatherStationObservation(
        provider="AviationWeather.gov METAR",
        station_id="DTTA",
        station_name="Tunis/Carthage Intl",
        station_latitude=36.851,
        station_longitude=10.227,
        station_elevation_m=7,
        observed_at=dataset.fetched_at - timedelta(minutes=age_minutes),
        retrieved_at=dataset.fetched_at,
        distance_to_spot_km=distance_km,
        wind_speed_kmh=wind_speed_kmh,
        wind_gust_kmh=wind_gust_kmh,
        wind_direction_deg=wind_direction_deg,
        air_temperature_c=air_temperature_c,
        dew_point_c=17,
        pressure_hpa=pressure_hpa,
        visibility_m=10_000,
        raw_report=raw_report,
        quality_control_flag=1,
    )
    return dataset.model_copy(update={"current_weather_observation": observation})


def test_nearby_consistent_station_observation_is_kept_separate(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = _with_observation(dataset_factory())

    result = DecisionEngine().evaluate(dataset)

    assert result.current_weather_observation is not None
    assert result.current_weather_observation.is_spot_observation is False
    assert result.observation_comparison.status.value == "consistent"
    assert result.observation_comparison.affects_confidence is False
    assert result.observation_comparison.wind_speed_difference_kmh == 1.0
    assert result.observation_comparison.compared_forecast_time == dataset.hours[0].time


def test_fresh_nearby_divergence_caps_confidence_and_marks_near_term_hours(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = _with_observation(
        dataset_factory(),
        wind_speed_kmh=50,
        wind_gust_kmh=65,
        wind_direction_deg=270,
        air_temperature_c=35,
        pressure_hpa=1000,
    )

    result = DecisionEngine().evaluate(dataset)

    assert result.observation_comparison.status.value == "divergent"
    assert result.observation_comparison.affects_confidence is True
    assert result.confidence.score <= 55
    direct_factors = [
        factor
        for hour in result.hourly[:3]
        for factor in hour.factors
        if factor.basis.value == "direct_observation"
    ]
    assert {factor.code for factor in direct_factors} >= {
        "station_model_divergence",
        "nearby_observed_wind_hazard",
    }
    assert all(factor.is_direct_observation for factor in direct_factors)
    assert any(hour.safety.value == "caution" for hour in result.hourly[:3])


def test_nearby_observed_thunderstorm_is_no_go_only_for_near_term(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = _with_observation(
        dataset_factory(),
        distance_km=15,
        raw_report="DTTA 062330Z 09007KT 5000 TSRA BKN018CB 24/17 Q1014",
    )

    result = DecisionEngine().evaluate(dataset)

    assert result.hourly[0].safety.value == "no_go"
    thunder = next(
        factor for factor in result.hourly[0].factors if factor.code == "nearby_metar_thunderstorm"
    )
    assert thunder.severity.value == "critical"
    assert thunder.is_direct_observation is True
    assert result.hourly[3].safety.value != "no_go"


def test_stale_or_distant_observation_never_changes_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    stale = _with_observation(
        dataset_factory(),
        age_minutes=180,
        wind_speed_kmh=80,
        wind_gust_kmh=100,
    )
    distant = _with_observation(
        dataset_factory(),
        distance_km=151,
        wind_speed_kmh=80,
        wind_gust_kmh=100,
    )

    stale_result = DecisionEngine().evaluate(stale)
    distant_result = DecisionEngine().evaluate(distant)

    assert stale_result.observation_comparison.status.value == "stale"
    assert distant_result.observation_comparison.status.value == "distant"
    assert all(
        factor.basis.value != "direct_observation"
        for result in (stale_result, distant_result)
        for hour in result.hourly
        for factor in hour.factors
    )


def test_future_dated_station_report_is_rejected_by_temporal_qc(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = _with_observation(dataset_factory(), age_minutes=-30)

    result = DecisionEngine().evaluate(dataset)

    assert result.observation_comparison.status.value == "not_applicable"
    assert "يتقدم وقت الجلب" in result.observation_comparison.reasons_ar[0]
    assert all(
        factor.basis.value != "direct_observation"
        for hour in result.hourly
        for factor in hour.factors
    )


def test_station_75_to_150_km_is_comparison_only(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = _with_observation(
        dataset_factory(),
        distance_km=100,
        wind_speed_kmh=80,
        wind_direction_deg=270,
    )

    result = DecisionEngine().evaluate(dataset)

    assert result.observation_comparison.status.value == "limited"
    assert result.observation_comparison.affects_confidence is False
    assert all(
        factor.basis.value != "direct_observation"
        for hour in result.hourly
        for factor in hour.factors
    )


def test_qnh_altimeter_pressure_is_not_compared_against_model_slp(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # A wild QNH offset must not masquerade as model/station pressure divergence:
    # altimeter setting is not physically comparable to model mean sea-level pressure.
    dataset = _with_observation(dataset_factory(), pressure_hpa=1030.0)
    observation = dataset.current_weather_observation
    assert observation is not None
    dataset = dataset.model_copy(
        update={
            "current_weather_observation": observation.model_copy(
                update={"pressure_kind": "altimeter_setting"}
            )
        }
    )

    result = DecisionEngine().evaluate(dataset)

    assert result.observation_comparison.pressure_difference_hpa is None
    assert result.observation_comparison.status.value == "consistent"
    assert any("حُجبت مقارنة الضغط" in reason for reason in result.observation_comparison.reasons_ar)


def test_factor_rejects_false_direct_observation_lineage() -> None:
    with pytest.raises(ValidationError, match="must match the factor basis"):
        Factor(
            code="bad-lineage",
            label_ar="اختبار",
            impact="neutral",
            basis="direct_observation",
            rule_nature="data_quality",
            explanation_ar="يجب ألا يمر هذا العامل.",
            is_direct_observation=False,
        )
