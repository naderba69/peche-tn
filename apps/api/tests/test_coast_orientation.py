import asyncio
from datetime import UTC, datetime

import httpx
import pytest
import respx

from spotdata.services import coast_orientation
from spotdata.services.coast_orientation import (
    SEARCH_RADII_M,
    CoastOrientationClient,
    calculate_orientation,
)


def coastline(points: list[tuple[float, float]]) -> list[object]:
    return [
        {
            "type": "way",
            "id": 1001,
            "tags": {"natural": "coastline"},
            "geometry": [{"lat": latitude, "lon": longitude} for latitude, longitude in points],
        }
    ]


def test_explicit_nearby_osm_tags_resolve_shore_type_but_never_guess_exposure() -> None:
    elements = coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02)])
    elements.append(
        {
            "type": "way",
            "id": 9001,
            "version": 3,
            "timestamp": "2026-09-08T10:00:00Z",
            "tags": {"natural": "beach", "surface": "sand"},
            "geometry": [
                {"lat": 36.0002, "lon": 10.0},
                {"lat": 36.0002, "lon": 10.02},
            ],
        }
    )
    result = calculate_orientation(
        elements,
        latitude=36.0002,
        longitude=10.01,
        search_radius_m=3_000,
        server="https://overpass.test/api",
        calculated_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    assert result.shore_profile is not None
    assert result.shore_profile.status == "resolved"
    assert result.shore_profile.shore_type.value == "sandy"
    assert result.shore_profile.exposure is None
    assert result.shore_profile.evidence_feature_id == 9001
    assert result.shore_profile.raw_tags == {"natural": "beach", "surface": "sand"}
    assert result.shore_profile.retrieved_at == datetime(2026, 9, 8, tzinfo=UTC)


def test_bare_natural_beach_without_substrate_tag_remains_unknown() -> None:
    elements = coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02)])
    elements.append(
        {
            "type": "way",
            "id": 9002,
            "version": 1,
            "timestamp": "2026-09-08T10:00:00Z",
            "tags": {"natural": "beach"},
            "geometry": [
                {"lat": 36.0002, "lon": 10.0},
                {"lat": 36.0002, "lon": 10.02},
            ],
        }
    )
    result = calculate_orientation(
        elements,
        latitude=36.0002,
        longitude=10.01,
        search_radius_m=3_000,
        server="https://overpass.test/api",
    )
    assert result.shore_profile is not None
    assert result.shore_profile.status == "unavailable"
    assert result.shore_profile.shore_type is None
    assert result.shore_profile.exposure is None


def test_corrected_original_selects_normal_away_from_land_point() -> None:
    elements = coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02), (36.0, 10.03)])
    result = calculate_orientation(
        elements,
        latitude=36.005,
        longitude=10.015,
        search_radius_m=3_000,
        server="https://overpass.test/api",
        calculated_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    assert result.status == "resolved"
    assert result.orientation_deg == pytest.approx(180.0, abs=0.2)
    assert result.evidence is not None
    assert result.evidence.coastline_tangent_deg == pytest.approx(90.0, abs=0.2)
    assert result.evidence.coastline_distance_m == pytest.approx(556, abs=3)
    assert result.evidence.segments_used >= 3


def test_true_north_tangent_and_zero_degree_orientation_are_valid() -> None:
    # A north-south coastline with the selected land point east of it has sea to the west (270°).
    elements = coastline([(36.0, 10.0), (36.01, 10.0), (36.02, 10.0), (36.03, 10.0)])
    west = calculate_orientation(
        elements,
        latitude=36.015,
        longitude=10.005,
        search_radius_m=3_000,
        server="https://overpass.test/api",
    )
    assert west.status == "resolved"
    assert west.evidence is not None
    assert west.evidence.coastline_tangent_deg == pytest.approx(0.0, abs=0.2)
    assert west.orientation_deg == pytest.approx(270.0, abs=0.2)

    # An east-west coastline with land south of it resolves a legitimate north-facing 0° normal.
    north = calculate_orientation(
        coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02)]),
        latitude=35.995,
        longitude=10.01,
        search_radius_m=3_000,
        server="https://overpass.test/api",
    )
    assert north.status == "resolved"
    assert north.orientation_deg == pytest.approx(0.0, abs=0.2)


def test_exact_coastline_point_uses_osm_water_on_right_convention() -> None:
    result = calculate_orientation(
        coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02)]),
        latitude=36.0,
        longitude=10.01,
        search_radius_m=3_000,
        server="https://overpass.test/api",
    )
    assert result.orientation_deg == pytest.approx(180.0, abs=0.2)
    assert result.evidence is not None
    assert any("اتفاقية OSM" in item for item in result.evidence.limitations_ar)


def test_missing_or_malformed_geometry_is_unavailable() -> None:
    result = calculate_orientation(
        [{"geometry": [{"lat": "bad", "lon": 10}]}],
        latitude=36.0,
        longitude=10.0,
        search_radius_m=3_000,
        server="https://overpass.test/api",
    )
    assert result.status == "unavailable"
    assert result.orientation_deg is None


@respx.mock
@pytest.mark.asyncio
async def test_client_fails_over_between_overpass_servers_without_confusing_zero() -> None:
    first = "https://first-overpass.test/api"
    second = "https://second-overpass.test/api"
    respx.get(first).mock(return_value=httpx.Response(504, text="timeout"))
    respx.get(second).mock(
        return_value=httpx.Response(
            200,
            json={
                "elements": coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02), (36.0, 10.03)])
            },
        )
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(first, second))
        result = await client.resolve(35.995, 10.015)
    assert result.status == "resolved"
    assert result.orientation_deg == pytest.approx(0.0, abs=0.2)
    assert result.evidence is not None
    assert result.evidence.server == second


@respx.mock
@pytest.mark.asyncio
async def test_unavailable_orientation_is_not_cached_against_manual_recalculation() -> None:
    server = "https://retry-overpass.test/api"
    route = respx.get(server).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(
                200,
                json={
                    "elements": coastline(
                        [(36.0, 10.0), (36.0, 10.01), (36.0, 10.02), (36.0, 10.03)]
                    )
                },
            ),
        ]
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        first = await client.resolve(35.9965, 10.015)
        second = await client.resolve(35.9965, 10.015)
    assert first.status == "unavailable"
    assert second.status == "resolved"
    assert route.call_count == 4


def _coastline_payload() -> dict[str, object]:
    """A straight east-west coast four nodes deep: enough for the high-confidence rules."""
    return {
        "elements": [
            {
                "type": "way",
                "id": 4004,
                "version": 2,
                "timestamp": "2026-09-08T10:00:00Z",
                "tags": {"natural": "coastline"},
                "geometry": [
                    {"lat": latitude, "lon": longitude}
                    for latitude, longitude in [
                        (36.0, 10.0),
                        (36.0, 10.01),
                        (36.0, 10.02),
                        (36.0, 10.03),
                    ]
                ],
            }
        ]
    }


@respx.mock
@pytest.mark.asyncio
async def test_time_out_mirror_is_parked_instead_of_beating_every_radius() -> None:
    """A mirror that only times out is probed on a schedule, not once per radius per request."""
    slow = "https://slow-mirror.test/api"
    healthy = "https://healthy-mirror.test/api"
    slow_route = respx.get(slow).mock(side_effect=httpx.ReadTimeout("queue jammed"))
    healthy_route = respx.get(healthy).mock(
        return_value=httpx.Response(200, json=_coastline_payload())
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(slow, healthy),
            mirror_failure_threshold=2,
            mirror_cooldown_seconds=600.0,
        )
        # Six distinct points: none of them may share a cache entry.
        for index in range(6):
            result = await client.resolve(35.9965 + index * 0.0001, 10.015)
            assert result.status == "resolved"
            assert result.evidence is not None
            assert result.evidence.server == healthy
        snapshot = {entry["server"]: entry for entry in client.mirror_health()}
    # Two failures to trip, then silence for the rest of the cooldown. Six searches would
    # otherwise have meant six read-timeout waits and a planner that never answers in time.
    assert slow_route.call_count == 2
    assert healthy_route.call_count == 6
    assert snapshot[slow]["status"] == "open"
    assert snapshot[healthy]["status"] == "closed"


@respx.mock
@pytest.mark.asyncio
async def test_no_coastline_near_a_point_never_parks_a_healthy_mirror() -> None:
    """An empty answer describes the map, not the mirror, so it must not count as a fault."""
    inland = "https://inland-mirror.test/api"
    route = respx.get(inland).mock(return_value=httpx.Response(200, json={"elements": []}))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(inland,))
        for index in range(4):
            result = await client.resolve(36.5 + index * 0.01, 10.0)
            assert result.status == "unavailable"
    assert route.call_count == 4 * len(SEARCH_RADII_M)
    assert client.mirror_health()[0]["status"] == "closed"
    assert client.mirror_health()[0]["consecutive_failures"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_parked_mirror_rejoins_after_one_good_answer() -> None:
    """Recovery must be automatic: a parked mirror is never permanently marked."""
    flaky = "https://flaky-mirror.test/api"
    reliable = "https://reliable-mirror.test/api"
    state = {"calls": 0}

    def flaky_route(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] <= 2:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json=_coastline_payload())

    respx.get(flaky).mock(side_effect=flaky_route)
    respx.get(reliable).mock(return_value=httpx.Response(200, json=_coastline_payload()))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(flaky, reliable),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=0.02,
        )
        for index in range(3):
            assert (await client.resolve(35.9965 + index * 0.001, 10.015)).status == "resolved"
            await asyncio.sleep(0.03)
        snapshot = {entry["server"]: entry for entry in client.mirror_health()}
    assert state["calls"] == 3
    assert snapshot[flaky]["status"] == "closed"
    assert snapshot[flaky]["consecutive_failures"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_all_mirrors_parked_are_still_probed_and_say_so() -> None:
    """Breaker state must never become the reason a user is told Unknown."""
    failing = "https://rate-limited-mirror.test/api"
    route = respx.get(failing).mock(return_value=httpx.Response(429, text="rate limited"))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(failing,),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=600.0,
        )
        assert (await client.resolve(35.9965, 10.015)).status == "unavailable"
        assert client.mirror_health()[0]["status"] == "open"
        second = await client.resolve(35.9965, 10.025)
    assert second.status == "unavailable"
    assert any("429" in reason for reason in second.reasons_ar)
    assert route.call_count >= 2


@respx.mock
@pytest.mark.asyncio
async def test_parked_mirror_changes_nothing_but_the_waiting() -> None:
    """Skipping a dead mirror must not change the answer, only say that it was skipped."""
    slow = "https://dropped-mirror.test/api"
    empty = "https://barren-mirror.test/api"
    slow_route = respx.get(slow).mock(side_effect=httpx.ConnectError("connection refused"))
    respx.get(empty).mock(return_value=httpx.Response(200, json={"elements": []}))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(slow, empty),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=600.0,
        )
        first = await client.resolve(35.9965, 10.015)
        assert first.status == "unavailable"
        second = await client.resolve(35.9965, 10.025)
    assert second.status == "unavailable"
    assert any("تجاوز" in reason for reason in second.reasons_ar)
    # The dead mirror was tried exactly once: the point stays Unknown because of the barren
    # mirror, not because a third of the search budget went to a refused connection.
    assert slow_route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_orientation_query_requests_only_classifiable_shore_features() -> None:
    """Bare `natural=beach` ways are downloaded, then dropped by the classifier: stop paying."""
    server = "https://payload-mirror.test/api"
    route = respx.get(server).mock(return_value=httpx.Response(200, json=_coastline_payload()))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        assert (await client.resolve(35.9965, 10.015)).status == "resolved"
    query = route.calls.last.request.url.params["data"]
    assert query.startswith("[out:json][timeout:")
    assert 'way(around:3000,35.9965,10.015)["natural"="coastline"];' in query
    assert '["natural"="beach"]["surface"~"^(sand|fine_sand)$"];' in query
    assert '["natural"~"^(beach|cliff|bare_rock)$"]' not in query
    assert query.endswith(");out meta geom;")
    # Every union block must stay semicolon-terminated or Overpass rejects the whole query:
    # the three non-block separators are the [out] header, the union close and the out clause.
    assert query.count(";") == query.count("way(around:3000,") + 3


def test_wide_search_radii_get_more_time_than_narrow_ones() -> None:
    """The budget only holds if a slow small-radius query cannot eat the whole search."""
    narrow = coast_orientation.ORIENTATION_MIRROR_TIMEOUT_BY_RADIUS_S[3_000]
    wide = coast_orientation.ORIENTATION_MIRROR_TIMEOUT_BY_RADIUS_S[10_000]
    assert narrow < wide
    assert narrow * len(coast_orientation.SEARCH_RADII_M) < (
        coast_orientation.ORIENTATION_SEARCH_BUDGET_S
    )


class _SteppingClock:
    """Deterministic stand-in for ``time`` so budget guards are not timing-sensitive."""

    def __init__(self, step_s: float) -> None:
        self.now = 0.0
        self.step_s = step_s

    def monotonic(self) -> float:
        value = self.now
        self.now += self.step_s
        return value


def _coastline_element() -> dict[str, object]:
    return {
        "type": "way",
        "id": 7,
        "tags": {"natural": "coastline"},
        "geometry": [
            {"lat": 36.0, "lon": 10.0},
            {"lat": 36.0, "lon": 10.01},
            {"lat": 36.0, "lon": 10.02},
        ],
    }


@respx.mock
@pytest.mark.asyncio
async def test_coastline_geometry_skips_the_mirror_that_rejected_us(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The optional fetch-shading lookup shares the breaker, so it waits on a live mirror."""
    monkeypatch.setattr(coast_orientation, "time", _SteppingClock(0.1))
    broken = "https://broken-mirror.test/api"
    working = "https://working-mirror.test/api"
    broken_route = respx.get(broken).mock(return_value=httpx.Response(503, text="queued"))
    working_route = respx.get(working).mock(
        return_value=httpx.Response(200, json={"elements": [_coastline_element()]})
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(broken, working),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=600.0,
        )
        segments = await client.coastline_segments(36.4, 10.58, 30_000)
        assert segments is not None
        assert len(segments) == 2
        # The park is per mirror, and the lookup never has to burn its short window twice.
        segments_again = await client.coastline_segments(36.5, 10.58, 30_000)
        assert segments_again is not None
    # The broken mirror is tried once, parked, and then skipped for the rest of the cooldown —
    # which is the whole point: the wide diagnostic gets its answer inside the short window.
    assert broken_route.call_count == 1
    assert working_route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_coastline_geometry_gives_up_inside_its_own_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A diagnostic must never outrun the request that optionally awaits it."""
    monkeypatch.setattr(coast_orientation, "time", _SteppingClock(20.0))
    server = "https://slow-wide-mirror.test/api"
    route = respx.get(server).mock(
        return_value=httpx.Response(200, json={"elements": [_coastline_element()]})
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        assert await client.coastline_segments(36.4, 10.58, 30_000) is None
    assert route.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_orientation_search_stops_before_a_radius_it_cannot_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The budget is checked before sending, so a discarded answer is never paid for."""
    monkeypatch.setattr(coast_orientation, "time", _SteppingClock(30.0))
    server = "https://late-mirror.test/api"
    route = respx.get(server).mock(return_value=httpx.Response(200, json=_coastline_payload()))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        result = await client.resolve(35.9965, 10.015)
    assert result.status == "unavailable"
    assert any("ميزانية البحث" in reason for reason in result.reasons_ar)
    assert route.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_malformed_success_is_treated_as_a_mirror_fault() -> None:
    """A 200 without an element list is the mirror, not a coastline-free sea."""
    server = "https://garbage-mirror.test/api"
    respx.get(server).mock(return_value=httpx.Response(200, json={"not-elements": True}))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(server,),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=600.0,
        )
        result = await client.resolve(35.9965, 10.015)
    assert result.status == "unavailable"
    assert any("قائمة عناصر" in reason for reason in result.reasons_ar)
    assert client.mirror_health()[0]["status"] == "open"


@respx.mock
@pytest.mark.asyncio
async def test_coastline_geometry_counts_a_broken_payload_as_a_mirror_fault() -> None:
    """A 200 that is not an element list is a broken mirror, not a coastline-free sea."""
    server = "https://garbage-coastline.test/api"
    respx.get(server).mock(return_value=httpx.Response(200, json={"error": "truncated"}))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(
            http_client=http_client,
            servers=(server,),
            mirror_failure_threshold=1,
            mirror_cooldown_seconds=600.0,
        )
        assert await client.coastline_segments(36.4, 10.58, 30_000) is None
    assert client.mirror_health()[0]["status"] == "open"


@respx.mock
@pytest.mark.asyncio
async def test_wider_radius_is_skipped_when_the_budget_is_already_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escalating to 5 km with no time left would only throw the 3 km answer away."""
    monkeypatch.setattr(coast_orientation, "time", _SteppingClock(10.0))
    server = "https://budget-mirror.test/api"
    route = respx.get(server).mock(return_value=httpx.Response(200, json={"elements": []}))
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        result = await client.resolve(35.9965, 10.015)
    assert result.status == "unavailable"
    assert any("نصف قطر أوسع" in reason for reason in result.reasons_ar)
    assert route.call_count == 1
