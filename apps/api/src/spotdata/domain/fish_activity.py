"""Relative fish-activity from *measured* forecast fields only.

Unknown channels are omitted and weights are renormalized. Filling missing
μ with 0.70 was a hidden error source and is forbidden.

Never used: surf-zone current (model ~8 km), tea-visibility in metres,
stomach, blitz, oxygen. Turbidity potential is a blocker channel, not a
visibility metre — it does not enter this rank.

Output is 0-100 relative rank for open hours, or null when coverage is too
thin. Never a catch probability and never GO/NO_GO.
"""

from __future__ import annotations

from collections.abc import Sequence

from .enums import TargetSpecies, TideState
from .math import in_gabes_zone, tunisian_zone
from .models import ForecastDataset, HourDecision, SpeciesForecast
from .species import BAIT_BY_SPECIES, SPECIES_PROFILES

FORECAST_SPECIES = (
    TargetSpecies.EUROPEAN_SEABASS,
    TargetSpecies.GILTHEAD_SEABREAM,
    TargetSpecies.WHITE_SEABREAM,
    TargetSpecies.STRIPED_SEABREAM,
)

SST_TRAP = {
    TargetSpecies.EUROPEAN_SEABASS: (8.0, 14.0, 19.0, 24.0),
    TargetSpecies.GILTHEAD_SEABREAM: (12.0, 20.0, 26.0, 28.0),
    TargetSpecies.WHITE_SEABREAM: (12.0, 15.0, 24.0, 28.0),
    TargetSpecies.STRIPED_SEABREAM: (13.0, 16.0, 26.0, 29.0),
}

# Lead weights. turb/curr stay in the table as *declared unknowns* (coverage
# hole), not as silent 0.70 fillers.
WEIGHTS = {
    TargetSpecies.EUROPEAN_SEABASS: {
        "temp": 0.20,
        "turb": 0.25,
        "light": 0.25,
        "tide": 0.10,
        "curr": 0.10,
        "season": 0.10,
    },
    TargetSpecies.GILTHEAD_SEABREAM: {
        "temp": 0.30,
        "turb": 0.10,
        "light": 0.15,
        "tide": 0.30,
        "curr": 0.05,
        "season": 0.10,
    },
    TargetSpecies.WHITE_SEABREAM: {
        "temp": 0.25,
        "turb": 0.10,
        "light": 0.30,
        "tide": 0.10,
        "curr": 0.05,
        "season": 0.20,
    },
    TargetSpecies.STRIPED_SEABREAM: {
        "temp": 0.30,
        "turb": 0.05,
        "light": 0.15,
        "tide": 0.30,
        "curr": 0.10,
        "season": 0.10,
    },
}

HS_FEED_MIN_M = 0.5
HS_FEED_MAX_M = 1.2
HS_STORM_M = 1.5
CHOP_WIND_MIN_KMH = 10.0
CHOP_WIND_MAX_KMH = 25.0
SHOCK_DROP_C = 4.0
AFTER_STORM_MULT = 1.5
MIN_COVERAGE = 0.40

FORECAST_NOTE_AR = (
    "ترتيب نسبي فقط من الحقول المقيسة: حرارة الماء، ضوء الشفق من الشروق/الغروب، "
    "Hs، مدّ قابس إن كنت في الخليج، الموسم. "
    "لا رؤية بالمتر ولا تيار كسرة ولا أوكسجين ولا جوع — هذه فجوات معلنة لا تُملأ. "
    "إن نقصت التغطية عن 40٪ لا يُعرض رقم. ليس احتمال مصيد ولا يفتح ساعة ممنوعة."
)

UNKNOWN_AR = (
    "رؤية بالمتر (عكارة الشاي)",
    "تيار منطقة الكسرة (نموذج ~8 كم لا يُستخدم هنا)",
    "أوكسجين",
    "امتلاء المعدة",
    "بليتز الطُعم",
)


def trapezoid(value: float, a: float, b: float, c: float, d: float) -> float:
    if value <= a or value >= d:
        return 0.0
    if b <= value <= c:
        return 1.0
    if value < b:
        return (value - a) / (b - a) if b > a else 1.0
    return (d - value) / (d - c) if d > c else 1.0


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _shock(dataset: ForecastDataset) -> bool:
    series = [
        h.sea_surface_temperature_c
        for h in dataset.hours
        if h.sea_surface_temperature_c is not None
    ]
    if len(series) < 8:
        return False
    window = series[:48]
    return max(window) - min(window) >= SHOCK_DROP_C and window[-1] <= window[0] - 2.0


def _after_storm(dataset: ForecastDataset, open_hours: Sequence[HourDecision]) -> bool:
    past = any(h.wave_height_m is not None and h.wave_height_m >= HS_STORM_M for h in dataset.hours)
    if not past or not open_hours:
        return False
    now = _mean([h.forecast.wave_height_m for h in open_hours])
    return now is not None and HS_FEED_MIN_M <= now <= HS_FEED_MAX_M


def feeding_mode_ar(species: TargetSpecies, open_hours: Sequence[HourDecision], gabes: bool) -> str:
    wave = _mean([h.forecast.wave_height_m for h in open_hours])
    rising = gabes and any(h.derived.tide_state == TideState.RISING for h in open_hours)
    twilight = any(h.derived.is_twilight for h in open_hours)
    if species == TargetSpecies.EUROPEAN_SEABASS:
        if wave is not None and HS_FEED_MIN_M <= wave <= HS_FEED_MAX_M:
            return "كمين على حافة الكسرة"
        if twilight:
            return "كمين شفق"
        return "دورية خفيفة قرب الشاطئ"
    if species == TargetSpecies.GILTHEAD_SEABREAM:
        return "رعي على خط الغمر" if rising else "رعي قاعي"
    if species == TargetSpecies.WHITE_SEABREAM:
        return "رعي فجر على الصخر" if twilight else "رعي على الصخر"
    return "قاع رملي هادئ"


def _reliability_ar(coverage: float) -> str:
    if coverage < MIN_COVERAGE:
        return "غير كافٍ — لا رقم"
    if coverage < 0.55:
        return "تغطية ضعيفة"
    if coverage < 0.75:
        return "تغطية متوسطة"
    return "تغطية كافية للترتيب لا للدقة الإحصائية"


def score_species(
    species: TargetSpecies,
    open_hours: Sequence[HourDecision],
    dataset: ForecastDataset,
) -> tuple[int | None, list[str], int, str]:
    """Return (score or None, drivers, coverage_pct, reliability_ar)."""
    sst = _mean([h.forecast.sea_surface_temperature_c for h in open_hours])
    wave = _mean([h.forecast.wave_height_m for h in open_hours])
    wind = _mean([h.forecast.wind_speed_kmh for h in open_hours])
    gabes = in_gabes_zone(dataset.location.latitude, dataset.location.longitude)
    w = WEIGHTS[species]
    measured: list[tuple[float, float, str]] = []
    hole = w["turb"] + w["curr"]
    drivers: list[str] = []

    if sst is not None:
        a, b, c, d = SST_TRAP[species]
        mu = trapezoid(sst, a, b, c, d)
        if _shock(dataset):
            mu *= 0.5
            drivers.append(f"صدمة حرارية ΔT>{SHOCK_DROP_C:.0f}°")
        measured.append((mu, w["temp"], f"حرارة {sst:.1f}°م ذروة {b:.0f}-{c:.0f}"))
    else:
        hole += w["temp"]

    n = len(open_hours)
    twilight = sum(1 for h in open_hours if h.derived.is_twilight) / n
    night = sum(1 for h in open_hours if h.derived.is_night and not h.derived.is_twilight) / n
    day = max(0.0, 1.0 - twilight - night)
    chop = wind is not None and CHOP_WIND_MIN_KMH <= wind <= CHOP_WIND_MAX_KMH
    month = dataset.target_date.month
    summer_hot = sst is not None and sst >= 26.0 and month in {7, 8}
    dusk = (
        sum(
            1
            for h in open_hours
            if h.time.hour >= 18 or (h.derived.is_twilight and h.time.hour >= 12)
        )
        / n
    )
    dawn = sum(1 for h in open_hours if 4 <= h.time.hour < 8) / n
    if species == TargetSpecies.EUROPEAN_SEABASS:
        mu_l = 0.35 * day + 1.0 * twilight + 0.75 * night
    elif species == TargetSpecies.WHITE_SEABREAM:
        mu_l = 0.55 * day + 1.0 * twilight + 0.40 * night
    else:
        mu_l = 0.50 * day + 0.90 * twilight + 0.55 * night
    if chop and day > 0.4:
        mu_l = min(1.0, mu_l * 1.12)
    if summer_hot and dusk > dawn:
        mu_l = min(1.0, mu_l * 1.30)
    elif summer_hot and dawn > dusk:
        mu_l *= 0.70
    measured.append((mu_l, w["light"], "ضوء من شروق/غروب النموذج"))

    if gabes:
        rising = sum(1 for h in open_hours if h.derived.tide_state == TideState.RISING)
        falling = sum(1 for h in open_hours if h.derived.tide_state == TideState.FALLING)
        slack = sum(1 for h in open_hours if h.derived.tide_state == TideState.SLACK)
        known = rising + falling + slack
        if known:
            if species in {TargetSpecies.GILTHEAD_SEABREAM, TargetSpecies.STRIPED_SEABREAM}:
                mu_c = (1.0 * rising + 0.55 * falling + 0.70 * slack) / n
            else:
                mu_c = (0.85 * rising + 0.70 * falling + 0.75 * slack) / n
            measured.append((min(1.0, mu_c), w["tide"], "مد قابس من مستوى البحر النموذجي"))
        else:
            hole += w["tide"]
    else:
        hole += w["tide"]

    profile = SPECIES_PROFILES[species]
    zone = tunisian_zone(dataset.location.latitude, dataset.location.longitude)
    presence = profile.monthly_presence(zone, month)
    if presence is not None:
        mu_s = {0: 0.25, 1: 0.45, 2: 0.75, 3: 1.0}[presence]
        measured.append((mu_s, w["season"], f"حضور موسمي مستوى {presence}"))
    else:
        hole += w["season"]

    coverage = 1.0 - hole
    coverage_pct = round(100.0 * max(0.0, min(1.0, coverage)))
    reliability = _reliability_ar(coverage)
    if coverage < MIN_COVERAGE or not measured:
        return None, ["تغطية الحقول المقيسة دون العتبة — لا رقم"], coverage_pct, reliability

    weight_sum = sum(item[1] for item in measured)
    activity = 1.0
    for mu, weight, note in measured:
        activity *= max(0.05, mu) ** (weight / weight_sum)
        drivers.append(f"{note} μ={mu:.2f}")

    if species == TargetSpecies.EUROPEAN_SEABASS and wave is not None:
        if HS_FEED_MIN_M <= wave <= HS_FEED_MAX_M:
            activity *= 1.3
            drivers.append(f"Hs {wave:.2f} م داخل 0.5-1.2")
        elif wave >= HS_STORM_M:
            activity *= 0.55
            drivers.append(f"Hs {wave:.2f} م فوق 1.5")

    if species == TargetSpecies.EUROPEAN_SEABASS and _after_storm(dataset, open_hours):
        activity *= AFTER_STORM_MULT
        drivers.append("بعد هياج ≥1.5 م ثم 0.5-1.2 م x1.5")

    score = round(100.0 * min(1.0, activity))
    return max(0, min(100, score)), drivers[:6], coverage_pct, reliability


def build_forecasts(
    dataset: ForecastDataset, open_hours: Sequence[HourDecision]
) -> tuple[str, list[SpeciesForecast]]:
    if not open_hours:
        empty = [
            SpeciesForecast(
                species=sp.value,
                label_ar=SPECIES_PROFILES[sp].label_ar,
                score=None,
                mode_ar="لا جلسة",
                drivers_ar=[],
                bait_ar=BAIT_BY_SPECIES[sp][0],
                coverage_pct=0,
                reliability_ar="لا ساعات مفتوحة",
                unknowns_ar=list(UNKNOWN_AR),
            )
            for sp in FORECAST_SPECIES
        ]
        return "لا توقع نشاط: لا ساعات بلا موانع محسوبة.", empty

    gabes = in_gabes_zone(dataset.location.latitude, dataset.location.longitude)
    rows: list[SpeciesForecast] = []
    for sp in FORECAST_SPECIES:
        score, drivers, coverage_pct, reliability = score_species(sp, open_hours, dataset)
        rows.append(
            SpeciesForecast(
                species=sp.value,
                label_ar=SPECIES_PROFILES[sp].label_ar,
                score=score,
                mode_ar=feeding_mode_ar(sp, open_hours, gabes) if score is not None else "لا رقم",
                drivers_ar=drivers,
                bait_ar=BAIT_BY_SPECIES[sp][0],
                coverage_pct=coverage_pct,
                reliability_ar=reliability,
                unknowns_ar=list(UNKNOWN_AR),
            )
        )
    ranked = sorted(rows, key=lambda row: (row.score is not None, row.score or 0), reverse=True)
    top = next((row for row in ranked if row.score is not None), None)
    if top is None:
        headline = "لا رقم نشاط: تغطية الحقول المقيسة غير كافية."
    else:
        headline = (
            f"الأعلى نسبياً (تغطية {top.coverage_pct}%): {top.label_ar} ({top.score}/100) — {top.mode_ar}. "
            f"{top.reliability_ar}."
        )
    return headline, ranked
