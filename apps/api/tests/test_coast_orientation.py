from datetime import UTC, datetime

import httpx
import pytest
import respx

from spotdata.services.coast_orientation import CoastOrientationClient, calculate_orientation


def coastline(points: list[tuple[float, float]]) -> list[object]:
    return [
        {
            "type": "way",
            "geometry": [{"lat": latitude, "lon": longitude} for latitude, longitude in points],
        }
    ]


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
                json={"elements": coastline([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02)])},
            ),
        ]
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(server,))
        first = await client.resolve(35.995, 10.01)
        second = await client.resolve(35.995, 10.01)
    assert first.status == "unavailable"
    assert second.status == "resolved"
    assert route.call_count == 4
