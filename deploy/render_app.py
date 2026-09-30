"""Single-origin Render entrypoint: FastAPI API plus exported Next.js frontend."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spotdata.main import app

_STATIC_ROOT = Path(os.environ.get("PECHE_TN_STATIC_DIR", "/app/web")).resolve()
_INDEX = _STATIC_ROOT / "index.html"

if not _INDEX.is_file():
    raise RuntimeError(
        f"Peche TN static frontend is missing at {_INDEX}. "
        "Build with PECHE_TN_STATIC_EXPORT=1 before starting the Render app."
    )


def _page_handler(page_file: Path):
    async def handler() -> FileResponse:
        return FileResponse(page_file)

    return handler


# Next's static export writes each route as ``<route>.html`` (e.g. ``calendar.html``)
# next to a ``<route>/`` directory that holds the RSC navigation payloads. Starlette's
# ``StaticFiles(html=True)`` only serves ``index.html`` inside a directory, so the
# clean URLs (``/calendar``, ``/wilayas``, ``/bulletin``) would 404. Register them
# explicitly before mounting the catch-all static files; the ``/api/*`` routes were
# registered first and keep their priority.
for _html in sorted(_STATIC_ROOT.glob("*.html")):
    _slug = _html.stem
    if _slug in {"index", "404", "_not-found"}:
        continue
    app.get(f"/{_slug}", include_in_schema=False)(_page_handler(_html))

app.mount("/", StaticFiles(directory=_STATIC_ROOT, html=True), name="frontend")

__all__ = ["app"]
