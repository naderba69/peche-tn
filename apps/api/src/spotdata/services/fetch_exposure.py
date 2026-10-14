"""Fetch-based exposure from OSM coastline geometry (pure geometry, no I/O).

For a spot and its seaward normal, cast rays over the sea half-plane and measure
the open-water distance (fetch) to the first coastline crossing in each direction.
A wave can only be generated locally from a direction with a long fetch. If the
forecast wave comes from a direction whose fetch is short, the forecast is not
physically consistent with this coast at this spot.

This module only computes geometry. It does not decide anything: the minimum
fetch that counts as "exposed" is supplied by the caller and must be labelled as
uncalibrated [C] until a local calibration exists.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from spotdata.domain.models import WaveFetchDiagnostic, WaveFetchSample

EARTH_RADIUS_M = 6_371_008.8
MIN_RAY_START_M = 5.0  # ignore the spot's own coastline when the spot sits on it


@dataclass(frozen=True, slots=True)
class FetchRay:
    bearing_deg: float  # direction FROM the spot TOWARD the sea (waves from here)
    fetch_m: float
    hit_coastline: bool  # False: no coastline crossed within the search radius


def _signed_difference(left: float, right: float) -> float:
    return (left - right + 180.0) % 360.0 - 180.0


def _to_local_xy(
    segments: Iterable[tuple[tuple[float, float], tuple[float, float]]],
    origin_lat: float,
    origin_lon: float,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    cos_lat = math.cos(math.radians(origin_lat))
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (lat1, lon1), (lat2, lon2) in segments:
        p = (
            math.radians(lon1 - origin_lon) * EARTH_RADIUS_M * cos_lat,
            math.radians(lat1 - origin_lat) * EARTH_RADIUS_M,
        )
        q = (
            math.radians(lon2 - origin_lon) * EARTH_RADIUS_M * cos_lat,
            math.radians(lat2 - origin_lat) * EARTH_RADIUS_M,
        )
        out.append((p, q))
    return out


def _ray_distance(
    direction: tuple[float, float],
    segment: tuple[tuple[float, float], tuple[float, float]],
) -> float | None:
    """Distance t along a ray from the origin to a segment, or None if no crossing."""
    (px, py), (qx, qy) = segment
    dx, dy = direction
    ex, ey = qx - px, qy - py
    denominator = dx * ey - dy * ex
    if abs(denominator) < 1e-12:
        return None  # parallel: no proper crossing
    # Solve t*d = p + s*e  ->  t = cross(p, e)/den, s = cross(p, d)/den
    t = (px * ey - py * ex) / denominator
    s = (px * dy - py * dx) / denominator
    if t < 0.0 or s < 0.0 or s > 1.0:
        return None
    return t


def fetch_profile(
    *,
    latitude: float,
    longitude: float,
    seaward_deg: float,
    coastline_segments: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    search_radius_m: float,
    step_deg: float = 5.0,
    half_plane_deg: float = 90.0,
) -> list[FetchRay]:
    """Fetch along every ray inside the seaward half-plane (bearings within ±half_plane_deg).

    Rays that hit no coastline inside the search radius report fetch = search radius
    and hit_coastline=False. Callers must treat that as "at least this long", not as
    confirmed open ocean beyond the radius.
    """
    if step_deg <= 0 or search_radius_m <= 0:
        raise ValueError("step_deg and search_radius_m must be positive")
    local = _to_local_xy(coastline_segments, latitude, longitude)
    rays: list[FetchRay] = []
    steps = round(360.0 / step_deg)
    for index in range(steps):
        bearing = (index * step_deg) % 360.0
        if abs(_signed_difference(bearing, seaward_deg)) > half_plane_deg:
            continue
        radians = math.radians(bearing)
        direction = (math.sin(radians), math.cos(radians))  # east, north
        nearest: float | None = None
        for segment in local:
            t = _ray_distance(direction, segment)
            if t is None or t < MIN_RAY_START_M or t > search_radius_m:
                continue
            if nearest is None or t < nearest:
                nearest = t
        if nearest is None:
            rays.append(FetchRay(bearing, search_radius_m, hit_coastline=False))
        else:
            rays.append(FetchRay(bearing, nearest, hit_coastline=True))
    return rays


def fetch_toward_wave_source(
    rays: Sequence[FetchRay], wave_from_deg: float, *, max_bearing_gap_deg: float = 5.0
) -> FetchRay | None:
    """Fetch of the ray nearest to the direction the wave comes FROM.

    Returns None when the direction is outside the sampled seaward half-plane, which
    means the wave comes from the land side of the coast at this spot.
    """
    if not rays:
        return None
    best = min(rays, key=lambda ray: abs(_signed_difference(ray.bearing_deg, wave_from_deg)))
    if abs(_signed_difference(best.bearing_deg, wave_from_deg)) > max_bearing_gap_deg:
        return None
    return best


def build_wave_fetch_diagnostic(
    *,
    latitude: float,
    longitude: float,
    seaward_deg: float | None,
    segments: Sequence[tuple[tuple[float, float], tuple[float, float]]] | None,
    search_radius_m: float,
    hourly_wave_from: Sequence[tuple[datetime, float | None]],
) -> WaveFetchDiagnostic:
    radius_km = round(search_radius_m / 1000.0, 1)
    if seaward_deg is None or not segments:
        return WaveFetchDiagnostic(
            status="unavailable",
            seaward_orientation_deg=seaward_deg,
            search_radius_km=radius_km,
            reasons_ar=[
                "لم تُجلب هندسة الساحل الواسعة أو لم يُعرف اتجاه البحر؛ التشخيص غير متاح ولا يغيّر القرار."
            ],
        )
    rays = fetch_profile(
        latitude=latitude,
        longitude=longitude,
        seaward_deg=seaward_deg,
        coastline_segments=segments,
        search_radius_m=search_radius_m,
    )
    samples: list[WaveFetchSample] = []
    for time, wave_from in hourly_wave_from:
        if wave_from is None:
            continue
        ray = fetch_toward_wave_source(rays, wave_from)
        samples.append(
            WaveFetchSample(
                time=time,
                wave_from_deg=round(wave_from % 360.0, 1),
                fetch_km=round(ray.fetch_m / 1000.0, 1) if ray is not None else None,
                hit_coastline=ray.hit_coastline if ray is not None else None,
                in_seaward_sector=ray is not None,
            )
        )
    reasons = [
        "تشخيص فقط: المسافة المفتوحة للماء من الساحل المحسوب في اتجاه مصدر الموج. لا تغيّر القرار ولا الثقة ولا النوافذ.",
        f"حدود البحث {radius_km:g} كم؛ إن لم يقطع الشعاع أي ساحل داخل الحد فالقيمة «على الأقل» وليست مسافة مؤكدة.",
    ]
    if not samples:
        reasons.append("لا توجد اتجاهات موج في ساعات التوقع.")
    return WaveFetchDiagnostic(
        status="resolved",
        seaward_orientation_deg=round(seaward_deg, 1) % 360.0,
        search_radius_km=radius_km,
        samples=samples,
        reasons_ar=reasons,
    )
