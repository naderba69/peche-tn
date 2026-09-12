from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from spotdata.domain.models import (
    ForecastDataset,
    ForecastDecisionRequest,
    ForecastHour,
    SourceMetadata,
)
from spotdata.services.aviation_weather import TUNISIA_METAR_STATIONS, parse_nearest_metar
from spotdata.services.cache import AsyncTTLCache

LOGGER = logging.getLogger(__name__)
TUNIS_TZ = ZoneInfo("Africa/Tunis")

MARINE_VARIABLES = (
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
)

WEATHER_VARIABLES = (
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
)


class UpstreamDataError(RuntimeError):
    def __init__(self, message_ar: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message_ar)
        self.message_ar = message_ar
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class _UpstreamBundle:
    marine: dict[str, Any]
    weather: dict[str, Any]
    metar: list[Any]
    retrieved_at: datetime


class OpenMeteoClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        weather_url: str,
        marine_url: str,
        observation_url: str = "https://aviationweather.gov/api/data/metar",
    ) -> None:
        self._http = http_client
        self._weather_url = weather_url
        self._marine_url = marine_url
        self._observation_url = observation_url
        self.cache: AsyncTTLCache[tuple[float, float, date, bool], _UpstreamBundle] = AsyncTTLCache(
            ttl_seconds=600,
            max_entries=256,
        )

    async def forecast_dataset(self, request: ForecastDecisionRequest) -> ForecastDataset:
        # Preserve up to 72 hours of model context for transparent trend displays.
        # This does not turn the matrix's fixed "48-hour rule" into a catch score.
        start_date = request.target_date - timedelta(days=3)
        end_date = request.target_date + timedelta(days=1)
        common = {
            "latitude": request.location.latitude,
            "longitude": request.location.longitude,
            "timezone": "Africa/Tunis",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        marine_params = {
            **common,
            "hourly": ",".join(MARINE_VARIABLES),
            "cell_selection": "sea",
        }
        weather_params = {
            **common,
            "hourly": ",".join(WEATHER_VARIABLES),
            "daily": "sunrise,sunset",
            "wind_speed_unit": "kmh",
            "cell_selection": "nearest",
        }
        include_current_observation = request.target_date == datetime.now(TUNIS_TZ).date()
        cache_key = (
            round(request.location.latitude, 4),
            round(request.location.longitude, 4),
            request.target_date,
            include_current_observation,
        )
        bundle = await self.cache.get_or_create(
            cache_key,
            lambda: self._fetch_bundle(
                marine_params,
                weather_params,
                include_current_observation=include_current_observation,
            ),
        )
        return parse_open_meteo(
            request=request,
            marine=bundle.marine,
            weather=bundle.weather,
            metar=bundle.metar,
            retrieved_at=bundle.retrieved_at,
        )

    async def _fetch_bundle(
        self,
        marine_params: dict[str, Any],
        weather_params: dict[str, Any],
        *,
        include_current_observation: bool,
    ) -> _UpstreamBundle:
        observation_task = (
            self._get_optional_observations()
            if include_current_observation
            else asyncio.sleep(0, result=[])
        )
        try:
            marine_result, weather_result, metar_result = await asyncio.gather(
                self._get_json(self._marine_url, marine_params, "البحر"),
                self._get_json(self._weather_url, weather_params, "الطقس"),
                observation_task,
            )
        except UpstreamDataError:
            raise
        except Exception as exc:
            raise UpstreamDataError("تعذر جلب بيانات الأرصاد المجانية.") from exc
        return _UpstreamBundle(
            marine=marine_result,
            weather=weather_result,
            metar=metar_result,
            retrieved_at=datetime.now(TUNIS_TZ),
        )

    async def _get_optional_observations(self) -> list[Any]:
        params: dict[str, str | int] = {
            "ids": ",".join(TUNISIA_METAR_STATIONS),
            "format": "json",
            "hours": 2,
        }
        try:
            response = await self._http.get(self._observation_url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("METAR JSON root is not an array")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            # Current station validation improves evidence but is not allowed to make the
            # forecast endpoint fail. Its absence is represented explicitly in the response.
            LOGGER.warning("AviationWeather METAR request unavailable: %s", exc)
            return []

    async def _get_json(
        self, url: str, params: dict[str, Any], source_label: str
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt, delay in enumerate((0.0, 0.35, 0.9), start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await self._http.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "temporary upstream response", request=response.request, response=response
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("JSON root is not an object")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                status = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                retryable = status is None or status == 429 or status >= 500
                LOGGER.warning(
                    "Open-Meteo %s request failed attempt=%s status=%s: %s",
                    source_label,
                    attempt,
                    status,
                    exc,
                )
                if not retryable:
                    break
        details: dict[str, Any] = {"source": source_label}
        if isinstance(last_error, httpx.HTTPStatusError):
            details["status"] = last_error.response.status_code
        raise UpstreamDataError(
            f"تعذر جلب بيانات {source_label} من مزود الأرصاد.", details=details
        ) from last_error


def parse_open_meteo(
    *,
    request: ForecastDecisionRequest,
    marine: dict[str, Any],
    weather: dict[str, Any],
    retrieved_at: datetime,
    metar: list[Any] | None = None,
) -> ForecastDataset:
    marine_hourly = _object(marine.get("hourly"), "marine.hourly")
    weather_hourly = _object(weather.get("hourly"), "weather.hourly")
    marine_index = _time_index(marine_hourly, "marine")
    weather_index = _time_index(weather_hourly, "weather")
    common_times = sorted(set(marine_index).intersection(weather_index))
    if not common_times:
        raise UpstreamDataError(
            "لا توجد ساعات مشتركة بين بيانات البحر والطقس.",
            details={"marine_hours": len(marine_index), "weather_hours": len(weather_index)},
        )

    hours: list[ForecastHour] = []
    for time_text in common_times:
        marine_i = marine_index[time_text]
        weather_i = weather_index[time_text]
        hours.append(
            ForecastHour(
                time=_local_datetime(time_text),
                wind_speed_kmh=_number(weather_hourly, "wind_speed_10m", weather_i),
                wind_gust_kmh=_number(weather_hourly, "wind_gusts_10m", weather_i),
                wind_direction_deg=_number(weather_hourly, "wind_direction_10m", weather_i),
                wave_height_m=_number(marine_hourly, "wave_height", marine_i),
                wave_period_s=_number(marine_hourly, "wave_period", marine_i),
                wave_direction_deg=_number(marine_hourly, "wave_direction", marine_i),
                wind_wave_height_m=_number(marine_hourly, "wind_wave_height", marine_i),
                wind_wave_period_s=_number(marine_hourly, "wind_wave_period", marine_i),
                wind_wave_direction_deg=_number(marine_hourly, "wind_wave_direction", marine_i),
                swell_height_m=_number(marine_hourly, "swell_wave_height", marine_i),
                swell_period_s=_number(marine_hourly, "swell_wave_period", marine_i),
                swell_direction_deg=_number(marine_hourly, "swell_wave_direction", marine_i),
                sea_surface_temperature_c=_number(
                    marine_hourly, "sea_surface_temperature", marine_i
                ),
                ocean_current_velocity_kmh=_number(
                    marine_hourly, "ocean_current_velocity", marine_i
                ),
                ocean_current_direction_deg=_number(
                    marine_hourly, "ocean_current_direction", marine_i
                ),
                sea_level_height_msl_m=_number(marine_hourly, "sea_level_height_msl", marine_i),
                air_temperature_c=_number(weather_hourly, "temperature_2m", weather_i),
                apparent_temperature_c=_number(weather_hourly, "apparent_temperature", weather_i),
                relative_humidity_pct=_number(weather_hourly, "relative_humidity_2m", weather_i),
                dew_point_c=_number(weather_hourly, "dew_point_2m", weather_i),
                cloud_cover_pct=_number(weather_hourly, "cloud_cover", weather_i),
                shortwave_radiation_wm2=_number(weather_hourly, "shortwave_radiation", weather_i),
                uv_index=_number(weather_hourly, "uv_index", weather_i),
                lightning_potential_jkg=_number(weather_hourly, "lightning_potential", weather_i),
                precipitation_mm=_number(weather_hourly, "precipitation", weather_i),
                precipitation_probability_pct=_number(
                    weather_hourly, "precipitation_probability", weather_i
                ),
                weather_code=_integer(weather_hourly, "weather_code", weather_i),
                pressure_msl_hpa=_number(weather_hourly, "pressure_msl", weather_i),
                visibility_m=_number(weather_hourly, "visibility", weather_i),
                cape_jkg=_number(weather_hourly, "cape", weather_i),
            )
        )

    sunrise, sunset = _sun_times(weather, request.target_date)
    marine_variables = [name for name in MARINE_VARIABLES if name in marine_hourly]
    weather_variables = [name for name in WEATHER_VARIABLES if name in weather_hourly]
    current_observation = parse_nearest_metar(metar or [], request.location, retrieved_at)
    sources = [
        SourceMetadata(
            provider="Open-Meteo / Météo-France, ECMWF, DWD and NCEP model blend",
            product="Marine Weather API (waves; SMOC currents, sea level and SST)",
            data_kind="model_forecast",
            variables=marine_variables,
            horizontal_resolution_km=8.0,
            retrieved_at=retrieved_at,
            limitations_ar=[
                "بيانات المدّ والتيار محسوبة نموذجياً بدقة تقارب 8 كم ودقتها الساحلية محدودة؛ ليست للملاحة.",
                "وثائق Open-Meteo تنصّ أن الدقة العالية للتيار ومستوى البحر متاحة فقط في أوروبا الوسطى وأمريكا الشمالية؛ في تونس تُحلَّل السلسلة من نموذج عالمي أخشن، لذلك يُعامل التيار والمدّ مؤشرين منخفضي الثقة لا قياساً محلياً.",
                "ارتفاع الموج هو الارتفاع الدال في خلية بحرية، وليس قياس كسرة الموج على الرمل أو الصخر.",
                "قد تختلف هذه السلسلة عن GFS-Wave أو نموذج منفرد ظاهر في تطبيق آخر بسبب الشبكة والدورة والمزج؛ لا يُعامل التطابق بين تطبيقين كقياس ميداني.",
                "فصل السويل عن موج الريح مستمد من النموذج نفسه؛ لا يرصد مكونات الموج داخل منطقة الكسرة.",
            ],
        ),
        SourceMetadata(
            provider="Open-Meteo model blend",
            product="Weather Forecast API (Best Match)",
            data_kind="model_forecast",
            variables=weather_variables,
            horizontal_resolution_km=None,
            retrieved_at=retrieved_at,
            limitations_ar=[
                "الطقس توقع عددي وليس محطة رصد في البقعة؛ راجع النشرة والرادار قبل الانطلاق.",
                "قد يختلف Best Match عن GFS أو ECMWF أو ICON منفرد؛ عند اختلافها، لا يُحسم الرعد من لقطة تطبيق واحدة ويجب الرجوع إلى الرادار والتنبيه الرسمي قرب الموعد.",
                "lightning_potential وCAPE مؤشرا حمل نموذجيان وليسا رصداً لضربة برق ضمن مسافة محددة.",
                "الرؤية تخص الغلاف الجوي ولا تقيس شفافية ماء البحر أو عكارته.",
            ],
        ),
    ]
    if current_observation is not None:
        sources.append(
            SourceMetadata(
                provider="AviationWeather.gov / METAR",
                product=f"Latest Tunisian airport observation ({current_observation.station_id})",
                data_kind="direct_observation",
                variables=[
                    "wind_speed",
                    "wind_gust",
                    "wind_direction",
                    "air_temperature",
                    "dew_point",
                    "pressure",
                    "visibility",
                    "weather_phenomena",
                ],
                horizontal_resolution_km=None,
                retrieved_at=retrieved_at,
                limitations_ar=[
                    "هذا رصد فعلي في محطة مطار لا داخل البقعة البحرية المختارة.",
                    f"تبعد المحطة {current_observation.distance_to_spot_km:.1f} كم عن البقعة؛ لا تُنقل قيمها مكانياً كأنها قياس ساحلي.",
                    "لا يقيس METAR الموج أو التيار أو حرارة البحر أو العكارة أو الصوفة.",
                ],
            )
        )
    return ForecastDataset(
        location=request.location,
        target_date=request.target_date,
        spot=request.spot,
        angler=request.angler,
        hours=hours,
        sunrise=sunrise,
        sunset=sunset,
        fetched_at=retrieved_at,
        sources=sources,
        current_weather_observation=current_observation,
        field_reports=request.field_reports,
        test_cast=request.test_cast,
        official_warning=request.official_warning,
    )


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UpstreamDataError("بيانات مزود الأرصاد ناقصة.", details={"missing_or_invalid": path})
    return value


def _time_index(hourly: dict[str, Any], source: str) -> dict[str, int]:
    times = hourly.get("time")
    if not isinstance(times, list):
        raise UpstreamDataError("بيانات الوقت من مزود الأرصاد ناقصة.", details={"source": source})
    return {value: index for index, value in enumerate(times) if isinstance(value, str)}


def _number(hourly: dict[str, Any], key: str, index: int) -> float | None:
    values = hourly.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(hourly: dict[str, Any], key: str, index: int) -> int | None:
    value = _number(hourly, key, index)
    return int(value) if value is not None else None


def _local_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise UpstreamDataError(
            "صيغة الوقت من مزود الأرصاد غير صحيحة.", details={"value": value}
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TUNIS_TZ)
    return parsed.astimezone(TUNIS_TZ)


def _sun_times(
    payload: dict[str, Any], target_date: date
) -> tuple[datetime | None, datetime | None]:
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return None, None
    dates = daily.get("time")
    sunrises = daily.get("sunrise")
    sunsets = daily.get("sunset")
    if (
        not isinstance(dates, list)
        or not isinstance(sunrises, list)
        or not isinstance(sunsets, list)
    ):
        return None, None
    try:
        index = dates.index(target_date.isoformat())
    except ValueError:
        return None, None
    if index >= len(sunrises) or index >= len(sunsets):
        return None, None
    sunrise_raw = sunrises[index]
    sunset_raw = sunsets[index]
    if not isinstance(sunrise_raw, str) or not isinstance(sunset_raw, str):
        return None, None
    return _local_datetime(sunrise_raw), _local_datetime(sunset_raw)
