"""Deterministic field report (التقرير الميداني) tests."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.math import moon_transit_times

TZ = ZoneInfo("Africa/Tunis")


def test_moon_transit_matches_independent_ephemeris() -> None:
    """Upper transit for Tunis on 2026-09-14 must match timeanddate.com (14:44)."""
    upper, lower = moon_transit_times(date(2026, 9, 14), 10.16579, TZ)
    assert upper.strftime("%H:%M") == "14:44"
    # Lower transit is ~12h24m after upper for a slow-declination day.
    lower_minutes = lower.hour * 60 + lower.minute
    upper_minutes = upper.hour * 60 + upper.minute
    delta = (lower_minutes - upper_minutes) % (24 * 60)
    assert 735 <= delta <= 760  # 12h15m..12h40m


def test_report_is_populated_and_does_not_touch_decision(dataset_factory) -> None:
    engine = DecisionEngine()
    dataset = dataset_factory()
    response = engine.evaluate(dataset)
    report = response.fisherman_report
    assert report is not None
    # The report echoes the engine's numbers, never replaces them.
    assert report.opportunity_score == response.opportunity_score
    assert report.decision_label_ar == response.decision_label_ar
    # Honest label, never a success probability.
    assert "ليس نسبة نجاح" in report.opportunity_note_ar
    assert response.score_is_success_probability is False


def test_report_periods_cover_four_blocks(dataset_factory) -> None:
    engine = DecisionEngine()
    dataset = dataset_factory()
    response = engine.evaluate(dataset)
    assert response.fisherman_report is not None
    keys = [period.key for period in response.fisherman_report.periods]
    assert keys == ["dawn", "morning", "midday", "dusk"]
    for period in response.fisherman_report.periods:
        assert 0 <= period.comfort_index <= 100
        assert period.wind_cast_effect_m >= 0


def test_cast_distance_and_wind_effect_are_documented_estimates(dataset_factory) -> None:
    engine = DecisionEngine()
    dataset = dataset_factory()  # wind 12 km/h onshore -> shoreward component > 0
    response = engine.evaluate(dataset)
    assert response.fisherman_report is not None
    report = response.fisherman_report
    # Wind penalty is ~0.15 m per km/h of opposing wind; 12 km/h -> ~2 m.
    sample = next(p for p in report.periods if p.cast_distance_m is not None)
    assert 0 < sample.cast_distance_m < 120
    assert sample.wind_cast_effect_m >= 1  # onshore wind must cost range


def test_report_bait_is_catalogued_and_disclosed(dataset_factory) -> None:
    engine = DecisionEngine()
    dataset = dataset_factory()
    response = engine.evaluate(dataset)
    assert response.fisherman_report is not None
    assert response.fisherman_report.target_bait_ar
    assert "ضمان مصيد" in response.fisherman_report.bait_note_ar


def test_astronomical_times_are_reference_only(dataset_factory) -> None:
    engine = DecisionEngine()
    dataset = dataset_factory()
    response = engine.evaluate(dataset)
    assert response.fisherman_report is not None
    report = response.fisherman_report
    kinds = {item.kind for item in report.astronomical_times}
    assert kinds  # upper/lower transit + tide events present
    assert "مرجعي" in report.astronomy_note_ar or "مرجعية" in report.astronomy_note_ar
