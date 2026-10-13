from __future__ import annotations

import asyncio
import logging
import sys
import types
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

xr = pytest.importorskip("xarray")
np = pytest.importorskip("numpy")

from spotdata.domain.models import Coordinates, ForecastDecisionRequest, SpotProfile  # noqa: E402
from spotdata.services import copernicus_marine_wave as cmw  # noqa: E402
from spotdata.services.open_meteo import parse_open_meteo  # noqa: E402
from tests.test_open_meteo import _payloads  # noqa: E402

TZ = ZoneInfo("Africa/Tunis")
PASSWORD = "unit-test-secret-password"


def _dataset(vhm0_values: list[float]) -> Any:
    # 2026-09-07 00:00 UTC == 01:00 Tunis. Three hours, one grid point near the spot.
    times = np.array(
        ["2026-09-07T00:00", "2026-09-07T01:00", "2026-09-07T02:00"], dtype="datetime64[ns]"
    )
    shape = (3, 2, 2)
    vhm0 = np.broadcast_to(np.array(vhm0_values, dtype=float).reshape(3, 1, 1), shape).copy()
    return xr.Dataset(
        {
            "VHM0": (("time", "latitude", "longitude"), vhm0),
            "VTM10": (("time", "latitude", "longitude"), np.full(shape, 5.5)),
        },
        coords={"time": times, "latitude": [36.7, 36.9], "longitude": [10.3, 10.5]},
    )


def test_hourly_from_dataset_uses_tunis_local_hours_and_keeps_nan_as_none() -> None:
    dataset = _dataset([0.8, float("nan"), 0.9])
    result = cmw.hourly_from_dataset(dataset, latitude=36.7, longitude=10.3)
    assert result is not None
    hourly = result["hourly"]
    assert hourly["time"] == ["2026-09-07T01:00", "2026-09-07T02:00", "2026-09-07T03:00"]
    assert hourly["wave_height"] == [0.8, None, 0.9]
    assert hourly["wave_period"] == [5.5, 5.5, 5.5]
    assert "wave_direction" not in hourly  # variable absent from the dataset is skipped


def test_hourly_from_dataset_returns_none_without_known_variables() -> None:
    dataset = xr.Dataset(
        {"UNRELATED": (("time", "latitude", "longitude"), np.zeros((3, 2, 2)))},
        coords={
            "time": np.array(
                ["2026-09-07T00:00", "2026-09-07T01:00", "2026-09-07T02:00"], dtype="datetime64[ns]"
            ),
            "latitude": [36.7, 36.9],
            "longitude": [10.3, 10.5],
        },
    )
    assert cmw.hourly_from_dataset(dataset, latitude=36.7, longitude=10.3) is None


def test_disabled_without_credentials_and_never_calls_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cmw, "package_installed", lambda: True)
    client = cmw.CopernicusWaveClient(None, None)
    assert client.enabled is False
    assert (
        asyncio.run(client.hourly_for_point(36.7, 10.3, date(2026, 9, 7), date(2026, 9, 8))) is None
    )


def test_disabled_when_optional_package_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmw, "package_installed", lambda: False)
    client = cmw.CopernicusWaveClient("user@example.test", PASSWORD)
    assert client.enabled is False


def test_enabled_client_passes_credentials_and_returns_converted_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_open_dataset(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _dataset([0.8, 0.7, 0.9])

    fake_module = types.ModuleType("copernicusmarine")
    fake_module.open_dataset = fake_open_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "copernicusmarine", fake_module)
    monkeypatch.setattr(cmw, "package_installed", lambda: True)

    client = cmw.CopernicusWaveClient("user@example.test", PASSWORD)
    result = asyncio.run(client.hourly_for_point(36.7, 10.3, date(2026, 9, 7), date(2026, 9, 8)))
    assert captured["dataset_id"] == cmw.DATASET_ID
    assert captured["username"] == "user@example.test"
    assert captured["password"] == PASSWORD
    assert captured["start_datetime"] == "2026-09-07T00:00:00"
    assert result is not None
    assert result["hourly"]["wave_height"] == [0.8, 0.7, 0.9]


def test_failure_returns_none_and_never_logs_the_password(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def failing_open_dataset(**_: Any) -> Any:
        raise RuntimeError("authentication refused")

    fake_module = types.ModuleType("copernicusmarine")
    fake_module.open_dataset = failing_open_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "copernicusmarine", fake_module)
    monkeypatch.setattr(cmw, "package_installed", lambda: True)

    client = cmw.CopernicusWaveClient("user@example.test", PASSWORD)
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            client.hourly_for_point(36.7, 10.3, date(2026, 9, 7), date(2026, 9, 8))
        )
    assert result is None
    assert PASSWORD not in caplog.text
    assert "user@example.test" not in caplog.text


def test_parser_fills_only_remaining_gaps_from_copernicus_and_tags_them() -> None:
    marine, weather = _payloads()
    copernicus = {
        "hourly": {
            "time": [f"2026-09-07T{hour:02d}:00" for hour in range(6)],
            "wave_height": [9.9, 0.95, 9.9, 9.9, 9.9, 9.9],
        }
    }
    request = ForecastDecisionRequest(
        location=Coordinates(latitude=36.8, longitude=10.3),
        target_date=date(2026, 9, 7),
        spot=SpotProfile(seaward_orientation_deg=90),
    )
    dataset = parse_open_meteo(
        request=request,
        marine=marine,
        weather=weather,
        retrieved_at=datetime(2026, 9, 7, tzinfo=TZ),
        copernicus_marine=copernicus,
    )
    # Primary hour 0 is present (0.5) and must not be replaced by 9.9.
    assert dataset.hours[0].wave_height_m == 0.5
    # Primary gap at hour 1 is filled and tagged.
    assert dataset.hours[1].wave_height_m == 0.95
    assert "wave_height_m" in dataset.hours[1].gap_filled_fields
    assert any("Copernicus Marine" in source.provider for source in dataset.sources)
