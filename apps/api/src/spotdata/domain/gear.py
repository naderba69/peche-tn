"""Surfcasting lead catalog and recommendation.

This is deliberately a recommendation, never an inventory. The engine proposes
weight *bands* with a shape and a montage class from a small physical catalog,
always conditional on the user's rod rating, and always multi-scenario because the
bottom under the cast is never known (decision D4). No brand, no single-gram value.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import LeadShape, MontageClass, PotentialLevel
from .models import GearRecommendation, LeadScenario

# Weight bands in grams. Displayed as a range, never a single number.
WEIGHT_BANDS: dict[str, tuple[int, int, str]] = {
    "light": (60, 90, "خفيف"),
    "medium": (100, 140, "متوسط"),
    "heavy": (150, 200, "ثقيل"),
    "extreme": (200, 250, "قاهر"),
}


@dataclass(frozen=True, slots=True)
class LeadType:
    shape: LeadShape
    label_ar: str
    bottom_ar: str
    lateral_hold: PotentialLevel
    burial: str
    snag_risk: PotentialLevel
    note_ar: str


CATALOG: tuple[LeadType, ...] = (
    LeadType(
        shape=LeadShape.STREAMLINED,
        label_ar="رصاص انسيابي عادي",
        bottom_ar="رمل ناعم إلى متوسط",
        lateral_hold=PotentialLevel.MODERATE,
        burial="ضعيف",
        snag_risk=PotentialLevel.LOW,
        note_ar="مرمى جيد ومقاومة ماء أقل، لكن ثباته جانبي محدود.",
    ),
    LeadType(
        shape=LeadShape.PYRAMID,
        label_ar="رصاص هرمي",
        bottom_ar="رمل وحصى",
        lateral_hold=PotentialLevel.HIGH,
        burial="جيد",
        snag_risk=PotentialLevel.MODERATE,
        note_ar="الخيار المتوازن ضد الجرّ الجانبي مع انغراس جيد.",
    ),
    LeadType(
        shape=LeadShape.GRAPNEL,
        label_ar="grapnel ثابت",
        bottom_ar="رمل خشن وقاع مضغوط",
        lateral_hold=PotentialLevel.HIGH,
        burial="عالٍ",
        snag_risk=PotentialLevel.HIGH,
        note_ar="أقوى ثبات، لكنه يعلّق بسهولة؛ لا يُنصح به إلا بعد تأكيد رمل ميدانياً.",
    ),
    LeadType(
        shape=LeadShape.BREAKAWAY_GRAPNEL,
        label_ar="breakaway grapnel",
        bottom_ar="رمل بقنوات أو صخر متفرق",
        lateral_hold=PotentialLevel.HIGH,
        burial="عالٍ",
        snag_risk=PotentialLevel.LOW,
        note_ar="أذرع تنثني عند الاسترجاع فتقاوم الجرّ دون أن تعلّق عادة.",
    ),
    LeadType(
        shape=LeadShape.ROCKY,
        label_ar="رصاص صخري قليل التعليق",
        bottom_ar="صخر وPosidonia",
        lateral_hold=PotentialLevel.MODERATE,
        burial="غير قابل",
        snag_risk=PotentialLevel.LOW,
        note_ar="يضحّي ببعض الثبات لتقليل خطر التعليق في قاع صخري أو عشبي.",
    ),
)

BY_SHAPE = {item.shape: item for item in CATALOG}

MONTAGE_LABELS: dict[MontageClass, str] = {
    MontageClass.LOW: "مونتاج منخفض المقاومة (مرتفع/شعر طويل)",
    MontageClass.MEDIUM: "مونتاج متوسط المقاومة (paternoster)",
    # HIGH is intentionally never recommended: the engine always lowers drag
    # resistance against holding, so a drag-aggravating montage is reserved
    # (audit 2026-09-14, item C4).
    MontageClass.HIGH: "مونتاج عالٍ المقاومة (قاع بطعم كبير) — تفاقم الجرّ",
}

ROD_RATING_NOTE = "فقط إذا كان الحد المطبوع على القصبة يسمح بهذا المجال."


def weight_band_for(
    holding: PotentialLevel,
    wave_height_m: float | None = None,
) -> tuple[str, tuple[int, int, str]]:
    """Map the holding gate to a conservative weight band.

    When holding is already HIGH and the significant wave height is large
    (>= 1.5 m), the heavier "extreme" band is offered so the catalog can answer
    very rough conditions instead of silently capping at 150-200 g
    (audit 2026-09-14, item C4).
    """
    if holding == PotentialLevel.LOW:
        return "light", WEIGHT_BANDS["light"]
    if holding == PotentialLevel.MODERATE:
        return "medium", WEIGHT_BANDS["medium"]
    if holding == PotentialLevel.HIGH:
        if wave_height_m is not None and wave_height_m >= 1.5:
            return "extreme", WEIGHT_BANDS["extreme"]
        return "heavy", WEIGHT_BANDS["heavy"]
    return "medium", WEIGHT_BANDS["medium"]


# Rod cap in grams: the printed limit on most surf rods is the operator's hard
# constraint, and the engine never proposes beyond it (no manual input: the
# default is the common surf-rod ceiling, stated to the user).
ROD_CAP_G = 150


# Bottom-load bands from the near-bed orbital velocity (m/s); see below.
def band_from_orbital_velocity(u_ms: float) -> str | None:
    """Return the weight band a bottom load needs, or None beyond the rod cap."""
    # 0.27 m/s: published start of sand motion (van Rijn, wave-driven, 0.1-0.5 mm).
    # Below it the bed stays put and a light lead holds. 0.40 and 0.50 are
    # estimates [C] pending calibration against logged casts.
    if u_ms < 0.27:
        return "light"
    if u_ms < 0.40:
        return "medium"
    if u_ms < 0.50:
        return "heavy"
    return None


def _clamped_band(key: str) -> tuple[int, int, str]:
    low, high, label = WEIGHT_BANDS[key]
    return min(low, ROD_CAP_G), min(high, ROD_CAP_G), label


def _scenario_band_key(index: int, base_key: str) -> str:
    order = ["light", "medium", "heavy", "extreme"]
    if index == 0:
        return base_key
    return order[max(0, order.index(base_key) - 1)]


def montage_class_for(holding: PotentialLevel) -> MontageClass:
    """Lower-resistance montage helps against drag; heavier setups increase drag."""
    if holding in {PotentialLevel.HIGH, PotentialLevel.MODERATE}:
        return MontageClass.LOW
    return MontageClass.MEDIUM


def primary_shapes_for(dominant: str) -> tuple[LeadShape, LeadShape, LeadShape]:
    """Three ranked scenarios per dominant holding mechanism (bottom-agnostic).

    Because the bottom is always Unknown, the first scenario is the least-risk
    general choice, the second is the range-optimised alternative, and the third
    is the rocky/Posidonia safety scenario.
    """
    if dominant == "longshore_current":
        return (
            LeadShape.BREAKAWAY_GRAPNEL,
            LeadShape.PYRAMID,
            LeadShape.ROCKY,
        )
    if dominant == "return_flow":
        return (
            LeadShape.STREAMLINED,
            LeadShape.PYRAMID,
            LeadShape.ROCKY,
        )
    if dominant == "tidal_current":
        return (
            LeadShape.PYRAMID,
            LeadShape.BREAKAWAY_GRAPNEL,
            LeadShape.ROCKY,
        )
    if dominant == "orbital_motion":
        return (
            LeadShape.PYRAMID,
            LeadShape.STREAMLINED,
            LeadShape.ROCKY,
        )
    # none / unknown: balanced default, wide confidence.
    return (
        LeadShape.PYRAMID,
        LeadShape.STREAMLINED,
        LeadShape.ROCKY,
    )


def scenario_weight_band(
    scenario_index: int,
    holding: PotentialLevel,
    wave_height_m: float | None = None,
) -> tuple[str, tuple[int, int, str]]:
    """Slightly vary the band per scenario: alternative may go one step lighter."""
    base_key, base = weight_band_for(holding, wave_height_m)
    if scenario_index == 0:
        return base_key, base
    order = ["light", "medium", "heavy", "extreme"]
    base_pos = order.index(base_key)
    lighter_pos = max(0, base_pos - 1)
    return order[lighter_pos], WEIGHT_BANDS[order[lighter_pos]]


def scenario_rationale(
    dominant: str,
    shape: LeadType,
    band_label: str,
) -> str:
    hint = {
        "longshore_current": "موج مائل يجرّ الخط جانبياً",
        "orbital_motion": "الموج يحرّك الماء فوق الرصاص",
        "return_flow": "الماء الراجع نحو البحر يسحب الطعم",
        "tidal_current": "تيار المدّ يجرّ الخيط",
        "none": "لا سبب غلب واضح",
    }[dominant]
    return f"مناسب للجرّ الناتج عن «{hint}»؛ مجال وزن {band_label} تقريبي."


def recommend_gear(
    holding: PotentialLevel,
    breakdown: object | None,
    fouling: PotentialLevel,
    wave_height_m: float | None,
    wind_speed_kmh: float | None,
    orbital_velocity_ms: float | None = None,
    longshore_current_ms: float | None = None,
) -> GearRecommendation:
    dominant = getattr(breakdown, "dominant", "none")
    breakdown_conf = getattr(breakdown, "confidence", 0) if breakdown is not None else 0
    shapes = primary_shapes_for(dominant)
    montage = montage_class_for(holding)
    beyond_cap = False
    # Bottom load = the stronger of the wave-driven bottom motion and the
    # longshore drag. The longshore value is the model current projected on the
    # coast: a LOWER bound for the surf zone, so it can only raise the load.
    load_candidates = [v for v in (orbital_velocity_ms, longshore_current_ms) if v is not None]
    load_velocity = max(load_candidates) if load_candidates else None
    if load_velocity is not None:
        load_key = band_from_orbital_velocity(load_velocity)
        if load_key is None:
            beyond_cap = True
            load_key = "heavy"
    else:
        load_key, _ = weight_band_for(holding, wave_height_m)
    scenarios: list[LeadScenario] = []
    for index, shape_key in enumerate(shapes):
        shape = BY_SHAPE[shape_key]
        min_g, max_g, band_label = _clamped_band(_scenario_band_key(index, load_key))
        scenarios.append(
            LeadScenario(
                shape=shape.shape,
                shape_ar=shape.label_ar,
                bottom_ar=shape.bottom_ar,
                weight_min_g=min_g,
                weight_max_g=max_g,
                weight_band_ar=f"{min_g} إلى {max_g} غ",
                montage_class=montage,
                montage_ar=MONTAGE_LABELS[montage],
                lateral_hold=shape.lateral_hold,
                snag_risk=shape.snag_risk,
                note_ar=shape.note_ar,
                rationale_ar=scenario_rationale(dominant, shape, band_label),
            )
        )

    confidence = breakdown_conf if breakdown is not None else 0
    if holding == PotentialLevel.UNKNOWN:
        confidence = min(confidence, 8)
    if wave_height_m is None or wind_speed_kmh is None:
        confidence = min(confidence, 12)

    note_parts = [ROD_RATING_NOTE]
    if dominant == "tidal_current":
        note_parts.append("في المدّ القوي استهدف الساعة القريبة من السكون (slack) إن أمكن.")
    if dominant == "orbital_motion":
        note_parts.append("الموج يحرّك الماء فوق الرصاص: فضّل وزناً أثقل قليلاً ضمن قدرة قصبتك.")
    if dominant == "return_flow":
        note_parts.append("الرجوع نحو البحر يسحب الطعم: مونتاج قليل المقاومة ورمية أقصر.")
    if fouling in {PotentialLevel.HIGH, PotentialLevel.MODERATE}:
        note_parts.append("قابلية الصوفة مرتفعة: ابدأ برمية اختبارية قبل نصب العتاد الكامل.")
    if dominant == "longshore_current":
        note_parts.append("ارمِ بزاوية مائلة عكس اتجاه الجرّ الجانبي.")
    if beyond_cap:
        note_parts.append(
            "الحمل عند القاع يتجاوز ما يثبته رصاص ضمن حد القصبة؛ لا تنصب على هذه الساعات."
        )

    return GearRecommendation(
        scenarios=scenarios,
        dominant_mechanism=dominant,
        required_rod_rating_note_ar=ROD_RATING_NOTE,
        casting_advice_ar=" · ".join(note_parts[1:]),
        confidence=confidence,
        limitations_ar=[
            "مجالات وزن تقريبية من كتالوج عام؛ لا رقم دقيق بلا بيانات قصبة وخيط وقاع.",
            "القاع تحت الطعم غير معروف؛ النتيجة سيناريوهات متعددة وليست حكماً هندسياً.",
            "لا تُستعمل grapnel ثابت على قاع صخري غير معروف؛ احتمال التعليق مرتفع.",
            f"حد القصبة المفترض {ROD_CAP_G} غ؛ لا يُقترح وزن فوقه.",
            "الحمل = الأكبر بين الموج عند القاع على عمق 1.5 م والتيار النموذجي الموازي للشاطئ؛ التيار النموذجي حد أدنى لتيار منطقة الكسر.",
        ],
    )
