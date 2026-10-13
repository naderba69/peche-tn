from __future__ import annotations

import asyncio
import copy
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from spotdata.domain.models import Coordinates, ForecastDecisionRequest, SpotProfile
from spotdata.services.open_meteo import OpenMeteoClient, parse_open_meteo
from tests.test_open_meteo import _payloads

TZ = ZoneInfo("Africa/Tunis")


def _request() -> ForecastDecisionRequest:
    return ForecastDecisionRequest(
        location=Coordinates(latitude=36.8, longitude=10.3),
        target_date=date(2026, 9, 7),
        spot=SpotProfile(seaward_orientation_deg=90),
    )


def _secondary_marine() -> dict[str, Any]:
    marine, _ = _payloads()
    hourly = copy.deepcopy(marine["hourly"])
    hourly["wave_height"] = [0.41, 0.9, 0.99, 0.99, 0.99, 0.99]
    hourly["wave_period"] = [None, 5.5, None, None, None, None]
    return {"hourly": hourly}


def _secondary_weather() -> dict[str, Any]:
    _, weather = _payloads()
    hourly = copy.deepcopy(weather["hourly"])
    hourly["lightning_potential"] = [None, 120, None, None, None, None]
    hourly["wind_speed_10m"] = [None] * 6  # must not fill anything
    return {"hourly": hourly}


def test_secondary_fills_only_empty_primary_values_and_tags_them() -> None:
    marine, weather = _payloads()
    dataset = parse_open_meteo(
        request=_request(),
        marine=marine,
        weather=weather,
        retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
        secondary_marine=_secondary_marine(),
        secondary_marine_model="meteofrance_wave",
        secondary_weather=_secondary_weather(),
        secondary_weather_model="icon_seamless",
    )
    hour0, hour1, hour2 = dataset.hours[0], dataset.hours[1], dataset.hours[2]
    # Primary value at hour 0 is authoritative and must not be overwritten.
    assert hour0.wave_height_m == 0.5
    assert "wave_height_m" not in hour0.gap_filled_fields
    # Primary gap at hour 1 is filled from the secondary family and tagged.
    assert hour1.wave_height_m == 0.9
    assert "wave_height_m" in hour1.gap_filled_fields
    # Primary wave_period at hour 1 is present (6 s): the secondary 5.5 must NOT replace it.
    assert hour1.wave_period_s == 6
    assert "wave_period_s" not in hour1.gap_filled_fields
    # Weather gap filled; primary wind (not None) untouched by a None secondary.
    assert hour1.lightning_potential_jkg == 120
    assert "lightning_potential_jkg" in hour1.gap_filled_fields
    assert hour1.wind_speed_kmh == 12
    assert hour2.gap_filled_fields == []
    # Provenance is recorded as separate, model-level sources.
    providers = [source.provider for source in dataset.sources]
    assert any("نموذج بحري ثانٍ" in provider for provider in providers)
    assert any("نموذج طقس ثانٍ" in provider for provider in providers)


def test_without_secondary_nothing_is_filled_and_no_extra_sources() -> None:
    marine, weather = _payloads()
    dataset = parse_open_meteo(
        request=_request(),
        marine=marine,
        weather=weather,
        retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
    )
    assert dataset.hours[1].wave_height_m is None
    assert all(hour.gap_filled_fields == [] for hour in dataset.hours)
    assert len(dataset.sources) == 2


def test_gap_summary_is_logged_for_diagnostics(caplog: Any) -> None:
    marine, weather = _payloads()
    with caplog.at_level(logging.INFO, logger="spotdata.services.open_meteo"):
        parse_open_meteo(
            request=_request(),
            marine=marine,
            weather=weather,
            retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
        )
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        message.startswith("forecast gaps") and "wave_height_m" in message for message in messages
    )


def test_client_uses_secondary_models_and_survives_their_failure() -> None:
    marine, weather = _payloads()
    seen_models: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = request.url.params.get("models")
        seen_models.append(model)
        host = request.url.host
        if model == "meteofrance_wave":
            return httpx.Response(200, json=_secondary_marine())
        if model == "icon_seamless":
            # Secondary weather family is down: the primary forecast must still succeed.
            return httpx.Response(500, json={"error": True})
        if "marine" in host:
            return httpx.Response(200, json=marine)
        return httpx.Response(200, json=weather)

    async def run() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.test/v1/forecast",
                marine_url="https://marine.open-meteo.test/v1/marine",
                observation_url="https://metar.test/api",
                secondary_marine_model="meteofrance_wave",
                secondary_weather_model="icon_seamless",
            )
            return await client.forecast_dataset(_request())

    dataset = asyncio.run(run())
    assert "meteofrance_wave" in seen_models
    assert "icon_seamless" in seen_models
    assert dataset.hours[1].wave_height_m == 0.9
    assert len(dataset.hours) == 6
    # One secondary marine source; the failed weather secondary is absent, not invented.
    assert sum("نموذج بحري ثانٍ" in source.provider for source in dataset.sources) == 1
    assert not any("نموذج طقس ثانٍ" in source.provider for source in dataset.sources)


def test_client_without_secondary_models_sends_no_models_param() -> None:
    marine, weather = _payloads()
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("models"))
        if "marine" in request.url.host:
            return httpx.Response(200, json=marine)
        return httpx.Response(200, json=weather)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenMeteoClient(
                http_client=http,
                weather_url="https://api.open-meteo.test/v1/forecast",
                marine_url="https://marine.open-meteo.test/v1/marine",
                observation_url="https://metar.test/api",
            )
            await client.forecast_dataset(_request())

    asyncio.run(run())
    assert seen and all(model is None for model in seen)
