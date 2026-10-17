"""Secondary Open-Meteo models are fetched only when the primary payload has a gap.

Each analysis used to issue four Open-Meteo requests; the two optional gap-fill requests
pushed the shared server IP into HTTP 429. Skipping them when unnecessary cannot change the
forecast, because secondary values are only used to fill None entries.
"""

from typing import Any

import pytest

from spotdata.services.open_meteo import (
    MARINE_VARIABLES,
    OpenMeteoClient,
    _has_hourly_gaps,
)


def _complete(variables: tuple[str, ...]) -> dict[str, Any]:
    return {"hourly": {name: [1.0, 2.0] for name in variables}}


class _CountingHttp:
    def __init__(self) -> None:
        self.calls = 0

    async def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.calls += 1
        raise AssertionError("no secondary request expected")


def test_complete_payload_has_no_gaps() -> None:
    assert _has_hourly_gaps(_complete(MARINE_VARIABLES), MARINE_VARIABLES) is False


def test_none_value_or_missing_variable_counts_as_gap() -> None:
    with_none = _complete(MARINE_VARIABLES)
    with_none["hourly"][MARINE_VARIABLES[0]] = [1.0, None]
    assert _has_hourly_gaps(with_none, MARINE_VARIABLES) is True

    missing = _complete(MARINE_VARIABLES)
    del missing["hourly"][MARINE_VARIABLES[-1]]
    assert _has_hourly_gaps(missing, MARINE_VARIABLES) is True

    assert _has_hourly_gaps({}, MARINE_VARIABLES) is True


@pytest.mark.asyncio
async def test_secondary_request_is_skipped_when_primary_is_complete() -> None:
    http = _CountingHttp()
    client = OpenMeteoClient(
        http_client=http,  # type: ignore[arg-type]
        weather_url="https://weather.test",
        marine_url="https://marine.test",
        secondary_marine_model="meteofrance_wave",
    )
    result = await client._secondary_if_gaps(
        "https://marine.test",
        {"models": "meteofrance_wave"},
        _complete(MARINE_VARIABLES),
        MARINE_VARIABLES,
        "البحر (نموذج ثانٍ)",
        enabled=True,
    )
    assert result is None
    assert http.calls == 0
