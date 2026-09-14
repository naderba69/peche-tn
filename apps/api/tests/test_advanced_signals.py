from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionLevel, DecisionReasonCode
from spotdata.domain.math import solar_elevation_deg, solar_twilight_times
from spotdata.domain.models import ForecastDataset

TZ = ZoneInfo("Africa/Tunis")
engine = DecisionEngine()


def test_advanced_signals_present_and_never_change_the_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
    )
    result = engine.evaluate(dataset)
    signals = result.advanced_signals_ar
    assert signals, "advanced signals must not be empty"
    # Honesty header is always first.
    assert signals[0].startswith("كل ما يلي")
    assert any("القمر" in line for line in signals)
    assert any("الشفق الحقيقي" in line for line in signals)
    assert any("نماذج الأرصاد" in line for line in signals)
    assert any("راحة الصياد" in line for line in signals)
    # The signals are reporting-only: the binary decision stays a normal GO day.
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW


def test_advanced_signals_report_upstream_moon_times(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
    )
    dataset.moonrise = datetime(2026, 9, 7, 3, 20, tzinfo=TZ)
    dataset.moonset = datetime(2026, 9, 7, 15, 45, tzinfo=TZ)
    result = engine.evaluate(dataset)
    moon_lines = [line for line in result.advanced_signals_ar if "القمر اليوم" in line]
    assert len(moon_lines) == 1
    assert "03:20" in moon_lines[0]
    assert "15:45" in moon_lines[0]
    assert "%" in moon_lines[0]


def test_advanced_signals_degrade_to_illumination_only_without_upstream_moon(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    dataset.moonrise = None
    dataset.moonset = None
    result = engine.evaluate(dataset)
    moon_lines = [line for line in result.advanced_signals_ar if "إضاءة القمر" in line]
    assert len(moon_lines) == 1
    assert "غير متوفرة" in moon_lines[0]


def test_solar_elevation_noon_positive_midnight_negative() -> None:
    noon = datetime(2026, 9, 7, 12, 0, tzinfo=TZ)
    midnight = datetime(2026, 9, 7, 0, 0, tzinfo=TZ)
    assert solar_elevation_deg(noon, 36.8, 10.3) > 30.0
    assert solar_elevation_deg(midnight, 36.8, 10.3) < 0.0


def test_true_twilight_times_are_ordered_and_fall_on_the_day() -> None:
    day = date(2026, 9, 7)
    nautical_start, nautical_end = solar_twilight_times(day, 36.8, 10.3, TZ, -12.0)
    civil_start, civil_end = solar_twilight_times(day, 36.8, 10.3, TZ, -6.0)
    assert nautical_start is not None and nautical_end is not None
    assert civil_start is not None and civil_end is not None
    assert nautical_start < civil_start < civil_end < nautical_end
    assert all(t.date() == day for t in (nautical_start, civil_start, civil_end, nautical_end))


def test_pressure_6h_and_12h_trends_are_computed(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    result = engine.evaluate(dataset)
    target_hours = [h for h in result.hourly if h.time.date() == date(2026, 9, 7)]
    later = [h for h in target_hours if h.time.hour >= 12]
    assert all(h.derived.pressure_change_6h_hpa is not None for h in later)
    assert all(h.derived.pressure_change_12h_hpa is not None for h in later)
    # The synthetic series falls 0.1 hPa/h, so 6h and 12h changes are negative.
    assert all(h.derived.pressure_change_6h_hpa < 0.0 for h in later)
    assert all(h.derived.pressure_change_12h_hpa < 0.0 for h in later)
