import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from spotdata.domain.models import (
    Coordinates,
    ForecastDecisionRequest,
    OpenMeteoClientPayload,
    SpotProfile,
)
from spotdata.services.cache import AsyncTTLCache
from spotdata.services.open_meteo import OpenMeteoClient, UpstreamDataError, parse_open_meteo

TZ = ZoneInfo("Africa/Tunis")


def _payloads() -> tuple[dict[str, object], dict[str, object]]:
    times = [f"2026-09-07T{hour:02d}:00" for hour in range(6)]
    marine = {
        "hourly": {
            "time": times,
            "wave_height": [0.5, None, 0.6, 0.7, 0.8, 0.7],
            "wave_period": [6, 6, 6, 6, 6, 6],
            "wave_direction": [90] * 6,
            "wind_wave_height": [0.25] * 6,
            "wind_wave_period": [4.5] * 6,
            "wind_wave_direction": [110] * 6,
            "swell_wave_height": [0.3] * 6,
            "swell_wave_period": [7] * 6,
            "swell_wave_direction": [90] * 6,
            "sea_surface_temperature": [22] * 6,
            "ocean_current_velocity": [0.4] * 6,
            "ocean_current_direction": [0] * 6,
            "sea_level_height_msl": [0, 0.1, 0.2, 0.1, 0, -0.1],
        }
    }
    weather = {
        "hourly": {
            "time": times,
            "temperature_2m": [24] * 6,
            "apparent_temperature": [25] * 6,
            "relative_humidity_2m": [60] * 6,
            "dew_point_2m": [16] * 6,
            "cloud_cover": [20] * 6,
            "shortwave_radiation": [350] * 6,
            "uv_index": [4.5] * 6,
            "lightning_potential": [None] * 6,
            "precipitation": [0] * 6,
            "precipitation_probability": [0] * 6,
            "weather_code": [1] * 6,
            "pressure_msl": [1014] * 6,
            "visibility": [20_000] * 6,
            "wind_speed_10m": [12] * 6,
            "wind_direction_10m": [90] * 6,
            "wind_gusts_10m": [18] * 6,
            "cape": [10] * 6,
        },
        "daily": {
            "time": ["2026-09-06", "2026-09-07", "2026-09-08"],
            "sunrise": ["2026-09-06T05:53", "2026-09-07T05:54", "2026-09-08T05:55"],
            "sunset": ["2026-09-06T18:39", "2026-09-07T18:38", "2026-09-08T18:37"],
        },
    }
    return marine, weather


def _request() -> ForecastDecisionRequest:
    return ForecastDecisionRequest(
        location=Coordinates(latitude=36.8, longitude=10.3),
        target_date=date(2026, 9, 7),
        spot=SpotProfile(seaward_orientation_deg=90),
    )


def test_parser_aligns_hours_preserves_missing_and_picks_sun_by_date() -> None:
    marine, weather = _payloads()
    dataset = parse_open_meteo(
        request=_request(),
        marine=marine,
        weather=weather,
        retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
    )
    assert len(dataset.hours) == 6
    assert dataset.hours[1].wave_height_m is None
    assert dataset.hours[1].wind_speed_kmh == 12
    assert dataset.hours[0].wind_wave_height_m == 0.25
    assert dataset.hours[0].wind_wave_direction_deg == 110
    assert dataset.hours[0].swell_direction_deg == 90
    assert dataset.hours[0].apparent_temperature_c == 25
    assert dataset.hours[0].dew_point_c == 16
    assert dataset.hours[0].cloud_cover_pct == 20
    assert dataset.hours[0].shortwave_radiation_wm2 == 350
    assert dataset.hours[0].uv_index == 4.5
    assert dataset.hours[0].lightning_potential_jkg is None
    assert dataset.sunrise is not None and dataset.sunrise.hour == 5
    assert dataset.sunset is not None and dataset.sunset.minute == 38
    assert len(dataset.sources) == 2
    assert all(source.data_kind == "model_forecast" for source in dataset.sources)
    assert dataset.sources[0].horizontal_resolution_km == 8
    assert "wind_wave_height" in dataset.sources[0].variables
    assert "swell_wave_direction" in dataset.sources[0].variables
    assert any("فصل السويل" in item for item in dataset.sources[0].limitations_ar)
    assert any("GFS-Wave" in item for item in dataset.sources[0].limitations_ar)
    assert any("GFS أو ECMWF أو ICON" in item for item in dataset.sources[1].limitations_ar)


def test_parser_keeps_direct_station_observation_as_a_separate_source() -> None:
    marine, weather = _payloads()
    metar = [
        {
            "icaoId": "DTTA",
            "name": "Tunis/Carthage Intl",
            "lat": 36.851,
            "lon": 10.227,
            "elev": 7,
            "reportTime": "2026-09-07T00:00:00Z",
            "rawOb": "DTTA 070000Z 09008KT 9999 FEW020 24/16 Q1014",
            "wspd": 8,
            "wgst": None,
            "wdir": 90,
            "temp": 24,
            "dewp": 16,
            "altim": 1014,
            "visib": "6+",
        }
    ]
    dataset = parse_open_meteo(
        request=_request(),
        marine=marine,
        weather=weather,
        metar=metar,
        retrieved_at=datetime(2026, 9, 7, 1, tzinfo=TZ),
    )

    assert dataset.current_weather_observation is not None
    assert dataset.current_weather_observation.station_id == "DTTA"
    assert dataset.current_weather_observation.is_spot_observation is False
    assert len(dataset.sources) == 3
    assert dataset.sources[-1].data_kind.value == "direct_observation"
    assert any("محطة مطار" in item for item in dataset.sources[-1].limitations_ar)


def test_parser_fails_when_no_common_times() -> None:
    marine, weather = _payloads()
    weather["hourly"]["time"] = ["2026-09-08T00:00"]  # type: ignore[index]
    with pytest.raises(UpstreamDataError, match="ساعات مشتركة"):
        parse_open_meteo(
            request=_request(),
            marine=marine,
            weather=weather,
            retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
        )


def test_get_json_retries_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spotdata.services.open_meteo._RETRY_DELAYS_SECONDS", (0.0, 0.01, 0.02, 0.03)
    )
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"ok": True})

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            return await client._get_json("https://api.open-meteo.com/v1/forecast", {}, "الطقس")

    payload = asyncio.run(run())
    assert payload == {"ok": True}
    assert calls["count"] == 3


def test_get_json_raises_after_repeated_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spotdata.services.open_meteo._RETRY_DELAYS_SECONDS", (0.0, 0.01, 0.02, 0.03)
    )
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(429)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            await client._get_json("https://api.open-meteo.com/v1/forecast", {}, "الطقس")

    with pytest.raises(UpstreamDataError, match="تعذر جلب بيانات الطقس"):
        asyncio.run(run())
    assert calls["count"] == 4


def test_forecast_dataset_serves_stale_bundle_when_upstream_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spotdata.services.open_meteo._RETRY_DELAYS_SECONDS", (0.0, 0.01, 0.02, 0.03)
    )
    marine_payload, weather_payload = _payloads()
    state = {"mode": "ok"}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["mode"] == "fail":
            return httpx.Response(429)
        if "marine" in request.url.host:
            return httpx.Response(200, json=marine_payload)
        return httpx.Response(200, json=weather_payload)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            client.cache = AsyncTTLCache(ttl_seconds=0.0)
            first = await client.forecast_dataset(_request())
            assert len(first.hours) == 6
            state["mode"] = "fail"
            second = await client.forecast_dataset(_request())
            assert len(second.hours) == 6
            assert second.sources[0].retrieved_at == first.sources[0].retrieved_at

    asyncio.run(run())


def test_forecast_dataset_raises_without_stale_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            client.cache = AsyncTTLCache(ttl_seconds=0.0)
            await client.forecast_dataset(_request())

    with pytest.raises(UpstreamDataError):
        asyncio.run(run())


def _client_request_with_payload(marine: dict, weather: dict) -> ForecastDecisionRequest:
    request = _request()
    return ForecastDecisionRequest(
        location=request.location,
        target_date=request.target_date,
        spot=request.spot,
        open_meteo_data=OpenMeteoClientPayload(marine=marine, weather=weather),
    )


def test_forecast_dataset_uses_client_payload_and_never_touches_upstream() -> None:
    # المتصفح جلب Open-Meteo؛ يجب ألا يُجري الخادم أي طلب HTTP للطقس/البحر.
    marine_payload, weather_payload = _payloads()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unexpected upstream call for a client-supplied payload")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            dataset = await client.forecast_dataset(
                _client_request_with_payload(marine_payload, weather_payload)
            )
            assert len(dataset.hours) == 6
            assert all(source.data_kind.value == "model_forecast" for source in dataset.sources)
            assert any(
                "متصفح المستخدم" in item
                for source in dataset.sources
                for item in source.limitations_ar
            )

    asyncio.run(run())


def test_forecast_dataset_falls_back_to_server_when_client_payload_unusable() -> None:
    # حزمة المتصفح بلا ساعات مشتركة؛ يجب الرجوع للجلب الخادمي بشفافية.
    marine_bad, weather_bad = _payloads()
    weather_bad["hourly"]["time"] = ["2026-09-08T00:00"]  # type: ignore[index]
    marine_good, weather_good = _payloads()

    def handler(request: httpx.Request) -> httpx.Response:
        if "marine" in request.url.host:
            return httpx.Response(200, json=marine_good)
        return httpx.Response(200, json=weather_good)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.com/v1/forecast",
                marine_url="https://marine-api.open-meteo.com/v1/marine",
            )
            dataset = await client.forecast_dataset(
                _client_request_with_payload(marine_bad, weather_bad)
            )
            assert len(dataset.hours) == 6
            assert not any(
                "متصفح المستخدم" in item
                for source in dataset.sources
                for item in source.limitations_ar
            )

    asyncio.run(run())
