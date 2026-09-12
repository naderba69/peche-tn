from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.models import Coordinates, ForecastDecisionRequest, SpotProfile
from spotdata.services.open_meteo import UpstreamDataError, parse_open_meteo

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
