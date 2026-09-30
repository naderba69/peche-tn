from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from spotdata.domain.enums import InmCheckStatus
from spotdata.services.inm_warnings import INM_BMS_URL, InmWarningClient


def _html(
    *,
    warning: bool = False,
    malformed: bool = False,
    warning_start: datetime | None = None,
) -> str:
    if not warning:
        return """
        <html><body>
          <div id="block-bmsblock"><div class="msg-result"><p>No gale warning</p></div></div>
          <div id="block-bms-frontblock"></div>
        </body></html>
        """
    start = warning_start or (datetime.now(UTC) + timedelta(hours=1))
    end = start + timedelta(hours=3)
    start_text = "bad-date" if malformed else f"{start:%d/%m/%Y} to {start:%H:%M}H UTC"
    end_text = "bad-date" if malformed else f"{end:%d/%m/%Y} to {end:%H:%M}H UTC"
    return f"""
    <html><body>
      <div id="block-bmsblock"><div class="msg-result"><p>No gale warning</p></div></div>
      <div id="block-bms-frontblock"></div>
      <div id="myModal"><table><tbody>
        <tr><td>Warning</td><td>Near Gale N° 144 In effect</td></tr>
        <tr><td>Reference time</td><td>06:00H UTC of {start:%d/%m/%Y}</td></tr>
        <tr><td>Beginning of validity</td><td>{start_text}</td></tr>
        <tr><td>End of validity</td><td>{end_text}</td></tr>
        <tr><td>Threatened Areas</td><td>Gulf of Gabes</td></tr>
      </tbody></table></div>
    </body></html>
    """


def _client_for(
    html: str,
    *,
    server_date: datetime | None = None,
    age_header: str | None = None,
) -> tuple[InmWarningClient, httpx.AsyncClient]:
    server_date = server_date or datetime.now(UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == INM_BMS_URL
        assert request.headers.get("cache-control") == "no-cache, no-store"
        headers = {
            "Date": format_datetime(server_date, usegmt=True),
            "Cache-Control": "must-revalidate, no-cache, private",
            "Content-Type": "text/html; charset=UTF-8",
        }
        if age_header is not None:
            headers["Age"] = age_header
        return httpx.Response(200, request=request, headers=headers, text=html)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return InmWarningClient(http), http


@pytest.mark.asyncio
async def test_fresh_explicit_national_clear_statement_is_verified() -> None:
    checker, http = _client_for(_html())
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=1), now + timedelta(hours=3))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.VERIFIED_CLEAR
    assert result.reason_code == "explicit_current_no_gale_warning"
    assert result.coverage_status == "verified_tunisian_coasts"
    assert result.response_sha256 and len(result.response_sha256) == 64


@pytest.mark.asyncio
async def test_expired_parsed_warning_does_not_override_fresh_explicit_clear() -> None:
    expired_start = datetime.now(UTC) - timedelta(days=3)
    checker, http = _client_for(_html(warning=True, warning_start=expired_start))
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=1), now + timedelta(hours=2))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.VERIFIED_CLEAR
    assert "Gulf of Gabes" in result.threatened_areas
    assert expired_start.isoformat()[:10] in result.warning_summary_ar[0]


@pytest.mark.asyncio
async def test_active_warning_overlapping_window_is_a_hard_block() -> None:
    checker, http = _client_for(_html(warning=True))
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=2), now + timedelta(hours=3))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.WARNING_ACTIVE
    assert result.reason_code == "official_warning_overlaps_window"
    assert result.threatened_areas == ["Gulf of Gabes"]
    assert result.warning_valid_until is not None


@pytest.mark.asyncio
async def test_warning_html_conflict_with_missing_validity_fails_closed() -> None:
    checker, http = _client_for(_html(warning=True, malformed=True))
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=1), now + timedelta(hours=2))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.UNVERIFIED
    assert result.reason_code == "warning_details_incomplete_or_conflicting"


@pytest.mark.asyncio
async def test_stale_server_date_cannot_become_verified_clear() -> None:
    checker, http = _client_for(_html(), server_date=datetime.now(UTC) - timedelta(hours=1))
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=1), now + timedelta(hours=2))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.UNVERIFIED
    assert result.reason_code == "stale_or_cacheable_http_response"


@pytest.mark.asyncio
async def test_nonzero_http_age_header_is_not_fresh_enough() -> None:
    checker, http = _client_for(_html(), age_header="30")
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=1), now + timedelta(hours=2))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.UNVERIFIED
    assert result.reason_code == "stale_or_cacheable_http_response"
    assert result.age_header_seconds == 30


@pytest.mark.asyncio
async def test_current_clear_statement_does_not_cover_windows_beyond_24_hours() -> None:
    checker, http = _client_for(_html())
    try:
        now = datetime.now(UTC)
        result = await checker.check([(now + timedelta(hours=23), now + timedelta(hours=25))])
    finally:
        await http.aclose()
    assert result.status == InmCheckStatus.UNVERIFIED
    assert result.reason_code == "requested_window_beyond_warning_status_horizon"
