from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from spotdata import __version__
from spotdata.api.routes import router
from spotdata.config import settings
from spotdata.services.coast_orientation import CoastOrientationClient
from spotdata.services.copernicus_water import CopernicusWaterClient
from spotdata.services.gemini import GeminiClient
from spotdata.services.open_meteo import OpenMeteoClient

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx logs full query URLs at INFO, including spot coordinates. Keep routine
# upstream URLs out of platform logs; adapters emit bounded warnings themselves.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    timeout = httpx.Timeout(settings.upstream_timeout_seconds, connect=5.0)
    limits = httpx.Limits(max_connections=40, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
        headers={"User-Agent": f"Peche-TN/{__version__}"},
    ) as http_client:
        app.state.http_client = http_client
        app.state.open_meteo = OpenMeteoClient(
            http_client=http_client,
            weather_url=settings.weather_url,
            marine_url=settings.marine_url,
            observation_url=settings.observation_url,
        )
        app.state.coast_orientation = CoastOrientationClient(
            http_client=http_client,
            servers=settings.overpass_servers,
        )
        app.state.copernicus_water = CopernicusWaterClient(http_client=http_client)
        app.state.gemini = GeminiClient(
            http_client=http_client,
            base_url=settings.gemini_base_url,
            model=settings.gemini_model,
        )
        yield


app = FastAPI(
    title="Peche TN Decision API",
    description=(
        "محرك قرار قابل للتفسير وآمن أولاً لصيد السيرفكاست في تونس. "
        "مؤشر الفرصة ليس احتمال نجاح، والبيانات الساحلية النموذجية لا تعوض المعاينة."
    ),
    version=__version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-Gemini-API-Key"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)


@app.middleware("http")
async def request_metadata(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1_000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    LOGGER.exception("unhandled request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message_ar": "حدث خطأ داخلي غير متوقع.",
                "request_id": request_id,
            }
        },
    )


app.include_router(router, prefix="/api")
