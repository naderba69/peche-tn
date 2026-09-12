from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import httpx

from spotdata.domain.models import (
    AutoOrientationResponse,
    OrientationEvidence,
)
from spotdata.services.cache import AsyncTTLCache

LOGGER = logging.getLogger(__name__)
EARTH_RADIUS_M = 6_371_008.8
SEARCH_RADII_M = (3_000, 5_000, 10_000)


@dataclass(frozen=True, slots=True)
class _Segment:
    geometry: tuple[tuple[float, float], ...]
    index: int
    distance_m: float
    projected_latitude: float
    projected_longitude: float
    tangent_deg: float


def _circular_difference(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _signed_difference(left: float, right: float) -> float:
    return (left - right + 180.0) % 360.0 - 180.0


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    first_latitude = math.radians(lat1)
    second_latitude = math.radians(lat2)
    longitude_delta = math.radians(lon2 - lon1)
    y = math.sin(longitude_delta) * math.cos(second_latitude)
    x = math.cos(first_latitude) * math.sin(second_latitude) - math.sin(first_latitude) * math.cos(
        second_latitude
    ) * math.cos(longitude_delta)
    if abs(x) < 1e-15 and abs(y) < 1e-15:
        return 0.0
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _local_xy(latitude: float, longitude: float, origin_latitude: float) -> tuple[float, float]:
    latitude_radians = math.radians(origin_latitude)
    x = math.radians(longitude) * EARTH_RADIUS_M * math.cos(latitude_radians)
    y = math.radians(latitude) * EARTH_RADIUS_M
    return x, y


def _project_to_segment(
    latitude: float,
    longitude: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float, float]:
    point_x, point_y = _local_xy(latitude, longitude, latitude)
    start_x, start_y = _local_xy(start[0], start[1], latitude)
    end_x, end_y = _local_xy(end[0], end[1], latitude)
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x**2 + delta_y**2
    if length_squared <= 1e-9:
        return start[0], start[1], math.hypot(point_x - start_x, point_y - start_y)
    fraction = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    projected_x = start_x + fraction * delta_x
    projected_y = start_y + fraction * delta_y
    projected_latitude = math.degrees(projected_y / EARTH_RADIUS_M)
    projected_longitude = math.degrees(
        projected_x / (EARTH_RADIUS_M * math.cos(math.radians(latitude)))
    )
    return (
        projected_latitude,
        projected_longitude,
        math.hypot(point_x - projected_x, point_y - projected_y),
    )


def _valid_geometry(element: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(element, dict):
        return ()
    raw_geometry = element.get("geometry")
    if not isinstance(raw_geometry, list):
        return ()
    geometry: list[tuple[float, float]] = []
    for point in raw_geometry:
        if not isinstance(point, dict):
            continue
        latitude = point.get("lat")
        longitude = point.get("lon")
        if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        geometry.append((float(latitude), float(longitude)))
    return tuple(geometry)


def _nearest_segment(elements: list[object], latitude: float, longitude: float) -> _Segment | None:
    nearest: _Segment | None = None
    for element in elements:
        geometry = _valid_geometry(element)
        for index, (start, end) in enumerate(pairwise(geometry)):
            if start == end:
                continue
            projected_latitude, projected_longitude, distance_m = _project_to_segment(
                latitude, longitude, start, end
            )
            if nearest is None or distance_m < nearest.distance_m:
                nearest = _Segment(
                    geometry=geometry,
                    index=index,
                    distance_m=distance_m,
                    projected_latitude=projected_latitude,
                    projected_longitude=projected_longitude,
                    tangent_deg=_bearing(start[0], start[1], end[0], end[1]),
                )
    return nearest


def _smoothed_tangent(segment: _Segment) -> tuple[float, int, float]:
    first_index = max(0, segment.index - 2)
    last_index = min(len(segment.geometry) - 2, segment.index + 2)
    bearings = [
        _bearing(
            segment.geometry[index][0],
            segment.geometry[index][1],
            segment.geometry[index + 1][0],
            segment.geometry[index + 1][1],
        )
        for index in range(first_index, last_index + 1)
        if segment.geometry[index] != segment.geometry[index + 1]
    ]
    if not bearings:
        return segment.tangent_deg, 1, 0.0

    aligned = [
        bearing + 180.0
        if _signed_difference(bearing, segment.tangent_deg) > 90.0
        or _signed_difference(bearing, segment.tangent_deg) < -90.0
        else bearing
        for bearing in bearings
    ]
    sine = sum(math.sin(math.radians(value)) for value in aligned)
    cosine = sum(math.cos(math.radians(value)) for value in aligned)
    mean = (math.degrees(math.atan2(sine, cosine)) + 360.0) % 360.0
    spread = max(_circular_difference(value % 360.0, mean) for value in aligned)
    return mean, len(aligned), spread


def calculate_orientation(
    elements: list[object],
    *,
    latitude: float,
    longitude: float,
    search_radius_m: int,
    server: str,
    calculated_at: datetime | None = None,
) -> AutoOrientationResponse:
    """Resolve the corrected original Overpass coastline-normal method.

    The selected point is expected to be on the land side of the coast. The normal
    opposite the coast-to-user bearing is therefore the seaward candidate. When the
    point lies almost exactly on the line, OSM's coastline convention (water on the
    right of the way) supplies the candidate.
    """
    segment = _nearest_segment(elements, latitude, longitude)
    if segment is None:
        return AutoOrientationResponse(
            status="unavailable",
            reasons_ar=["لم يرجع Overpass مقطع ساحل صالحاً قرب النقطة المختارة."],
        )

    tangent, segments_used, spread = _smoothed_tangent(segment)
    right_normal = (tangent + 90.0) % 360.0
    left_normal = (tangent - 90.0) % 360.0
    limitations: list[str] = [
        "الاتجاه مشتق من هندسة OpenStreetMap وليس قياس بوصلة ميدانياً.",
    ]

    if segment.distance_m >= 5.0:
        coast_to_user = _bearing(
            segment.projected_latitude,
            segment.projected_longitude,
            latitude,
            longitude,
        )
        orientation = (
            right_normal
            if _circular_difference(right_normal, coast_to_user)
            > _circular_difference(left_normal, coast_to_user)
            else left_normal
        )
    else:
        orientation = right_normal
        limitations.append(
            "النقطة تقع تقريباً على خط الساحل؛ اختير يمين اتجاه way حسب اتفاقية OSM ويجب فحص السهم بصرياً."
        )

    if segment.distance_m <= 500 and spread <= 15 and segments_used >= 3:
        confidence: str = "high"
    elif segment.distance_m <= 1_500 and spread <= 30:
        confidence = "medium"
    else:
        confidence = "low"
    if segment.distance_m > 1_500:
        limitations.append(
            "النقطة بعيدة نسبياً عن خط الساحل؛ قربها من موضع الوقوف الفعلي يرفع موثوقية الاتجاه."
        )
    if spread > 30:
        limitations.append(
            "انحناء الساحل المحلي كبير؛ المتوسط الآلي حساس لموضع الوقوف ويجب تأكيده على الخريطة."
        )

    rounded_orientation = round(orientation, 1) % 360.0
    evidence = OrientationEvidence(
        orientation_deg=rounded_orientation,
        coastline_tangent_deg=round(tangent, 1) % 360.0,
        coastline_distance_m=round(segment.distance_m, 1),
        search_radius_m=search_radius_m,
        segments_used=segments_used,
        confidence=confidence,
        server=server,
        calculated_at=calculated_at or datetime.now(UTC),
        limitations_ar=limitations,
    )
    return AutoOrientationResponse(
        status="resolved",
        orientation_deg=rounded_orientation,
        evidence=evidence,
        reasons_ar=[
            f"حُسب عمود الساحل من {segments_used} مقطع/مقاطع؛ المسافة إلى الساحل {segment.distance_m:.0f} م وتشتت المماس {spread:.1f}°."
        ],
    )


class CoastOrientationClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        servers: tuple[str, ...],
    ) -> None:
        self._http_client = http_client
        self._servers = servers
        self.cache: AsyncTTLCache[tuple[float, float], AutoOrientationResponse] = AsyncTTLCache(
            ttl_seconds=24 * 60 * 60,
            max_entries=256,
        )

    async def resolve(self, latitude: float, longitude: float) -> AutoOrientationResponse:
        key = (round(latitude, 5), round(longitude, 5))
        result = await self.cache.get_or_create(
            key,
            lambda: self._resolve_uncached(latitude, longitude),
        )
        if result.status == "unavailable":
            # A transient mirror outage must not poison the explicit recalculate button.
            await self.cache.delete(key)
        return result

    async def _resolve_uncached(self, latitude: float, longitude: float) -> AutoOrientationResponse:
        failures: list[str] = []
        try:
            async with asyncio.timeout(25):
                for radius in SEARCH_RADII_M:
                    query = (
                        "[out:json][timeout:12];"
                        f'(way(around:{radius},{latitude},{longitude})["natural"="coastline"];);'
                        "out geom;"
                    )
                    for server in self._servers:
                        try:
                            response = await self._http_client.get(
                                server,
                                params={"data": query},
                                timeout=8.0,
                                headers={"Accept": "application/json"},
                            )
                            response.raise_for_status()
                            payload: Any = response.json()
                            elements = (
                                payload.get("elements") if isinstance(payload, dict) else None
                            )
                            if not isinstance(elements, list) or not elements:
                                failures.append(f"{server}: لا توجد هندسة ضمن {radius} م")
                                continue
                            result = calculate_orientation(
                                elements,
                                latitude=latitude,
                                longitude=longitude,
                                search_radius_m=radius,
                                server=server,
                            )
                            if result.status == "resolved":
                                return result
                            failures.extend(result.reasons_ar)
                        except (httpx.HTTPError, ValueError, TypeError) as exc:
                            LOGGER.warning(
                                "Overpass orientation failed server=%s radius=%s type=%s",
                                server,
                                radius,
                                type(exc).__name__,
                            )
                            failures.append(f"{server}: تعذر الاتصال أو تحليل الاستجابة")
        except TimeoutError:
            failures.append("انتهت مهلة Overpass الكلية بعد 25 ثانية")

        return AutoOrientationResponse(
            status="unavailable",
            reasons_ar=(
                ["تعذر حساب اتجاه البحر آلياً؛ ثبّت السهم يدوياً على الخريطة.", *failures[-3:]]
            ),
        )
