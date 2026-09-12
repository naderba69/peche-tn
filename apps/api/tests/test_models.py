from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from spotdata.domain.models import (
    CoastalWaterContext,
    Coordinates,
    Factor,
    FieldFeasibilityResult,
    ForecastHour,
    SpotProfile,
)


def test_tunisia_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        Coordinates(latitude=48.8, longitude=2.3)


def test_360_orientation_normalizes_to_north() -> None:
    assert SpotProfile(seaward_orientation_deg=360).seaward_orientation_deg == 0


def test_naive_forecast_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ForecastHour(time=datetime(2026, 9, 7, 10))


def test_field_proxy_cannot_be_serialized_as_direct_observation() -> None:
    with pytest.raises(ValidationError):
        FieldFeasibilityResult(
            status="favorable",
            score=90,
            confidence=50,
            holding_difficulty="low",
            fouling_transport_potential="low",
            rip_current_potential="low",
            reasons_ar=[],
            limitations_ar=[],
            is_direct_observation=True,
        )


def test_field_proxy_confidence_is_contractually_capped() -> None:
    with pytest.raises(ValidationError):
        FieldFeasibilityResult(
            status="favorable",
            score=90,
            confidence=51,
            holding_difficulty="low",
            fouling_transport_potential="low",
            rip_current_potential="low",
            reasons_ar=[],
            limitations_ar=[],
        )


def test_factor_cannot_claim_model_rule_is_a_direct_observation() -> None:
    with pytest.raises(ValidationError):
        Factor(
            code="test",
            label_ar="اختبار",
            impact="neutral",
            basis="model_forecast",
            rule_nature="data_quality",
            explanation_ar="اختبار عقد المصدر.",
            is_direct_observation=True,
        )


def test_new_weather_fields_keep_physical_bounds() -> None:
    aware = datetime.fromisoformat("2026-09-07T10:00:00+01:00")
    with pytest.raises(ValidationError):
        ForecastHour(time=aware, relative_humidity_pct=101)
    with pytest.raises(ValidationError):
        ForecastHour(time=aware, uv_index=-0.1)
    with pytest.raises(ValidationError):
        ForecastHour(time=aware, shortwave_radiation_wm2=-1)


def test_satellite_context_enforces_availability_age_and_unit_contract() -> None:
    valid_time = datetime(2026, 9, 6, tzinfo=UTC)
    retrieved_at = datetime(2026, 9, 9, tzinfo=UTC)
    available = {
        "availability": "available",
        "sample_latitude": 36.81,
        "sample_longitude": 10.31,
        "sample_distance_from_spot_m": 1_000,
        "pixel_latitude": 36.8102,
        "pixel_longitude": 10.3104,
        "pixel_distance_from_spot_m": 1_015,
        "pixel_distance_from_sample_m": 41,
        "valid_time": valid_time,
        "retrieved_at": retrieved_at,
        "age_hours": 72,
        "turbidity_fnu": 0.32,
        "reason_ar": "اختبار.",
    }
    context = CoastalWaterContext(**available)
    assert context.turbidity_unit == "FNU"
    assert context.suspended_particulate_matter_unit == "g/m³"
    assert context.chlorophyll_a_unit == "mg/m³"

    with pytest.raises(ValidationError, match="age must match"):
        CoastalWaterContext(**{**available, "age_hours": 12})
    with pytest.raises(ValidationError, match="cannot expose retrieval values"):
        CoastalWaterContext(
            availability="unavailable",
            sample_latitude=36.81,
            sample_longitude=10.31,
            sample_distance_from_spot_m=1_000,
            retrieved_at=retrieved_at,
            turbidity_fnu=0.32,
            reason_ar="اختبار.",
        )
