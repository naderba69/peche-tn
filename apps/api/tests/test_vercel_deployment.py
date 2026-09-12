from __future__ import annotations

import json
from pathlib import Path

from api.index import app
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_vercel_entrypoint_uses_file_routing_without_custom_api_routes() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))

    function_config = config["functions"]["api/index.py"]
    assert function_config["includeFiles"] == "apps/api/src/spotdata/**"

    # Vercel natively treats api/index.py as the /api/* catch-all. A custom
    # rewrite or route to the same path can divert the request into Next.js or
    # rematch itself, which caused the production failures in 1.0.1 and 1.1.0.
    assert "rewrites" not in config
    assert "routes" not in config
    assert "builds" not in config

    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fastapi==" in requirements
    assert "httpx==" in requirements
    assert "pydantic==" in requirements
    assert isinstance(app, FastAPI)

    # FastAPI routes keep the complete public /api prefix, matching Vercel's
    # documented file-system routing contract for api/index.py.
    with TestClient(app) as client:
        root = client.get("/api")
        health = client.get("/api/health", params={"probe": "kept"})
        methodology = client.get("/api/methodology")

    assert root.status_code == 200
    assert root.json()["name"] == "Peche TN Decision API"
    assert health.status_code == 200
    assert health.json()["version"] == "1.10.0"
    assert methodology.status_code == 200


def test_render_app_serves_clean_urls_for_exported_pages(
    tmp_path: Path, monkeypatch
) -> None:
    """The Render entrypoint must serve Next's ``<route>.html`` exports at clean URLs.

    Next's static export writes ``calendar.html`` next to a ``calendar/`` directory
    of RSC navigation payloads; Starlette's ``StaticFiles(html=True)`` only serves
    ``index.html`` inside directories, so ``/calendar`` would 404 without the
    explicit clean-URL routes registered in ``deploy/render_app.py``.
    """
    import importlib

    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>home</title>", encoding="utf-8")
    (web / "calendar.html").write_text("<!doctype html><title>calendar</title>", encoding="utf-8")
    (web / "wilayas.html").write_text("<!doctype html><title>wilayas</title>", encoding="utf-8")
    monkeypatch.setenv("PECHE_TN_STATIC_DIR", str(web))
    render_app = importlib.import_module("deploy.render_app")

    with TestClient(render_app.app) as client:
        assert client.get("/calendar").status_code == 200
        assert client.get("/calendar").text == "<!doctype html><title>calendar</title>"
        assert client.get("/wilayas").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/api/health").status_code == 200


def test_render_blueprint_builds_and_health_checks_one_full_stack_container() -> None:
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    adapter = (PROJECT_ROOT / "deploy" / "render_app.py").read_text(encoding="utf-8")

    assert "runtime: docker" in blueprint
    assert "plan: free" in blueprint
    assert "region: frankfurt" in blueprint
    assert "healthCheckPath: /api/health" in blueprint
    assert "FROM node:22-bookworm-slim AS frontend-build" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "npm run build:render" in dockerfile
    assert "${PORT:-10000}" in dockerfile
    assert "deploy.render_app:app" in dockerfile
    assert 'app.mount("/", StaticFiles' in adapter
    assert "GEMINI" not in blueprint.upper()
