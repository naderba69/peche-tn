"""Deterministic field report (التقرير الميداني المنظّم).

Every number in the report is either (a) a real forecast/observation value
already present in the deterministic response, or (b) a documented
physical/astronomical derivation:

- Moon upper/lower transits: Meeus low-precision series (validated against an
  independent ephemeris for Tunis, 2026-09-14).
- Cast distance / wind penalty: a disclosed simplified ballistic reference
  table + linear headwind drag approximation.
- Comfort index: NOAA/NWS wind chill + wave/rain composite (documented below).

Nothing here is written or invented by a language model, and nothing touches the
binary decision, any safety gate, or the spring/neap classification.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime
from typing import TypeVar

from .enums import WindRelation
from .labels import DECISION_LABEL_AR, WIND_RELATION_AR
from .math import moon_illumination, moon_transit_times
from .models import (
    AstronomicalTime,
    DecisionResponse,
    FishermanReport,
    ForecastDataset,
    ReportPeriod,
)
from .species import (
    BAIT_BY_SPECIES,
    SEA_STATE_LABELS_AR,
    classify_sea_state,
)

_T = TypeVar("_T")

_COMPASS_AR = (
    "شمالية",
    "شمالية شرقية",
    "شرقية",
    "جنوبية شرقية",
    "جنوبية",
    "جنوبية غربية",
    "غربية",
    "شمالية غربية",
)

# Fixed four-block day partition (presentation only).
_PERIODS = (
    ("dawn", "السحر", 0, 4),
    ("morning", "الصباح", 4, 12),
    ("midday", "الظهيرة", 12, 18),
    ("dusk", "الغسق", 18, 24),
)

# Documented reference table: typical surfcasting release range (4.2 m rod,
# lead-only, still air) per weight band. Coarse reference, not a measurement.
_BASE_CAST_BY_BAND_M = {"light": 55, "medium": 70, "heavy": 85, "extreme": 95}

# Wind penalty: ~0.15 m lost per 1 km/h of opposing (onshore) wind — a
# documented linear drag approximation, applied only to the seaward-opposing
# component the engine already resolves.
_WIND_CAST_PENALTY_M_PER_KMH = 0.15

_DECISION_REASON_AR = {
    "safe_window": "نافذة آمنة اجتازت فحوص المحرك",
    "safety_hazard": "خطر سلامة فوق الحدود المحافظة",
    "field_infeasible": "تعذّر التنفيذ الميداني",
    "critical_data_missing": "نقص بيانات حرجة",
    "conservative_uncertainty": "شك محافظ في المدخلات",
    "fouling_confirmed": "صوفة مؤكدة (قوة قاهرة)",
    "official_warning": "بلاغ رسمي (حماية مدنية / رصد جوي)",
    "trip_ruin_confirmed": "عامل مفسد للخرجة مؤكد",
}

_ASTRONOMY_NOTE_AR = (
    "أوقات فلكية مرجعية محسوبة (سلسلة Meeus) أو من مزوّد الأرصاد؛ "
    "ليست قاعدة صيد ولا تدخل القرار أو السلامة."
)


def _compass_ar(deg: float | None) -> str:
    if deg is None:
        return "غير معروفة"
    return _COMPASS_AR[round(((deg % 360.0) + 360.0) % 360.0 / 45.0) % 8]


def _hm(value: datetime | None) -> str | None:
    return None if value is None else value.strftime("%H:%M")


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(statistics.fmean(present))


def _circular_mean_deg(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    sin_sum = sum(math.sin(math.radians(value)) for value in present)
    cos_sum = sum(math.cos(math.radians(value)) for value in present)
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0


def _most_frequent(values: list[_T], default: _T) -> _T:
    present = [value for value in values if value is not None]
    if not present:
        return default
    return Counter(present).most_common(1)[0][0]


def _wind_chill_c(temp_c: float | None, wind_kmh: float | None) -> float | None:
    """NOAA/NWS wind-chill (°C) — applies only below 10 °C and above 4.8 km/h."""
    if temp_c is None:
        return None
    if temp_c > 10.0 or wind_kmh is None or wind_kmh <= 4.8:
        return temp_c
    wind_power = wind_kmh**0.16
    return float(
        round(13.12 + 0.6215 * temp_c - 11.37 * wind_power + 0.3965 * temp_c * wind_power, 1)
    )


def _thermal_comfort(feels_like_c: float | None) -> int:
    """0-100 mapping: 15-25 °C ideal, zero at <=0 °C or >=40 °C (documented)."""
    if feels_like_c is None:
        return 60
    if 15.0 <= feels_like_c <= 25.0:
        return 100
    if feels_like_c <= 0.0:
        return 0
    if feels_like_c < 15.0:
        return round(100.0 * feels_like_c / 15.0)
    if feels_like_c >= 40.0:
        return 0
    return round(100.0 * (40.0 - feels_like_c) / 15.0)


def _wave_comfort(wave_m: float | None) -> int:
    """0-100: full comfort up to 0.3 m, zero at >=1.5 m (documented)."""
    if wave_m is None:
        return 60
    if wave_m <= 0.3:
        return 100
    if wave_m >= 1.5:
        return 0
    return round(100.0 * (1.5 - wave_m) / 1.2)


def _rain_comfort(rain_prob_pct: float | None) -> int:
    """0-100: full comfort at 0% rain probability, zero at >=50%."""
    if rain_prob_pct is None:
        return 80
    if rain_prob_pct <= 0.0:
        return 100
    if rain_prob_pct >= 50.0:
        return 0
    return round(100.0 * (50.0 - rain_prob_pct) / 50.0)


def _comfort_index(
    feels_like_c: float | None,
    wave_m: float | None,
    rain_prob_pct: float | None,
) -> int:
    """Documented composite: 0.4 thermal + 0.4 wave + 0.2 rain (0-100)."""
    return round(
        0.4 * _thermal_comfort(feels_like_c)
        + 0.4 * _wave_comfort(wave_m)
        + 0.2 * _rain_comfort(rain_prob_pct)
    )


def _montage_ar(state: str, wind_kmh: float | None) -> str:
    """Standard surfcasting practice: longer leader in calm water, shorter in
    moving water to keep the bait near the bottom."""
    if state == "rough" or (wind_kmh is not None and wind_kmh >= 30.0):
        return "مونتاج قصير برصاص أثقل (فرع 60-80سم) — يثبّت الطعم قرب القاع في الماء المتحرك."
    if state == "moderate" or (wind_kmh is not None and wind_kmh >= 18.0):
        return "مونتاج متوسط (فرع 80-100سم) — مرن للظروف المتوسطة."
    return "مونتاج بسنود طويل (فرع سفلي ~150سم، خفيف) — حركة طبيعية للطعم في الماء الهادئ."


def _turbidity_ar(wind_kmh: float | None, fnu: float | None) -> str:
    if wind_kmh is not None and wind_kmh >= 25.0:
        return "رياح قوية قد تثير العكارة قرب الكسرة — عاين قبل الرمي."
    if fnu is not None and fnu >= 2.0:
        return "العينة الساتلية (1كم من الشاطئ) مرتفعة نسبياً — سياق لا قياس."
    return "لا مؤشر نموذجي قوي على عكارة."


def _pressure_trend_ar(hours_pressure_change: list[float | None]) -> str:
    change = _mean(hours_pressure_change)
    if change is None:
        return "غير متوفر"
    if change > 1.0:
        return "صاعد (استقرار تدريجي)"
    if change < -1.0:
        return "هابط (تغيّر محتمل)"
    return "مستقر (محايد)"


def _beach_summary_ar(state: str, wind_kmh: float | None, pressure_trend: str) -> str:
    if state == "rough" or (wind_kmh is not None and wind_kmh >= 30.0):
        return "مضطربة: موج مرتفع أو ريح قوية — انتبه للسلامة."
    if state == "moderate" or (wind_kmh is not None and wind_kmh >= 20.0):
        return "متوسطة: موج/ريح تتطلب انتباهاً — صيد ممكن باحتياطات."
    return f"هادئة نسبياً: موج خفيف وريح معتدلة — جلسة مريحة ({pressure_trend})."


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_fisherman_report(
    dataset: ForecastDataset,
    decision: DecisionResponse,
) -> FishermanReport:
    hourly = decision.hourly
    target_date = dataset.target_date
    tz = dataset.fetched_at.tzinfo
    assert tz is not None, "fetched_at must be timezone-aware"

    # ── 0. Executive summary ────────────────────────────────────────────── #
    target_bait_ar, bait_note_ar = BAIT_BY_SPECIES[dataset.angler.target_species]
    seaward = dataset.spot.seaward_orientation_deg

    # ── 1. Timing and water movement ────────────────────────────────────── #
    sunrise_ar = _hm(dataset.sunrise)
    sunset_ar = _hm(dataset.sunset)
    moonrise_ar = _hm(dataset.moonrise)
    moonset_ar = _hm(dataset.moonset)
    illumination = moon_illumination(target_date)
    upper_transit, lower_transit = moon_transit_times(target_date, dataset.location.longitude, tz)
    tide_high_ar = [
        event.time.strftime("%H:%M") for event in decision.tide_events if event.kind == "high"
    ]
    tide_low_ar = [
        event.time.strftime("%H:%M") for event in decision.tide_events if event.kind == "low"
    ]
    tide_note_ar = "مواقيت مدّ نموذجية من النموذج البحري؛ المدّ والجزر في تونس ضعيف جداً (~0.3م)."
    pressure_hpa = _rounded_mean([item.forecast.pressure_msl_hpa for item in hourly])
    pressure_trend = _pressure_trend_ar([item.derived.pressure_change_12h_hpa for item in hourly])
    day_wind = _mean([item.forecast.wind_speed_kmh for item in hourly])
    day_wave = _mean([item.forecast.wave_height_m for item in hourly])
    day_state, _ = classify_sea_state(day_wave, day_wind)

    # ── 2. Astronomical reference times ─────────────────────────────────── #
    astronomical_times: list[AstronomicalTime] = []
    if upper_transit is not None:
        astronomical_times.append(
            AstronomicalTime(
                kind="upper_transit",
                label_ar="العبور القمري العلوي (القمر في أعلى نقطة)",
                time_ar=upper_transit.strftime("%H:%M"),
                note_ar="محسوب فلكياً — مرجعي.",
            )
        )
    if lower_transit is not None:
        astronomical_times.append(
            AstronomicalTime(
                kind="lower_transit",
                label_ar="العبور القمري السفلي",
                time_ar=lower_transit.strftime("%H:%M"),
                note_ar="محسوب فلكياً — مرجعي.",
            )
        )
    if moonrise_ar is not None:
        astronomical_times.append(
            AstronomicalTime(
                kind="moonrise",
                label_ar="طلوع القمر",
                time_ar=moonrise_ar,
                note_ar="من مزوّد الأرصاد.",
            )
        )
    if moonset_ar is not None:
        astronomical_times.append(
            AstronomicalTime(
                kind="moonset",
                label_ar="غروب القمر",
                time_ar=moonset_ar,
                note_ar="من مزوّد الأرصاد.",
            )
        )
    for event in decision.tide_events:
        astronomical_times.append(
            AstronomicalTime(
                kind="high_tide" if event.kind == "high" else "low_tide",
                label_ar="قمة مدّ نموذجية" if event.kind == "high" else "قاع جزر نموذجي",
                time_ar=event.time.strftime("%H:%M"),
                note_ar="من النموذج البحري؛ المدّ ضعيف في تونس.",
            )
        )

    # ── 3. Temporal breakdown (four blocks) ─────────────────────────────── #
    fnu = (
        decision.coastal_water_context.turbidity_fnu
        if decision.coastal_water_context is not None
        else None
    )
    gear = decision.gear_recommendation
    band_key = "medium"
    if gear is not None and gear.scenarios:
        first = gear.scenarios[0]
        band_key = _band_key_for(first.weight_min_g, first.weight_max_g)
    base_cast_m = _BASE_CAST_BY_BAND_M[band_key]

    periods: list[ReportPeriod] = []
    for key, label, start_hour, end_hour in _PERIODS:
        block = [item for item in hourly if start_hour <= item.time.astimezone(tz).hour < end_hour]
        if not block:
            periods.append(
                ReportPeriod(
                    key=key,
                    label_ar=label,
                    range_ar=f"{start_hour:02d}:00-{end_hour:02d}:00",
                    state_ar="لا بيانات نموذجية في هذه الفترة.",
                    wind_relation_ar="غير متوفر",
                    turbidity_ar=_turbidity_ar(None, None),
                    montage_ar="—",
                )
            )
            continue

        wind_speed = _mean([item.forecast.wind_speed_kmh for item in block])
        wind_gust = _mean([item.forecast.wind_gust_kmh for item in block])
        wind_dir = _circular_mean_deg([item.forecast.wind_direction_deg for item in block])
        wave_height = _mean([item.forecast.wave_height_m for item in block])
        wave_period = _mean([item.forecast.wave_period_s for item in block])
        relation = _most_frequent([item.derived.wind_relation.value for item in block], "unknown")
        shoreward = _mean([item.derived.wind_shoreward_component_kmh for item in block])
        opposing = max(0.0, shoreward or 0.0)
        cast_effect_m = round(opposing * _WIND_CAST_PENALTY_M_PER_KMH)
        cast_distance_m = max(0, base_cast_m - cast_effect_m)
        mean_confidence = _mean([float(item.confidence.score) for item in block])
        confidence_pct = round(mean_confidence) if mean_confidence is not None else None
        feels_like = _wind_chill_c(
            _mean([item.forecast.air_temperature_c for item in block]), wind_speed
        )
        comfort = _comfort_index(
            feels_like,
            wave_height,
            _mean([item.forecast.precipitation_probability_pct for item in block]),
        )
        state, _ = classify_sea_state(wave_height, wind_speed)

        warnings: list[str] = []
        if wind_gust is not None and wind_gust >= 35.0:
            warnings.append(f"هبات قوية (≈{round(wind_gust)} كم/س) تزعج الرمي والثبات.")
        elif wind_gust is not None and wind_gust >= 25.0:
            warnings.append(f"هبات ملحوظة (≈{round(wind_gust)} كم/س) — رصاص أثقل عند الحاجة.")
        if wave_height is not None and wave_height >= 1.1:
            warnings.append(f"الموج مرتفع (≈{wave_height:.1f} م) — احذر من الانزلاق.")
        if any(
            item.forecast.lightning_potential_jkg
            for item in block
            if item.forecast.lightning_potential_jkg
        ):
            warnings.append("مؤشر رعد نموذجي — غادر الشاطئ فور سماع الرعد.")

        periods.append(
            ReportPeriod(
                key=key,
                label_ar=label,
                range_ar=f"{start_hour:02d}:00-{end_hour:02d}:00",
                state_ar=SEA_STATE_LABELS_AR.get(state, "حالة البحر غير متاحة"),
                confidence_pct=confidence_pct,
                wind_speed_kmh=_rounded1(wind_speed),
                wind_gust_kmh=_rounded1(wind_gust),
                wind_dir_deg=_rounded0(wind_dir),
                wind_relation_ar=WIND_RELATION_AR.get(_wind_relation_enum(relation), relation),
                wind_cast_effect_m=float(cast_effect_m),
                wave_height_m=_rounded2(wave_height),
                wave_period_s=_rounded1(wave_period),
                cast_distance_m=cast_distance_m,
                comfort_index=comfort,
                turbidity_ar=_turbidity_ar(wind_speed, fnu),
                montage_ar=_montage_ar(state, wind_speed),
                warnings_ar=warnings,
            )
        )

    # ── 4. Factor balance ───────────────────────────────────────────────── #
    red_factors: list[str] = []
    green_factors: list[str] = []
    for item in hourly:
        for factor in item.factors:
            if factor.severity.value in {"critical", "caution"}:
                red_factors.append(factor.explanation_ar)
            elif factor.impact.value == "positive":
                green_factors.append(factor.explanation_ar)
    red_factors = _unique(red_factors)[:4]
    green_factors = _unique(green_factors)[:4]

    # ── 5. Field tactics ────────────────────────────────────────────────── #
    lead_advice_ar = _lead_advice(gear)
    timing_advice_ar = _timing_advice(decision)
    distance_advice_ar = _distance_advice(base_cast_m, periods)
    safety_advice_ar = _safety_advice(decision, dataset)

    # ── 6. Reference numbers ────────────────────────────────────────────── #
    water_temp = _mean([item.forecast.sea_surface_temperature_c for item in hourly])
    air_temp = _mean([item.forecast.air_temperature_c for item in hourly])
    max_gust = max(
        (item.forecast.wind_gust_kmh for item in hourly if item.forecast.wind_gust_kmh is not None),
        default=None,
    )

    return FishermanReport(
        decision_label_ar=DECISION_LABEL_AR[decision.decision],
        decision_reason_ar=_DECISION_REASON_AR.get(decision.decision_reason_code.value, "—"),
        opportunity_score=decision.opportunity_score,
        opportunity_note_ar="مؤشر الفرصة ترتيب نسبي 0-100 للمقارنة؛ ليس نسبة نجاح ولا ضمان مصيد.",
        target_bait_ar=target_bait_ar,
        bait_note_ar=bait_note_ar,
        beach_direction_deg=seaward,
        beach_direction_ar=_compass_ar(seaward),
        sunrise_ar=sunrise_ar,
        sunset_ar=sunset_ar,
        moonrise_ar=moonrise_ar,
        moonset_ar=moonset_ar,
        moon_illumination_pct=round(illumination * 100.0),
        moon_upper_transit_ar=_hm(upper_transit),
        moon_lower_transit_ar=_hm(lower_transit),
        tide_high_ar=tide_high_ar,
        tide_low_ar=tide_low_ar,
        tide_note_ar=tide_note_ar,
        pressure_hpa=pressure_hpa,
        pressure_trend_ar=pressure_trend,
        beach_summary_ar=_beach_summary_ar(day_state, day_wind, pressure_trend),
        astronomical_times=astronomical_times,
        astronomy_note_ar=_ASTRONOMY_NOTE_AR,
        periods=periods,
        red_factors_ar=red_factors,
        green_factors_ar=green_factors,
        lead_advice_ar=lead_advice_ar,
        timing_advice_ar=timing_advice_ar,
        distance_advice_ar=distance_advice_ar,
        safety_advice_ar=safety_advice_ar,
        water_temp_c=_rounded1(water_temp),
        air_temp_c=_rounded1(air_temp),
        max_gust_kmh=_rounded1(max_gust),
        reference_note_ar=(
            "الأرقام المرجعية قيم نموذجية متوسطة ليوم الحصة؛ المسافة وأثر الريح ومؤشر الراحة "
            "تقديرات موثقة بنماذج مبسّطة معلنة — وليست قياسات ميدانية."
        ),
    )


def _wind_relation_enum(value: str) -> WindRelation:
    try:
        return WindRelation(value)
    except ValueError:
        return WindRelation.UNKNOWN


def _rounded0(value: float | None) -> float | None:
    return None if value is None else round(value)


def _rounded1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _rounded2(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _rounded_mean(values: list[float | None]) -> float | None:
    return _rounded1(_mean(values))


def _band_key_for(min_g: int, max_g: int) -> str:
    midpoint = (min_g + max_g) / 2.0
    if midpoint <= 90.0:
        return "light"
    if midpoint <= 140.0:
        return "medium"
    if midpoint <= 200.0:
        return "heavy"
    return "extreme"


def _lead_advice(gear) -> str:  # type: ignore[no-untyped-def]
    if gear is None or not gear.scenarios:
        return "رصاص بوزن متوسط وشكل انسيابي/هرمي حسب القاع؛ عاين الكسرة قبل النصب."
    first = gear.scenarios[0]
    return (
        f"رصاص {first.shape_ar} في مجال {first.weight_band_ar}؛ {first.note_ar} "
        f"({first.montage_ar})."
    )


def _timing_advice(decision: DecisionResponse) -> str:
    if decision.recommended_windows:
        best = decision.recommended_windows[0]
        start = best.start.strftime("%H:%M")
        end = best.end.strftime("%H:%M")
        return f"النافذة الأنسب {start}-{end}؛ التزم بها ولا تمدّدها إذا تغيّر البحر على الأرض."
    twilight = [item for item in decision.hourly if item.derived.is_twilight]
    if twilight:
        first = twilight[0].time.strftime("%H:%M")
        return f"لا نافذة آمنة اليوم؛ إن خرجت فقرب الشفق ({first}) بعد معاينة ميدانية."
    return "لا نافذة آمنة اليوم؛ معاينة ميدانية قبل أي قرار بالخروج."


def _distance_advice(base_cast_m: int, periods: list[ReportPeriod]) -> str:
    distances = [period.cast_distance_m for period in periods if period.cast_distance_m is not None]
    if not distances:
        return f"مسافة رمي مرجعية ≈ {base_cast_m} م (تقدير موثق، يقل مع الريح البحرية)."
    low = min(distances)
    high = max(distances)
    if low == high:
        return f"المسافة المتوقعة ≈ {low} م (تقدير موثق من وزن الرصاص والريح)."
    return f"المسافة المتوقعة بين {low} و {high} م حسب الفترة (تقدير موثق من وزن الرصاص والريح)."


def _safety_advice(decision: DecisionResponse, dataset: ForecastDataset) -> str:
    parts = ["افحص معداتك قبل البدء، وانتبه للهبات المفاجئة وحركة الموج."]
    if decision.field_feasibility.status.value == "difficult":
        parts.append("التنفيذ الميداني صعب اليوم — لا تخاطر بسلامتك.")
    if dataset.spot.shore_type.value == "rocky":
        parts.append("قاع صخري: احذر الانزلاق وارتدِ حذاء مناسباً.")
    if (
        decision.current_weather_observation is not None
        and not decision.current_weather_observation.is_direct_observation
    ):
        parts.append("الرصد من محطة مطار وليس داخل البقعة؛ قدّم عينك الميدانية على التوقع.")
    return " ".join(parts)
