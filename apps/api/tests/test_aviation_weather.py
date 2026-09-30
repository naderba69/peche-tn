from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from spotdata.domain.models import Coordinates
from spotdata.services.aviation_weather import haversine_km, parse_nearest_metar
from spotdata.services.open_meteo import OpenMeteoClient


def _metar(
    station: str,
    *,
    latitude: float,
    longitude: float,
    report_time: str,
    wind_speed: object = 10,
) -> dict[str, object]:
    return {
        "icaoId": station,
        "name": f"Station {station}",
        "lat": latitude,
        "lon": longitude,
        "elev": 7,
        "reportTime": report_time,
        "rawOb": f"{station} 081200Z 09010KT 6SM FEW020 25/18 Q1015",
        "wspd": wind_speed,
        "wgst": 18,
        "wdir": 90,
        "temp": 25,
        "dewp": 18,
        "altim": 1015,
        "visib": "6+",
        "wxString": "-RA",
        "cover": "FEW",
        "qcField": 1,
    }


def test_parse_nearest_metar_selects_latest_report_from_nearest_station() -> None:
    retrieved_at = datetime(2026, 9, 8, 13, 5, tzinfo=UTC)
    payload = [
        _metar(
            "DTTA",
            latitude=36.851,
            longitude=10.227,
            report_time="2026-09-08T11:30:00.000Z",
            wind_speed=4,
        ),
        _metar(
            "DTTA",
            latitude=36.851,
            longitude=10.227,
            report_time="2026-09-08T12:30:00.000Z",
            wind_speed=10,
        ),
        _metar(
            "DTMB",
            latitude=35.758,
            longitude=10.755,
            report_time="2026-09-08T12:30:00.000Z",
            wind_speed=20,
        ),
    ]

    observation = parse_nearest_metar(
        payload,
        Coordinates(latitude=36.8, longitude=10.3),
        retrieved_at,
    )

    assert observation is not None
    assert observation.station_id == "DTTA"
    assert observation.observed_at.isoformat() == "2026-09-08T12:30:00+00:00"
    assert observation.wind_speed_kmh == pytest.approx(18.5)
    assert observation.wind_gust_kmh == pytest.approx(33.3)
    assert observation.pressure_hpa == 1015
    assert observation.pressure_kind == "altimeter_setting"
    assert observation.visibility_m == pytest.approx(9_656)
    assert observation.visibility_is_lower_bound is True
    assert observation.distance_to_spot_km == pytest.approx(8.6, abs=0.2)
    assert observation.is_direct_observation is True
    assert observation.is_spot_observation is False
    assert observation.raw_report.startswith("DTTA")


def test_parse_nearest_metar_rejects_malformed_rows_and_handles_variable_wind() -> None:
    report = _metar(
        "DTTB",
        latitude=37.245,
        longitude=9.791,
        report_time="2026-09-08T12:00:00Z",
    )
    report["wdir"] = "VRB"
    report["visib"] = "not-a-number"
    report["slp"] = 1013.2

    observation = parse_nearest_metar(
        [{"icaoId": "BROKEN"}, None, report],
        Coordinates(latitude=37.2, longitude=9.8),
        datetime(2026, 9, 8, 12, 10, tzinfo=UTC),
    )

    assert observation is not None
    assert observation.station_id == "DTTB"
    assert observation.wind_direction_deg is None
    assert observation.pressure_hpa == 1013.2
    assert observation.pressure_kind == "sea_level_pressure"
    assert observation.visibility_m is None
    assert (
        parse_nearest_metar(
            [{"icaoId": "BROKEN"}],
            Coordinates(latitude=37.2, longitude=9.8),
            datetime(2026, 9, 8, 12, 10, tzinfo=UTC),
        )
        is None
    )


def test_haversine_is_zero_for_same_point_and_symmetric() -> None:
    assert haversine_km(36.8, 10.3, 36.8, 10.3) == pytest.approx(0)
    forward = haversine_km(36.8, 10.3, 35.758, 10.755)
    reverse = haversine_km(35.758, 10.755, 36.8, 10.3)
    assert forward == pytest.approx(reverse)
    assert forward == pytest.approx(123.0, abs=1.0)


@pytest.mark.asyncio
async def test_metar_upstream_failure_degrades_to_an_empty_optional_layer() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        assert "DTTA" in request.url.params["ids"]
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenMeteoClient(http_client, "https://weather.test", "https://marine.test")
        payload = await client._get_optional_observations()

    assert payload == []


@pytest.mark.asyncio
async def test_metar_adapter_accepts_an_array_payload() -> None:
    expected = [{"icaoId": "DTTA"}]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=expected)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenMeteoClient(http_client, "https://weather.test", "https://marine.test")
        payload = await client._get_optional_observations()

    assert payload == expected
