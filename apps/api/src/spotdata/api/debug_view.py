"""DEVELOPMENT-ONLY debug view. Remove before production.

Enabled only when the environment variable SPOTDATA_DEV_DEBUG=1 is set.
It shows the same decision the app computes, plus the per-hour reasons and the
raw JSON, in a single mobile-friendly page. It stores nothing and sends no keys.
"""

from __future__ import annotations

import html
import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from spotdata.api.routes import forecast_decision
from spotdata.domain.models import Coordinates, ForecastDecisionRequest, SpotProfile

router = APIRouter(prefix="/debug", tags=["debug-dev-only"])
TUNIS = ZoneInfo("Africa/Tunis")


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


@router.get("/view", response_class=HTMLResponse, include_in_schema=False)
async def debug_view(
    request: Request,
    lat: float = Query(36.399),
    lon: float = Query(10.578),
    date: str | None = Query(None, description="YYYY-MM-DD; default today (Tunis)"),
    shore: str = Query("sandy"),
) -> HTMLResponse:
    target = datetime.fromisoformat(date).date() if date else datetime.now(TUNIS).date()
    body = ""
    try:
        payload = ForecastDecisionRequest(
            location=Coordinates(latitude=lat, longitude=lon),
            target_date=target,
            spot=SpotProfile(shore_type=shore, shore_type_source="user"),
        )
        result = await forecast_decision(payload, request)
        data = result.model_dump(mode="json")
        body = _render(data)
    except Exception as exc:  # dev-only: show the failure instead of hiding it
        body = (
            f"<h2>خطأ داخلي</h2><pre>{_esc(type(exc).__name__)}: {_esc(exc)}</pre>"
            f"<pre>{_esc(traceback.format_exc())}</pre>"
        )
    return HTMLResponse(_page(body))


def _render(data: dict[str, object]) -> str:
    decision = _esc(data.get("decision"))
    reason = _esc(data.get("decision_reason_code"))
    windows = data.get("recommended_windows") or []
    hourly = data.get("hourly") or []
    rows = []
    for item in hourly:  # type: ignore[attr-defined]
        factors = [
            f for f in item.get("factors", []) if f.get("severity") in ("caution", "critical")
        ]
        reasons = "، ".join(_esc(f.get("code")) for f in factors) or "—"
        rows.append(
            "<tr>"
            f"<td>{_esc(str(item.get('time'))[11:16])}</td>"
            f"<td class='s-{_esc(item.get('safety'))}'>{_esc(item.get('safety'))}</td>"
            f"<td>{reasons}</td>"
            "</tr>"
        )
    win_rows = (
        "".join(
            f"<li>{_esc(w.get('safety'))}: {_esc(w.get('headline_ar'))}</li>"
            for w in windows  # type: ignore[attr-defined]
        )
        or "<li>لا توجد نوافذ</li>"
    )
    raw = _esc(json.dumps(data, ensure_ascii=False, indent=2))
    return (
        f"<h2>القرار: {decision}</h2><p>السبب الرمزي: <b>{reason}</b></p>"
        f"<h3>النوافذ</h3><ul>{win_rows}</ul>"
        "<h3>الساعات</h3><table><tr><th>الساعة</th><th>السلامة</th>"
        f"<th>أسباب التحذير/المنع</th></tr>{''.join(rows)}</table>"
        f"<details><summary>JSON الخام</summary><pre>{raw}</pre></details>"
    )


def _page(body: str) -> str:
    return f"""<!doctype html><html dir="rtl" lang="ar"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DEV debug view</title>
<style>
body{{font-family:system-ui,sans-serif;margin:12px;font-size:15px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #ccc;padding:4px}}
.s-go{{background:#d9f7e3}} .s-caution{{background:#fff3c4}}
.s-no_go{{background:#ffd6d6}} .s-unknown{{background:#e6e6e6}}
pre{{white-space:pre-wrap;word-break:break-word;font-size:11px;direction:ltr}}
</style></head><body>
<p style="color:#a00"><b>وضع تطوير فقط — يُحذف قبل الإنتاج</b></p>
{body}
</body></html>"""


@router.get("/dataset", include_in_schema=False)
async def debug_dataset(
    request: Request,
    lat: float = Query(36.399),
    lon: float = Query(10.578),
    date: str | None = Query(None),
    shore: str = Query("sandy"),
) -> dict[str, object]:
    """DEV ONLY: return the raw forecast INPUT (dataset) so it can be replayed offline."""
    from spotdata.domain.enums import OrientationSource

    target = datetime.fromisoformat(date).date() if date else datetime.now(TUNIS).date()
    auto = await request.app.state.coast_orientation.resolve(lat, lon)
    spot = SpotProfile(
        seaward_orientation_deg=auto.orientation_deg,
        orientation_source=OrientationSource.OVERPASS,
        orientation_evidence=auto.evidence,
        shore_type=shore,
        shore_type_source="user",
    )
    payload = ForecastDecisionRequest(
        location=Coordinates(latitude=lat, longitude=lon),
        target_date=target,
        spot=spot,
    )
    dataset = await request.app.state.open_meteo.forecast_dataset(payload)
    result: dict[str, object] = dataset.model_dump(mode="json")
    return result
