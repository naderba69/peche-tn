from __future__ import annotations

import math
from typing import Any

import httpx
import pytest

from spotdata.domain.models import Coordinates, SpotProfile
from spotdata.services.aviation_weather import haversine_km
from spotdata.services.copernicus_water import (
    CopernicusWaterClient,
    destination_point,
    parse_feature_value,
    web_mercator_tile_pixel,
)


def _feature(variable: str, value: float | None, unit: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "lat": 36.801,
                    "lon": 10.311,
                    "variableId": variable,
                    "value": value,
                    "units": unit,
                },
            }
        ],
    }


def test_fixed_sample_follows_declared_seaward_axis_and_tile_math() -> None:
    latitude, longitude = destination_point(36.8, 10.3, 90.0, 1_000.0)
    assert latitude == pytest.approx(36.8, abs=0.0001)
    assert longitude > 10.3
    assert haversine_km(36.8, 10.3, latitude, longitude) == pytest.approx(1.0, abs=0.001)
    col, row, pixel_i, pixel_j = web_mercator_tile_pixel(latitude, longitude, 10)
    assert (col, row) == (541, 399)
    assert 0 <= pixel_i <= 255
    assert 0 <= pixel_j <= 255


def test_feature_parser_preserves_units_and_treats_null_as_unknown() -> None:
    value = parse_feature_value(_feature("TUR", 1.25, "FNU"), "TUR")
    assert value is not None
    assert value.value == 1.25
    assert value.units == "FNU"
    assert parse_feature_value(_feature("TUR", None, "FNU"), "TUR") is None
    assert parse_feature_value(_feature("TUR", math.nan, "FNU"), "TUR") is None
    with pytest.raises(ValueError, match="unexpected unit"):
        parse_feature_value(_feature("TUR", 1.25, "NTU"), "TUR")


@pytest.mark.asyncio
async def test_client_selects_latest_valid_fixed_pixel_then_reads_same_day_variables() -> None:
    tur_requests = 0
    selected_time = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tur_requests, selected_time
        params = request.url.params
        variable = params["LAYER"].split("/")[-1]
        assert params["REQUEST"] == "GetFeatureInfo"
        assert params["TILEMATRIXSET"] == "EPSG:3857"
        if variable == "TUR":
            tur_requests += 1
            if tur_requests < 3:
                return httpx.Response(200, json=_feature("TUR", None, "FNU"))
            selected_time = params["TIME"]
            return httpx.Response(200, json=_feature("TUR", 0.3159, "FNU"))
        assert params["TIME"] == selected_time
        if variable == "SPM":
            return httpx.Response(200, json=_feature("SPM", 0.1841, "g m-3"))
        return httpx.Response(200, json=_feature("CHL", 0.5391, "mg m-3"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        context = await CopernicusWaterClient(http).coastal_context(
            Coordinates(latitude=36.8, longitude=10.3),
            SpotProfile(seaward_orientation_deg=90.0),
        )

    assert context.availability == "available"
    assert tur_requests == 3
    assert context.data_kind == "remote_sensing_estimate"
    assert context.sample_distance_from_spot_m == pytest.approx(1_000, abs=1)
    assert context.turbidity_fnu == 0.3159
    assert context.turbidity_unit == "FNU"
    assert context.suspended_particulate_matter_g_m3 == 0.1841
    assert context.suspended_particulate_matter_unit == "g/m³"
    assert context.chlorophyll_a_mg_m3 == 0.5391
    assert context.chlorophyll_a_unit == "mg/m³"
    assert context.affects_final_decision is False
    assert context.is_forecast is False


@pytest.mark.asyncio
async def test_client_does_not_label_older_value_latest_when_newer_date_is_unresolved() -> None:
    tur_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tur_requests
        variable = request.url.params["LAYER"].split("/")[-1]
        assert variable == "TUR"
        tur_requests += 1
        if tur_requests == 1:
            return httpx.Response(503, text="temporary upstream failure")
        return httpx.Response(200, json=_feature("TUR", 0.3159, "FNU"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        context = await CopernicusWaterClient(http).coastal_context(
            Coordinates(latitude=36.8, longitude=10.3),
            SpotProfile(seaward_orientation_deg=90.0),
        )

    assert tur_requests == 2
    assert context.availability == "unavailable"
    assert context.valid_time is None
    assert context.turbidity_fnu is None
    assert "أحدث استعادة" in context.reason_ar


@pytest.mark.asyncio
async def test_client_fails_safe_to_explicit_unknown_after_fixed_search_window() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_feature("TUR", None, "FNU"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        context = await CopernicusWaterClient(http).coastal_context(
            Coordinates(latitude=36.8, longitude=10.3),
            SpotProfile(seaward_orientation_deg=90.0),
        )

    assert calls == 10
    assert context.availability == "unavailable"
    assert context.valid_time is None
    assert context.turbidity_fnu is None
    assert "Unknown" in context.reason_ar
