from collections.abc import Callable
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from spotdata.domain.enums import InmCheckStatus
from spotdata.domain.models import (
    AutomatedShoreProfile,
    AutoOrientationResponse,
    Coordinates,
    ForecastDataset,
    InmWarningAudit,
    OrientationEvidence,
    SpotProfile,
)
from spotdata.main import app

TZ = ZoneInfo("Africa/Tunis")


def _inm_audit(status: InmCheckStatus) -> InmWarningAudit:
    now = datetime.now(TZ)
    verified = status in {InmCheckStatus.VERIFIED_CLEAR, InmCheckStatus.WARNING_ACTIVE}
    return InmWarningAudit(
        status=status,
        request_id="test-request",
        checked_at=now,
        http_status_code=200 if verified else None,
        server_date=now if verified else None,
        response_age_seconds=0 if verified else None,
        cache_control="no-cache" if verified else None,
        age_header_seconds=0 if verified else None,
        response_sha256="a" * 64 if verified else None,
        coverage_status="verified_tunisian_coasts" if verified else "unknown",
        coverage_ar="test national coverage" if verified else "unknown",
        reason_code="test_status",
        explanation_ar="Synthetic INM status for unit test.",
    )


def test_health_and_methodology() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["version"] == "1.16.0"
        assert health.json()["engine_version"] == "1.10.2"
        assert health.json()["schema_version"] == "3.20"
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
        assert any(
            "the API fetches forecasts and exposes a request-scoped INM BMS audit" in item
            for item in method.json()["principles"]
        )
        catalog = client.get("/api/methodology/factors")
        assert catalog.status_code == 200
        assert catalog.json()["coverage"]["source_claimed_total"] == 62
        assert len(catalog.json()["factors"]) == 63


def test_arbitrary_dataset_evaluate_endpoint_is_not_public() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/decisions/evaluate", json={})
    assert response.status_code == 404


def test_forecast_endpoint_rejects_client_supplied_environmental_bundle() -> None:
    payload = {
        "location": {"latitude": 36.8, "longitude": 10.3},
        "target_date": datetime.now(TZ).date().isoformat(),
        "spot": {"seaward_orientation_deg": 90},
        "open_meteo_data": {"marine": {"hourly": {}}, "weather": {"hourly": {}}},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/decisions/forecast", json=payload)
    assert response.status_code == 422


def test_forecast_preflight_returns_binary_no_go_without_verified_automated_spot_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "location": {"latitude": 36.8, "longitude": 10.3},
        "target_date": datetime.now(TZ).date().isoformat(),
        "spot": {
            "seaward_orientation_deg": 90,
            "orientation_source": "overpass",
            "orientation_evidence": {
                "orientation_deg": 90,
                "coastline_tangent_deg": 0,
                "coastline_distance_m": 43,
                "search_radius_m": 3000,
                "segments_used": 4,
                "confidence": "high",
                "provider": "OpenStreetMap Overpass",
                "server": "https://overpass-api.de/api/interpreter",
                "calculated_at": datetime.now(TZ).isoformat(),
                "limitations_ar": [],
            },
            "shore_type": "sandy",
            "exposure": "open",
        },
    }
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.coast_orientation,
            "resolve",
            AsyncMock(
                return_value=AutoOrientationResponse(
                    status="unavailable",
                    reasons_ar=["synthetic unavailable map profile"],
                )
            ),
        )
        response = client.post("/api/v1/decisions/forecast", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "no_go"
    assert body["decision_reason_code"] == "critical_data_missing"
    assert body["decision_label_ar"] == "لا تذهب"
    assert body["automated_orientation"]["status"] == "unavailable"
    assert body["sources"] == []
    assert any("اتجاه الساحل" in item for item in body["missing_context_ar"])
    assert not any("نوع الشاطئ" in item for item in body["missing_context_ar"])
    assert "opportunity_score" not in body


def test_forecast_uses_server_fetched_shore_profile_and_keeps_exposure_unknown(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(TZ).date()
    retrieved_at = datetime.now(TZ)
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
        shore_type="sandy",
        exposure=None,
        evidence_feature_id=8123,
        evidence_feature_version=4,
        evidence_feature_timestamp=retrieved_at,
        feature_distance_m=12,
        raw_tags={"natural": "beach", "surface": "sand"},
        confidence="high",
        limitations_ar=["test map tags"],
    )
    profile = AutoOrientationResponse(
        status="resolved",
        orientation_deg=135,
        evidence=evidence,
        shore_profile=shore,
        reasons_ar=["test map profile"],
    )
    dataset = dataset_factory(
        target_date=today,
        count=96,
        start_at=datetime.combine(today, datetime.min.time(), TZ),
    )
    forecast_mock = AsyncMock(return_value=dataset)

    from spotdata.services.copernicus_water import unavailable_water_context

    location = Coordinates(latitude=36.8, longitude=10.3, name="اختبار")
    verified_spot = SpotProfile(
        seaward_orientation_deg=135,
        orientation_source="overpass",
        orientation_evidence=evidence,
        shore_type="sandy",
        exposure=None,
    )
    water = unavailable_water_context(location, verified_spot, "synthetic test context")
    payload = {
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
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.coast_orientation, "resolve", AsyncMock(return_value=profile))
        monkeypatch.setattr(app.state.open_meteo, "forecast_dataset", forecast_mock)
        monkeypatch.setattr(
            app.state.copernicus_water,
            "coastal_context",
            AsyncMock(return_value=water),
        )
        monkeypatch.setattr(
            app.state.inm_warnings,
            "check",
            AsyncMock(return_value=_inm_audit(InmCheckStatus.VERIFIED_CLEAR)),
        )
        response = client.post("/api/v1/decisions/forecast", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "go"
    assert body["decision_reason_code"] == "safe_window"
    assert body["decision_label_ar"] == "اذهب"
    assert body["spot_profile"]["seaward_orientation_deg"] == 135
    assert body["automated_shore_profile"]["evidence_feature_id"] == 8123
    assert body["official_warning_check"]["status"] == "verified_clear"
    forecast_mock.assert_awaited_once()
    normalized_request = forecast_mock.await_args.args[0]
    assert normalized_request.angler.session_hours == 24
    assert normalized_request.angler.experience is None


def test_forecast_keeps_weather_analysis_but_fails_closed_when_inm_is_unverified(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(TZ).date()
    now = datetime.now(TZ)
    evidence = OrientationEvidence(
        orientation_deg=135,
        coastline_tangent_deg=45,
        coastline_distance_m=37,
        search_radius_m=3000,
        segments_used=4,
        confidence="high",
        provider="OpenStreetMap Overpass",
        server="https://overpass.test/api",
        calculated_at=now,
        limitations_ar=["synthetic"],
    )
    shore = AutomatedShoreProfile(
        status="resolved",
        retrieved_at=now,
        shore_type="sandy",
        exposure=None,
        evidence_feature_id=88,
        evidence_feature_version=1,
        evidence_feature_timestamp=now,
        feature_distance_m=12,
        raw_tags={"natural": "beach", "surface": "sand"},
        confidence="high",
        limitations_ar=["synthetic"],
    )
    profile = AutoOrientationResponse(
        status="resolved",
        orientation_deg=135,
        evidence=evidence,
        shore_profile=shore,
        reasons_ar=["synthetic"],
    )
    dataset = dataset_factory(
        target_date=today,
        count=96,
        start_at=datetime.combine(today, datetime.min.time(), TZ),
    )
    location = Coordinates(latitude=36.8, longitude=10.3, name="test")
    spot = SpotProfile(
        seaward_orientation_deg=135,
        orientation_source="overpass",
        orientation_evidence=evidence,
        shore_type="sandy",
        exposure=None,
    )
    from spotdata.services.copernicus_water import unavailable_water_context

    payload = {
        "location": {"latitude": 36.8, "longitude": 10.3, "name": "test"},
        "target_date": today.isoformat(),
        "spot": {"seaward_orientation_deg": 90, "shore_type": "rocky"},
        "angler": {"experience": "intermediate", "target_species": "general", "session_hours": 24},
    }
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.coast_orientation, "resolve", AsyncMock(return_value=profile))
        forecast_mock = AsyncMock(return_value=dataset)
        monkeypatch.setattr(app.state.open_meteo, "forecast_dataset", forecast_mock)
        monkeypatch.setattr(
            app.state.copernicus_water,
            "coastal_context",
            AsyncMock(return_value=unavailable_water_context(location, spot, "test")),
        )
        inm_mock = AsyncMock(side_effect=RuntimeError("synthetic verifier crash"))
        monkeypatch.setattr(app.state.inm_warnings, "check", inm_mock)
        response = client.post("/api/v1/decisions/forecast", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "no_go"
    assert body["decision_reason_code"] == "official_warning_unverified"
    assert body["official_warning_check"]["status"] == "unverified"
    assert body["official_warning_check"]["reason_code"] == "verifier_internal_error"
    assert body["hourly"]
    assert body["sources"]
    assert body["recommended_windows"] == []
    forecast_mock.assert_awaited_once()
    inm_mock.assert_awaited_once()


@pytest.mark.parametrize("manual_choice", [False, True])
def test_unknown_osm_shore_type_uses_manual_choice_only_when_explicit(
    manual_choice: bool,
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(TZ).date()
    retrieved_at = datetime.now(TZ)
    evidence = OrientationEvidence(
        orientation_deg=121.5,
        coastline_tangent_deg=31.5,
        coastline_distance_m=28,
        search_radius_m=3_000,
        segments_used=5,
        confidence="high",
        provider="OpenStreetMap Overpass",
        server="https://overpass.test/api",
        calculated_at=retrieved_at,
        limitations_ar=["Synthetic orientation evidence."],
    )
    shore = AutomatedShoreProfile(
        status="unavailable",
        retrieved_at=retrieved_at,
        confidence="unknown",
        raw_tags={"natural": "beach"},
        limitations_ar=["No explicit substrate tag in test fixture."],
    )
    map_result = AutoOrientationResponse(
        status="resolved",
        orientation_deg=121.5,
        evidence=evidence,
        shore_profile=shore,
        reasons_ar=["test map geometry; substrate is ambiguous"],
    )
    dataset = dataset_factory(
        target_date=today,
        count=96,
        start_at=datetime.combine(today, datetime.min.time(), TZ),
        spot_updates={"shore_type": None, "exposure": None},
    )
    from spotdata.services.copernicus_water import unavailable_water_context

    location = Coordinates(latitude=36.8, longitude=10.3, name="test")
    spot = SpotProfile(
        seaward_orientation_deg=121.5,
        orientation_source="overpass",
        orientation_evidence=evidence,
        shore_type=None,
        exposure=None,
    )
    forecast_mock = AsyncMock(
        side_effect=lambda request: dataset.model_copy(update={"spot": request.spot})
    )
    with TestClient(app) as client:
        monkeypatch.setattr(
            app.state.coast_orientation, "resolve", AsyncMock(return_value=map_result)
        )
        monkeypatch.setattr(app.state.open_meteo, "forecast_dataset", forecast_mock)
        monkeypatch.setattr(
            app.state.copernicus_water,
            "coastal_context",
            AsyncMock(return_value=unavailable_water_context(location, spot, "test")),
        )
        monkeypatch.setattr(
            app.state.inm_warnings,
            "check",
            AsyncMock(return_value=_inm_audit(InmCheckStatus.VERIFIED_CLEAR)),
        )
        response = client.post(
            "/api/v1/decisions/forecast",
            json={
                "location": {"latitude": 36.8, "longitude": 10.3, "name": "test"},
                "target_date": today.isoformat(),
                "spot": {
                    "shore_type": "sandy",
                    "shore_type_source": "user" if manual_choice else "overpass",
                    "exposure": "open",
                },
                "angler": {"target_species": "general"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["hourly"]) == 24
    assert body["automated_shore_profile"]["raw_tags"] == {"natural": "beach"}
    if manual_choice:
        assert body["spot_profile"]["shore_type"] == "sandy"
        assert body["spot_profile"]["shore_type_source"] == "user"
        assert body["decision_reason_code"] != "critical_data_missing"
        assert body["decision_context_ar"] == []
        assert "نوع الساحل غير محدد" not in body["summary_ar"]
    else:
        assert body["decision"] == "no_go"
        assert body["decision_reason_code"] == "critical_data_missing"
        assert body["recommended_windows"] == []
        assert "نوع الساحل لم يوثّقه OSM" in body["summary_ar"]
        assert body["decision_context_ar"]
        assert "نافذة" in body["decision_context_ar"][0]
        assert body["spot_profile"]["shore_type"] is None
        assert body["spot_profile"]["shore_type_source"] == "unknown"
    assert any(source["provider"] == "OpenStreetMap Overpass" for source in body["sources"])
    forecast_mock.assert_awaited_once()


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
