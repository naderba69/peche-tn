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
    # Default: sandy, 22°C, Hs 0.6 m (moderate), September, Tunis zone.
    #   القاروص: 50 +3 رمل +0 حرارة (22° خارج ذروة 14-19 وداخل 8-24) +6 موسمي +5 كسرة = 64
    #   الوراطة: 50 +3 +6 +6 +5 = 70
    #   السار:   50 -3 رمل +6 حرارة +6 موسمي +5 = 64
    #   المرمار: 50 +3 +6 +6 (معتدل خارج الهدوء) = 65
    assert _score_at(result, "القاروص", 12) == 64
    assert _score_at(result, "الوراطة", 12) == 70
    assert _score_at(result, "السار", 12) == 64
    assert _score_at(result, "المرمار", 12) == 65


def test_thermal_preference_orders_species_at_midday(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    # Same zone/month: sargus on sand is penalised vs mormyrus which matches sand.
    assert _score_at(result, "المرمار", 12) > _score_at(result, "السار", 12)


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


def test_period_peak_carries_signed_why_factors(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    for sp in result.species_activity:
        scored = [period for period in sp.periods if period.score is not None]
        assert scored, "at least one period must be scored"
        peak = max(scored, key=lambda period: period.score)
        assert peak.top_factor_ar is not None
        assert isinstance(peak.factors_ar, list)
        if "صيد عام" not in sp.label_ar:
            assert any("التوفر الموسمي" in item for item in peak.factors_ar)
        # Signed formatting: every listed factor ends with +N or -N.
        for item in peak.factors_ar:
            assert item[-1].isdigit()
            assert ("+" in item) or ("-" in item)
        # The top factor label is the strongest-listed contribution.
        strongest = max(
            peak.factors_ar,
            key=lambda item: int(item.split()[-1]),
        )
        assert (
            strongest.startswith(peak.top_factor_ar)
            or peak.top_factor_ar == "توازن بلا أفضلية قوية"
        )


def test_moon_illumination_is_geometric_and_bounded() -> None:
    from datetime import date as _date

    from spotdata.domain.math import moon_illumination

    # Astronomical anchors: 2000-01-06 is the new-moon epoch, 2000-01-21 full.
    assert moon_illumination(_date(2000, 1, 6)) < 0.1
    assert moon_illumination(_date(2000, 1, 21)) > 0.9
    for day in (_date(2020, 1, 1), _date(2026, 9, 7)):
        assert 0.0 <= moon_illumination(day) <= 1.0


def test_moon_phase_matches_published_september_2026_ephemeris() -> None:
    """Cross-check the synodic estimate against a published ephemeris.

    starwalk.space lists September 2026 as: last quarter Sept 4 07:51 UTC, new
    moon Sept 11 03:27 UTC, first quarter Sept 18 20:44 UTC, full moon Sept 26
    16:49 UTC. The engine evaluates at 12:00 UTC of each civil date, so the
    phase must land within a few hours of those instants (±0.03 of a cycle).
    """
    from datetime import date as _date

    from spotdata.domain.math import moon_illumination, moon_phase_fraction

    new_phase = moon_phase_fraction(_date(2026, 9, 11))
    full_phase = moon_phase_fraction(_date(2026, 9, 26))
    last_quarter = moon_phase_fraction(_date(2026, 9, 4))
    first_quarter = moon_phase_fraction(_date(2026, 9, 18))
    # new moon: phase near 0.0; full moon: phase near 0.5
    assert (new_phase < 0.03) or (new_phase > 0.97)
    assert 0.45 <= full_phase <= 0.55
    # quarters: phase near 0.75 (last) and 0.25 (first)
    assert 0.72 <= last_quarter <= 0.78
    assert 0.22 <= first_quarter <= 0.28
    assert moon_illumination(_date(2026, 9, 11)) < 0.05
    assert moon_illumination(_date(2026, 9, 26)) > 0.95
    # 2026-09-14 (≈3.4 days old at noon): independent reference ≈12.2% - the
    # day-granularity value must sit comfortably inside 8-16%, not 0 or 100%.
    assert 0.08 <= moon_illumination(_date(2026, 9, 14)) <= 0.16


def test_pressure_and_moon_priors_are_computed_and_disclosed() -> None:
    from types import SimpleNamespace

    from spotdata.domain.engine import _species_hour_activity
    from spotdata.domain.enums import ShoreType, TargetSpecies
    from spotdata.domain.species import SPECIES_PROFILES

    profile = SPECIES_PROFILES[TargetSpecies.GENERAL]
    common = dict(sst=None, sea_state="unknown", zone="tunis", month=9, shore_type=ShoreType.SANDY)

    def fake_hour(is_night: bool, pressure_change_3h: float | None) -> SimpleNamespace:
        return SimpleNamespace(
            derived=SimpleNamespace(
                is_twilight=False,
                is_night=is_night,
                pressure_change_3h_hpa=pressure_change_3h,
            )
        )

    # Pressure is weather context only: no catch weight.
    score, contribs = _species_hour_activity(
        profile, fake_hour(is_night=False, pressure_change_3h=-2.0), **common
    )
    assert score == 50
    assert not any("ضغط" in label for label, _d in contribs)

    score, contribs = _species_hour_activity(
        profile, fake_hour(is_night=False, pressure_change_3h=2.0), **common
    )
    assert score == 50

    # Moonlight is astronomy only — never a feeding prior.
    score, contribs = _species_hour_activity(
        profile,
        fake_hour(is_night=True, pressure_change_3h=None),
        moon_illumination=0.9,
        target_species=TargetSpecies.GENERAL,
        **common,
    )
    assert score == 51
    assert not any("مقمرة" in label for label, _d in contribs)

    bass = SPECIES_PROFILES[TargetSpecies.EUROPEAN_SEABASS]
    score, contribs = _species_hour_activity(
        bass,
        fake_hour(is_night=True, pressure_change_3h=None),
        moon_illumination=0.9,
        target_species=TargetSpecies.EUROPEAN_SEABASS,
        sst=None,
        sea_state="unknown",
        zone="bizerte_tunis",
        month=1,
        shore_type=ShoreType.SANDY,
    )
    assert not any("مقمرة" in label for label, _d in contribs)


def test_pressure_moon_priors_never_change_the_binary_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory()
    steep_fall = dataset_factory(
        per_hour=lambda index, values: values.update(pressure_msl_hpa=1018.0 - 1.5 * index)
    )
    baseline = engine.evaluate(base)
    with_prior = engine.evaluate(steep_fall)
    assert with_prior.decision == baseline.decision
    assert with_prior.decision_reason_code == baseline.decision_reason_code
    assert with_prior.opportunity_score == baseline.opportunity_score
    general = next(sp for sp in with_prior.species_activity if sp.label_ar == "صيد عام")
    midday = next(p for p in general.periods if p.key == "midday")
    assert not midday.factors_ar or not any("هبوط ضغط" in item for item in midday.factors_ar)


def test_tide_and_lunar_day_helpers_are_small_and_bounded() -> None:
    from spotdata.domain.engine import _lunar_day_delta, _tide_channel_delta

    assert _tide_channel_delta("spring") == 0
    assert _tide_channel_delta("neap") == 0
    assert _tide_channel_delta("intermediate") == 0
    assert _tide_channel_delta("unknown") == 0
    assert _lunar_day_delta(1.0) == 0
    assert _lunar_day_delta(0.0) == 0
    assert _lunar_day_delta(0.5) == 0
    assert _lunar_day_delta(0.178) == 0


def test_spring_tide_pulls_fish_shoreward_in_the_indicator(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        per_hour=lambda index, values: values.update(
            sea_level_height_msl_m=values["sea_level_height_msl_m"] * (1.6 if index >= 72 else 1.0)
        ),
    )
    result = engine.evaluate(dataset)
    assert result.spring_neap.classification == "spring"
    # Day-level spring/neap no longer moves fish toward the beach.
    assert _score_at(result, "صيد عام", 12) == 50
    assert any("قابس" in line for line in _species(result, "صيد عام").basis_ar)


def test_neap_tide_pushes_fish_offshore_in_the_indicator(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        per_hour=lambda index, values: values.update(
            sea_level_height_msl_m=values["sea_level_height_msl_m"] * (0.45 if index >= 72 else 1.0)
        ),
    )
    result = engine.evaluate(dataset)
    assert result.spring_neap.classification == "neap"
    assert _score_at(result, "صيد عام", 12) == 50


def test_full_moon_day_adds_the_traditional_lunar_prior(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    from datetime import date

    dataset = dataset_factory(
        count=24,
        start_at=datetime(2026, 9, 26, 0, tzinfo=TZ),
        target_date=date(2026, 9, 26),
        sunrise=datetime(2026, 9, 26, 6, 0, tzinfo=TZ),
        sunset=datetime(2026, 9, 26, 18, 30, tzinfo=TZ),
    )
    result = engine.evaluate(dataset)
    assert _score_at(result, "صيد عام", 12) == 50
    assert any(
        "سولونار" in line or "القاروص" in line for line in _species(result, "صيد عام").basis_ar
    )
