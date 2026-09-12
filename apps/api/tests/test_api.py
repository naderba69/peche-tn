from collections.abc import Callable
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from spotdata.domain.models import ForecastDataset
from spotdata.main import app

TZ = ZoneInfo("Africa/Tunis")


def test_health_and_methodology() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["version"] == "1.10.0"
        assert health.json()["engine_version"] == "1.6.8"
        assert health.json()["schema_version"] == "3.9"
        assert health.json()["upstream_cache"]["scope"] == "process_memory"
        assert health.json()["satellite_cache"]["scope"] == "process_memory"
        assert health.headers["X-Request-ID"]
        method = client.get("/api/methodology")
        assert method.status_code == 200
        assert method.json()["llm_in_decision_path"] is False
        assert method.json()["factor_coverage"]["audited_total"] == 63
        assert any("low-confidence proxies" in item for item in method.json()["principles"])
        assert any("METAR" in item for item in method.json()["free_data_providers"])
        assert any("Sentinel-2" in item for item in method.json()["free_data_providers"])
        catalog = client.get("/api/methodology/factors")
        assert catalog.status_code == 200
        assert catalog.json()["coverage"]["source_claimed_total"] == 62
        assert len(catalog.json()["factors"]) == 63


def test_offline_evaluate_endpoint(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/evaluate",
            json=dataset_factory(
                count=96,
                start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
            ).model_dump(mode="json"),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "go"
    assert body["score_is_success_probability"] is False
    assert body["schema_version"] == "3.9"
    assert body["decision_reason_code"] == "safe_window"
    assert len(body["factor_assessments"]) == 63
    assert body["engine_version"] == "1.6.8"
    assert body["field_feasibility"]["is_direct_observation"] is False
    assert body["field_feasibility"]["confidence"] <= 50
    assert body["factor_coverage"]["audited_total"] == 63
    assert body["current_weather_observation"] is None
    assert body["observation_comparison"]["status"] == "unavailable"
    assert "forecast" in body["hourly"][0]
    assert "observed" not in body["hourly"][0]
    assert all(factor["is_direct_observation"] is False for factor in body["hourly"][0]["factors"])
    assert body["sunrise"] == "2026-09-07T06:00:00+01:00"
    assert body["sunset"] == "2026-09-07T18:30:00+01:00"
    assert body["recommended_windows"]


def test_evaluate_reports_insufficient_data(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/decisions/evaluate",
            json=dataset_factory(count=2).model_dump(mode="json"),
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "insufficient_forecast_data"


def test_optional_satellite_failure_cannot_break_forecast_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    payload = {
        "location": {"latitude": 36.8, "longitude": 10.3},
        "target_date": datetime.now(TZ).date().isoformat(),
        "spot": {"seaward_orientation_deg": 90},
    }
    with TestClient(app) as client:
        app.state.open_meteo.forecast_dataset = AsyncMock(return_value=dataset_factory())
        app.state.copernicus_water.coastal_context = AsyncMock(
            side_effect=RuntimeError("optional service failure")
        )
        response = client.post("/api/v1/decisions/forecast", json=payload)

    assert response.status_code == 200
    assert response.json()["coastal_water_context"]["availability"] == "unavailable"
    assert response.json()["coastal_water_context"]["turbidity_unit"] == "FNU"
    assert "Unknown" in response.json()["coastal_water_context"]["reason_ar"]
    assert response.json()["decision"] in {"go", "no_go"}


def test_forecast_rejects_past_date_without_network() -> None:
    payload = {
        "location": {"latitude": 36.8, "longitude": 10.3},
        "target_date": "2020-01-01",
        "spot": {"seaward_orientation_deg": 90},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/decisions/forecast", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "target_date_out_of_range"


def test_validation_rejects_location_outside_tunisia() -> None:
    payload = {
        "location": {"latitude": 51.5, "longitude": -0.1},
        "target_date": datetime.now(TZ).date().isoformat(),
        "spot": {"seaward_orientation_deg": 90},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/decisions/forecast", json=payload)
    assert response.status_code == 422


def test_invalid_runtime_gemini_key_is_never_echoed() -> None:
    private_value = "short-private-value"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/gemini/verify",
            headers={"X-Gemini-API-Key": private_value},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_gemini_key_format"
    assert private_value not in response.text
    assert response.headers["Cache-Control"] == "no-store"
