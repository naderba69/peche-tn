from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx

from spotdata.domain.models import CoastalWaterContext, Coordinates, SpotProfile
from spotdata.services.aviation_weather import haversine_km
from spotdata.services.cache import AsyncTTLCache

LOGGER = logging.getLogger(__name__)

WMTS_URL = "https://wmts.marine.copernicus.eu/teroWmts"
PRODUCT_ID = "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205"
DATASET_ID = "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107"
TILE_MATRIX_SET = "EPSG:3857"
TILE_ZOOM = 10
TILE_SIZE = 256
SAMPLE_DISTANCE_M = 1_000.0
SEARCH_DAYS = 10
EARTH_RADIUS_M = 6_371_008.8

_VARIABLE_STYLES = {
    "TUR": "cmap:viridis",
    "SPM": "cmap:dense",
    "CHL": "cmap:algae",
}
_EXPECTED_UNITS = {
    "TUR": "FNU",
    "SPM": "g m-3",
    "CHL": "mg m-3",
}


def unavailable_water_context(
    location: Coordinates,
    spot: SpotProfile,
    reason_ar: str,
) -> CoastalWaterContext:
    """Build explicit Unknown context while retaining fixed-sample provenance."""
    sample_latitude, sample_longitude = destination_point(
        location.latitude,
        location.longitude,
        spot.seaward_orientation_deg,
        SAMPLE_DISTANCE_M,
    )
    sample_distance = (
        haversine_km(
            location.latitude,
            location.longitude,
            sample_latitude,
            sample_longitude,
        )
        * 1_000
    )
    return CoastalWaterContext(
        availability="unavailable",
        sample_latitude=sample_latitude,
        sample_longitude=sample_longitude,
        sample_distance_from_spot_m=round(sample_distance, 1),
        retrieved_at=datetime.now(UTC),
        search_days=SEARCH_DAYS,
        reason_ar=reason_ar,
    )


@dataclass(frozen=True, slots=True)
class _FeatureValue:
    value: float
    latitude: float
    longitude: float
    units: str


class CopernicusWaterClient:
    """Read optional Sentinel-2 ocean-colour context from the public Copernicus WMTS.

    One fixed point is sampled 1 km along the declared seaward axis. The adapter looks
    backwards for the latest valid daily TUR pixel and then reads SPM and CHL at exactly
    the same point and date. It never searches sideways for a favourable/valid pixel,
    fills gaps, turns the retrieval into a forecast, or affects the decision engine.
    """

    def __init__(self, http_client: httpx.AsyncClient, wmts_url: str = WMTS_URL) -> None:
        self._http = http_client
        self._wmts_url = wmts_url
        self.cache: AsyncTTLCache[tuple[float, float, float, date], CoastalWaterContext] = (
            AsyncTTLCache(ttl_seconds=21_600, max_entries=256)
        )

    async def coastal_context(
        self,
        location: Coordinates,
        spot: SpotProfile,
    ) -> CoastalWaterContext:
        retrieved_date = datetime.now(UTC).date()
        key = (
            round(location.latitude, 4),
            round(location.longitude, 4),
            round(spot.seaward_orientation_deg, 1),
            retrieved_date,
        )
        return await self.cache.get_or_create(
            key,
            lambda: self._resolve(location, spot, retrieved_date),
        )

    async def _resolve(
        self,
        location: Coordinates,
        spot: SpotProfile,
        retrieved_date: date,
    ) -> CoastalWaterContext:
        retrieved_at = datetime.now(UTC)
        sample_latitude, sample_longitude = destination_point(
            location.latitude,
            location.longitude,
            spot.seaward_orientation_deg,
            SAMPLE_DISTANCE_M,
        )
        sample_distance = (
            haversine_km(
                location.latitude,
                location.longitude,
                sample_latitude,
                sample_longitude,
            )
            * 1_000
        )
        unresolved_dates = 0
        start_date = retrieved_date
        selected_date: date | None = None
        turbidity: _FeatureValue | None = None
        unavailable_reason: str | None = None
        for offset in range(SEARCH_DAYS):
            candidate_date = start_date - timedelta(days=offset)
            try:
                candidate = await self._feature_value(
                    "TUR", candidate_date, sample_latitude, sample_longitude
                )
            except httpx.HTTPStatusError as exc:
                # WMTS commonly returns 400/404 while a requested daily layer has not
                # been published. That is an explicit unavailable date, not a valid zero.
                if exc.response.status_code in {400, 404}:
                    continue
                unresolved_dates += 1
                LOGGER.debug("Copernicus WMTS TUR date unresolved: %s", exc)
                continue
            except (httpx.HTTPError, ValueError) as exc:
                unresolved_dates += 1
                LOGGER.debug("Copernicus WMTS TUR date unresolved: %s", exc)
                continue
            if candidate is not None:
                if unresolved_dates:
                    unavailable_reason = "وُجدت قيمة أقدم لكن تعذر التحقق من تاريخ أحدث؛ لم تُعتمد كي لا تُوصف خطأً بأنها أحدث استعادة."
                    break
                selected_date = candidate_date
                turbidity = candidate
                break

        if selected_date is None or turbidity is None:
            if unavailable_reason is not None:
                detail = unavailable_reason
            elif unresolved_dates == SEARCH_DAYS:
                detail = "تعذر الوصول إلى WMTS العام أو تحليل استجابته."
            elif unresolved_dates:
                detail = "لم توجد قيمة TUR صالحة في التواريخ المتحققة وتعذر حسم تواريخ أخرى؛ بقي السياق Unknown."
            else:
                detail = "لا توجد قيمة TUR صالحة خلال نافذة البحث؛ السحب والظل والوهج والبكسل المختلط قد تنتج Unknown."
            return CoastalWaterContext(
                availability="unavailable",
                sample_latitude=sample_latitude,
                sample_longitude=sample_longitude,
                sample_distance_from_spot_m=round(sample_distance, 1),
                retrieved_at=retrieved_at,
                search_days=SEARCH_DAYS,
                reason_ar=detail,
            )

        spm_result, chlorophyll_result = await asyncio.gather(
            self._optional_feature_value("SPM", selected_date, sample_latitude, sample_longitude),
            self._optional_feature_value("CHL", selected_date, sample_latitude, sample_longitude),
        )
        valid_time = datetime.combine(selected_date, time.min, tzinfo=UTC)
        age_hours = max(0.0, (retrieved_at - valid_time).total_seconds() / 3_600.0)
        pixel_to_spot = (
            haversine_km(
                location.latitude,
                location.longitude,
                turbidity.latitude,
                turbidity.longitude,
            )
            * 1_000
        )
        pixel_to_sample = (
            haversine_km(
                sample_latitude,
                sample_longitude,
                turbidity.latitude,
                turbidity.longitude,
            )
            * 1_000
        )
        return CoastalWaterContext(
            availability="available",
            sample_latitude=sample_latitude,
            sample_longitude=sample_longitude,
            sample_distance_from_spot_m=round(sample_distance, 1),
            pixel_latitude=turbidity.latitude,
            pixel_longitude=turbidity.longitude,
            pixel_distance_from_spot_m=round(pixel_to_spot, 1),
            pixel_distance_from_sample_m=round(pixel_to_sample, 1),
            valid_time=valid_time,
            retrieved_at=retrieved_at,
            age_hours=round(age_hours, 1),
            search_days=SEARCH_DAYS,
            turbidity_fnu=round(turbidity.value, 4),
            suspended_particulate_matter_g_m3=(
                round(spm_result.value, 4) if spm_result is not None else None
            ),
            chlorophyll_a_mg_m3=(
                round(chlorophyll_result.value, 4) if chlorophyll_result is not None else None
            ),
            reason_ar=(
                "أحدث بكسل TUR يومي صالح عند نقطة ثابتة تبعد 1 كم على محور البحر؛ "
                "SPM وCHL يبقيان Unknown إذا لم يرجعا صالحين في اليوم والبكسل نفسيهما."
            ),
        )

    async def _optional_feature_value(
        self,
        variable: str,
        valid_date: date,
        latitude: float,
        longitude: float,
    ) -> _FeatureValue | None:
        try:
            return await self._feature_value(variable, valid_date, latitude, longitude)
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.debug("Copernicus WMTS %s sample unavailable: %s", variable, exc)
            return None

    async def _feature_value(
        self,
        variable: str,
        valid_date: date,
        latitude: float,
        longitude: float,
    ) -> _FeatureValue | None:
        tile_col, tile_row, pixel_i, pixel_j = web_mercator_tile_pixel(
            latitude, longitude, TILE_ZOOM
        )
        params: dict[str, str | int] = {
            "SERVICE": "WMTS",
            "REQUEST": "GetFeatureInfo",
            "VERSION": "1.0.0",
            "LAYER": f"{PRODUCT_ID}/{DATASET_ID}/{variable}",
            "STYLE": _VARIABLE_STYLES[variable],
            "FORMAT": "image/png",
            "INFOFORMAT": "application/json",
            "TILEMATRIXSET": TILE_MATRIX_SET,
            "TILEMATRIX": str(TILE_ZOOM),
            "TILEROW": tile_row,
            "TILECOL": tile_col,
            "I": pixel_i,
            "J": pixel_j,
            "TIME": f"{valid_date.isoformat()}T00:00:00Z",
        }
        response = await self._http.get(self._wmts_url, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Copernicus WMTS returned non-JSON feature info") from exc
        return parse_feature_value(payload, variable)


def parse_feature_value(payload: Any, variable: str) -> _FeatureValue | None:
    if not isinstance(payload, dict):
        raise ValueError("feature-info root must be an object")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        return None
    feature = features[0]
    if not isinstance(feature, dict):
        raise ValueError("feature-info item must be an object")
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("feature-info properties are missing")
    if properties.get("variableId") != variable:
        raise ValueError("feature-info variable does not match request")
    value = _finite_nonnegative(properties.get("value"))
    latitude = _finite(properties.get("lat"))
    longitude = _finite(properties.get("lon"))
    units = properties.get("units")
    if value is None:
        return None
    if latitude is None or longitude is None or not isinstance(units, str):
        raise ValueError("feature-info provenance is incomplete")
    if units != _EXPECTED_UNITS[variable]:
        raise ValueError(f"unexpected unit for {variable}")
    return _FeatureValue(value=value, latitude=latitude, longitude=longitude, units=units)


def destination_point(
    latitude: float,
    longitude: float,
    bearing_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    angular_distance = distance_m / EARTH_RADIUS_M
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    normalized_lon = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return math.degrees(lat2), normalized_lon


def web_mercator_tile_pixel(
    latitude: float,
    longitude: float,
    zoom: int,
) -> tuple[int, int, int, int]:
    clamped_latitude = max(-85.05112878, min(85.05112878, latitude))
    scale = 2**zoom
    tile_x = (longitude + 180.0) / 360.0 * scale
    tile_y = (1.0 - math.asinh(math.tan(math.radians(clamped_latitude))) / math.pi) / 2.0 * scale
    tile_col = min(scale - 1, max(0, int(tile_x)))
    tile_row = min(scale - 1, max(0, int(tile_y)))
    pixel_i = min(TILE_SIZE - 1, max(0, int((tile_x - tile_col) * TILE_SIZE)))
    pixel_j = min(TILE_SIZE - 1, max(0, int((tile_y - tile_row) * TILE_SIZE)))
    return tile_col, tile_row, pixel_i, pixel_j


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_nonnegative(value: Any) -> float | None:
    parsed = _finite(value)
    return parsed if parsed is not None and parsed >= 0 else None
