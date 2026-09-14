from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    host: str
    port: int
    log_level: str
    allowed_origins: tuple[str, ...]
    weather_url: str
    marine_url: str
    observation_url: str
    overpass_servers: tuple[str, ...]
    gemini_base_url: str
    gemini_model: str
    upstream_timeout_seconds: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            host=os.getenv("APP_HOST", "0.0.0.0"),
            port=int(os.getenv("APP_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            allowed_origins=_csv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000"),
            weather_url=os.getenv(
                "OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast"
            ),
            marine_url=os.getenv(
                "OPEN_METEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine"
            ),
            observation_url=os.getenv(
                "AVIATION_WEATHER_METAR_URL", "https://aviationweather.gov/api/data/metar"
            ),
            overpass_servers=_csv(
                "OVERPASS_SERVERS",
                "https://overpass-api.de/api/interpreter,"
                "https://overpass.kumi.systems/api/interpreter,"
                "https://overpass.openstreetmap.fr/api/interpreter",
            ),
            gemini_base_url=os.getenv(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
            ).rstrip("/"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            upstream_timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "15")),
        )


settings = Settings.from_env()
