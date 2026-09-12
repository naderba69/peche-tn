from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.models import (
    AnglerProfile,
    Coordinates,
    ForecastDataset,
    ForecastHour,
    SourceMetadata,
    SpotProfile,
)

TZ = ZoneInfo("Africa/Tunis")
TARGET = date(2026, 9, 7)


def build_dataset(
    *,
    hour_updates: dict[str, Any] | None = None,
    per_hour: Callable[[int, dict[str, Any]], None] | None = None,
    spot_updates: dict[str, Any] | None = None,
    angler_updates: dict[str, Any] | None = None,
    include_source: bool = True,
    count: int = 24,
    start_at: datetime | None = None,
) -> ForecastDataset:
    hours: list[ForecastHour] = []
    first_hour = start_at or datetime(2026, 9, 7, 0, tzinfo=TZ)
    for index in range(count):
        values: dict[str, Any] = {
            "time": first_hour + timedelta(hours=index),
            "wind_speed_kmh": 12.0,
            "wind_gust_kmh": 18.0,
            "wind_direction_deg": 90.0,
            "wave_height_m": 0.6,
            "wave_period_s": 6.0,
            "wave_direction_deg": 90.0,
            "wind_wave_height_m": 0.35,
            "wind_wave_period_s": 4.5,
            "wind_wave_direction_deg": 90.0,
            "swell_height_m": 0.35,
            "swell_period_s": 7.0,
            "swell_direction_deg": 90.0,
            "sea_surface_temperature_c": 22.0,
            "ocean_current_velocity_kmh": 0.6,
            "ocean_current_direction_deg": 0.0,
            "sea_level_height_msl_m": round(0.35 * math.sin(2 * math.pi * index / 12.4), 3),
            "air_temperature_c": 24.0,
            "apparent_temperature_c": 24.5,
            "relative_humidity_pct": 65.0,
            "dew_point_c": 17.0,
            "cloud_cover_pct": 20.0,
            "shortwave_radiation_wm2": 300.0,
            "uv_index": 4.0,
            "lightning_potential_jkg": None,
            "precipitation_mm": 0.0,
            "precipitation_probability_pct": 5.0,
            "weather_code": 1,
            "pressure_msl_hpa": 1014.0 - 0.1 * index,
            "visibility_m": 20_000.0,
            "cape_jkg": 50.0,
        }
        if hour_updates:
            values.update(hour_updates)
        if per_hour:
            per_hour(index, values)
        hours.append(ForecastHour(**values))

    spot_values: dict[str, Any] = {
        "seaward_orientation_deg": 90,
        "orientation_source": "manual",
        "shore_type": "sandy",
        "exposure": "open",
    }
    spot_values.update(spot_updates or {})
    angler_values: dict[str, Any] = {
        "experience": "intermediate",
        "target_species": "general",
        "session_hours": 3,
    }
    angler_values.update(angler_updates or {})
    fetched = datetime(2026, 9, 7, 0, tzinfo=TZ)
    sources = (
        [
            SourceMetadata(
                provider="test",
                product="synthetic",
                data_kind="synthetic_test",
                variables=["all"],
                horizontal_resolution_km=8,
                retrieved_at=fetched,
                limitations_ar=["مصدر اختباري."],
            )
        ]
        if include_source
        else []
    )
    return ForecastDataset(
        location=Coordinates(latitude=36.8, longitude=10.3, name="اختبار"),
        target_date=TARGET,
        spot=SpotProfile(**spot_values),
        angler=AnglerProfile(**angler_values),
        hours=hours,
        sunrise=datetime(2026, 9, 7, 6, 0, tzinfo=TZ),
        sunset=datetime(2026, 9, 7, 18, 30, tzinfo=TZ),
        fetched_at=fetched,
        sources=sources,
    )


@pytest.fixture
def dataset_factory() -> Callable[..., ForecastDataset]:
    return build_dataset
