#!/usr/bin/env python3
"""Zero-dependency post-deployment smoke test for Peche TN.

Expected versions are read from the repository source (``spotdata.__version__``,
``ENGINE_VERSION`` and ``SCHEMA_VERSION``) so this script never drifts out of
sync with a release. When run outside a checkout it falls back to consistency
checks only (root version must equal health version, and the decision must echo
the health engine/schema versions), which still catches a mismatched deploy.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://peche-tn.vercel.app").rstrip("/")
# Render Free can need roughly a minute to wake after idling; leave margin for
# the first request without weakening any response-contract assertion.
TIMEOUT = 120

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_constant(relative_path: str, marker: str) -> str:
    try:
        text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped.split("=", 1)[1].strip().strip("\"'")
    return ""


def _expected_versions() -> dict[str, str]:
    """Read release versions from source, overridable via environment."""
    return {
        "version": os.environ.get(
            "PECHE_TN_EXPECTED_VERSION",
            _extract_constant("apps/api/src/spotdata/__init__.py", "__version__"),
        ),
        "engine": os.environ.get(
            "PECHE_TN_EXPECTED_ENGINE",
            _extract_constant("apps/api/src/spotdata/domain/engine.py", "ENGINE_VERSION"),
        ),
        "schema": os.environ.get(
            "PECHE_TN_EXPECTED_SCHEMA",
            _extract_constant("apps/api/src/spotdata/domain/models.py", "SCHEMA_VERSION"),
        ),
    }


def request(path: str, payload: dict[str, object] | None = None) -> tuple[int, str, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"User-Agent": "Peche-TN-release-smoke", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + path, data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def require_json(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    status, content_type, raw = request(path, payload)
    if status != 200 or "json" not in content_type.lower():
        excerpt = raw[:180].decode(errors="replace").replace("\n", " ")
        raise RuntimeError(
            f"{path}: HTTP {status}, {content_type or 'no content-type'} — {excerpt}"
        )
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{path}: JSON root is not an object")
    body = cast(dict[str, object], parsed)
    print(f"PASS {path} — HTTP 200 JSON")
    return body


def main() -> int:
    versions = _expected_versions()
    try:
        status, content_type, _ = request("/")
        if status != 200 or "html" not in content_type.lower():
            raise RuntimeError(f"/: HTTP {status}, {content_type}")
        print("PASS / — frontend HTML")

        root = require_json("/api")
        health = require_json("/api/health")
        require_json("/api/methodology")
        require_json("/api/openapi.json")
        docs_status, docs_type, _ = request("/api/docs")
        if docs_status != 200 or "html" not in docs_type.lower():
            raise RuntimeError(f"/api/docs: HTTP {docs_status}, {docs_type}")
        print("PASS /api/docs — Swagger HTML")

        if root.get("version") != health.get("version"):
            raise RuntimeError(
                f"root and health disagree: root={root.get('version')} health={health.get('version')}"
            )
        expected_version = versions["version"]
        if expected_version:
            if health.get("version") != expected_version:
                raise RuntimeError(
                    f"wrong API version: health={health.get('version')} expected={expected_version}"
                )
            print(f"PASS version pin — health reports {expected_version}")
        else:
            print("PASS version consistency — root == health (no source checkout to pin)")

        # Always test tomorrow: a late-evening smoke of today's date can
        # correctly have fewer future hours than the requested session length.
        target_date = (
            datetime.now(ZoneInfo("Africa/Tunis")).date() + timedelta(days=1)
        ).isoformat()
        decision = require_json(
            "/api/v1/decisions/forecast",
            {
                "location": {
                    "latitude": 36.4561,
                    "longitude": 10.7389,
                    "name": "Nabeul smoke test",
                },
                "target_date": target_date,
                "spot": {
                    "seaward_orientation_deg": 90,
                    "orientation_source": "manual",
                    "shore_type": "sandy",
                    "exposure": "open",
                },
                "angler": {
                    "experience": "intermediate",
                    "target_species": "general",
                    "session_hours": 3,
                },
            },
        )
        if decision.get("decision") not in {"go", "no_go"}:
            raise RuntimeError(f"headline is not binary: {decision.get('decision')}")
        if versions["schema"] and decision.get("schema_version") != versions["schema"]:
            raise RuntimeError(
                f"wrong decision schema: {decision.get('schema_version')} expected={versions['schema']}"
            )
        if versions["engine"] and decision.get("engine_version") != versions["engine"]:
            raise RuntimeError(
                f"wrong decision engine: {decision.get('engine_version')} expected={versions['engine']}"
            )
        factor_assessments = decision.get("factor_assessments")
        if not isinstance(factor_assessments, list) or len(factor_assessments) != 63:
            raise RuntimeError("factor ledger does not contain exactly 63 records")
        water = decision.get("coastal_water_context")
        if not isinstance(water, dict) or water.get("availability") not in {
            "available",
            "unavailable",
        }:
            raise RuntimeError("Sentinel-2 context is missing its explicit availability contract")
        if water.get("affects_final_decision") is not False:
            raise RuntimeError("Sentinel-2 context unexpectedly affects the final decision")
        if water.get("turbidity_unit") != "FNU":
            raise RuntimeError("Sentinel-2 TUR unit contract is not FNU")
        antecedent_hours = decision.get("antecedent_hours")
        if not isinstance(antecedent_hours, list) or len(antecedent_hours) < 48:
            raise RuntimeError("antecedent history is shorter than 48 hours")
        print(
            f"PASS decision contract — {decision['decision']}, 63 factors, "
            f"48-72h history, Sentinel-2 {water['availability']}"
        )

        orientation = require_json(
            "/api/v1/spots/orientation",
            {"latitude": 36.4561, "longitude": 10.7389},
        )
        if orientation.get("status") not in {"resolved", "unavailable"}:
            raise RuntimeError(f"unexpected orientation status: {orientation.get('status')}")
        if orientation.get("status") == "resolved" and not orientation.get("evidence"):
            raise RuntimeError("resolved orientation is missing evidence")
        print(f"PASS orientation contract — {orientation.get('status')} (no fabricated fallback)")
        version_label = health.get("version") or "current"
        print(f"\nALL PASS — {BASE} is serving Peche TN {version_label} frontend and API contracts.")
        return 0
    except Exception as exc:
        print(f"\nFAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
