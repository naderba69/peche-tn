"""Owner-device forecast path: gated by SPOTDATA_DEVICE_KEY, never trusted without it."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from spotdata.api import routes
from spotdata.domain.models import (
    AutomatedShoreProfile,
    AutoOrientationResponse,
    Coordinates,
    OrientationEvidence,
    SpotProfile,
)
from spotdata.main import app
from spotdata.services.copernicus_water import unavailable_water_context

TZ = ZoneInfo("Africa/Tunis")
KEY = "test-owner-key-123"


def _device_bundle(day: datetime) -> dict[str, Any]:
    """Synthetic 24-hour marine + weather JSON in Open-Meteo's shape (not real data)."""
    times = [(day + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(24)]
    marine_hourly: dict[str, Any] = {"time": times}
    for name in (
        "wave_height",
        "wave_period",
        "wave_direction",
        "wind_wave_height",
        "wind_wave_period",
        "wind_wave_direction",
        "swell_wave_height",
        "swell_wave_period",
        "swell_wave_direction",
        "sea_surface_temperature",
        "ocean_current_velocity",
        "ocean_current_direction",
        "sea_level_height_msl",
    ):
        marine_hourly[name] = [0.4] * 24
    weather_hourly: dict[str, Any] = {"time": times}
    for name in (
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "dew_point_2m",
        "cloud_cover",
        "shortwave_radiation",
        "uv_index",
        "lightning_potential",
        "precipitation",
        "precipitation_probability",
        "weather_code",
        "pressure_msl",
        "visibility",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "cape",
    ):
        weather_hourly[name] = [10] * 24
    weather_hourly["pressure_msl"] = [1014] * 24
    weather_hourly["visibility"] = [20_000] * 24
    return {
        "marine": {"hourly": marine_hourly},
        "weather": {"hourly": weather_hourly},
        "retrieved_at": datetime.now(TZ).isoformat(),
    }


def _payload(bundle: dict[str, Any] | None) -> dict[str, Any]:
    today = datetime.now(TZ).date()
    body: dict[str, Any] = {
        "location": {"latitude": 36.8, "longitude": 10.3, "name": "اختبار"},
        "target_date": today.isoformat(),
        "spot": {
            "seaward_orientation_deg": 12,
            "orientation_source": "manual",
            "shore_type": "rocky",
            "exposure": "sheltered",
        },
        "angler": {"experience": "intermediate", "target_species": "general", "session_hours": 24},
    }
    if bundle is not None:
        body["device_forecast"] = bundle
    return body


def _profile(retrieved_at: datetime) -> AutoOrientationResponse:
    evidence = OrientationEvidence(
        orientation_deg=135,
        coastline_tangent_deg=45,
        coastline_distance_m=37,
        search_radius_m=3_000,
        segments_used=4,
        confidence="high",
        provider="OpenStreetMap Overpass",
        server="https://overpass.test/api",
        calculated_at=retrieved_at,
        limitations_ar=["test geometry"],
    )
    shore = AutomatedShoreProfile(
        status="resolved",
        retrieved_at=retrieved_at,
        shore_type="rocky",
        exposure=None,
        evidence_feature_id=8123,
        evidence_feature_version=4,
        evidence_feature_timestamp=retrieved_at,
        feature_distance_m=12,
        raw_tags={"natural": "coastline"},
        confidence="high",
        limitations_ar=["test map tags"],
    )
    return AutoOrientationResponse(
        status="resolved",
        orientation_deg=135,
        evidence=evidence,
        shore_profile=shore,
        reasons_ar=["test map profile"],
    )


def _set_key(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    monkeypatch.setattr(routes, "settings", SimpleNamespace(device_access_key=value))


def test_request_spec_returns_the_same_upstream_parameters_as_the_server() -> None:
    today = datetime.now(TZ).date()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/forecast/request-spec",
            params={"latitude": 36.8, "longitude": 10.3, "target_date": today.isoformat()},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["marine_params"]["cell_selection"] == "sea"
    assert "wave_height" in body["marine_params"]["hourly"]
    assert "wind_gusts_10m" in body["weather_params"]["hourly"]
    assert body["include_current_observation"] is True


def test_device_bundle_without_configured_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, None)
    today = datetime.now(TZ)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/forecast",
            json=_payload(_device_bundle(today.replace(hour=0, minute=0, second=0, microsecond=0))),
            headers={"X-Device-Key": "anything"},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "device_key_invalid"


def test_device_bundle_with_wrong_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, KEY)
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/forecast",
            json=_payload(_device_bundle(today)),
            headers={"X-Device-Key": "wrong"},
        )
    assert response.status_code == 403


def test_device_bundle_that_does_not_cover_the_day_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_key(monkeypatch, KEY)
    other_day = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=30
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/forecast",
            json=_payload(_device_bundle(other_day)),
            headers={"X-Device-Key": KEY},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "device_forecast_invalid"


def test_valid_device_bundle_is_used_without_any_server_open_meteo_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_key(monkeypatch, KEY)
    now = datetime.now(TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    http_get = AsyncMock(side_effect=AssertionError("server must not call Open-Meteo"))
    monkeypatch.setattr(app.state.open_meteo._http, "get", http_get)
    monkeypatch.setattr(
        app.state.open_meteo,
        "_get_optional_observations",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        app.state.coast_orientation, "resolve", AsyncMock(return_value=_profile(now))
    )
    water = unavailable_water_context(
        Coordinates(latitude=36.8, longitude=10.3),
        SpotProfile(seaward_orientation_deg=135),
        "synthetic test context",
    )
    monkeypatch.setattr(
        app.state.copernicus_water, "coastal_context", AsyncMock(return_value=water)
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/forecast",
            json=_payload(_device_bundle(today)),
            headers={"X-Device-Key": KEY},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "decision" in body
    http_get.assert_not_awaited()
    assert "device_forecast" not in body


def test_device_dataset_labels_its_origin_in_sources() -> None:
    import asyncio

    from spotdata.services.open_meteo import OpenMeteoClient

    now = datetime.now(TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    bundle = _device_bundle(today)
    client = OpenMeteoClient(AsyncMock(), "https://w.test", "https://m.test")
    request = _request_for_today()
    dataset = asyncio.run(
        client.dataset_from_device_bundle(
            request,
            bundle["marine"],
            bundle["weather"],
            now,
        )
    )
    providers = [source.provider for source in dataset.sources]
    assert providers, "device dataset must report its sources"
    assert all("جُلبت من جهاز المالك" in name for name in providers)


def _request_for_today() -> Any:
    from spotdata.domain.models import ForecastDecisionRequest

    return ForecastDecisionRequest(
        location=Coordinates(latitude=36.8, longitude=10.3),
        target_date=datetime.now(TZ).date(),
        spot=SpotProfile(seaward_orientation_deg=90),
    )
