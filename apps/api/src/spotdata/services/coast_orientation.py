from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import httpx

from spotdata.domain.enums import ShoreType
from spotdata.domain.models import (
    AutomatedShoreProfile,
    AutoOrientationResponse,
    OrientationEvidence,
)
from spotdata.services.cache import AsyncTTLCache

LOGGER = logging.getLogger(__name__)
EARTH_RADIUS_M = 6_371_008.8
ORIENTATION_SEARCH_BUDGET_S = 25
# Per-mirror read timeout by search radius. One flat 8 s ceiling decides how much budget a
# single unresponsive mirror eats: three of them burn 24 s at the *first* radius and the wider
# radii are never reached, which is exactly the shape of the production outage logs. A small
# radius should answer fast, so it gets the tightest ceiling; a wide radius legitimately needs
# longer and is allowed more.
ORIENTATION_MIRROR_TIMEOUT_BY_RADIUS_S = {3_000: 6.0, 5_000: 8.0, 10_000: 10.0}
ORIENTATION_MIRROR_TIMEOUT_S = 8.0
# Leave room for at least one more mirror attempt inside the global budget; below this
# remaining time a new request is pointless because its answer would be discarded.
ORIENTATION_MIRROR_MIN_TIME_S = 1.5
SEARCH_RADII_M = (3_000, 5_000, 10_000)
COASTLINE_FETCH_TIMEOUT_S = 6.0
COASTLINE_SEARCH_BUDGET_S = 7.0
MAX_SHORE_FEATURE_DISTANCE_M = 100.0
# Public Overpass mirrors degrade for minutes at a time (queueing, 429/504, read timeouts).
# Probing a dead mirror once per search radius, per request, per spot multiplies into a
# request storm against a mirror that is already refusing work. A mirror that keeps failing
# is therefore parked briefly and retried on a probe schedule instead.
MIRROR_FAILURE_THRESHOLD = 3
MIRROR_COOLDOWN_S = 90.0
# Once every mirror is parked the cooldown cannot wait passively, so a shared probe
# interval lets a recovering mirror rejoin without turning the outage into a dead end.
MIRROR_PROBE_INTERVAL_S = 10.0
# HTTP statuses that mean "the mirror is unhealthy or rate-limiting us", not "no data".
_MIRROR_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
# Transient upstream faults: the mirror is at fault, the point on the map is not.
# ``httpx.CancelledError`` is a ``TransportError`` subclass, so caller-side cancellation
# (never swallowed here) still propagates as a plain ``asyncio.CancelledError``.
_MIRROR_ERRORS = (httpx.HTTPError, TimeoutError, ValueError, TypeError)


@dataclass(slots=True)
class _MirrorState:
    server: str
    consecutive_failures: int = 0
    opened_at: float | None = None
    last_probe_at: float | None = None

    @property
    def status(self) -> str:
        return "open" if self.opened_at is not None else "closed"


class _MirrorBreaker:
    """Per-mirror consecutive-failure breaker with half-open probing.

    Health is process-local and deliberately shares no state with the result cache: a
    parked mirror must never turn into an ``unavailable`` answer for the user, only into a
    skipped candidate while another mirror is tried.
    """

    def __init__(
        self,
        servers: Sequence[str],
        *,
        threshold: int = MIRROR_FAILURE_THRESHOLD,
        cooldown_s: float = MIRROR_COOLDOWN_S,
        probe_interval_s: float = MIRROR_PROBE_INTERVAL_S,
    ) -> None:
        self._states = {server: _MirrorState(server=server) for server in servers}
        self._threshold = max(1, threshold)
        self._cooldown = cooldown_s
        self._probe_interval = probe_interval_s

    def is_eligible(self, server: str, now: float) -> bool:
        state = self._states.get(server)
        if state is None or state.opened_at is None:
            return True
        if now - state.opened_at >= self._cooldown:
            # Full cooldown elapsed: the mirror is healthy again until proven otherwise, so
            # the park is lifted rather than kept as a permanent mark.
            state.opened_at = None
            state.last_probe_at = None
            state.consecutive_failures = self._threshold - 1
            return True
        if state.last_probe_at is None or now - state.last_probe_at >= self._probe_interval:
            state.last_probe_at = now
            return True
        return False

    def eligible_servers(self, servers: Sequence[str], now: float) -> tuple[str, ...]:
        eligible = tuple(server for server in servers if self.is_eligible(server, now))
        # Every mirror parked and still cooling down: probing anyway is strictly better
        # than answering "unavailable" while OSM may already be healthy again.
        return eligible if eligible else tuple(servers)

    def record_success(self, server: str) -> None:
        state = self._states.get(server)
        if state is None:
            return
        if state.opened_at is not None:
            LOGGER.info("Overpass mirror recovered server=%s", server)
        state.consecutive_failures = 0
        state.opened_at = None
        state.last_probe_at = None

    def record_failure(self, server: str, now: float) -> None:
        state = self._states.get(server)
        if state is None:
            return
        state.consecutive_failures += 1
        if state.opened_at is None and state.consecutive_failures >= self._threshold:
            state.opened_at = now
            # The call that tripped the breaker *is* the first probe; without this the next
            # search radius of the same request would immediately probe it again.
            state.last_probe_at = now
            LOGGER.warning(
                "Overpass mirror parked server=%s failures=%s cooldown=%.0fs",
                server,
                state.consecutive_failures,
                self._cooldown,
            )

    def snapshot(self) -> list[dict[str, object]]:
        now = time.monotonic()
        return [
            {
                "server": state.server,
                "status": state.status,
                "consecutive_failures": state.consecutive_failures,
                "retry_in_seconds": (
                    round(max(0.0, state.opened_at + self._cooldown - now), 1)
                    if state.opened_at is not None
                    else None
                ),
            }
            for state in self._states.values()
        ]


@dataclass(frozen=True, slots=True)
class _MirrorAttempt:
    """Outcome of one Overpass request. ``fail`` is the mirror's fault; ``empty`` is the map's."""

    outcome: str
    response: AutoOrientationResponse | None = None
    detail: str = ""


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


def _nearest_segment(
    elements: Sequence[object], latitude: float, longitude: float
) -> _Segment | None:
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


def _classify_shore_tags(tags: dict[str, str]) -> ShoreType | None:
    """Map explicit OSM feature tags only; do not infer substrate from proximity alone."""
    natural = tags.get("natural", "").lower()
    surface = tags.get("surface", "").lower()
    if natural == "cliff":
        return ShoreType.CLIFF
    if natural == "bare_rock":
        return ShoreType.ROCKY
    if natural == "beach" and surface in {"sand", "fine_sand"}:
        return ShoreType.SANDY
    if natural == "coastline" and surface in {"sand", "fine_sand"}:
        return ShoreType.SANDY
    if natural == "coastline" and surface in {"rock", "stone", "bare_rock"}:
        return ShoreType.ROCKY
    if tags.get("man_made", "").lower() in {"jetty", "breakwater"}:
        return ShoreType.JETTY
    if tags.get("breakwater", "").lower() not in {"", "no"}:
        return ShoreType.JETTY
    return None


def _shore_profile(
    elements: list[object],
    *,
    latitude: float,
    longitude: float,
    retrieved_at: datetime,
) -> AutomatedShoreProfile:
    candidates: list[tuple[float, int, int, datetime, ShoreType, dict[str, str]]] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        raw_tags = element.get("tags")
        if not isinstance(raw_tags, dict):
            continue
        tags = {str(key): str(value) for key, value in raw_tags.items()}
        shore_type = _classify_shore_tags(tags)
        feature_id = element.get("id")
        feature_version = element.get("version")
        raw_timestamp = element.get("timestamp")
        if (
            shore_type is None
            or not isinstance(feature_id, int)
            or feature_id <= 0
            or not isinstance(feature_version, int)
            or feature_version <= 0
            or not isinstance(raw_timestamp, str)
        ):
            continue
        try:
            feature_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if feature_timestamp.tzinfo is None or feature_timestamp.utcoffset() is None:
            continue
        segment = _nearest_segment([element], latitude, longitude)
        if segment is None or segment.distance_m > MAX_SHORE_FEATURE_DISTANCE_M:
            continue
        candidates.append(
            (segment.distance_m, feature_id, feature_version, feature_timestamp, shore_type, tags)
        )

    limitations = [
        "التصنيف مشتق فقط من وسوم OSM الصريحة؛ قد تكون الوسوم ناقصة أو قديمة ولا تصف القاع تحت الماء.",
        "ثقة تصنيف الشاطئ وصفية بحسب قرب معلم موسوم صراحةً، وليست احتمالاً إحصائياً أو تحققاً ميدانياً.",
        "لم يُستنتج التعرض المكاني من اتجاه الساحل أو القرب؛ exposure يبقى Unknown ولا يدخل الحسابات.",
    ]
    if not candidates:
        return AutomatedShoreProfile(
            status="unavailable",
            retrieved_at=retrieved_at,
            confidence="unknown",
            limitations_ar=[
                *limitations,
                "لم يُعثر على معلم ساحلي موسوم صراحةً بنوع قابل للتصنيف ضمن 100 م؛ بقي نوع الساحل Unknown.",
            ],
        )

    distance_m, feature_id, feature_version, feature_timestamp, shore_type, raw_tags = min(
        candidates, key=lambda item: item[0]
    )
    confidence: str = "high" if distance_m <= 30 else "medium"
    return AutomatedShoreProfile(
        status="resolved",
        retrieved_at=retrieved_at,
        shore_type=shore_type,
        exposure=None,
        evidence_feature_id=feature_id,
        evidence_feature_version=feature_version,
        evidence_feature_timestamp=feature_timestamp,
        feature_distance_m=round(distance_m, 1),
        raw_tags=raw_tags,
        confidence=confidence,
        limitations_ar=limitations,
    )


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
    resolved_at = calculated_at or datetime.now(UTC)
    shore_profile = _shore_profile(
        elements,
        latitude=latitude,
        longitude=longitude,
        retrieved_at=resolved_at,
    )
    coastline_elements = [
        element
        for element in elements
        if isinstance(element, dict)
        and isinstance(element.get("tags"), dict)
        and element["tags"].get("natural") == "coastline"
    ]
    segment = _nearest_segment(coastline_elements, latitude, longitude)
    if segment is None:
        return AutoOrientationResponse(
            status="unavailable",
            shore_profile=shore_profile,
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
        calculated_at=resolved_at,
        limitations_ar=limitations,
    )
    return AutoOrientationResponse(
        status="resolved",
        orientation_deg=rounded_orientation,
        evidence=evidence,
        shore_profile=shore_profile,
        reasons_ar=[
            f"حُسب عمود الساحل من {segments_used} مقطع/مقاطع؛ المسافة إلى الساحل {segment.distance_m:.0f} م وتشتت المماس {spread:.1f}°."
        ],
    )


_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def _meets_verified_rules(result: AutoOrientationResponse) -> bool:
    """Same rules the frontend and backend use to accept an orientation (unchanged)."""
    evidence = result.evidence
    return (
        evidence is not None
        and evidence.confidence == "high"
        and evidence.coastline_distance_m <= 500
        and evidence.segments_used >= 3
    )


def _orientation_rank(result: AutoOrientationResponse) -> tuple[int, float]:
    evidence = result.evidence
    if evidence is None:
        return (-1, 0.0)
    return (_CONFIDENCE_RANK.get(evidence.confidence, -1), -evidence.coastline_distance_m)


def _coastline_query(latitude: float, longitude: float, radius_m: int) -> str:
    """Wide coastline-only geometry lookup for the optional fetch-shading diagnostic."""
    return (
        "[out:json][timeout:20];"
        f'way(around:{radius_m},{latitude},{longitude})["natural"="coastline"];'
        "out geom;"
    )


def _orientation_query(latitude: float, longitude: float, radius_m: int) -> str:
    """Bounded Overpass union for coastline geometry plus explicitly classifiable shore ways.

    One deliberate narrowing versus the previous union: a ``natural=beach`` way is fetched only
    when it carries a substrate the classifier can actually read. Bare beach ways were
    downloaded at every radius on every mirror and then dropped by ``_classify_shore_tags``,
    which is pure timeout risk on a loaded public mirror for an element that can never be used.
    ``out meta`` stays, because shore-type evidence needs the feature version and timestamp.
    """
    bounds = f"around:{radius_m},{latitude},{longitude}"
    blocks = [
        f'way({bounds})["natural"="coastline"]',
        f'way({bounds})["natural"~"^(cliff|bare_rock)$"]',
        f'way({bounds})["natural"="beach"]["surface"~"^(sand|fine_sand)$"]',
        f'way({bounds})["man_made"~"^(jetty|breakwater)$"]',
        f'way({bounds})["breakwater"]',
    ]
    return f"[out:json][timeout:12];({''.join(block + ';' for block in blocks)});out meta geom;"


class CoastOrientationClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        servers: tuple[str, ...],
        mirror_failure_threshold: int = MIRROR_FAILURE_THRESHOLD,
        mirror_cooldown_seconds: float = MIRROR_COOLDOWN_S,
    ) -> None:
        self._http_client = http_client
        self._servers = servers
        self._mirrors = _MirrorBreaker(
            servers,
            threshold=mirror_failure_threshold,
            cooldown_s=mirror_cooldown_seconds,
        )
        self.cache: AsyncTTLCache[tuple[float, float], AutoOrientationResponse] = AsyncTTLCache(
            ttl_seconds=24 * 60 * 60,
            max_entries=256,
        )
        self.segment_cache: AsyncTTLCache[
            tuple[float, float, int],
            tuple[tuple[tuple[float, float], tuple[float, float]], ...] | None,
        ] = AsyncTTLCache(ttl_seconds=24 * 60 * 60, max_entries=64)

    async def coastline_segments(
        self, latitude: float, longitude: float, radius_m: int
    ) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...] | None:
        """Wide coastline geometry for fetch exposure. None when unavailable."""
        key = (round(latitude, 4), round(longitude, 4), radius_m)
        cached = await self.segment_cache.get_or_create(
            key, lambda: self._coastline_uncached(latitude, longitude, radius_m)
        )
        if cached is None:
            await self.segment_cache.delete(key)
        return cached

    async def _coastline_uncached(
        self, latitude: float, longitude: float, radius_m: int
    ) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...] | None:
        query = _coastline_query(latitude, longitude, radius_m)
        # The caller wraps this in its own short wait: a 30 km geometry fetch is optional
        # context for the wave-shading diagnostic, so a parked mirror must not consume the
        # whole window. Stop as soon as a further attempt could not finish in time.
        deadline = time.monotonic() + COASTLINE_SEARCH_BUDGET_S
        for server in self._mirrors.eligible_servers(self._servers, time.monotonic()):
            if deadline - time.monotonic() < 1.0:
                LOGGER.info("Overpass coastline fetch budget exhausted radius=%s", radius_m)
                return None
            try:
                async with asyncio.timeout(max(1.0, deadline - time.monotonic())):
                    response = await self._http_client.get(
                        server,
                        params={"data": query},
                        timeout=COASTLINE_FETCH_TIMEOUT_S,
                        headers={"Accept": "application/json"},
                    )
                if response.status_code in _MIRROR_RETRY_STATUSES:
                    self._mirrors.record_failure(server, time.monotonic())
                    LOGGER.warning(
                        "Overpass coastline fetch rejected server=%s status=%s",
                        server,
                        response.status_code,
                    )
                    continue
                response.raise_for_status()
                payload: Any = response.json()
                elements = payload.get("elements") if isinstance(payload, dict) else None
                if not isinstance(elements, list):
                    # A 200 that is not a JSON element list is a broken mirror, not an empty sea.
                    self._mirrors.record_failure(server, time.monotonic())
                    continue
                self._mirrors.record_success(server)
                segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
                for element in elements:
                    geometry = _valid_geometry(element)
                    segments.extend(
                        (start, end) for start, end in pairwise(geometry) if start != end
                    )
                if segments:
                    return tuple(segments)
            except _MIRROR_ERRORS as exc:
                self._mirrors.record_failure(server, time.monotonic())
                LOGGER.warning(
                    "Overpass coastline fetch failed server=%s type=%s",
                    server,
                    type(exc).__name__,
                )
        return None

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
        best: AutoOrientationResponse | None = None
        started_at = time.monotonic()
        deadline = started_at + ORIENTATION_SEARCH_BUDGET_S
        eligible: tuple[str, ...] = self._servers
        try:
            # Bounded search budget: the UI waits for this result before the planner can
            # render an actionable state. On expiry we return the strongest result seen.
            async with asyncio.timeout(ORIENTATION_SEARCH_BUDGET_S):
                for radius in SEARCH_RADII_M:
                    query = _orientation_query(latitude, longitude, radius)
                    eligible = self._mirrors.eligible_servers(self._servers, time.monotonic())
                    for server in eligible:
                        remaining = deadline - time.monotonic()
                        if remaining < ORIENTATION_MIRROR_MIN_TIME_S:
                            failures.append(
                                "لم يتبقَّ وقت كافٍ ضمن ميزانية البحث لتجربة مزوّد آخر؛ "
                                "أُعيدت أقوى نتيجة متوفرة."
                            )
                            return self._finalize(best, failures, eligible, started_at)
                        result = await self._attempt_orientation(
                            server,
                            query,
                            radius,
                            latitude,
                            longitude,
                            timeout_s=min(
                                ORIENTATION_MIRROR_TIMEOUT_BY_RADIUS_S.get(
                                    radius, ORIENTATION_MIRROR_TIMEOUT_S
                                ),
                                remaining,
                            ),
                        )
                        if result.outcome == "ok":
                            assert result.response is not None
                            self._mirrors.record_success(server)
                            # Keep searching: a mirror or radius can return a
                            # weaker geometry for the same point. Return the first
                            # result that meets the verification rules; otherwise
                            # the strongest one seen (never a silent first-answer).
                            if _meets_verified_rules(result.response):
                                return result.response
                            if best is None or _orientation_rank(
                                result.response
                            ) > _orientation_rank(best):
                                best = result.response
                        elif result.outcome == "empty":
                            # A valid answer with no elements is a property of the map, not of
                            # the mirror — an inland or un-surveyed point must never park a
                            # healthy mirror for every other user.
                            self._mirrors.record_success(server)
                            failures.append(f"{server}: لا توجد هندسة ضمن {radius} م")
                        else:
                            self._mirrors.record_failure(server, time.monotonic())
                            failures.append(f"{server}: {result.detail}")
                    if deadline - time.monotonic() < ORIENTATION_MIRROR_MIN_TIME_S:
                        failures.append(
                            "لم يتبقَّ وقت كافٍ ضمن ميزانية البحث لتجربة نصف قطر أوسع؛ "
                            "أُعيدت أقوى نتيجة متوفرة."
                        )
                        break
        except TimeoutError:
            failures.append(f"انتهت مهلة Overpass الكلية بعد {ORIENTATION_SEARCH_BUDGET_S} ثوانٍ")

        return self._finalize(best, failures, eligible, started_at)

    def _finalize(
        self,
        best: AutoOrientationResponse | None,
        failures: list[str],
        eligible: Sequence[str],
        started_at: float,
    ) -> AutoOrientationResponse:
        if best is not None:
            return best
        parked = [server for server in self._servers if server not in set(eligible)]
        if parked:
            LOGGER.info(
                "Overpass orientation served without parked mirrors parked=%s elapsed=%.1fs",
                ",".join(parked),
                time.monotonic() - started_at,
            )
            failures.append(
                "تم تجاوز مزوّد Overpass غير الصحي مؤقتاً ("
                + "، ".join(parked)
                + ") بدل انتظار مهلته؛ يعود تلقائياً بعد فترة الاستراحة."
            )
        return AutoOrientationResponse(
            status="unavailable",
            reasons_ar=(
                [
                    "تعذر حساب اتجاه الساحل آلياً؛ بقي الاتجاه Unknown ولم يُستبدل بقيمة يدوية أو تقديرية.",
                    *failures[-3:],
                ]
            ),
        )

    def mirror_health(self) -> list[dict[str, object]]:
        """Breaker state for `/api/health`, so a parked mirror is visible without log spelunking."""
        return self._mirrors.snapshot()

    async def _attempt_orientation(
        self,
        server: str,
        query: str,
        radius: int,
        latitude: float,
        longitude: float,
        *,
        timeout_s: float,
    ) -> _MirrorAttempt:
        try:
            response = await self._http_client.get(
                server,
                params={"data": query},
                timeout=timeout_s,
                headers={"Accept": "application/json"},
            )
            if response.status_code in _MIRROR_RETRY_STATUSES:
                return _MirrorAttempt(
                    outcome="fail",
                    detail=f"استجابة المزوّد {response.status_code}",
                )
            response.raise_for_status()
            payload: Any = response.json()
            elements = payload.get("elements") if isinstance(payload, dict) else None
            if not isinstance(elements, list):
                # A 200 that is not a JSON element list is the mirror misbehaving.
                return _MirrorAttempt(outcome="fail", detail="استجابة بلا قائمة عناصر صالحة")
            if not elements:
                LOGGER.info(
                    "Overpass orientation empty server=%s radius=%s",
                    server,
                    radius,
                )
                return _MirrorAttempt(outcome="empty", detail="لا توجد هندسة")
            LOGGER.info(
                "Overpass orientation elements server=%s radius=%s count=%s",
                server,
                radius,
                len(elements),
            )
            return _MirrorAttempt(
                outcome="ok",
                response=calculate_orientation(
                    elements,
                    latitude=latitude,
                    longitude=longitude,
                    search_radius_m=radius,
                    server=server,
                ),
            )
        except _MIRROR_ERRORS as exc:
            LOGGER.warning(
                "Overpass orientation failed server=%s radius=%s type=%s",
                server,
                radius,
                type(exc).__name__,
            )
            return _MirrorAttempt(
                outcome="fail",
                detail=f"تعذر الاتصال أو تحليل الاستجابة ({type(exc).__name__})",
            )
