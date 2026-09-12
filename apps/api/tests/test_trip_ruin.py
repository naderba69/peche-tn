"""Regression tests for the evidence-gated trip-ruining factors (v1.9.8).

Policy: confirmed evidence may force majeure; forecast/proxy stays a caution;
unsupported stays Unknown (D11). Dense fouling blocks via FOULING_CONFIRMED,
jellyfish/debris/turbidity(dense field report) via TRIP_RUIN_CONFIRMED.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionLevel, DecisionReasonCode, ForceMajeureKind
from spotdata.domain.models import CoastalWaterContext, FieldReport, ForecastDataset

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")


def _context(
    fetched_at: datetime,
    *,
    chl: float | None = None,
    tur: float = 0.5,
    sst: float | None = None,
) -> CoastalWaterContext:
    return CoastalWaterContext(
        availability="available",
        sample_latitude=36.79,
        sample_longitude=10.32,
        sample_distance_from_spot_m=1000.0,
        pixel_latitude=36.79,
        pixel_longitude=10.32,
        pixel_distance_from_spot_m=1000.0,
        pixel_distance_from_sample_m=0.0,
        valid_time=fetched_at - timedelta(hours=20),
        retrieved_at=fetched_at,
        age_hours=20.0,
        turbidity_fnu=tur,
        chlorophyll_a_mg_m3=chl,
        sea_surface_temperature_c=sst,
        reason_ar="اختبار",
    )


def _report(
    fetched_at: datetime, *, kind: str, severity: str = "dense", hours_ago: float = 2
) -> FieldReport:
    return FieldReport(
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        source="user",
        reported_at=fetched_at - timedelta(hours=hours_ago),
    )


def _onshore_transport_dataset(dataset_factory: Callable[..., ForecastDataset]) -> ForecastDataset:
    """Wave/wind/current forcing that raises the fouling transport proxy to HIGH
    while staying inside the safety gates (so the day decision stays GO)."""
    return dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={
            "wave_height_m": 1.4,
            "wave_period_s": 7.0,
            "wave_direction_deg": 90.0,
            "wind_speed_kmh": 30.0,
            "wind_gust_kmh": 38.0,
            "wind_direction_deg": 90.0,
            "ocean_current_velocity_kmh": 0.6,
            "ocean_current_direction_deg": 270.0,
        },
    )


def test_satellite_dense_bloom_with_onshore_transport_is_force_majeure(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = _onshore_transport_dataset(dataset_factory)
    dataset = base.model_copy(update={"coastal_water_context": _context(base.fetched_at, chl=12.0)})
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.FOULING_CONFIRMED
    assert result.force_majeure_kind == ForceMajeureKind.FOULING
    fouling = next(f for f in result.trip_ruin_factors if f.factor == "dense_fouling")
    assert fouling.level == "high"
    assert fouling.basis == "satellite"
    assert fouling.is_force_majeure is True
    assert fouling.age_ar and "صورة ساتلية" in fouling.age_ar


def test_satellite_moderate_bloom_is_caution_only(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(update={"coastal_water_context": _context(base.fetched_at, chl=7.0)})
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    fouling = next(f for f in result.trip_ruin_factors if f.factor == "dense_fouling")
    assert fouling.level == "moderate"
    assert fouling.is_force_majeure is False


def test_jellyfish_dense_report_blocks(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(
        update={"field_reports": [_report(base.fetched_at, kind="jellyfish")]}
    )
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.TRIP_RUIN_CONFIRMED
    assert result.force_majeure_kind == ForceMajeureKind.TRIP_RUIN
    jelly = next(f for f in result.trip_ruin_factors if f.factor == "jellyfish")
    assert jelly.level == "high" and jelly.is_force_majeure is True


def test_storm_debris_dense_report_blocks(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(update={"field_reports": [_report(base.fetched_at, kind="debris")]})
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.TRIP_RUIN_CONFIRMED
    debris = next(f for f in result.trip_ruin_factors if f.factor == "storm_debris")
    assert debris.level == "high" and debris.is_force_majeure is True


def test_turbidity_satellite_is_caution_only(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(update={"coastal_water_context": _context(base.fetched_at, tur=6.0)})
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    tur = next(f for f in result.trip_ruin_factors if f.factor == "turbidity")
    assert tur.level == "high"
    assert tur.basis == "satellite"
    assert tur.is_force_majeure is False


def test_turbidity_dense_field_report_blocks(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(
        update={"field_reports": [_report(base.fetched_at, kind="turbidity")]}
    )
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.TRIP_RUIN_CONFIRMED


def test_marine_heatwave_is_informational(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset = base.model_copy(
        update={"coastal_water_context": _context(base.fetched_at, sst=28.0)}
    )
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    mhw = next(f for f in result.trip_ruin_factors if f.factor == "marine_heatwave")
    assert mhw.basis == "satellite"
    assert mhw.level in {"moderate", "high"}
    assert mhw.is_force_majeure is False


def test_trip_ruin_factors_always_present_and_disclosed(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    result = engine.evaluate(base)
    factors = {f.factor: f for f in result.trip_ruin_factors}
    assert set(factors) == {
        "dense_fouling",
        "turbidity",
        "jellyfish",
        "marine_heatwave",
        "storm_debris",
    }
    for factor in factors.values():
        assert factor.level in {"unknown", "low", "moderate", "high"}
        assert factor.basis in {"satellite", "forecast_proxy", "field_report", "unknown"}
        assert isinstance(factor.is_force_majeure, bool)
        assert factor.label_ar
    # Without satellite or reports: jellyfish/debris stay Unknown (never fabricated).
    assert factors["jellyfish"].level == "unknown"
    assert factors["storm_debris"].level == "unknown"
