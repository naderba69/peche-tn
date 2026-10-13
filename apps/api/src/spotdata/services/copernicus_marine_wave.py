"""Optional Copernicus Marine Mediterranean wave source, used only to fill empty hourly values.

Disabled unless BOTH are true:
  * the optional ``copernicusmarine`` package is installed (extra ``copernicus``), and
  * ``COPERNICUSMARINE_SERVICE_USERNAME`` and ``COPERNICUSMARINE_SERVICE_PASSWORD`` are set.

Credentials are never logged. Any failure returns ``None`` so the forecast is never blocked.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import math
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
TUNIS_TZ = ZoneInfo("Africa/Tunis")
PRODUCT_ID = "MEDSEA_ANALYSISFORECAST_WAV_006_017"
DATASET_ID = "cmems_mod_med_wav_anfc_4.2km_PT1H-i"
# Copernicus variable -> Open-Meteo marine raw name used by the gap-filler.
# VHM0 and VTM10 are confirmed in the product manual; VMDR is not yet verified live.
VARIABLE_MAP: dict[str, str] = {
    "VHM0": "wave_height",
    "VTM10": "wave_period",
    "VMDR": "wave_direction",
}
TIMEOUT_SECONDS = 15.0
BBOX_HALF_DEG = 0.05


def package_installed() -> bool:
    return importlib.util.find_spec("copernicusmarine") is not None


class CopernicusWaveClient:
    def __init__(self, username: str | None, password: str | None) -> None:
        self._username = username or None
        self._password = password or None

    @property
    def enabled(self) -> bool:
        return bool(self._username and self._password and package_installed())

    async def hourly_for_point(
        self, latitude: float, longitude: float, start: date, end: date
    ) -> dict[str, Any] | None:
        """Return ``{"hourly": {...}}`` in the Open-Meteo shape, or ``None`` when unavailable."""
        if not self.enabled:
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, latitude, longitude, start, end),
                TIMEOUT_SECONDS,
            )
        except Exception as exc:  # optional source: never let it break the forecast
            LOGGER.warning("Copernicus Marine gap-fill skipped: %s", type(exc).__name__)
            return None

    def _fetch_sync(
        self, latitude: float, longitude: float, start: date, end: date
    ) -> dict[str, Any] | None:
        copernicusmarine = importlib.import_module("copernicusmarine")  # optional extra

        dataset = copernicusmarine.open_dataset(
            dataset_id=DATASET_ID,
            username=self._username,
            password=self._password,
            variables=list(VARIABLE_MAP),
            minimum_longitude=longitude - BBOX_HALF_DEG,
            maximum_longitude=longitude + BBOX_HALF_DEG,
            minimum_latitude=latitude - BBOX_HALF_DEG,
            maximum_latitude=latitude + BBOX_HALF_DEG,
            start_datetime=f"{start.isoformat()}T00:00:00",
            end_datetime=f"{end.isoformat()}T23:00:00",
        )
        return hourly_from_dataset(dataset, latitude, longitude)


def hourly_from_dataset(dataset: Any, latitude: float, longitude: float) -> dict[str, Any] | None:
    """Convert one grid point of an xarray dataset to the Open-Meteo hourly shape.

    Separated from the network call so the conversion is testable offline.
    """
    np: Any = importlib.import_module("numpy")  # numpy ships with the optional extra only

    try:
        point = dataset.sel(latitude=latitude, longitude=longitude, method="nearest")
    except (KeyError, ValueError):
        return None
    times_raw = np.atleast_1d(point["time"].values)
    times: list[str] = []
    for value in times_raw:
        seconds = int(value.astype("datetime64[s]").astype("int64"))
        local = datetime.fromtimestamp(seconds, UTC).astimezone(TUNIS_TZ)
        times.append(local.strftime("%Y-%m-%dT%H:%M"))
    hourly: dict[str, Any] = {"time": times}
    for source_name, raw_name in VARIABLE_MAP.items():
        if source_name not in point:
            continue
        values = np.atleast_1d(point[source_name].values)
        hourly[raw_name] = [
            None if (x is None or math.isnan(float(x))) else round(float(x), 3) for x in values
        ]
    if len(hourly) == 1:
        return None
    return {"hourly": hourly}
