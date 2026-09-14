from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, tzinfo

from .enums import TideState, WaveIncidence, WindRelation
from .models import ForecastHour, TideEvent


def circular_difference_deg(a: float, b: float) -> float:
    """Smallest unsigned angle between two bearings, in [0, 180]."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def signed_difference_deg(a: float, b: float) -> float:
    """Signed a-b angular difference, in [-180, 180)."""
    return (a - b + 180.0) % 360.0 - 180.0


def classify_wind(
    wind_from_deg: float | None, seaward_orientation_deg: float
) -> tuple[WindRelation, float | None]:
    """Classify meteorological wind direction relative to the shore normal.

    Wind direction is the bearing it comes *from*. A wind source aligned with the
    seaward bearing therefore blows onshore.
    """
    if wind_from_deg is None:
        return WindRelation.UNKNOWN, None
    signed = signed_difference_deg(wind_from_deg, seaward_orientation_deg)
    angle = abs(signed)
    if angle <= 30.0:
        return WindRelation.ONSHORE, signed
    if angle < 80.0:
        return WindRelation.CROSS_ONSHORE, signed
    if angle <= 100.0:
        return WindRelation.ALONGSHORE, signed
    if angle < 150.0:
        return WindRelation.CROSS_OFFSHORE, signed
    return WindRelation.OFFSHORE, signed


def incoming_direction_components(
    magnitude: float | None,
    source_from_deg: float | None,
    seaward_orientation_deg: float,
) -> tuple[float | None, float | None]:
    """Resolve an incoming wind/wave magnitude against the outward shore normal.

    `source_from_deg` follows the meteorological/ocean-wave "coming from" convention.
    The first component is positive when the source is seaward (therefore travelling
    towards shore) and negative when it comes from land. The second is the absolute
    alongshore magnitude retained for API compatibility. Bearings are clockwise from
    true north.
    """
    shoreward, alongshore_signed = incoming_direction_signed_components(
        magnitude, source_from_deg, seaward_orientation_deg
    )
    return shoreward, abs(alongshore_signed) if alongshore_signed is not None else None


def incoming_direction_signed_components(
    magnitude: float | None,
    source_from_deg: float | None,
    seaward_orientation_deg: float,
) -> tuple[float | None, float | None]:
    """Resolve an incoming travel vector into signed shore axes.

    The first component is positive towards shore. The second is positive along the
    declared alongshore bearing `(S + 90) mod 360`, where `S` is the seaward normal.
    Wind and wave bearings describe where they come *from*, so their travel vectors are
    reversed before projection; this is the source of the minus sign on `sin(delta)`.
    """
    if magnitude is None or source_from_deg is None:
        return None, None
    angle = math.radians(signed_difference_deg(source_from_deg, seaward_orientation_deg))
    shoreward = magnitude * math.cos(angle)
    alongshore = -magnitude * math.sin(angle)
    return shoreward, alongshore


def classify_wave(
    wave_from_deg: float | None, seaward_orientation_deg: float
) -> tuple[WaveIncidence, float | None]:
    """Classify the direction waves come from relative to the seaward shore normal."""
    if wave_from_deg is None:
        return WaveIncidence.UNKNOWN, None
    signed = signed_difference_deg(wave_from_deg, seaward_orientation_deg)
    angle = abs(signed)
    if angle <= 25.0:
        return WaveIncidence.DIRECT, signed
    if angle <= 70.0:
        return WaveIncidence.OBLIQUE, signed
    if angle <= 110.0:
        return WaveIncidence.ALONGSHORE, signed
    return WaveIncidence.INCONSISTENT, signed


def _julian_day(moment: datetime) -> float:
    """Julian day number of a UTC-aware moment (valid for the civil range)."""
    utc = moment.astimezone(UTC)
    year, month = utc.year, utc.month
    if month <= 2:
        year -= 1
        month += 12
    century_term = 2 - (year // 100) + (year // 100) // 4
    day_fraction = (utc.hour + utc.minute / 60.0 + utc.second / 3600.0) / 24.0
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + utc.day
        + century_term
        - 1524.5
        + day_fraction
    )


def _moon_elongation_deg(moment: datetime) -> float:
    """Moon-Sun elongation in degrees from the truncated Meeus low-precision series.

    Accuracy ≈0.1° (~15 minutes of phase timing) across 1900-2100. Convention:
    0° = new moon, 90° = first quarter, 180° = full moon, 270° = last quarter.
    The daily motion (~12.19°/day) is fast enough that a 0.1° error is sub-hour.
    """
    days_since_j2000 = _julian_day(moment) - 2451545.0
    sun_mean_long = 280.4592 + 0.98564736 * days_since_j2000
    sun_mean_anom = 357.5291 + 0.98560028 * days_since_j2000
    moon_mean_long = 218.3165 + 13.176396 * days_since_j2000
    moon_mean_anom = 134.9634 + 13.064993 * days_since_j2000
    moon_mean_elong = 297.8502 + 12.190749 * days_since_j2000
    moon_arg_lat = 93.2721 + 13.229350 * days_since_j2000
    sun_mean_anom_rad = math.radians(sun_mean_anom)
    sun_true_long = (
        sun_mean_long
        + 1.915 * math.sin(sun_mean_anom_rad)
        + 0.020 * math.sin(2.0 * sun_mean_anom_rad)
    )
    moon_true_long = (
        moon_mean_long
        + 6.288750 * math.sin(math.radians(moon_mean_anom))
        + 1.274018 * math.sin(math.radians(2.0 * moon_mean_elong - moon_mean_anom))
        + 0.658309 * math.sin(math.radians(2.0 * moon_mean_elong))
        + 0.213616 * math.sin(math.radians(2.0 * moon_mean_anom))
        - 0.185596 * math.sin(sun_mean_anom_rad)
        - 0.114336 * math.sin(math.radians(2.0 * moon_arg_lat))
    )
    return (moon_true_long - sun_true_long) % 360.0


def moon_phase_fraction(day: date) -> float:
    """Lunar phase fraction in [0, 1): 0 = new moon, 0.5 = full moon.

    Evaluated at 12:00 UTC of `day` (the representative instant for a civil
    date). Truncated Meeus series (~0.1° accuracy) — a real astronomical
    computation, never a solunar rule.
    """
    moment = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    return _moon_elongation_deg(moment) / 360.0


def moon_illumination(day: date) -> float:
    """Geometric Moon illumination fraction in [0, 1] (0 = new, 1 = full).

    Evaluated at 12:00 UTC of `day` from the truncated Meeus elongation series
    (≈0.1° accuracy). It feeds only a disclosed, low-weight night-light prior
    inside the reporting-only species activity indicator (the scientifically
    supported channel: moonlight helps nocturnal feeding sight). It is not a
    solunar rule and never touches the binary decision, any safety gate, or the
    spring/neap classification (D9).
    """
    elongation = _moon_elongation_deg(datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC))
    return (1.0 - math.cos(math.radians(elongation))) / 2.0


def solar_elevation_deg(moment: datetime, latitude: float, longitude: float) -> float:
    """Topocentric solar elevation in degrees (NOAA/Michalsky compact algorithm).

    Real astronomy (~0.01° accuracy for the civil range). Used only to derive
    true twilight windows and solar comfort context — never a decision input.
    """
    utc = moment.astimezone(UTC)
    year, month = utc.year, utc.month
    if month <= 2:
        year -= 1
        month += 12
    century_term = 2 - (year // 100) + (year // 100) // 4
    day_fraction = (utc.hour + utc.minute / 60.0 + utc.second / 3600.0) / 24.0
    jd = (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + utc.day
        + century_term
        - 1524.5
        + day_fraction
    )
    t = (jd - 2451545.0) / 36525.0  # Julian centuries since J2000
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    mean_anomaly_deg = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    m_rad = math.radians(mean_anomaly_deg)
    equation_of_center = (
        math.sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2.0 * m_rad) * (0.019993 - 0.000101 * t)
        + math.sin(3.0 * m_rad) * 0.000289
    )
    true_longitude = l0 + equation_of_center
    omega = 125.04 - 1934.136 * t
    apparent_longitude = true_longitude - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    mean_obliquity = (
        23.0 + 26.0 / 60.0 + (21.448 - t * (46.815 + t * (0.00059 - 0.001813 * t))) / 3600.0
    )
    obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(omega))
    obliquity_rad = math.radians(obliquity)
    apparent_longitude_rad = math.radians(apparent_longitude)
    declination = math.degrees(
        math.asin(math.sin(obliquity_rad) * math.sin(apparent_longitude_rad))
    )
    equation_of_time_min = 229.18 * (
        0.000075
        + 0.001868 * math.cos(m_rad)
        - 0.032077 * math.sin(m_rad)
        - 0.014615 * math.cos(2.0 * m_rad)
        - 0.040849 * math.sin(2.0 * m_rad)
    )
    minutes_of_day = utc.hour * 60.0 + utc.minute + utc.second / 60.0
    true_solar_time_min = (minutes_of_day + equation_of_time_min + 4.0 * longitude) % 1440.0
    hour_angle_deg = true_solar_time_min / 4.0 - 180.0
    latitude_rad = math.radians(latitude)
    declination_rad = math.radians(declination)
    hour_angle_rad = math.radians(hour_angle_deg)
    zenith = math.degrees(
        math.acos(
            math.sin(latitude_rad) * math.sin(declination_rad)
            + math.cos(latitude_rad) * math.cos(declination_rad) * math.cos(hour_angle_rad)
        )
    )
    return 90.0 - zenith


def _bisect_altitude_crossing(
    low: datetime, high: datetime, target_deg: float, latitude: float, longitude: float
) -> datetime | None:
    """Find the moment solar elevation crosses target_deg inside [low, high]."""
    low_value = solar_elevation_deg(low, latitude, longitude) - target_deg
    high_value = solar_elevation_deg(high, latitude, longitude) - target_deg
    if (low_value > 0.0) == (high_value > 0.0):
        return None
    left, right = low, high
    left_value = low_value
    for _ in range(60):
        mid = left + (right - left) / 2.0
        mid_value = solar_elevation_deg(mid, latitude, longitude) - target_deg
        if (mid_value > 0.0) == (left_value > 0.0):
            left, left_value = mid, mid_value
        else:
            right = mid
    return left + (right - left) / 2.0


def solar_twilight_times(
    day: date, latitude: float, longitude: float, tz: tzinfo, altitude_deg: float = -12.0
) -> tuple[datetime | None, datetime | None]:
    """True (morning, evening) crossing times of the given solar altitude.

    -12° = nautical twilight, -6° = civil twilight. Computed from real solar
    geometry (bisection over the local day), not a fixed ±N-minute rule.
    """
    local_start = datetime(day.year, day.month, day.day, tzinfo=tz)
    noon = local_start + timedelta(hours=12)
    end = local_start + timedelta(hours=24)
    morning = _bisect_altitude_crossing(local_start, noon, altitude_deg, latitude, longitude)
    evening = _bisect_altitude_crossing(noon, end, altitude_deg, latitude, longitude)
    return morning, evening


STANDARD_GRAVITY_M_S2 = 9.80665
STANDARD_AIR_DENSITY_KG_M3 = 1.225
MIN_DIRECTIONAL_WIND_KMH = 5.0
KMH_PER_KNOT = 1.852


def knots_to_kmh(value: float) -> float:
    return value * KMH_PER_KNOT


def kmh_to_knots(value: float) -> float:
    return value / KMH_PER_KNOT


def kmh_to_mps(value: float) -> float:
    return value / 3.6


def neutral_wind_drag_coefficient(wind_speed_mps: float | None) -> float | None:
    """Large-Pond-style neutral 10 m drag coefficient.

    `Cd=1.2e-3` from 4 to 11 m/s and `(0.49+0.065U)e-3` from 11 to 25 m/s.
    The nearest endpoint is held outside that documented interval rather than
    extrapolating the empirical relation. This is a diagnostic, not a replacement for
    the product's direct wind and gust safety limits.
    """
    if wind_speed_mps is None or wind_speed_mps < 0:
        return None
    bounded_speed = min(max(wind_speed_mps, 4.0), 25.0)
    if bounded_speed < 11.0:
        return 1.2e-3
    return (0.49 + 0.065 * bounded_speed) * 1e-3


def wind_stress_pa(
    wind_speed_kmh: float | None,
    *,
    air_density_kg_m3: float = STANDARD_AIR_DENSITY_KG_M3,
) -> float | None:
    """Return neutral wind-stress magnitude `rho_air * Cd * U10²`, in pascals."""
    if wind_speed_kmh is None or wind_speed_kmh < 0 or air_density_kg_m3 <= 0:
        return None
    speed_mps = kmh_to_mps(wind_speed_kmh)
    drag = neutral_wind_drag_coefficient(speed_mps)
    if drag is None:
        return None
    return air_density_kg_m3 * drag * speed_mps**2


def wind_stress_signed_components(
    wind_speed_kmh: float | None,
    wind_from_deg: float | None,
    seaward_orientation_deg: float,
) -> tuple[float | None, float | None, float | None]:
    """Return stress magnitude, shoreward stress and signed alongshore stress (Pa)."""
    stress = wind_stress_pa(wind_speed_kmh)
    shoreward, alongshore = incoming_direction_signed_components(
        stress, wind_from_deg, seaward_orientation_deg
    )
    return stress, shoreward, alongshore


def weighted_directional_coherence(
    observations: Iterable[tuple[float | None, float | None]],
    *,
    minimum_speed_kmh: float = MIN_DIRECTIONAL_WIND_KMH,
    minimum_samples: int = 3,
) -> tuple[float | None, int]:
    """Return speed-weighted circular resultant length R and valid sample count.

    Calm/missing samples are excluded because their bearings are unstable. `R` is in
    [0, 1]: one means aligned directions and zero means complete circular cancellation.
    At least three valid samples are required to avoid pretending one direction is a
    stable window statistic.
    """
    vectors = [
        (float(speed), math.radians(float(direction)))
        for speed, direction in observations
        if speed is not None
        and direction is not None
        and speed >= minimum_speed_kmh
        and math.isfinite(speed)
        and math.isfinite(direction)
    ]
    sample_count = len(vectors)
    if sample_count < minimum_samples:
        return None, sample_count
    weight = sum(speed for speed, _ in vectors)
    if weight <= 0:
        return None, sample_count
    x = sum(speed * math.cos(direction) for speed, direction in vectors)
    y = sum(speed * math.sin(direction) for speed, direction in vectors)
    return min(1.0, math.hypot(x, y) / weight), sample_count


def dominant_wind_direction_deg(
    observations: Iterable[tuple[float | None, float | None]],
    *,
    minimum_speed_kmh: float = MIN_DIRECTIONAL_WIND_KMH,
    minimum_samples: int = 3,
) -> tuple[float | None, int]:
    """Return the speed-weighted circular mean wind direction and sample count.

    Calm/missing samples are excluded (unstable bearings). Used to name the
    day's dominant wind sector honestly instead of a fixed template label
    (audit 2026-09-14: the "sustained southerly winds" factor name was applied
    without checking the actual direction).
    """
    vectors = [
        (float(speed), math.radians(float(direction)))
        for speed, direction in observations
        if speed is not None
        and direction is not None
        and speed >= minimum_speed_kmh
        and math.isfinite(speed)
        and math.isfinite(direction)
    ]
    sample_count = len(vectors)
    if sample_count < minimum_samples:
        return None, sample_count
    weight = sum(speed for speed, _ in vectors)
    if weight <= 0:
        return None, sample_count
    x = sum(speed * math.cos(direction) for speed, direction in vectors)
    y = sum(speed * math.sin(direction) for speed, direction in vectors)
    return math.degrees(math.atan2(y, x)) % 360.0, sample_count


def minimal_arc_extent_deg(bearings: list[float]) -> tuple[float, float]:
    """Return the (start, end) bearings of the smallest circular arc containing all.

    A plain min/max over degrees fails when bearings straddle 0° (e.g. 350° and
    10° are 20° apart, not 340°). This finds the largest angular gap between
    consecutive sorted bearings and returns the complementary arc, so the two
    endpoint sectors honestly span the wind's actual range of origin.
    """
    if not bearings:
        return 0.0, 0.0
    ordered = sorted(bearings)
    if len(ordered) == 1:
        return ordered[0], ordered[0]
    gaps = [
        ((ordered[(index + 1) % len(ordered)] - ordered[index]) % 360.0, index)
        for index in range(len(ordered))
    ]
    _gap_size, gap_before = max(gaps)
    start = ordered[(gap_before + 1) % len(ordered)]
    end = ordered[gap_before]
    return start, end


def deep_water_wavelength_m(period_s: float | None) -> float | None:
    """Return linear-wave deep-water wavelength gT²/(2π), in metres.

    This is only valid where depth is large relative to wavelength. It must not be
    presented as wavelength or breaking distance in the surf zone.
    """
    if period_s is None or period_s <= 0.5:
        return None
    return STANDARD_GRAVITY_M_S2 * period_s**2 / (2.0 * math.pi)


def deep_water_wave_steepness(height_m: float | None, period_s: float | None) -> float | None:
    """Return Hs/L0 using the linear-wave deep-water wavelength.

    This is a rough-water indicator, not a prediction of the shore-breaking wave.
    """
    wavelength = deep_water_wavelength_m(period_s)
    if height_m is None or wavelength is None:
        return None
    return height_m / wavelength


def dispersion_wavenumber(omega_rad_s: float | None, depth_m: float | None) -> float | None:
    """Solve the linear dispersion relation omega² = g·k·tanh(k·h) for k (rad/m).

    Newton iteration seeded from the deep-water value k = omega²/g. Used only for a
    transparent, low-confidence estimate of near-bed orbital motion; the local depth
    inside the surf zone is never actually known.
    """
    if omega_rad_s is None or depth_m is None or omega_rad_s <= 0 or depth_m <= 0:
        return None
    g = STANDARD_GRAVITY_M_S2
    k = omega_rad_s**2 / g
    for _ in range(80):
        kh = k * depth_m
        tanh_kh = math.tanh(kh)
        residual = g * k * tanh_kh - omega_rad_s**2
        sech_kh = 1.0 / math.cosh(kh)
        derivative = g * tanh_kh + g * kh * sech_kh * sech_kh
        if derivative <= 0:
            break
        step = residual / derivative
        candidate = k - step
        if candidate <= 0:
            candidate = k * 0.5
        if abs(candidate - k) <= 1e-10 * max(1.0, abs(k)):
            k = candidate
            break
        k = candidate
    return k


def near_bottom_orbital_velocity_ms(
    height_m: float | None, period_s: float | None, depth_m: float | None
) -> float | None:
    """Estimate the near-bed orbital velocity amplitude Ub = π·H / (T·sinh(k·h)).

    `height_m` is the significant wave height (Hs). A representative single-wave
    height for near-bed orbital motion is Hrms = Hs/√2 under a Rayleigh sea-state
    assumption, so the engine divides Hs by √2 before applying the monochromatic
    formula — otherwise the diagnostic would be inflated by the highest-third
    average (audit 2026-09-14, item B1).

    This is a linear-wave estimate at one assumed depth, not an observed surf-zone
    current; with no local bathymetry it is presented as a band across a declared
    depth range and must never gate the decision on its own.
    """
    if (
        height_m is None
        or period_s is None
        or depth_m is None
        or height_m < 0
        or period_s <= 0
        or depth_m <= 0
    ):
        return None
    omega = 2.0 * math.pi / period_s
    k = dispersion_wavenumber(omega, depth_m)
    if k is None:
        return None
    sinh_kh = math.sinh(k * depth_m)
    if sinh_kh <= 0:
        return None
    representative_height_m = height_m / math.sqrt(2.0)
    return math.pi * representative_height_m / (period_s * sinh_kh)


def gust_factor(
    sustained_wind_kmh: float | None,
    gust_kmh: float | None,
    *,
    minimum_sustained_kmh: float = MIN_DIRECTIONAL_WIND_KMH,
) -> float | None:
    """Return gust/sustained wind, avoiding unstable ratios near calm conditions."""
    if sustained_wind_kmh is None or gust_kmh is None or sustained_wind_kmh < minimum_sustained_kmh:
        return None
    return gust_kmh / sustained_wind_kmh


def wave_energy_proxy(height_m: float | None, period_s: float | None) -> float | None:
    """Relative deep-water energy-flux proxy proportional to Hs²*T.

    It intentionally omits physical constants because it is used only for ranking.
    """
    if height_m is None or period_s is None or period_s <= 0:
        return None
    return height_m**2 * period_s


def alongshore_wave_proxy(
    height_m: float | None,
    period_s: float | None,
    wave_from_deg: float | None,
    seaward_orientation_deg: float,
) -> float | None:
    """Return the legacy absolute relative alongshore forcing proxy.

    Bathymetry, breaking transformation and refraction are unavailable, so this must
    never be presented as a measured surf-zone current or physical transport rate.
    """
    signed = alongshore_wave_signed_proxy(
        height_m, period_s, wave_from_deg, seaward_orientation_deg
    )
    return abs(signed) if signed is not None else None


def alongshore_wave_signed_proxy(
    height_m: float | None,
    period_s: float | None,
    wave_from_deg: float | None,
    seaward_orientation_deg: float,
) -> float | None:
    """Return signed `H²T sin(2*alpha)` along the `(S+90) mod 360` axis.

    This is the radiation-stress (S_xy) form, not a direct alongshore speed: it is
    zero for a perfectly alongshore wave (alpha = 90°) and maximal near 45°
    incidence, where the cross-shore gradient of alongshore momentum is largest.
    The sign convention follows the incoming travel vector: a wave source clockwise
    from the seaward normal travels along the negative tangent, hence `-sin(2 delta)`.
    Only source directions within ±90° of the seaward normal are geometrically retained.
    """
    energy = wave_energy_proxy(height_m, period_s)
    if energy is None or wave_from_deg is None:
        return None
    alpha_deg = signed_difference_deg(wave_from_deg, seaward_orientation_deg)
    if abs(alpha_deg) > 90.0:
        return None
    return -energy * math.sin(math.radians(2.0 * alpha_deg))


def secondary_wave_energy_share(
    wind_wave_height_m: float | None,
    swell_height_m: float | None,
) -> float | None:
    """Return weaker-system `H²` share, in [0, 0.5], without inventing a composite index."""
    if (
        wind_wave_height_m is None
        or swell_height_m is None
        or wind_wave_height_m < 0
        or swell_height_m < 0
    ):
        return None
    wind_energy = wind_wave_height_m**2
    swell_energy = swell_height_m**2
    total = wind_energy + swell_energy
    if total <= 0:
        return None
    return min(wind_energy, swell_energy) / total


def project_current(
    velocity_kmh: float | None,
    current_towards_deg: float | None,
    seaward_orientation_deg: float,
) -> tuple[float | None, float | None]:
    """Project a current vector into alongshore and cross-shore components.

    Cross-shore is positive seaward and negative shoreward. Alongshore is positive on
    the declared `(S + 90) mod 360` tangent; both signed components are exposed.
    """
    if velocity_kmh is None or current_towards_deg is None:
        return None, None
    angle = math.radians(signed_difference_deg(current_towards_deg, seaward_orientation_deg))
    cross_shore = velocity_kmh * math.cos(angle)
    alongshore = velocity_kmh * math.sin(angle)
    return alongshore, cross_shore


def _hours_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def sea_level_rates(hours: list[ForecastHour]) -> list[float | None]:
    """Central finite-difference rate for modelled sea level (m/h)."""
    rates: list[float | None] = [None] * len(hours)
    for index, item in enumerate(hours):
        previous = next(
            (
                hours[j]
                for j in range(index - 1, -1, -1)
                if hours[j].sea_level_height_msl_m is not None
            ),
            None,
        )
        following = next(
            (
                hours[j]
                for j in range(index + 1, len(hours))
                if hours[j].sea_level_height_msl_m is not None
            ),
            None,
        )
        current_level = item.sea_level_height_msl_m
        previous_level = previous.sea_level_height_msl_m if previous is not None else None
        following_level = following.sea_level_height_msl_m if following is not None else None
        if (
            previous is not None
            and previous_level is not None
            and following is not None
            and following_level is not None
        ):
            elapsed = _hours_between(previous.time, following.time)
            if elapsed > 0:
                rates[index] = (following_level - previous_level) / elapsed
        elif current_level is not None and previous is not None and previous_level is not None:
            elapsed = _hours_between(previous.time, item.time)
            if elapsed > 0:
                rates[index] = (current_level - previous_level) / elapsed
        elif current_level is not None and following is not None and following_level is not None:
            elapsed = _hours_between(item.time, following.time)
            if elapsed > 0:
                rates[index] = (following_level - current_level) / elapsed
    return rates


def tide_states(
    hours: list[ForecastHour], target_date: date
) -> list[tuple[TideState, float | None, float | None]]:
    """Classify modelled sea-level movement without inventing astronomical tide times."""
    rates = sea_level_rates(hours)
    target_levels = [
        item.sea_level_height_msl_m
        for item in hours
        if item.time.date() == target_date and item.sea_level_height_msl_m is not None
    ]
    target_rates = [
        abs(rate)
        for item, rate in zip(hours, rates, strict=True)
        if item.time.date() == target_date and rate is not None
    ]
    if not target_levels or not target_rates:
        return [(TideState.UNKNOWN, rate, None) for rate in rates]

    level_range = max(target_levels) - min(target_levels)
    max_rate = max(target_rates)
    # A floor avoids labelling numerical interpolation noise as meaningful movement.
    slack_rate = max(0.005, level_range * 0.02)
    result: list[tuple[TideState, float | None, float | None]] = []
    for rate in rates:
        if rate is None:
            result.append((TideState.UNKNOWN, None, None))
            continue
        movement_index = min(1.0, abs(rate) / max(max_rate, 1e-9))
        if abs(rate) <= slack_rate or movement_index < 0.12:
            state = TideState.SLACK
        elif rate > 0:
            state = TideState.RISING
        else:
            state = TideState.FALLING
        result.append((state, rate, movement_index))
    return result


def detect_tide_events(hours: list[ForecastHour], target_date: date) -> list[TideEvent]:
    """Detect local extrema in modelled total sea-level height for display only."""
    points = [
        item
        for item in hours
        if item.time.date() == target_date and item.sea_level_height_msl_m is not None
    ]
    if len(points) < 3:
        return []

    candidates: list[tuple[str, ForecastHour]] = []
    for previous, current, following in zip(points, points[1:], points[2:], strict=False):
        p = previous.sea_level_height_msl_m
        c = current.sea_level_height_msl_m
        n = following.sea_level_height_msl_m
        if p is None or c is None or n is None:
            continue
        if c >= p and c > n:
            candidates.append(("high", current))
        elif c <= p and c < n:
            candidates.append(("low", current))

    # Hourly interpolation can produce adjacent duplicate extrema. Keep the most extreme
    # candidate of the same kind inside a three-hour cluster.
    collapsed: list[tuple[str, ForecastHour]] = []
    for kind, item in candidates:
        if (
            collapsed
            and collapsed[-1][0] == kind
            and _hours_between(collapsed[-1][1].time, item.time) <= 3.0
        ):
            previous_item = collapsed[-1][1]
            previous_level = previous_item.sea_level_height_msl_m
            current_level = item.sea_level_height_msl_m
            if previous_level is None or current_level is None:
                continue
            more_extreme = (kind == "high" and current_level > previous_level) or (
                kind == "low" and current_level < previous_level
            )
            if more_extreme:
                collapsed[-1] = (kind, item)
        else:
            collapsed.append((kind, item))

    disclaimer = "تقدير من نموذج بحري بدقة تقارب 8 كم؛ ليس جدول مدّ ملاحي وقد يخطئ قرب الساحل."
    return [
        TideEvent(
            time=item.time,
            kind=kind,
            level_msl_m=round(item.sea_level_height_msl_m or 0.0, 3),
            disclaimer_ar=disclaimer,
        )
        for kind, item in collapsed
    ]


# ─── Spring/neap classification from the modelled sea-level series (phase 5)

# Gulf of Gabès: the strongest Mediterranean tides (≈2.1-2.3 m at spring).
_GABES_LAT = (33.5, 34.9)
_GABES_LON = (9.7, 11.4)

SPRING_RATIO = 1.3
NEAP_RATIO = 0.7


def in_gabes_zone(latitude: float, longitude: float) -> bool:
    """Conservative bounding box for the high-tide Gulf of Gabès area."""
    return (
        _GABES_LAT[0] <= latitude <= _GABES_LAT[1] and _GABES_LON[0] <= longitude <= _GABES_LON[1]
    )


def daily_sea_level_ranges(hours: list[ForecastHour]) -> dict[date, float]:
    """Per-day peak-to-trough sea-level range from the modelled series."""
    by_day: dict[date, list[float]] = {}
    for item in hours:
        level = item.sea_level_height_msl_m
        if level is not None:
            by_day.setdefault(item.time.date(), []).append(level)
    return {
        day: round(max(values) - min(values), 3)
        for day, values in by_day.items()
        if len(values) >= 6
    }


def classify_spring_neap(
    target_range_m: float | None, all_ranges_m: list[float]
) -> tuple[str, float | None, float | None]:
    """Classify spring/neap from the actual daily range, never from moon phase.

    The target-day range is compared to the median daily range across the
    available model series: ratio >= 1.3 → spring (حيّة), <= 0.7 → neap (مات).
    """
    if target_range_m is None or not all_ranges_m:
        return "unknown", None, None
    reference = statistics.median(all_ranges_m)
    if reference <= 0:
        return "unknown", None, reference
    ratio = target_range_m / reference
    if ratio >= SPRING_RATIO:
        return "spring", round(ratio, 2), round(reference, 3)
    if ratio <= NEAP_RATIO:
        return "neap", round(ratio, 2), round(reference, 3)
    return "intermediate", round(ratio, 2), round(reference, 3)


# ─── Tunisian coastal zone classification (docs/SOURCES-AUDIT.md §1) ───
# Approximate linear thresholds along the coast: accurate enough to place a
# spot in its region, not a physical boundary of the gulfs.
def tunisian_zone(latitude: float, longitude: float) -> str:
    # The northwest (سراط) coast climbs past 37°N (Cap Serrat ~37.2°N, 9.0°E),
    # so longitude must be tested before the bizerte_tunis latitude band.
    if latitude >= 36.6 and longitude < 9.6:
        return "northwest"
    if latitude >= 36.6:
        # Cap Bon tip (Haouaria ~37.05°N) sits east of 10.6°E; the north
        # coast (Bizerte → Cap Farina) and the Gulf of Tunis are west of it.
        return "cap_bon_hammamet" if longitude >= 10.6 else "bizerte_tunis"
    if latitude >= 36.0:
        return "cap_bon_hammamet"
    if latitude >= 35.0:
        return "sahel"
    # Gulf of Gabès mainland (Sfax → Gabès) versus the Djerba/Zarzis south.
    # Djerba sits east of the Ajim channel and must not flip zone with a 0.01°
    # latitude step, so the gulf box is split into the mainland strip (lon <
    # 10.7) and the northern Sfax corner (lat >= 34.2, lon < 10.9).
    if (latitude >= 33.85 and longitude < 10.7) or (latitude >= 34.2 and longitude < 10.9):
        return "gabes"
    return "south"


def _moon_ra_dec_deg(moment: datetime) -> tuple[float, float]:
    """Moon geocentric right ascension and declination in degrees.

    Truncated Meeus low-precision series (the same 1900-2100 band as the phase
    series elsewhere in this module). Ecliptic longitude reuses the elongation
    series' major terms; ecliptic latitude keeps the four dominant terms of
    Meeus 47. Accuracy is on the order of ~0.3°, i.e. roughly a minute of
    transit timing — appropriate for a *reference* astronomical time, never a
    decision input.
    """
    days_since_j2000 = _julian_day(moment) - 2451545.0
    sun_mean_anom = 357.5291 + 0.98560028 * days_since_j2000
    moon_mean_long = 218.3165 + 13.176396 * days_since_j2000
    moon_mean_anom = 134.9634 + 13.064993 * days_since_j2000
    moon_mean_elong = 297.8502 + 12.190749 * days_since_j2000
    moon_arg_lat = 93.2721 + 13.229350 * days_since_j2000
    sun_mean_anom_rad = math.radians(sun_mean_anom)
    moon_lambda = (
        moon_mean_long
        + 6.288750 * math.sin(math.radians(moon_mean_anom))
        + 1.274018 * math.sin(math.radians(2.0 * moon_mean_elong - moon_mean_anom))
        + 0.658309 * math.sin(math.radians(2.0 * moon_mean_elong))
        + 0.213616 * math.sin(math.radians(2.0 * moon_mean_anom))
        - 0.185596 * math.sin(sun_mean_anom_rad)
        - 0.114336 * math.sin(math.radians(2.0 * moon_arg_lat))
    )
    moon_beta = (
        5.128 * math.sin(math.radians(moon_arg_lat))
        + 0.2806 * math.sin(math.radians(moon_mean_anom + moon_arg_lat))
        + 0.2777 * math.sin(math.radians(moon_mean_anom - moon_arg_lat))
        + 0.1732 * math.sin(math.radians(2.0 * moon_mean_elong - moon_arg_lat))
    )
    obliquity = 23.439291 - 0.0130042 * (days_since_j2000 / 36525.0)
    lambda_rad = math.radians(moon_lambda)
    beta_rad = math.radians(moon_beta)
    eps_rad = math.radians(obliquity)
    right_ascension = (
        math.degrees(
            math.atan2(
                math.sin(lambda_rad) * math.cos(eps_rad) - math.tan(beta_rad) * math.sin(eps_rad),
                math.cos(lambda_rad),
            )
        )
        % 360.0
    )
    declination = math.degrees(
        math.asin(
            math.sin(beta_rad) * math.cos(eps_rad)
            + math.cos(beta_rad) * math.sin(eps_rad) * math.sin(lambda_rad)
        )
    )
    return right_ascension, declination


def _gmst_deg(moment: datetime) -> float:
    """Greenwich mean sidereal time in degrees (Meeus 12.4)."""
    jd = _julian_day(moment)
    t = (jd - 2451545.0) / 36525.0
    return (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    ) % 360.0


def moon_transit_times(
    day: date,
    longitude: float,
    tz: tzinfo,
) -> tuple[datetime, datetime]:
    """Moon upper and lower meridian transits for a civil date (timezone-aware).

    Upper transit = the instant the Moon crosses the observer's meridian at its
    highest point; lower transit ≈ 12h25m later. These are genuine astronomical
    times (sidereal hour-angle solution with the Moon's own right-ascension
    motion), provided as *reference* times only. They are never a solunar rule
    and never influence the binary decision, any safety gate, or the
    spring/neap classification.
    """
    midnight = datetime(day.year, day.month, day.day, 0, 0, tzinfo=tz)
    ra0, _ = _moon_ra_dec_deg(midnight)
    ra1, _ = _moon_ra_dec_deg(midnight + timedelta(hours=24))
    ra_rate = ((ra1 - ra0 + 180.0) % 360.0 - 180.0) / 24.0
    local_sidereal_0 = (_gmst_deg(midnight) + longitude) % 360.0
    hour_angle_0 = (local_sidereal_0 - ra0) % 360.0
    relative_rate = 360.98564736629 / 24.0 - ra_rate
    hours_to_upper = ((360.0 - hour_angle_0) % 360.0) / relative_rate
    hours_to_lower = (hours_to_upper + 180.0 / relative_rate) % 24.0
    return (
        midnight + timedelta(hours=hours_to_upper),
        midnight + timedelta(hours=hours_to_lower),
    )
