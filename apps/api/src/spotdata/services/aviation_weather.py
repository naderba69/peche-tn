from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from spotdata.domain.math import knots_to_kmh
from spotdata.domain.models import Coordinates, WeatherStationObservation

# Coastal and near-coastal Tunisian METAR stations. One compact request retrieves the latest
# reports; the nearest returned station is selected by coordinates from the report itself.
TUNISIA_METAR_STATIONS: tuple[str, ...] = (
    "DTKA",  # Tabarka
    "DTTB",  # Bizerte
    "DTTA",  # Tunis-Carthage
    "DTNH",  # Enfidha-Hammamet
    "DTMB",  # Monastir
    "DTTX",  # Sfax
    "DTTG",  # Gabes
    "DTTJ",  # Djerba-Zarzis
)


def parse_nearest_metar(
    payload: list[Any],
    location: Coordinates,
    retrieved_at: datetime,
) -> WeatherStationObservation | None:
    """Return the nearest station's latest valid METAR observation.

    METAR is a direct station observation, not an observation at the selected beach. Distance,
    report time and the raw report are retained so the engine cannot hide this distinction.
    """
    latest_by_station: dict[str, dict[str, Any]] = {}
    for candidate in payload:
        if not isinstance(candidate, dict):
            continue
        station_id = candidate.get("icaoId")
        report_time = _report_time(candidate.get("reportTime"))
        latitude = _float(candidate.get("lat"))
        longitude = _float(candidate.get("lon"))
        raw_report = candidate.get("rawOb")
        if (
            not isinstance(station_id, str)
            or report_time is None
            or latitude is None
            or longitude is None
            or not isinstance(raw_report, str)
        ):
            continue
        previous = latest_by_station.get(station_id)
        if previous is None:
            latest_by_station[station_id] = candidate
            continue
        previous_time = _report_time(previous.get("reportTime"))
        if previous_time is None or report_time > previous_time:
            latest_by_station[station_id] = candidate

    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in latest_by_station.values():
        latitude = _float(candidate.get("lat"))
        longitude = _float(candidate.get("lon"))
        if latitude is None or longitude is None:
            continue
        distance = haversine_km(
            location.latitude,
            location.longitude,
            latitude,
            longitude,
        )
        ranked.append((distance, candidate))
    if not ranked:
        return None

    distance, report = min(ranked, key=lambda item: item[0])
    observed_at = _report_time(report.get("reportTime"))
    latitude = _float(report.get("lat"))
    longitude = _float(report.get("lon"))
    if observed_at is None or latitude is None or longitude is None:
        return None

    visibility_m, visibility_is_lower_bound = _visibility_metres(report.get("visib"))
    wind_knots = _float(report.get("wspd"))
    sea_level_pressure = _float(report.get("slp"))
    altimeter_setting = _float(report.get("altim"))
    gust_knots = _float(report.get("wgst"))
    direction = _float(report.get("wdir"))
    return WeatherStationObservation(
        provider="AviationWeather.gov METAR",
        station_id=str(report.get("icaoId")),
        station_name=str(report.get("name") or report.get("icaoId")),
        station_latitude=latitude,
        station_longitude=longitude,
        station_elevation_m=_float(report.get("elev")),
        observed_at=observed_at,
        retrieved_at=retrieved_at,
        distance_to_spot_km=round(distance, 1),
        wind_speed_kmh=round(knots_to_kmh(wind_knots), 1) if wind_knots is not None else None,
        wind_gust_kmh=round(knots_to_kmh(gust_knots), 1) if gust_knots is not None else None,
        wind_direction_deg=direction,
        air_temperature_c=_float(report.get("temp")),
        dew_point_c=_float(report.get("dewp")),
        pressure_hpa=sea_level_pressure if sea_level_pressure is not None else altimeter_setting,
        pressure_kind=(
            "sea_level_pressure"
            if sea_level_pressure is not None
            else "altimeter_setting"
            if altimeter_setting is not None
            else None
        ),
        visibility_m=visibility_m,
        visibility_is_lower_bound=visibility_is_lower_bound,
        weather_text=str(report.get("wxString")) if report.get("wxString") else None,
        cloud_cover_code=str(report.get("cover")) if report.get("cover") else None,
        raw_report=str(report.get("rawOb")),
        quality_control_flag=_integer(report.get("qcField")),
    )


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_km = 6_371.0088
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    central_angle = 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    return radius_km * central_angle


def _report_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _visibility_metres(value: Any) -> tuple[float | None, bool]:
    """Decode AviationWeather JSON visibility, expressed in statute miles."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value) * 1_609.344), False
    if not isinstance(value, str):
        return None, False
    text = value.strip()
    lower_bound = text.endswith("+")
    if lower_bound:
        text = text[:-1]
    try:
        statute_miles = float(text)
    except ValueError:
        return None, False
    return round(statute_miles * 1_609.344), lower_bound


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    parsed = _float(value)
    return int(parsed) if parsed is not None else None
