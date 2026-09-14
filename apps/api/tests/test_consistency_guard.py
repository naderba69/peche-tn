"""Self-check guard: a report must never contradict its own sub-indicators.

These invariants encode the lessons from the 2026-09-14 critical review and the
"meta-review". They run over the engine output for many generated datasets so a
contradiction between the headline number and its own breakdown (the original
"تنفيذ 100/100 مع جر جانبي متوسط" bug) can never return silently.

The guard checks *presentation-layer consistency*, not the underlying physics:
the physics is covered by the per-domain test files. Every violation returned
here is a real inconsistency a user could read in a generated report.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import (
    FieldFeasibilityLevel,
    PotentialLevel,
    WaveIncidence,
)
from spotdata.domain.models import (
    DecisionResponse,
    FieldFeasibilityResult,
    ForecastDataset,
    HoldingBreakdown,
)

engine = DecisionEngine()

_POTENTIAL_RANK = {
    PotentialLevel.UNKNOWN: 0,
    PotentialLevel.LOW: 1,
    PotentialLevel.MODERATE: 2,
    PotentialLevel.HIGH: 3,
}

_BASIS_RE = re.compile(
    r"الأساس (\d+)/100 قبل السقوف = اكتمال المتغيرات (\d+) نقطة .*?"
    r"أفق التوقع (\d+) .*?جودة المصادر (\d+) .*?اتجاه الشاطئ (\d+)"
)
_CAP_RE = re.compile(r"السقف الوحيد المطبَّق 85/100 = الأساس (\d+) ناقص (\d+) نقطة")
_SECTOR_RE = re.compile(
    r"^(?:الريح السائدة: .+ \(متوسط دائري \d+° من \d+ ساعة مقيمة\)"
    r"|رياح متقلبة بين .+ و.+ \(متوسط دائري \d+° من \d+ ساعة مقيمة\)"
    r"|اتجاه الريح .+)$"
)


def _potential_label(value: PotentialLevel) -> str:
    return {
        PotentialLevel.LOW: "منخفض في الفحص الآلي ولا ينفي الخطر",
        PotentialLevel.MODERATE: "متوسط ويحتاج تحققاً ميدانياً",
        PotentialLevel.HIGH: "مرتفع ويستوجب الحذر",
        PotentialLevel.UNKNOWN: "غير معروف لنقص البيانات",
    }[value]


def _dominant_level(breakdown: HoldingBreakdown) -> PotentialLevel | None:
    """The level of the breakdown's own dominant (most severe) mechanism."""
    mechanisms = {
        "longshore_current": breakdown.longshore_current,
        "orbital_motion": breakdown.orbital_motion,
        "return_flow": breakdown.return_flow,
        "tidal_current": breakdown.tidal_current,
    }
    if breakdown.dominant == "none":
        return None
    return mechanisms[breakdown.dominant]


def _expected_status(holding: PotentialLevel, score: int) -> FieldFeasibilityLevel:
    """The single status rule shared by the hour level and the aggregation."""
    if holding == PotentialLevel.HIGH:
        return FieldFeasibilityLevel.DIFFICULT
    if holding == PotentialLevel.MODERATE:
        return FieldFeasibilityLevel.WORKABLE
    if holding == PotentialLevel.UNKNOWN:
        return FieldFeasibilityLevel.UNKNOWN
    if score >= 75:
        return FieldFeasibilityLevel.FAVORABLE
    if score >= 50:
        return FieldFeasibilityLevel.WORKABLE
    return FieldFeasibilityLevel.DIFFICULT


def _check_feasibility(field: FieldFeasibilityResult, where: str) -> list[str]:
    """Invariants linking the headline difficulty/score/status to its causes.

    Applies to the hour-level result only (the aggregated window result uses a
    different reasons structure and is checked by `_check_breakdown_dominant`).
    """
    violations: list[str] = []
    holding = field.holding_difficulty
    breakdown = field.holding_breakdown

    # 1. The summary level can never sit below its own most severe displayed
    #    cause (the floor guarantees holding >= dominant mechanism level).
    if breakdown is not None:
        dominant_level = _dominant_level(breakdown)
        if (
            dominant_level is not None
            and _POTENTIAL_RANK[holding] < _POTENTIAL_RANK[dominant_level]
        ):
            violations.append(
                f"{where}: الخلاصة {holding.value} أدنى من سببه الغالب "
                f"{breakdown.dominant}={dominant_level.value} — تناقض رقم مع شرحه."
            )

    # 2. The verbal status follows the holding level (a "متوسط" never shows
    #    "مريحة ميدانياً").
    expected = _expected_status(holding, field.score)
    if field.status != expected:
        violations.append(
            f"{where}: صعوبة {holding.value} ونتيجة {field.score} مع حالة "
            f"{field.status.value} (المتوقع {expected.value})."
        )

    # 3. Score respects the existing deduction table bounds.
    if holding == PotentialLevel.MODERATE and field.score > 85:
        violations.append(f"{where}: صعوبة MODERATE لكن النتيجة {field.score} > 85.")
    if holding == PotentialLevel.HIGH and field.score > 65:
        violations.append(f"{where}: صعوبة HIGH لكن النتيجة {field.score} > 65.")
    if (
        holding == PotentialLevel.LOW
        and field.fouling_transport_potential == PotentialLevel.LOW
        and field.turbidity_potential == PotentialLevel.LOW
        and field.rip_current_potential == PotentialLevel.LOW
        and field.score != 100
    ):
        violations.append(f"{where}: كل المؤشرات LOW لكن النتيجة {field.score} != 100.")

    # 4. The headline reason line ("صعوبة تثبيت الخط: …") must name the same
    #    level as the number. The unknown-data guard path uses a different
    #    headline and is skipped.
    if holding != PotentialLevel.UNKNOWN and field.reasons_ar:
        first = field.reasons_ar[0]
        if first.startswith("صعوبة تثبيت الخط:"):
            label = _potential_label(holding)
            if label not in first:
                violations.append(f"{where}: سطر الصعوبة لا يطابق المستوى {holding.value}: {first}")

    return violations


def _check_breakdown_dominant(breakdown: HoldingBreakdown, where: str) -> list[str]:
    """The `dominant` mechanism must be the most severe one shown."""
    mechanisms = {
        "longshore_current": breakdown.longshore_current,
        "orbital_motion": breakdown.orbital_motion,
        "return_flow": breakdown.return_flow,
        "tidal_current": breakdown.tidal_current,
    }
    top = max(_POTENTIAL_RANK[level] for level in mechanisms.values())
    if breakdown.dominant == "none":
        if any(level != PotentialLevel.UNKNOWN for level in mechanisms.values()):
            return [f"{where}: dominant='none' رغم وجود آليات معروفة: {mechanisms}"]
        return []
    if _POTENTIAL_RANK[mechanisms[breakdown.dominant]] != top:
        return [
            f"{where}: السبب الغالب {breakdown.dominant} "
            f"({mechanisms[breakdown.dominant].value}) ليس الأشد {top}."
        ]
    return []


def check_report_consistency(result: DecisionResponse) -> list[str]:
    """Return every presentation-layer inconsistency found in a generated report."""
    violations: list[str] = []

    field = result.field_feasibility
    if field.holding_breakdown is not None:
        violations += _check_breakdown_dominant(field.holding_breakdown, "التجميع")
        # The aggregated summary must still sit at or above its own dominant cause.
        dominant_level = _dominant_level(field.holding_breakdown)
        if (
            dominant_level is not None
            and _POTENTIAL_RANK[field.holding_difficulty] < _POTENTIAL_RANK[dominant_level]
        ):
            violations.append("التجميع: الخلاصة أدنى من سببه الغالب — تناقض رقم مع شرحه.")
    # The aggregated status must match its own aggregated score + holding level
    # (the same rule as the hour level). Proven consistent across a 342-scenario
    # sweep; this freezes that guarantee.
    agg_expected = _expected_status(field.holding_difficulty, field.score)
    if field.status != agg_expected:
        violations.append(
            f"التجميع: الحالة {field.status.value} لا تطابق "
            f"{field.holding_difficulty.value}+{field.score} (المتوقع {agg_expected.value})."
        )
    for index, hour in enumerate(result.hourly):
        violations += _check_feasibility(hour.field_feasibility, f"الساعة {index}")
        if hour.field_feasibility.holding_breakdown is not None:
            violations += _check_breakdown_dominant(
                hour.field_feasibility.holding_breakdown, f"الساعة {index}"
            )

    # 5. Confidence breakdown text: no legacy self-contradiction, and the
    #    printed arithmetic adds up.
    for line in result.confidence.breakdown_ar:
        if "لا خافض محدد" in line:
            violations.append(f"ثقة: صيغة قديمة متناقضة: {line}")
        if "السقف الوحيد المطبَّق 85/100" in line and "ناقص" not in line:
            violations.append(f"ثقة: سقف بلا ذكر الخصم: {line}")
        cap = _CAP_RE.search(line)
        if cap and int(cap.group(1)) - int(cap.group(2)) != 85:
            violations.append(f"ثقة: حساب السقف لا يساوي 85: {line}")
        basis = _BASIS_RE.search(line)
        if basis:
            stated = int(basis.group(1))
            parts = sum(int(basis.group(i)) for i in range(2, 6))
            if abs(stated - parts) > 2:  # rounding slack across four terms
                violations.append(
                    f"ثقة: مكوّنات الأساس ({parts}) لا تطابق الأساس ({stated}): {line}"
                )
            if stated > 100:
                violations.append(f"ثقة: أساس فوق 100: {line}")

    # 6. Factor [1.11] label/value coherence.
    for assessment in result.factor_assessments:
        if assessment.matrix_id == "1.11":
            if assessment.title_ar != "اتجاه الريح السائد واستمراريته":
                violations.append(f"[1.11]: اسم العامل {assessment.title_ar!r} غير متوقع.")
            if not _SECTOR_RE.match(assessment.value_ar):
                violations.append(f"[1.11]: قيمة غير متوقعة: {assessment.value_ar!r}")

    # 7. The weak-surf textual flag must appear exactly when the data shows it.
    heights = [
        h.forecast.wave_height_m for h in result.hourly if h.forecast.wave_height_m is not None
    ]
    incidences = {h.derived.wave_incidence for h in result.hourly}
    weak_surf_expected = (
        bool(heights)
        and max(heights) < 0.6
        and bool(incidences & {WaveIncidence.OBLIQUE, WaveIncidence.ALONGSHORE})
    )
    signals = result.advanced_signals_ar or []
    weak_surf_shown = any("الكسرة ضعيفة" in signal for signal in signals)
    if weak_surf_expected and not weak_surf_shown:
        violations.append("الإشارات: كسرة ضعيفة متوقعة وغير معروضة.")
    if weak_surf_shown and not weak_surf_expected:
        violations.append("الإشارات: تنبيه كسرة ضعيفة معروض دون تحقق شرطه.")

    # 7b. Cross-sea flag must appear exactly when its (real-data) condition holds.
    cross_pairs = [
        (h.derived.wave_component_angle_deg, h.derived.wave_component_secondary_energy_share)
        for h in result.hourly
        if h.derived.wave_component_angle_deg is not None
        and h.derived.wave_component_secondary_energy_share is not None
    ]
    cross_expected = (
        bool(cross_pairs)
        and max(angle for angle, _ in cross_pairs) >= 40.0
        and max(share for _, share in cross_pairs) >= 0.25
    )
    cross_shown = any("بحر متقاطع" in signal for signal in signals)
    if cross_expected and not cross_shown:
        violations.append("الإشارات: بحر متقاطع متوقع وغير معروض.")
    if cross_shown and not cross_expected:
        violations.append("الإشارات: تنبيه بحر متقاطع معروض دون تحقق شرطه.")

    # 8. The comfort line must mention gusts when they clearly exceed the mean.
    winds = [
        h.forecast.wind_speed_kmh for h in result.hourly if h.forecast.wind_speed_kmh is not None
    ]
    gusts = [
        h.forecast.wind_gust_kmh for h in result.hourly if h.forecast.wind_gust_kmh is not None
    ]
    comfort_line = next((s for s in signals if "راحة الصياد" in s), None)
    if (
        comfort_line
        and winds
        and gusts
        and max(gusts) >= (sum(winds) / len(winds)) + 10
        and "الهبات" not in comfort_line
    ):
        violations.append("الإشارات: راحة بدون ذكر الهبات رغم هبات قوية.")

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Sweep: run the guard over a wide grid of generated reports.
# ─────────────────────────────────────────────────────────────────────────────

_SCENARIOS = [
    # (wave_h, wave_from, wind_kmh, wind_from, current_kmh, shore_type, species)
    (0.4, 170.0, 18.0, 180.0, 0.3, "sandy", "general"),  # the fixed bug case
    (0.6, 90.0, 12.0, 90.0, 0.6, "sandy", "general"),  # default good day
    (0.3, 45.0, 8.0, 45.0, 0.2, "sandy", "european_seabass"),
    (0.5, 0.0, 15.0, 0.0, 0.5, "rocky", "gilthead_seabream"),
    (0.8, 100.0, 20.0, 100.0, 0.8, "jetty", "white_seabream"),
    (1.2, 80.0, 25.0, 80.0, 1.0, "sandy", "general"),
    (2.0, 90.0, 35.0, 90.0, 1.2, "sandy", "general"),  # storm no-go
    (1.5, 60.0, 30.0, 60.0, 0.9, "cliff", "european_seabass"),
    (0.4, 140.0, 22.0, 140.0, 0.4, "sandy", "general"),
    (0.7, 25.0, 45.0, 25.0, 0.6, "jetty", "general"),  # strong onshore
    (0.55, 170.0, 16.0, 170.0, 0.3, "sandy", "european_seabass"),
    (0.9, 45.0, 18.0, 135.0, 0.5, "rocky", "gilthead_seabream"),
    (0.35, 20.0, 10.0, 200.0, 0.1, "sandy", "striped_seabream"),
    (1.0, 110.0, 28.0, 110.0, 0.7, "jetty", "general"),
    (0.6, 70.0, 24.0, 70.0, 0.6, "sandy", "white_seabream"),
    (0.2, 160.0, 5.0, 160.0, 0.2, "sandy", "general"),
    (1.8, 30.0, 40.0, 30.0, 1.0, "cliff", "european_seabass"),
    (0.75, 85.0, 21.0, 85.0, 0.55, "sandy", "general"),
]


@pytest.mark.parametrize(
    "wave_h, wave_from, wind_kmh, wind_from, current_kmh, shore_type, species",
    _SCENARIOS,
    ids=[f"{s[0]}-{s[1]}-{s[2]}-{s[3]}-{s[5]}-{s[6]}" for s in _SCENARIOS],
)
def test_generated_report_has_no_presentation_contradictions(
    dataset_factory: Callable[..., ForecastDataset],
    wave_h: float,
    wave_from: float,
    wind_kmh: float,
    wind_from: float,
    current_kmh: float,
    shore_type: str,
    species: str,
) -> None:
    dataset = dataset_factory(
        count=24,
        start_at=datetime(2026, 9, 7, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        hour_updates={
            "wave_height_m": wave_h,
            "wave_direction_deg": wave_from,
            "wind_speed_kmh": wind_kmh,
            "wind_gust_kmh": wind_kmh + 10.0,
            "wind_direction_deg": wind_from,
            "ocean_current_velocity_kmh": current_kmh,
            "ocean_current_direction_deg": wave_from,
        },
        spot_updates={"shore_type": shore_type, "seaward_orientation_deg": 90.0},
        angler_updates={"target_species": species},
    )
    result = engine.evaluate(dataset)
    violations = check_report_consistency(result)
    assert not violations, " · ".join(violations)


def test_missing_core_fields_still_pass_the_guard(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(hour_updates={"wave_direction_deg": None})
    result = engine.evaluate(dataset)
    violations = check_report_consistency(result)
    assert not violations, " · ".join(violations)


def test_guard_catches_summary_below_dominant_cause(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    """Freeze the third-audit regression: 'منخفض' summary + a 'متوسط' dominant cause.

    The engine now floors the gate level to the dominant mechanism, so a genuine
    result can no longer produce this shape. This test corrupts a real result to
    the old broken shape and asserts the guard would refuse to display it.
    """
    result = engine.evaluate(dataset_factory(count=24))
    breakdown = result.field_feasibility.holding_breakdown
    assert breakdown is not None
    corrupted_breakdown = breakdown.model_copy(
        update={
            "orbital_motion": PotentialLevel.MODERATE,
            "longshore_current": PotentialLevel.LOW,
            "return_flow": PotentialLevel.LOW,
            "tidal_current": PotentialLevel.LOW,
            "dominant": "orbital_motion",
        }
    )
    corrupted = result.model_copy(
        update={
            "field_feasibility": result.field_feasibility.model_copy(
                update={
                    "holding_difficulty": PotentialLevel.LOW,
                    "holding_breakdown": corrupted_breakdown,
                }
            )
        }
    )
    violations = check_report_consistency(corrupted)
    assert any("أدنى من سببه الغالب" in v for v in violations), violations
