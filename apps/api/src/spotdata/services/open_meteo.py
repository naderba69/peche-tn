from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
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
from spotdata.services.copernicus_marine_wave import CopernicusWaveClient

LOGGER = logging.getLogger(__name__)
TUNIS_TZ = ZoneInfo("Africa/Tunis")

# Backoff before each upstream attempt. 429s on the shared cloud egress IP are
# usually short-lived; longer waits ride them out without hammering the provider.
_RETRY_DELAYS_SECONDS = (0.0, 0.75, 2.0, 5.0)
# Upper bound for honouring an upstream Retry-After header inside one request.
_MAX_RETRY_AFTER_SECONDS = 8.0
# When a fresh upstream fetch fails, a recently cached bundle is served instead
# of an error. 6 hours keeps the fallback useful without misleading staleness.
_STALE_BUNDLE_SECONDS = 6 * 3600.0
_MAX_STALE_ENTRIES = 128

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

# Raw Open-Meteo hourly variable -> ForecastHour field, used to report which hourly
# values were gap-filled from the secondary model family.
MARINE_RAW_TO_FIELD: dict[str, str] = {
    "wave_height": "wave_height_m",
    "wave_period": "wave_period_s",
    "wave_direction": "wave_direction_deg",
    "wind_wave_height": "wind_wave_height_m",
    "wind_wave_period": "wind_wave_period_s",
    "wind_wave_direction": "wind_wave_direction_deg",
    "swell_wave_height": "swell_height_m",
    "swell_wave_period": "swell_period_s",
    "swell_wave_direction": "swell_direction_deg",
    "sea_surface_temperature": "sea_surface_temperature_c",
    "ocean_current_velocity": "ocean_current_velocity_kmh",
    "ocean_current_direction": "ocean_current_direction_deg",
    "sea_level_height_msl": "sea_level_height_msl_m",
}
WEATHER_RAW_TO_FIELD: dict[str, str] = {
    "wind_speed_10m": "wind_speed_kmh",
    "wind_gusts_10m": "wind_gust_kmh",
    "wind_direction_10m": "wind_direction_deg",
    "temperature_2m": "air_temperature_c",
    "apparent_temperature": "apparent_temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "dew_point_2m": "dew_point_c",
    "cloud_cover": "cloud_cover_pct",
    "shortwave_radiation": "shortwave_radiation_wm2",
    "uv_index": "uv_index",
    "lightning_potential": "lightning_potential_jkg",
    "precipitation": "precipitation_mm",
    "precipitation_probability": "precipitation_probability_pct",
    "weather_code": "weather_code",
    "pressure_msl": "pressure_msl_hpa",
    "visibility": "visibility_m",
    "cape": "cape_jkg",
}


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
    # Optional second model family, used only to fill gaps. None when disabled/unavailable.
    secondary_marine: dict[str, Any] | None = None
    secondary_weather: dict[str, Any] | None = None
    copernicus_marine: dict[str, Any] | None = None


class OpenMeteoClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        weather_url: str,
        marine_url: str,
        observation_url: str = "https://aviationweather.gov/api/data/metar",
        *,
        stale_seconds: float = _STALE_BUNDLE_SECONDS,
        secondary_marine_model: str = "",
        secondary_weather_model: str = "",
        copernicus_client: CopernicusWaveClient | None = None,
    ) -> None:
        self._http = http_client
        self._copernicus = copernicus_client
        self._weather_url = weather_url
        self._marine_url = marine_url
        self._observation_url = observation_url
        self._stale_seconds = stale_seconds
        self._secondary_marine_model = secondary_marine_model
        self._secondary_weather_model = secondary_weather_model
        self._stale_bundles: OrderedDict[
            tuple[float, float, date, bool], tuple[float, _UpstreamBundle]
        ] = OrderedDict()
        self.cache: AsyncTTLCache[tuple[float, float, date, bool], _UpstreamBundle] = AsyncTTLCache(
            ttl_seconds=600,
            max_entries=256,
        )

    async def forecast_dataset(self, request: ForecastDecisionRequest) -> ForecastDataset:
        # Environmental inputs come only from this server-side provider fetch; the
        # public request cannot substitute a browser-supplied forecast bundle.
        return await self._dataset_from_upstream(request)

    async def _dataset_from_upstream(self, request: ForecastDecisionRequest) -> ForecastDataset:
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
            "daily": "sunrise,sunset,moonrise,moonset",
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
        cache_fallback_used = False
        cache_fallback_age_seconds: float | None = None
        try:
            bundle = await self.cache.get_or_create(
                cache_key,
                lambda: self._fetch_bundle(
                    marine_params,
                    weather_params,
                    include_current_observation=include_current_observation,
                ),
            )
        except UpstreamDataError:
            stale = self._stale_bundles.get(cache_key)
            if stale is not None and (time.monotonic() - stale[0]) <= self._stale_seconds:
                cache_fallback_age_seconds = time.monotonic() - stale[0]
                cache_fallback_used = True
                LOGGER.warning(
                    "Open-Meteo serving stale bundle for %s (age %.0fs)",
                    cache_key,
                    cache_fallback_age_seconds,
                )
                bundle = stale[1]
            else:
                raise
        else:
            self._stale_bundles[cache_key] = (time.monotonic(), bundle)
            self._stale_bundles.move_to_end(cache_key)
            while len(self._stale_bundles) > _MAX_STALE_ENTRIES:
                self._stale_bundles.popitem(last=False)
        return parse_open_meteo(
            request=request,
            marine=bundle.marine,
            weather=bundle.weather,
            metar=bundle.metar,
            retrieved_at=bundle.retrieved_at,
            cache_fallback_used=cache_fallback_used,
            cache_fallback_age_seconds=cache_fallback_age_seconds,
            secondary_marine=bundle.secondary_marine,
            secondary_marine_model=self._secondary_marine_model or None,
            secondary_weather=bundle.secondary_weather,
            secondary_weather_model=self._secondary_weather_model or None,
            copernicus_marine=bundle.copernicus_marine,
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
        secondary_marine_task = (
            self._get_optional_json(
                self._marine_url,
                {**marine_params, "models": self._secondary_marine_model},
                "البحر (نموذج ثانٍ)",
            )
            if self._secondary_marine_model
            else asyncio.sleep(0, result=None)
        )
        secondary_weather_task = (
            self._get_optional_json(
                self._weather_url,
                {**weather_params, "models": self._secondary_weather_model},
                "الطقس (نموذج ثانٍ)",
            )
            if self._secondary_weather_model
            else asyncio.sleep(0, result=None)
        )
        copernicus_task = (
            self._copernicus.hourly_for_point(
                float(marine_params["latitude"]),
                float(marine_params["longitude"]),
                date.fromisoformat(str(marine_params["start_date"])),
                date.fromisoformat(str(marine_params["end_date"])),
            )
            if self._copernicus is not None and self._copernicus.enabled
            else asyncio.sleep(0, result=None)
        )
        try:
            (
                marine_result,
                weather_result,
                metar_result,
                secondary_marine,
                secondary_weather,
                copernicus_marine,
            ) = await asyncio.gather(
                self._get_json(self._marine_url, marine_params, "البحر"),
                self._get_json(self._weather_url, weather_params, "الطقس"),
                observation_task,
                secondary_marine_task,
                secondary_weather_task,
                copernicus_task,
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
            secondary_marine=secondary_marine,
            secondary_weather=secondary_weather,
            copernicus_marine=copernicus_marine,
        )

    async def _get_optional_json(
        self, url: str, params: dict[str, Any], source_label: str
    ) -> dict[str, Any] | None:
        # A secondary model must never make the primary forecast fail: one attempt, no
        # retry storm, and any error simply means "no gap-filling this time".
        try:
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("JSON root is not an object")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("Open-Meteo %s unavailable, gap-fill skipped: %s", source_label, exc)
            return None

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
        for attempt, delay in enumerate(_RETRY_DELAYS_SECONDS, start=1):
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
                if attempt == len(_RETRY_DELAYS_SECONDS):
                    break
                if isinstance(exc, httpx.HTTPStatusError) and status == 429:
                    retry_after = _parse_retry_after(exc.response.headers.get("retry-after"))
                    if retry_after is not None:
                        await asyncio.sleep(min(retry_after, _MAX_RETRY_AFTER_SECONDS))
        details: dict[str, Any] = {"source": source_label}
        if isinstance(last_error, httpx.HTTPStatusError):
            details["status"] = last_error.response.status_code
        raise UpstreamDataError(
            f"تعذر جلب بيانات {source_label} من مزود الأرصاد.", details=details
        ) from last_error


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if seconds <= 0.0:
        return None
    return seconds


def parse_open_meteo(
    *,
    request: ForecastDecisionRequest,
    marine: dict[str, Any],
    weather: dict[str, Any],
    retrieved_at: datetime,
    metar: list[Any] | None = None,
    cache_fallback_used: bool = False,
    cache_fallback_age_seconds: float | None = None,
    secondary_marine: dict[str, Any] | None = None,
    secondary_marine_model: str | None = None,
    secondary_weather: dict[str, Any] | None = None,
    secondary_weather_model: str | None = None,
    copernicus_marine: dict[str, Any] | None = None,
) -> ForecastDataset:
    marine_hourly = _object(marine.get("hourly"), "marine.hourly")
    weather_hourly = _object(weather.get("hourly"), "weather.hourly")
    marine_index = _time_index(marine_hourly, "marine")
    weather_index = _time_index(weather_hourly, "weather")
    # Gap-fill ONLY empty primary values from the independent secondary family. The
    # primary blend stays authoritative; filled values are tagged per hour and per field.
    marine_hourly, marine_filled = _fill_hourly_gaps(
        marine_hourly, marine_index, secondary_marine, MARINE_VARIABLES
    )
    marine_hourly, copernicus_filled = _fill_hourly_gaps(
        marine_hourly, marine_index, copernicus_marine, MARINE_VARIABLES
    )
    for raw_name, times in copernicus_filled.items():
        marine_filled.setdefault(raw_name, set()).update(times)
    weather_hourly, weather_filled = _fill_hourly_gaps(
        weather_hourly, weather_index, secondary_weather, WEATHER_VARIABLES
    )
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
                gap_filled_fields=_gap_filled_fields(time_text, marine_filled, weather_filled),
            )
        )

    _log_forecast_gaps(request, hours, marine_filled, weather_filled)
    sunrise, sunset = _sun_times(weather, request.target_date)
    moonrise, moonset = _moon_times(weather, request.target_date)
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
    if secondary_marine is not None and secondary_marine_model:
        sources.append(
            SourceMetadata(
                provider="Open-Meteo (نموذج بحري ثانٍ مستقل)",
                product=f"Marine Weather API model={secondary_marine_model} (gap-fill فقط)",
                data_kind="model_forecast",
                variables=list(marine_filled),
                horizontal_resolution_km=8.0,
                retrieved_at=retrieved_at,
                limitations_ar=[
                    "استُعمل هذا النموذج فقط لملء قيم فارغة في النموذج الأساسي، ولا يحلّ محله.",
                    "نموذج مختلف المؤسسة/الشبكة يرفع التنوع، لكنه لا يعني تحققاً ميدانياً من الموج داخل الكسرة.",
                ],
            )
        )
    if copernicus_filled:
        sources.append(
            SourceMetadata(
                provider="Copernicus Marine Service (Med-WAV)",
                product="MEDSEA_ANALYSISFORECAST_WAV_006_017 cmems_mod_med_wav_anfc_4.2km_PT1H-i (gap-fill فقط)",
                data_kind="model_forecast",
                variables=list(copernicus_filled),
                horizontal_resolution_km=4.2,
                retrieved_at=retrieved_at,
                limitations_ar=[
                    "استُعمل هذا المصدر فقط لملء قيم بحرية فارغة في النموذجين الآخرين، ولا يحلّ محلهما.",
                    "النموذج يدمج قياسات أقمار صناعية للموج والريح، لكنه ليس قياساً داخل الكسرة أو عند نقطة الصيد.",
                ],
            )
        )
    if secondary_weather is not None and secondary_weather_model:
        sources.append(
            SourceMetadata(
                provider="Open-Meteo (نموذج طقس ثانٍ مستقل)",
                product=f"Weather Forecast API model={secondary_weather_model} (gap-fill فقط)",
                data_kind="model_forecast",
                variables=[v for v in weather_filled],
                horizontal_resolution_km=None,
                retrieved_at=retrieved_at,
                limitations_ar=[
                    "استُعمل هذا النموذج فقط لملء قيم طقس فارغة في النموذج الأساسي، ولا يحلّ محله.",
                    "لا يقيس النموذج الرعد أو الرؤية داخل البقعة؛ هو توقع عددي آخر.",
                ],
            )
        )
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
        moonrise=moonrise,
        moonset=moonset,
        fetched_at=retrieved_at,
        cache_fallback_used=cache_fallback_used,
        cache_fallback_age_seconds=cache_fallback_age_seconds,
        sources=sources,
        current_weather_observation=current_observation,
    )


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UpstreamDataError("بيانات مزود الأرصاد ناقصة.", details={"missing_or_invalid": path})
    return value


def _fill_hourly_gaps(
    primary: dict[str, Any],
    primary_index: dict[str, int],
    secondary: dict[str, Any] | None,
    variables: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, set[str]]]:
    """Return a copy of ``primary`` hourly data with None values replaced by secondary values.

    The result maps each filled raw variable to the set of ISO times that were filled.
    Inputs are never mutated because the upstream bundle is cached.
    """
    filled: dict[str, set[str]] = {}
    if not isinstance(secondary, dict):
        return primary, filled
    secondary_hourly = secondary.get("hourly")
    if not isinstance(secondary_hourly, dict):
        return primary, filled
    try:
        secondary_index = _time_index(secondary_hourly, "secondary")
    except UpstreamDataError:
        return primary, filled

    replacements: dict[str, list[Any]] = {}
    for name in variables:
        primary_values = primary.get(name)
        secondary_values = secondary_hourly.get(name)
        if not isinstance(primary_values, list) or not isinstance(secondary_values, list):
            continue
        new_values = list(primary_values)
        times_filled: set[str] = set()
        for time_text, index in primary_index.items():
            if index >= len(new_values) or new_values[index] is not None:
                continue
            secondary_i = secondary_index.get(time_text)
            if secondary_i is None or secondary_i >= len(secondary_values):
                continue
            candidate = secondary_values[secondary_i]
            if candidate is None or isinstance(candidate, bool):
                continue
            new_values[index] = candidate
            times_filled.add(time_text)
        if times_filled:
            replacements[name] = new_values
            filled[name] = times_filled
    if not replacements:
        return primary, filled
    return {**primary, **replacements}, filled


def _gap_filled_fields(
    time_text: str,
    marine_filled: dict[str, set[str]],
    weather_filled: dict[str, set[str]],
) -> list[str]:
    fields: list[str] = []
    for raw, times in marine_filled.items():
        if time_text in times and raw in MARINE_RAW_TO_FIELD:
            fields.append(MARINE_RAW_TO_FIELD[raw])
    for raw, times in weather_filled.items():
        if time_text in times and raw in WEATHER_RAW_TO_FIELD:
            fields.append(WEATHER_RAW_TO_FIELD[raw])
    return sorted(fields)


def _log_forecast_gaps(
    request: ForecastDecisionRequest,
    hours: list[ForecastHour],
    marine_filled: dict[str, set[str]],
    weather_filled: dict[str, set[str]],
) -> None:
    """Log which decision-relevant fields are still empty, for diagnosing the quality score."""
    if not hours:
        return
    tracked = (
        "wind_speed_kmh",
        "wind_gust_kmh",
        "wind_direction_deg",
        "wave_height_m",
        "wave_period_s",
        "wave_direction_deg",
        "swell_height_m",
        "ocean_current_velocity_kmh",
        "sea_level_height_msl_m",
        "visibility_m",
        "weather_code",
        "pressure_msl_hpa",
    )
    missing = {name: sum(1 for hour in hours if getattr(hour, name) is None) for name in tracked}
    missing = {name: count for name, count in missing.items() if count}
    filled_counts = {
        "marine": {raw: len(times) for raw, times in marine_filled.items()},
        "weather": {raw: len(times) for raw, times in weather_filled.items()},
    }
    LOGGER.info(
        "forecast gaps date=%s lat=%.2f lon=%.2f hours=%d missing=%s gap_filled=%s",
        request.target_date.isoformat(),
        request.location.latitude,
        request.location.longitude,
        len(hours),
        missing,
        filled_counts,
    )


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


def _moon_times(
    payload: dict[str, Any], target_date: date
) -> tuple[datetime | None, datetime | None]:
    """Moonrise/moonset from the upstream astronomy fields (real data, not a rule)."""
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        return None, None
    dates = daily.get("time")
    moonrises = daily.get("moonrise")
    moonsets = daily.get("moonset")
    if (
        not isinstance(dates, list)
        or not isinstance(moonrises, list)
        or not isinstance(moonsets, list)
    ):
        return None, None
    try:
        index = dates.index(target_date.isoformat())
    except ValueError:
        return None, None
    if index >= len(moonrises) or index >= len(moonsets):
        return None, None
    moonrise_raw = moonrises[index]
    moonset_raw = moonsets[index]
    if not isinstance(moonrise_raw, str) or not isinstance(moonset_raw, str):
        return None, None
    return _local_datetime(moonrise_raw), _local_datetime(moonset_raw)
