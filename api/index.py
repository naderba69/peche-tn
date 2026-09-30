"""Vercel Python Function entrypoint for the Peche TN FastAPI app.

Vercel natively maps ``api/index.py`` to ``/api`` and ``/api/*``. The routes in
``spotdata.main`` therefore keep their complete public ``/api`` prefix. The
small ``functions.includeFiles`` setting only bundles the engine source; no
custom rewrite or route is used.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PROJECT_ROOT / "apps" / "api" / "src"
if not _SOURCE_ROOT.is_dir():
    # Vercel normally preserves the repository layout under /var/task. Keep a
    # conservative fallback in case the entrypoint is relocated in the bundle.
    _SOURCE_ROOT = Path.cwd() / "apps" / "api" / "src"

sys.path.insert(0, str(_SOURCE_ROOT))

# Vercel's Python runtime detects this top-level ASGI application directly.
from spotdata.main import app  # noqa: E402

__all__ = ["app"]
