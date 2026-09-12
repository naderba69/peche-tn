"""Regression tests for the reporting-only daily species-activity indicator (v1.9.9).

Policy: a relative 0-100 indicator built from documented low-weight priors
(feeding window, water temperature, seasonal availability from published
studies, shore match, sea-state fit). It is never a catch probability and never
feeds the binary go/no_go decision (D10/D11).
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionLevel, DecisionReasonCode
from spotdata.domain.models import ForecastDataset

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")

PERIOD_KEYS = ["dawn", "morning", "midday", "afternoon", "dusk", "night"]
SPECIES_LABELS = ["القاروص", "الوراطة", "السار", "المرمار", "صيد عام"]


def _default(dataset_factory: Callable[..., ForecastDataset]) -> ForecastDataset:
    return dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))


def _species(result, label: str):
    return next(sp for sp in result.species_activity if sp.label_ar == label)


def _score_at(result, label: str, hour_of_day: int) -> int:
    sp = _species(result, label)
    hour = next(item for item in sp.hourly if item.time.hour == hour_of_day)
    return hour.score


def test_activity_block_has_five_species_with_flags(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    assert [sp.label_ar for sp in result.species_activity] == SPECIES_LABELS
    assert all(sp.is_probability is False for sp in result.species_activity)
    assert {sp.species for sp in result.species_activity} == {
        "european_seabass",
        "gilthead_seabream",
        "white_seabream",
        "striped_seabream",
        "general",
    }


def test_each_species_has_six_periods_and_matching_hourly(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    for sp in result.species_activity:
        assert [period.key for period in sp.periods] == PERIOD_KEYS
        assert len(sp.hourly) == len(result.hourly)
        assert all(0 <= item.score <= 100 for item in sp.hourly)
        assert all(period.score is None or 0 <= period.score <= 100 for period in sp.periods)


def test_general_species_uses_feeding_window_only(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    # General has no thermal/seasonal/shore profile: midday is exactly the base.
    assert _score_at(result, "صيد عام", 12) == 50
    # Twilight bonus 9 (sunrise 06:00 within ±90 min).
    assert _score_at(result, "صيد عام", 6) == 59
    # Night bonus 1 (after sunset 18:30).
    assert _score_at(result, "صيد عام", 21) == 51


def test_twilight_beats_daylight_for_same_species(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    midday = _score_at(result, "القاروص", 12)
    twilight = _score_at(result, "القاروص", 18)
    # 18:00 is within ±90 min of sunset (18:30); the only difference is the
    # seabass twilight bonus of 11.
    assert twilight == midday + 11
    assert twilight > midday


def test_midday_scores_lock_the_documented_priors(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    # Default dataset: sandy shore, 22°C water, wave 0.6 m (moderate sea state),
    # September in the Tunis zone. Midday has no twilight/night bonus, so the
    # score isolates the documented priors (base 50 + shore + SST + seasonal +
    # sea state) and locks the formula:
    #   القاروص: 50 +3 رمل -0 حرارة (22° خارج المفضل 13-21 وضمن التحمل) +6 موسمي = 59
    #   الوراطة: 50 +3 +6 (مفضلة 17-26) +6 +5 (كسرة معتدلة مناسبة) = 70
    #   السار:   50 -3 (رمل خارج صخر/رصيف) +6 (مفضلة 15-24) -6 (موسمي 1) +5 = 52
    #   المرمار: 50 +3 +6 (مفضلة 16-26) +6 (حالة البحر معتدلة خارج الهدوء) = 65
    assert _score_at(result, "القاروص", 12) == 59
    assert _score_at(result, "الوراطة", 12) == 70
    assert _score_at(result, "السار", 12) == 52
    assert _score_at(result, "المرمار", 12) == 65


def test_thermal_preference_orders_species_at_midday(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    # Same zone/month/sea-state: mormyrus (22°C inside its preferred 16-26°C)
    # scores above seabass (22°C only tolerated; preferred 13-21°C) at midday.
    assert _score_at(result, "المرمار", 12) > _score_at(result, "القاروص", 12)


def test_indicator_never_changes_the_binary_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert result.score_is_success_probability is False
    assert result.species_activity


def test_every_species_discloses_it_is_not_a_probability(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    for sp in result.species_activity:
        assert sp.basis_ar
        assert any("ليس احتمالاً" in line for line in sp.basis_ar)
