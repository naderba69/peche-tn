from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from spotdata.domain.enums import InmCheckStatus
from spotdata.domain.models import InmWarningAudit

LOGGER = logging.getLogger(__name__)
INM_BMS_URL = "https://www.meteo.tn/en/bms"
PARSER_VERSION = "inm-bms-1"
MAX_HTTP_DATE_AGE_SECONDS = 30 * 60
MAX_HTTP_DATE_FUTURE_SKEW_SECONDS = 5 * 60
MAX_TARGET_LEAD_HOURS = 24

_CLEAR_PHRASES = (
    "no gale warning",
    "pas d'avis de coup de vent",
    "aucun avis de coup de vent",
    "لا يوجد تحذير من هبوب الرياح",
)


class _BmsHtmlParser(HTMLParser):
    """Extract only the official BMS block and table rows from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: dict[str, list[str]] = {"block-bmsblock": [], "block-bms-frontblock": []}
        self._active: dict[str, int] = {}
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            for block_id in tuple(self._active):
                self._active[block_id] += 1
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id in self.blocks:
            self._active[element_id] = 1
        if tag.lower() == "tr":
            self._row = []
            self._cell = None
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join(self._cell))
            self._cell = None
        elif lowered == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None
        for block_id in tuple(self._active):
            self._active[block_id] -= 1
            if self._active[block_id] <= 0:
                del self._active[block_id]

    def handle_data(self, data: str) -> None:
        for block_id in self._active:
            self.blocks[block_id].append(data)
        if self._cell is not None:
            self._cell.append(data)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _parse_server_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_utc_datetime(value: str) -> datetime | None:
    normalized = re.sub(r"\s+", " ", value).strip()
    patterns = (
        r"(?P<time>\d{1,2}:\d{2})\s*H?\s*UTC\s*(?:of\s+)?(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*(?:to|à)\s*(?P<time>\d{1,2}:\d{2})\s*H?\s*UTC",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            try:
                day, month, year = (int(part) for part in match.group("date").split("/"))
                hour, minute = (int(part) for part in match.group("time").split(":"))
                return datetime(year, month, day, hour, minute, tzinfo=UTC)
            except (ValueError, OverflowError):
                return None
    return None


def _rows_as_warning_entries(rows: list[list[str]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        if not row:
            continue
        label = _normalized(row[0]).rstrip(":")
        value = " ".join(cell.strip() for cell in row[1:] if cell.strip())
        if label in {"warning", "avis", "تحذير"}:
            if current is not None:
                entries.append(current)
            current = {
                "description": value,
                "reference": None,
                "valid_from": None,
                "valid_until": None,
                "areas": [],
            }
        elif current is not None and label in {
            "reference time",
            "heure de référence",
            "وقت الإصدار",
        }:
            current["reference"] = value
        elif current is not None and label in {
            "beginning of validity",
            "début de validité",
            "بداية الصلاحية",
        }:
            current["valid_from"] = _parse_utc_datetime(value)
        elif current is not None and label in {
            "end of validity",
            "fin de validité",
            "نهاية الصلاحية",
        }:
            current["valid_until"] = _parse_utc_datetime(value)
        elif current is not None and label in {
            "threatened areas",
            "zones menacées",
            "المناطق المعنية",
        }:
            current["areas"] = [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
    if current is not None:
        entries.append(current)
    return entries


def _audit(
    *,
    request_id: str | None = None,
    status: InmCheckStatus,
    checked_at: datetime,
    reason_code: str,
    explanation_ar: str,
    http_status_code: int | None = None,
    server_date: datetime | None = None,
    response_age_seconds: float | None = None,
    cache_control: str | None = None,
    age_header_seconds: int | None = None,
    response_sha256: str | None = None,
    coverage_status: Literal["verified_tunisian_coasts", "unknown", "not_checked"] = "unknown",
    coverage_ar: str = "لم يثبت نطاق تغطية نشرة INM.",
    warning_entries_parsed: int = 0,
    warning_summary_ar: list[str] | None = None,
    warning_valid_from: datetime | None = None,
    warning_valid_until: datetime | None = None,
    threatened_areas: list[str] | None = None,
) -> InmWarningAudit:
    record = InmWarningAudit(
        status=status,
        request_id=request_id,
        checked_at=checked_at,
        http_status_code=http_status_code,
        server_date=server_date,
        response_age_seconds=response_age_seconds,
        cache_control=cache_control,
        age_header_seconds=age_header_seconds,
        response_sha256=response_sha256,
        coverage_status=coverage_status,
        coverage_ar=coverage_ar,
        warning_entries_parsed=warning_entries_parsed,
        warning_summary_ar=warning_summary_ar or [],
        warning_valid_from=warning_valid_from,
        warning_valid_until=warning_valid_until,
        threatened_areas=threatened_areas or [],
        reason_code=reason_code,
        explanation_ar=explanation_ar,
    )
    LOGGER.info(
        "inm_bms_audit request_id=%s status=%s reason=%s checked_at=%s http_status=%s "
        "response_sha256=%s coverage=%s parsed_entries=%s",
        record.request_id,
        record.status.value,
        record.reason_code,
        record.checked_at.isoformat(),
        record.http_status_code,
        record.response_sha256,
        record.coverage_status,
        record.warning_entries_parsed,
    )
    return record


class InmWarningClient:
    """Fail-closed checker for INM's official national BMS page.

    A clear result requires a fresh, uncached HTTP response, the explicit BMS
    clear phrase, parseable details for any bulletin still shown on the page,
    and complete Tunisian-coast scope. Any conflicting or unparseable content is
    returned as UNVERIFIED, never silently treated as clear.
    """

    def __init__(self, http_client: httpx.AsyncClient, *, timeout_seconds: float = 10.0) -> None:
        self._http = http_client
        self._timeout_seconds = timeout_seconds

    async def check(
        self,
        windows: list[tuple[datetime, datetime]],
        *,
        request_id: str | None = None,
    ) -> InmWarningAudit:
        def record(**kwargs: Any) -> InmWarningAudit:
            return _audit(request_id=request_id, **kwargs)

        checked_at = datetime.now(UTC)
        if not windows:
            return record(
                status=InmCheckStatus.NOT_CHECKED,
                checked_at=checked_at,
                reason_code="no_candidate_window",
                explanation_ar="لا توجد نافذة اجتازت بوابات الطقس والتنفيذ؛ لم تكن هناك حاجة لفحص INM.",
                coverage_status="not_checked",
                coverage_ar="لم يُطلب فحص التغطية لأن القرار NO_GO قبل بوابة INM.",
            )
        try:
            response = await self._http.get(
                INM_BMS_URL,
                headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="upstream_unavailable",
                explanation_ar=f"تعذر جلب نشرة INM الرسمية ({type(exc).__name__})؛ لا يمكن إثبات غياب التحذير.",
            )

        response_bytes = response.content
        digest = hashlib.sha256(response_bytes).hexdigest()
        server_date = _parse_server_date(response.headers.get("Date"))
        age_header_text = response.headers.get("Age")
        try:
            age_header = int(age_header_text) if age_header_text is not None else None
        except ValueError:
            age_header = -1
        cache_control = response.headers.get("Cache-Control", "")
        age_seconds = (checked_at - server_date).total_seconds() if server_date else None
        common = {
            "http_status_code": response.status_code,
            "server_date": server_date,
            "response_age_seconds": max(0.0, age_seconds) if age_seconds is not None else None,
            "cache_control": cache_control or None,
            "age_header_seconds": age_header
            if age_header is not None and age_header >= 0
            else None,
            "response_sha256": digest,
        }
        parsed_url = urlparse(str(response.url))
        host = parsed_url.hostname
        content_type = response.headers.get("Content-Type", "").casefold()
        if len(response_bytes) > 2_000_000:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="response_too_large",
                explanation_ar="استجابة INM تجاوزت الحجم التشغيلي المحدد؛ لم تُحلل جزئياً.",
                **common,
            )
        if response.status_code != 200:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="http_status_not_ok",
                explanation_ar=f"أعاد مصدر INM رمز HTTP {response.status_code}؛ لم تُعامل الاستجابة كتحذير صافٍ.",
                **common,
            )
        if (
            host not in {"meteo.tn", "www.meteo.tn"}
            or parsed_url.path.rstrip("/") != "/en/bms"
            or not content_type.startswith("text/html")
        ):
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="unexpected_source_or_content_type",
                explanation_ar="لم تطابق الاستجابة نطاق INM الرسمي أو نوع HTML المتوقع.",
                **common,
            )
        if (
            server_date is None
            or age_seconds is None
            or age_seconds < -MAX_HTTP_DATE_FUTURE_SKEW_SECONDS
            or age_seconds > MAX_HTTP_DATE_AGE_SECONDS
            or (age_header is not None and age_header != 0)
            or not any(
                token in cache_control.casefold()
                for token in ("no-cache", "no-store", "must-revalidate")
            )
        ):
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="stale_or_cacheable_http_response",
                explanation_ar="حداثة الاستجابة غير مثبتة: يلزم Date حديث، وعدم وجود Age مخزّن، وتوجيه إعادة تحقق من الكاش.",
                **common,
            )
        latest_window_end = max(end for _, end in windows)
        if latest_window_end > checked_at + timedelta(hours=MAX_TARGET_LEAD_HOURS):
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="requested_window_beyond_warning_status_horizon",
                explanation_ar="حالة «لا يوجد تحذير» الحالية لا تثبت حالة يوم مستقبلي بعيد؛ نافذة القرار تتجاوز 24 ساعة من وقت التحقق.",
                **common,
            )

        parser = _BmsHtmlParser()
        try:
            parser.feed(response.text)
            parser.close()
        except Exception:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="html_parse_failed",
                explanation_ar="تعذر تحليل بنية نشرة INM بأمان؛ لم يُفترض أنها خالية من التحذير.",
                **common,
            )
        bms_text = _normalized(" ".join(parser.blocks["block-bmsblock"]))
        front_text = _normalized(" ".join(parser.blocks["block-bms-frontblock"]))
        clear_present = any(phrase in bms_text for phrase in _CLEAR_PHRASES)
        entries = _rows_as_warning_entries(parser.rows)
        if not bms_text:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="official_bms_block_missing",
                explanation_ar="لم يُعثر على كتلة BMS الرسمية المتوقعة؛ تغير تخطيط الموقع أو نقصت الاستجابة.",
                **common,
            )
        if not clear_present and not entries:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="no_explicit_clear_or_parseable_warning",
                explanation_ar="لم تعرض كتلة BMS عبارة خلو صريحة ولم يمكن تحليل نشرة تحذير كاملة.",
                **common,
            )

        summaries: list[str] = []
        all_areas: list[str] = []
        active_entries: list[dict[str, Any]] = []
        unparsed_entries: list[dict[str, Any]] = []
        for entry in entries:
            description = re.sub(r"\s+", " ", entry["description"]).strip()
            if not description or _normalized(description) in {"none", "aucun", "لا يوجد"}:
                continue
            valid_from = entry["valid_from"]
            valid_until = entry["valid_until"]
            areas = entry["areas"]
            validity_text = (
                f" {valid_from.isoformat()} → {valid_until.isoformat()}"
                if valid_from is not None and valid_until is not None
                else " صلاحية غير مكتملة"
            )
            area_text = f" · {', '.join(areas)}" if areas else ""
            summaries.append(f"{description[:120]}{validity_text}{area_text}")
            all_areas.extend(areas)
            if valid_from is None or valid_until is None or not areas:
                unparsed_entries.append(entry)
                continue
            if valid_until <= valid_from:
                unparsed_entries.append(entry)
                continue
            if any(valid_from < end and valid_until > start for start, end in windows):
                active_entries.append(entry)

        if active_entries:
            chosen = active_entries[0]
            warning_message = "؛ ".join(str(item["description"]) for item in active_entries)
            return record(
                status=InmCheckStatus.WARNING_ACTIVE,
                checked_at=checked_at,
                reason_code="official_warning_overlaps_window",
                explanation_ar=f"وجدت نشرة BMS رسمية تتقاطع صلاحيتها مع نافذة الخروج: {warning_message[:350]}.",
                coverage_status="verified_tunisian_coasts",
                coverage_ar="نطاق BMS الوطني؛ احتُسب أي تحذير ساحلي تونسي نشط مانعاً احترازياً لكل السبوتات، دون تخمين تقاطع محلي.",
                warning_entries_parsed=len(entries),
                warning_summary_ar=summaries,
                warning_valid_from=chosen["valid_from"],
                warning_valid_until=chosen["valid_until"],
                threatened_areas=list(
                    dict.fromkeys(area for entry in active_entries for area in entry["areas"])
                ),
                **common,
            )
        if unparsed_entries:
            return record(
                status=InmCheckStatus.UNVERIFIED,
                checked_at=checked_at,
                reason_code="warning_details_incomplete_or_conflicting",
                explanation_ar="توجد مادة تحذير في الصفحة لكن وقت الصلاحية أو المنطقة غير مكتمل؛ تعارضها مع عبارة الخلو يمنع إصدار GO.",
                warning_entries_parsed=len(entries),
                warning_summary_ar=summaries,
                threatened_areas=all_areas,
                **common,
            )
        if clear_present:
            if entries and not summaries and "warning" not in front_text:
                return record(
                    status=InmCheckStatus.UNVERIFIED,
                    checked_at=checked_at,
                    reason_code="clear_statement_conflict",
                    explanation_ar="تعذر التوفيق بين كتلة BMS وبيانات التحذير المرافقة؛ بقيت الحالة غير متحققة.",
                    warning_entries_parsed=len(entries),
                    **common,
                )
            return record(
                status=InmCheckStatus.VERIFIED_CLEAR,
                checked_at=checked_at,
                reason_code="explicit_current_no_gale_warning",
                explanation_ar="استجابة INM حديثة وغير مخزنة تعرض صراحةً «No gale warning»؛ كل تفاصيل التحذيرات الظاهرة قابلة للتحليل ولا تتقاطع مع النافذة.",
                coverage_status="verified_tunisian_coasts",
                coverage_ar="نشرة BMS الوطنية للإنذار البحري في السواحل التونسية؛ عند ظهور أي تحذير نشط يُمنع القرار تحفظياً دون افتراض نطاق محلي.",
                warning_entries_parsed=len(entries),
                warning_summary_ar=summaries,
                threatened_areas=all_areas,
                **common,
            )
        return record(
            status=InmCheckStatus.UNVERIFIED,
            checked_at=checked_at,
            reason_code="warning_page_not_explicitly_clear",
            explanation_ar="لا تثبت الصفحة خلوّاً صريحاً من التحذير للفترة المطلوبة.",
            warning_entries_parsed=len(entries),
            warning_summary_ar=summaries,
            threatened_areas=all_areas,
            **common,
        )
