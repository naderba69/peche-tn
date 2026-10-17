"""Server selection: a weaker first answer must not hide a verified one."""

import httpx
import pytest
import respx

from spotdata.services.coast_orientation import CoastOrientationClient


def _coast(points: list[tuple[float, float]]) -> dict[str, object]:
    return {
        "type": "way",
        "id": 2001,
        "tags": {"natural": "coastline"},
        "geometry": [{"lat": la, "lon": lo} for la, lo in points],
    }


@respx.mock
@pytest.mark.asyncio
async def test_weaker_first_mirror_does_not_hide_verified_geometry() -> None:
    weak = "https://weak-overpass.test/api"
    strong = "https://strong-overpass.test/api"
    # Two-node way: a single smoothing segment, fails the >=3 segments rule.
    respx.get(weak).mock(
        return_value=httpx.Response(200, json={"elements": [_coast([(36.0, 10.0), (36.0, 10.03)])]})
    )
    respx.get(strong).mock(
        return_value=httpx.Response(
            200,
            json={
                "elements": [_coast([(36.0, 10.0), (36.0, 10.01), (36.0, 10.02), (36.0, 10.03)])]
            },
        )
    )
    async with httpx.AsyncClient() as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=(weak, strong))
        result = await client.resolve(35.9965, 10.015)
    assert result.status == "resolved"
    assert result.evidence is not None
    assert result.evidence.server == strong
    assert result.evidence.confidence == "high"
    assert result.evidence.tangent_spread_deg is not None
    assert result.evidence.tangent_spread_deg <= 15
