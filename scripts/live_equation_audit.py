#!/usr/bin/env python3
"""Live equation audit: inventory + reference cross-check + live-data verification.

Every physics/astronomy formula in the engine is checked three ways:
  1. exact-value checks against published references (physics constants, NOAA
     solar algorithm, published 2026 ephemeris, Metcheck sunrise/sunset),
  2. internal-identity checks (components vs magnitude, recomputed proxies),
  3. live plausibility + end-to-end consistency on real Open-Meteo data.

Policy thresholds (safety caution/no-go, species availability weights) are
*not* physics: they are inventoried separately (see docs) and marked as
CALIBRATION - they can only be validated with field data, never from a formula.

Run:
    PYTHONPATH=apps/api:apps/api/src python scripts/live_equation_audit.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api", "src"))

from spotdata.domain import math as M
from spotdata.domain.enums import TideState, WaveIncidence, WindRelation

TUNIS = ZoneInfo("Africa/Tunis")
API_URL = os.environ.get("PECHE_TN_API_URL", "http://127.0.0.1:8000")

G = 9.80665
RHO_AIR = 1.225

RESULTS: list[dict] = []


def record(category: str, name: str, ok: bool, detail: str, ref: str = "") -> None:
    RESULTS.append(
        {
            "category": category,
            "name": name,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
            "reference": ref,
        }
    )


def approx(actual: float, expected: float, tol: float) -> bool:
    return abs(actual - expected) <= tol


# ─────────────────────────────────────────────────────────────────────────────
# A. Units & conversions
# ─────────────────────────────────────────────────────────────────────────────
def check_units() -> None:
    record(
        "الوحدات",
        "knots → km/h (1.852)",
        approx(M.knots_to_kmh(10.0), 18.52, 1e-9),
        f"10 knots = {M.knots_to_kmh(10.0)} km/h",
        "1 knot = 1.852 km/h بالتعريف",
    )
    record(
        "الوحدات",
        "km/h → knots (عكس)",
        approx(M.kmh_to_knots(18.52), 10.0, 1e-9),
        f"18.52 km/h = {M.kmh_to_knots(18.52)} knots",
        "عكس التحويل الأول",
    )
    record(
        "الوحدات",
        "km/h → m/s (÷3.6)",
        approx(M.kmh_to_mps(36.0), 10.0, 1e-9),
        f"36 km/h = {M.kmh_to_mps(36.0)} m/s",
        "1 m/s = 3.6 km/h بالتعريف",
    )


# ─────────────────────────────────────────────────────────────────────────────
# B. Direction conventions (from vs toward)
# ─────────────────────────────────────────────────────────────────────────────
def check_conventions() -> None:
    record(
        "الاصطلاحات",
        "ريح من اتجاه البحر = بحرية (ONSHORE)",
        M.classify_wind(90.0, 90.0)[0] == WindRelation.ONSHORE,
        f"ريح من 90° على شاطئ 90° => {M.classify_wind(90.0, 90.0)[0].value}",
        "Open-Meteo: wind_direction = جهة القدوم",
    )
    record(
        "الاصطلاحات",
        "ريح من البر = برّية (OFFSHORE)",
        M.classify_wind(270.0, 90.0)[0] == WindRelation.OFFSHORE,
        f"ريح من 270° => {M.classify_wind(270.0, 90.0)[0].value}",
        "عكس اتجاه البحر 180°",
    )
    record(
        "الاصطلاحات",
        "موج من اتجاه البحر = DIRECT",
        M.classify_wave(90.0, 90.0)[0] == WaveIncidence.DIRECT,
        f"موج من 90° => {M.classify_wave(90.0, 90.0)[0].value}",
        "Open-Meteo: wave_direction = جهة القدوم",
    )
    record(
        "الاصطلاحات",
        "موج من البر = INCONSISTENT",
        M.classify_wave(270.0, 90.0)[0] == WaveIncidence.INCONSISTENT,
        f"موج من 270° => {M.classify_wave(270.0, 90.0)[0].value}",
        "|Δ| > 110°",
    )
    # project_current: cross_shore positive = seaward (toward convention)
    _, cross = M.project_current(1.0, 90.0, 90.0)
    record(
        "الاصطلاحات",
        "تيار نحو اتجاه البحر => cross=+1 (بحراً)",
        approx(cross, 1.0, 1e-9),
        f"تيار نحو 90° => cross_shore={cross}",
        "Open-Meteo: ocean_current_direction = جهة الذهاب",
    )
    _, cross_back = M.project_current(1.0, 270.0, 90.0)
    record(
        "الاصطلاحات",
        "تيار نحو الشاطئ => cross=-1 (شاطئاً)",
        approx(cross_back, -1.0, 1e-9),
        f"تيار نحو 270° => cross_shore={cross_back}",
        "نفس الاصطلاح معكوساً",
    )
    sh, al = M.incoming_direction_signed_components(10.0, 90.0, 90.0)
    record(
        "الاصطلاحات",
        "مركبة الريح الشاطئية = v·cosΔ",
        approx(sh, 10.0, 1e-9) and approx(al, 0.0, 1e-9),
        f"ريح 10 كم/س من 90° => shoreward={sh}, along={al}",
        "إسقاط متجه قياسي",
    )
    sh2, _ = M.incoming_direction_signed_components(10.0, 270.0, 90.0)
    record(
        "الاصطلاحات",
        "ريح برّية => shoreward سالب",
        approx(sh2, -10.0, 1e-9),
        f"ريح 10 كم/س من 270° => shoreward={sh2}",
        "cos(180°) = -1",
    )
    record(
        "الاصطلاحات",
        "فرق دائري 350°↔10° = 20° (وليس 340°)",
        approx(M.circular_difference_deg(350.0, 10.0), 20.0, 1e-9),
        f"circular_difference = {M.circular_difference_deg(350.0, 10.0)}",
        "الفرق الأقصر دائرياً",
    )
    record(
        "الاصطلاحات",
        "فرق موقّع يلتف عبر ±180",
        approx(M.signed_difference_deg(10.0, 350.0), 20.0, 1e-9)
        and approx(M.signed_difference_deg(350.0, 10.0), -20.0, 1e-9),
        f"10-350 = {M.signed_difference_deg(10.0, 350.0)}",
        "في [-180, 180)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# C. Wave physics (linear theory)
# ─────────────────────────────────────────────────────────────────────────────
def check_wave_physics() -> None:
    L0 = M.deep_water_wavelength_m(6.0)
    record(
        "فيزياء الموج",
        "طول الموجة العميقة L0 = gT²/2π",
        approx(L0, 56.19, 0.01),
        f"T=6s => L0 = {L0:.3f} م",
        "g·36/(2π) = 56.19 م",
    )
    steep = M.deep_water_wave_steepness(1.0, 6.0)
    record(
        "فيزياء الموج",
        "الانحدار Hs/L0",
        approx(steep, 1.0 / 56.19, 1e-4),
        f"Hs=1, T=6 => {steep:.5f}",
        "1/56.19",
    )
    omega = 2.0 * math.pi / 6.0
    for depth in (1.5, 10.0, 50.0):
        k = M.dispersion_wavenumber(omega, depth)
        lhs = G * k * math.tanh(k * depth)
        record(
            "فيزياء الموج",
            f"معادلة التشتت ω²=g·k·tanh(kh) عند h={depth}m",
            approx(lhs, omega**2, 1e-9),
            f"g·k·tanh(kh) = {lhs:.6f} vs ω² = {omega**2:.6f}",
            "العلاقة التشتتية القياسية",
        )
    # Ub uses Hrms = Hs/√2 (Rayleigh), so the reference must match that.
    k15 = M.dispersion_wavenumber(2 * math.pi / 6.0, 1.5)
    ub_ref = math.pi * (0.6 / math.sqrt(2.0)) / (6.0 * math.sinh(k15 * 1.5))
    ub = M.near_bottom_orbital_velocity_ms(0.6, 6.0, 1.5)
    record(
        "فيزياء الموج",
        "Ub = π·Hrms/(T·sinh(kh)) مع Hrms=Hs/√2",
        approx(ub, ub_ref, 1e-9),
        f"Ub = {ub:.4f} م/ث (مرجع {ub_ref:.4f})",
        "حل النظرية الخطية بفرض رايلي",
    )
    record(
        "فيزياء الموج",
        "وكيل طاقة الموج H²T",
        approx(M.wave_energy_proxy(2.0, 8.0), 32.0, 1e-9),
        f"H=2,T=8 => {M.wave_energy_proxy(2.0, 8.0)}",
        "∝ P=(rho·g²/64π)·Hs²·T",
    )
    a45 = M.alongshore_wave_proxy(1.0, 6.0, 135.0, 90.0)
    a0 = M.alongshore_wave_proxy(1.0, 6.0, 90.0, 90.0)
    a90 = M.alongshore_wave_proxy(1.0, 6.0, 180.0, 90.0)
    record(
        "فيزياء الموج",
        "جرّ جانبي ∝ sin(2alpha): أعظمي عند 45° وصفر عند 0/90",
        a45 > 0 and approx(a0, 0.0, 1e-9) and approx(a90, 0.0, 1e-9),
        f"alpha=45° => {a45:.3f} · alpha=0° => {a0:.3f} · alpha=90° => {a90:.3f}",
        "صيغة إجهاد الإشعاع Sxy",
    )
    share = M.secondary_wave_energy_share(1.0, 1.0)
    record(
        "فيزياء الموج",
        "حصة النظام الثانوي (طاقتان متساويتان = 0.5)",
        approx(share, 0.5, 1e-9),
        f"share = {share}",
        "طاقة ∝ H²",
    )


# ─────────────────────────────────────────────────────────────────────────────
# D. Wind stress & directional statistics
# ─────────────────────────────────────────────────────────────────────────────
def check_wind() -> None:
    cd = M.neutral_wind_drag_coefficient(10.0)
    tau = M.wind_stress_pa(36.0)  # 36 km/h = 10 m/s
    tau_ref = RHO_AIR * cd * 100.0
    record(
        "الريح",
        "إجهاد الريح τ = rho·Cd·U²",
        approx(tau, tau_ref, 1e-9),
        f"U=10 m/s => τ = {tau:.4f} Pa (مرجع {tau_ref:.4f})",
        "معادلة السحب القياسية",
    )
    cds = [M.neutral_wind_drag_coefficient(u) for u in (3.0, 10.0, 25.0)]
    record(
        "الريح",
        "معامل السحب Cd ضمن المجال الفيزيائي (0.0008-0.003)",
        all(0.0008 <= c <= 0.003 for c in cds),
        f"Cd(3,10,25) = {[f'{c:.5f}' for c in cds]}",
        "قيم منشورة لـ Cd فوق البحر",
    )
    r, n = M.weighted_directional_coherence([(10.0, 90.0), (12.0, 90.0), (11.0, 90.0)])
    record(
        "الريح",
        "تماسك الاتجاه R=1 عند اتساق كامل",
        approx(r, 1.0, 1e-9) and n == 3,
        f"R = {r} (n={n})",
        "R=|ΣUe^{iθ}|/ΣU",
    )
    mean, _ = M.dominant_wind_direction_deg([(10.0, 0.0), (10.0, 90.0), (10.0, 0.0), (10.0, 90.0)])
    record(
        "الريح",
        "المتوسط الدائري الموزون بالسرعة (0°/90° متناظر = 45°)",
        approx(mean, 45.0, 1e-9),
        f"متوسط (0°,90°) = {mean}°",
        "atan2 للمجموع المتجهي",
    )
    gf = M.gust_factor(20.0, 30.0)
    gf_calm = M.gust_factor(3.0, 30.0)
    record(
        "الريح",
        "معامل الهبة = هبة/مستمرة (وحجب قرب الهدوء)",
        approx(gf, 1.5, 1e-9) and gf_calm is None,
        f"gust_factor(20,30) = {gf} · (3,30) = {gf_calm}",
        "نسبة بسيطة تُحجب تحت عتبة الاستقرار",
    )


# ─────────────────────────────────────────────────────────────────────────────
# E. Astronomy (external published references)
# ─────────────────────────────────────────────────────────────────────────────
def check_astronomy() -> None:
    new_phase = M.moon_phase_fraction(date(2026, 9, 11))
    full_phase = M.moon_phase_fraction(date(2026, 9, 26))
    record(
        "الفلك",
        "القمر الجديد 11 سبتمبر 2026 (phase ≈ 0)",
        (new_phase < 0.03) or (new_phase > 0.97),
        f"phase(11/9) = {new_phase:.4f}",
        "starwalk.space: قمر جديد 11/9 03:27 UTC",
    )
    record(
        "الفلك",
        "البدر 26 سبتمبر 2026 (phase ≈ 0.5)",
        0.45 <= full_phase <= 0.55,
        f"phase(26/9) = {full_phase:.4f}",
        "starwalk.space: بدر 26/9 16:49 UTC",
    )
    ill_new = M.moon_illumination(date(2026, 9, 11))
    ill_full = M.moon_illumination(date(2026, 9, 26))
    record(
        "الفلك",
        "إضاءة القمر: محاق ≈ 0% وبدر ≈ 100%",
        ill_new < 0.05 and ill_full > 0.95,
        f"illumination(11/9) = {ill_new:.3f} · (26/9) = {ill_full:.3f}",
        "النموذج الجيومتري",
    )
    mr, ev = M.solar_twilight_times(date(2026, 9, 15), 36.819, 10.166, TUNIS, altitude_deg=-0.833)
    mr_min = mr.hour * 60 + mr.minute
    ev_min = ev.hour * 60 + ev.minute
    record(
        "الفلك",
        "الشروق مطابق للمرجع (06:02)",
        abs(mr_min - (6 * 60 + 2)) <= 3,
        f"المحرك: {mr.strftime('%H:%M')} · المرجع Metcheck: 06:02",
        "Metcheck Tunis 2026-09-15 (alt=-0.833°)",
    )
    record(
        "الفلك",
        "الغروب مطابق للمرجع (18:30 ±5د)",
        abs(ev_min - (18 * 60 + 30)) <= 5,
        f"المحرك: {ev.strftime('%H:%M')} · المرجع Metcheck: 18:30",
        "فرق الانكسار النموذجي ≤ 5 دقائق",
    )
    noon = datetime(2026, 9, 15, 12, 0, tzinfo=TUNIS)
    midnight = datetime(2026, 9, 15, 0, 0, tzinfo=TUNIS)
    el_noon = M.solar_elevation_deg(noon, 36.819, 10.166)
    el_mid = M.solar_elevation_deg(midnight, 36.819, 10.166)
    record(
        "الفلك",
        "ارتفاع الشمس: موجب ظهراً وسالب منتصف الليل",
        el_noon > 40 and el_mid < 0,
        f"ظهراً {el_noon:.1f}° · منتصف الليل {el_mid:.1f}°",
        "NOAA/Michalsky",
    )


# ─────────────────────────────────────────────────────────────────────────────
# F. Tides (synthetic ground truth)
# ─────────────────────────────────────────────────────────────────────────────
def _synthetic_hours() -> list:
    from spotdata.domain.models import ForecastHour

    start = datetime(2026, 9, 15, 0, tzinfo=TUNIS)
    hours = []
    for i in range(48):
        t = start + timedelta(hours=i)
        sl = 0.8 * math.sin(2 * math.pi * i / 12.42)
        hours.append(
            ForecastHour(
                time=t,
                wind_speed_kmh=10.0,
                wind_gust_kmh=14.0,
                wind_direction_deg=90.0,
                wave_height_m=0.6,
                wave_period_s=6.0,
                wave_direction_deg=90.0,
                wind_wave_height_m=0.4,
                wind_wave_period_s=5.0,
                wind_wave_direction_deg=90.0,
                swell_height_m=0.4,
                swell_period_s=8.0,
                swell_direction_deg=90.0,
                sea_surface_temperature_c=24.0,
                ocean_current_velocity_kmh=0.4,
                ocean_current_direction_deg=0.0,
                sea_level_height_msl_m=round(sl, 4),
                air_temperature_c=24.0,
                apparent_temperature_c=24.0,
                relative_humidity_pct=65.0,
                dew_point_c=17.0,
                cloud_cover_pct=20.0,
                shortwave_radiation_wm2=300.0,
                uv_index=4.0,
                lightning_potential_jkg=0.0,
                cape_jkg=50.0,
                precipitation_mm=0.0,
                precipitation_probability_pct=5.0,
                weather_code=1,
                pressure_msl_hpa=1014.0,
                visibility_m=20000.0,
            )
        )
    return hours


def check_tides() -> None:
    hours = _synthetic_hours()
    rates = M.sea_level_rates(hours)
    peak = max(abs(r) for r in rates if r is not None)
    record(
        "المد",
        "معدل مستوى البحر = مشتقة السلسلة (ذروة جيبية)",
        approx(peak, 2 * math.pi * 0.8 / 12.42, 0.05),
        f"أقصى معدل {peak:.3f} م/س (مرجع نظري {2 * math.pi * 0.8 / 12.42:.3f})",
        "dh/dt بفروق مركزية",
    )
    states = M.tide_states(hours, date(2026, 9, 15))
    bad = 0
    for (state, _rate, _idx), r in zip(states, rates, strict=True):
        if state == TideState.RISING and not (r is not None and r > 0):
            bad += 1
        if state == TideState.FALLING and not (r is not None and r < 0):
            bad += 1
        if state == TideState.SLACK and not (r is None or abs(r) <= 0.1):
            bad += 1
    record(
        "المد",
        "تصنيف المد (صاعد/هابط/ركود) مطابق للمشتقة",
        bad == 0,
        f"{len(states)} ساعة مصنفة · مخالفات {bad}",
        "إشارة المشتقة مع عتبة ركود",
    )
    events = M.detect_tide_events(hours, date(2026, 9, 15))
    highs = [e for e in events if e.kind == "high"]
    lows = [e for e in events if e.kind == "low"]
    record(
        "المد",
        "كشف قمم/قيعان المد (48س جيبية => قمتان وقاعان)",
        len(highs) == 2 and len(lows) == 2,
        f"قمم {len(highs)} · قيعان {len(lows)}",
        "منعطفات الجيبية بفترة 12.42س",
    )
    ranges = M.daily_sea_level_ranges(hours)
    r15 = ranges.get(date(2026, 9, 15))
    record(
        "المد",
        "مدى المد اليومي ≈ سعة المنحنى (~1.6 م)",
        r15 is not None and approx(r15, 1.6, 0.1),
        f"مدى {date(2026, 9, 15)} = {r15:.3f} م",
        "max - min لكل يوم",
    )
    kind, ratio, _ = M.classify_spring_neap(1.6, [1.0, 1.0, 1.0, 1.6])
    record(
        "المد",
        "تصنيف حيّة/مات حسب نسبة المدى (1.6/1.0 = حيّة)",
        kind == "spring" and ratio >= 1.3,
        f"تصنيف {kind} · نسبة {ratio}",
        "نسبة المدى إلى الوسيط",
    )


# ─────────────────────────────────────────────────────────────────────────────
# G. Geography
# ─────────────────────────────────────────────────────────────────────────────
def check_geography() -> None:
    cases = [
        ("بنزرت", 37.27, 9.87, "bizerte_tunis"),
        ("قليبية", 36.85, 11.12, "cap_bon_hammamet"),
        ("المنستير", 35.76, 10.83, "sahel"),
        ("قابس", 33.88, 10.10, "gabes"),
        ("جربة", 33.80, 10.85, "south"),
    ]
    for name, lat, lon, expected in cases:
        got = M.tunisian_zone(lat, lon)
        record(
            "الجغرافيا",
            f"منطقة {name} => {expected}",
            got == expected,
            f"tunisian_zone({lat},{lon}) = {got}",
            "الخريطة الساحلية التونسية",
        )
    record(
        "الجغرافيا",
        "منطقة قابس داخل نطاق المد العالي",
        M.in_gabes_zone(33.9, 10.1) and not M.in_gabes_zone(36.8, 10.2),
        "قابس داخل النطاق، تونس العاصمة خارجه",
        "خليج قابس",
    )


# ─────────────────────────────────────────────────────────────────────────────
# H. Live data plausibility (real Open-Meteo fetch)
# ─────────────────────────────────────────────────────────────────────────────
def check_live_plausibility(decision: dict) -> None:
    hours = decision.get("hourly", [])
    if not hours:
        record("البيانات الحية", "سحب قرار حي", False, "لا ساعات في الاستجابة", "API")
        return
    winds = [
        h["forecast"]["wind_speed_kmh"]
        for h in hours
        if h["forecast"]["wind_speed_kmh"] is not None
    ]
    waves = [
        h["forecast"]["wave_height_m"] for h in hours if h["forecast"]["wave_height_m"] is not None
    ]
    ssts = [
        h["forecast"]["sea_surface_temperature_c"]
        for h in hours
        if h["forecast"]["sea_surface_temperature_c"] is not None
    ]
    pres = [
        h["forecast"]["pressure_msl_hpa"]
        for h in hours
        if h["forecast"]["pressure_msl_hpa"] is not None
    ]
    uvs = [h["forecast"]["uv_index"] for h in hours if h["forecast"]["uv_index"] is not None]
    sls = [
        h["forecast"]["sea_level_height_msl_m"]
        for h in hours
        if h["forecast"]["sea_level_height_msl_m"] is not None
    ]
    record(
        "البيانات الحية",
        "ريح ضمن المجال الفيزيائي (0-60 كم/س)",
        bool(winds) and min(winds) >= 0 and max(winds) <= 60,
        f"الريح {min(winds):.1f}-{max(winds):.1f} كم/س",
        "حدود فيزيائية",
    )
    record(
        "البيانات الحية",
        "موج ضمن المجال الفيزيائي (0-8 م)",
        bool(waves) and min(waves) >= 0 and max(waves) <= 8,
        f"الموج {min(waves):.2f}-{max(waves):.2f} م",
        "حدود فيزيائية",
    )
    record(
        "البيانات الحية",
        "حرارة سطح البحر تونس سبتمبر (15-32°م)",
        bool(ssts) and min(ssts) >= 15 and max(ssts) <= 32,
        f"SST {min(ssts):.1f}-{max(ssts):.1f}°م",
        "المناخ المحلي",
    )
    record(
        "البيانات الحية",
        "الضغط ضمن المجال (950-1050 hPa)",
        bool(pres) and min(pres) >= 950 and max(pres) <= 1050,
        f"الضغط {min(pres):.1f}-{max(pres):.1f} hPa",
        "حدود فيزيائية",
    )
    record(
        "البيانات الحية",
        "الأشعة فوق البنفسجية ضمن (0-12)",
        bool(uvs) and min(uvs) >= 0 and max(uvs) <= 12,
        f"UV {min(uvs):.1f}-{max(uvs):.1f}",
        "حدود فيزيائية",
    )
    record(
        "البيانات الحية",
        "مستوى البحر ضمن (±1.5 م MSL)",
        bool(sls) and min(sls) >= -1.5 and max(sls) <= 1.5,
        f"SL {min(sls):.3f}-{max(sls):.3f} م",
        "حدود فيزيائية",
    )


# ─────────────────────────────────────────────────────────────────────────────
# I. End-to-end live internal consistency
# ─────────────────────────────────────────────────────────────────────────────
def check_live_consistency(decision: dict) -> None:
    hours = decision.get("hourly", [])
    if not hours:
        return
    worst = 0.0
    for h in hours:
        d = h.get("derived", {})
        spd = h["forecast"]["wind_speed_kmh"]
        sh = d.get("wind_shoreward_component_kmh")
        al = d.get("wind_alongshore_signed_component_kmh")
        if spd is not None and sh is not None and al is not None:
            worst = max(worst, abs(math.hypot(sh, al) - spd))
    record(
        "الاتساق الحي",
        "هوية المركبات: √(V⊥²+V∥²) = V",
        worst < 0.015,
        f"أكبر انحراف {worst:.2e} كم/س (ضمن تقريب خانتين)",
        "الإسقاط يحفظ المقدار؛ الانحراف من تقريب JSON",
    )
    hh = next(
        h
        for h in hours
        if h["forecast"]["wave_height_m"] is not None and h["forecast"]["wave_period_s"] is not None
    )
    proxy = hh["derived"].get("wave_energy_proxy")
    expect = hh["forecast"]["wave_height_m"] ** 2 * hh["forecast"]["wave_period_s"]
    record(
        "الاتساق الحي",
        "إعادة حساب H²T مطابقة للمشتق",
        proxy is not None and approx(proxy, expect, 0.001),
        f"proxy={proxy:.4f} vs {expect:.4f} (ضمن تقريب 4 خانات)",
        "H²·T",
    )
    # orbital velocity: monotonic decrease with depth (Ub ∝ 1/sinh(kh))
    max_hour = max(
        (
            h
            for h in hours
            if h["forecast"]["wave_height_m"] is not None
            and h["forecast"]["wave_period_s"] is not None
        ),
        key=lambda h: h["forecast"]["wave_height_m"],
    )
    hs, tp = max_hour["forecast"]["wave_height_m"], max_hour["forecast"]["wave_period_s"]
    ub_shallow = M.near_bottom_orbital_velocity_ms(hs, tp, 1.5)
    ub_deep = M.near_bottom_orbital_velocity_ms(hs, tp, 5.0)
    record(
        "الاتساق الحي",
        "السرعة المدارية تتناقص مع العمق",
        ub_shallow is not None and ub_deep is not None and ub_shallow >= ub_deep,
        f"Ub(1.5م)={ub_shallow:.3f} م/ث ≥ Ub(5م)={ub_deep:.3f} م/ث",
        "Ub ∝ 1/sinh(kh)",
    )
    b = decision["field_feasibility"].get("holding_breakdown")
    if b:
        band = b.get("orbital_velocity_band_ms")
        if band and " إلى " in band:
            parts = band.split(" إلى ")
            a, bb = float(parts[0]), float(parts[1])
            record(
                "الاتساق الحي",
                "نطاق السرعة المدارية مرتّب وبين قيمتي العمق",
                a <= bb and abs(a - ub_deep) < 0.05 and abs(bb - ub_shallow) < 0.05,
                f"النطاق {band} · المرجّع: {ub_deep:.2f}-{ub_shallow:.2f}",
                "يُبنى من Ub عند 5م و1.5م",
            )
    dirs = [(h["forecast"]["wind_speed_kmh"], h["forecast"]["wind_direction_deg"]) for h in hours]
    mean, _ = M.dominant_wind_direction_deg(dirs)
    sector_line = next(
        (f["value_ar"] for f in decision["factor_assessments"] if f["matrix_id"] == "1.11"), ""
    )
    ok = mean is not None and f"{mean:.0f}°" in sector_line
    record(
        "الاتساق الحي",
        "عامل [1.11] يحمل نفس المتوسط الدائري المعاد حسابه",
        ok,
        f"متوسط {mean:.0f}° في: {sector_line[:60]}…",
        "إعادة حساب مستقلة",
    )
    ff = decision["field_feasibility"]
    rank = {"unknown": 0, "low": 1, "moderate": 2, "high": 3}
    if b and b.get("dominant") not in ("none", None):
        dom_level = b.get(b["dominant"], "low")
        ok = rank[ff["holding_difficulty"]] >= rank[dom_level]
        record(
            "الاتساق الحي",
            "الخلاصة لا تقل عن آليتها الغالبة",
            ok,
            f"خلاصة {ff['holding_difficulty']} · الغالبة {b['dominant']}={dom_level}",
            "قاعدة الشدة القصوى",
        )
    cap = next(
        (
            line
            for line in decision["confidence"]["breakdown_ar"]
            if "اكتمال المتغيرات" in line and "أفق التوقع" in line
        ),
        "",
    )
    record(
        "الاتساق الحي",
        "سطر أساس الثقة يعرض المكونات المرجّحة",
        bool(cap) and "الأساس" in cap,
        cap[:70] + "…",
        "نشر القاعدة للتدقيق",
    )


def pull_live_decision() -> dict | None:
    payload = {
        "location": {"latitude": 36.83, "longitude": 10.27, "name": "المرسى"},
        "target_date": "2026-09-15",
        "spot": {"seaward_orientation_deg": 90, "shore_type": "sandy"},
        "angler": {"target_species": "general", "session_hours": 3},
    }
    try:
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{API_URL}/api/v1/decisions/forecast", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        record("البيانات الحية", "الاتصال بالخادم الحي", False, str(exc), API_URL)
        return None


def main() -> int:
    print("=" * 78)
    print("جرد ومراجعة حية لكل المعادلات والترابطات - Peche TN")
    print("=" * 78)
    check_units()
    check_conventions()
    check_wave_physics()
    check_wind()
    check_astronomy()
    check_tides()
    check_geography()

    decision = pull_live_decision()
    if decision is not None:
        check_live_plausibility(decision)
        check_live_consistency(decision)

    by_cat: dict[str, list] = {}
    for r in RESULTS:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, items in by_cat.items():
        print(f"\n## {cat}")
        for it in items:
            mark = "✅" if it["status"] == "PASS" else "❌"
            print(f"  {mark} {it['name']}: {it['detail']}")
            if it["status"] == "FAIL" and it["reference"]:
                print(f"       المرجع: {it['reference']}")

    n_pass = sum(1 for r in RESULTS if r["status"] == "PASS")
    n_fail = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print("\n" + "=" * 78)
    print(f"النتيجة: {n_pass} نجاح · {n_fail} فشل · المجموع {len(RESULTS)}")
    print("=" * 78)
    with open("scripts/engine-experiments-results.json", "w", encoding="utf-8") as fh:
        json.dump(RESULTS, fh, ensure_ascii=False, indent=2)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
