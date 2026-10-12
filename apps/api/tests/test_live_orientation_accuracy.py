"""Live accuracy check for the coastline orientation against real OpenStreetMap geometry.

Opt-in: runs only when PECHE_TN_LIVE_OSM=1 (needs outbound access to Overpass).

For each preset spot it compares two things that were computed independently:
  * the API's seaward orientation (CoastOrientationClient, real Overpass data), and
  * a reference bearing from the spot to the nearest point on the same OSM coastline,
    computed here with separate code (raw Overpass query, local projection, nearest point).
The reference is only compared where the coastline is within 500 m, the distance the app
itself uses to call an orientation verified.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
from pathlib import Path

import httpx
import pytest

from spotdata.services.coast_orientation import CoastOrientationClient

LIVE = os.getenv("PECHE_TN_LIVE_OSM") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set PECHE_TN_LIVE_OSM=1 to query Overpass")

DEFAULT_SERVERS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)
VERIFIED_MAX_COAST_M = 500.0
ANGLE_TOLERANCE_DEG = 5.0
REFERENCE_RADIUS_M = 3000
REPO_ROOT = Path(__file__).resolve().parents[3]


def preset_points() -> list[tuple[str, float, float]]:
    text = (REPO_ROOT / "lib" / "spots.ts").read_text(encoding="utf-8")
    pattern = re.compile(
        r'name:\s*"([^"]+)".*?latitude:\s*([0-9.]+),\s*longitude:\s*([0-9.]+)', re.DOTALL
    )
    return [(name, float(lat), float(lon)) for name, lat, lon in pattern.findall(text)]


def servers() -> tuple[str, ...]:
    raw = os.getenv("OVERPASS_SERVERS")
    return tuple(s.strip() for s in raw.split(",") if s.strip()) if raw else DEFAULT_SERVERS


async def fetch_coastline_ways(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    query = f'[out:json][timeout:25];way(around:{REFERENCE_RADIUS_M},{lat},{lon})["natural"="coastline"];out geom;'
    for server in servers():
        try:
            response = await client.post(server, data={"data": query}, timeout=40)
            response.raise_for_status()
            return [e for e in response.json().get("elements", []) if e.get("type") == "way"]
        except (httpx.HTTPError, ValueError):
            continue
    raise RuntimeError("no Overpass server answered")


def reference_seaward_bearing(ways: list[dict], lat: float, lon: float) -> tuple[float, float]:
    """Returns (bearing from spot to nearest coast point in degrees, distance in metres)."""
    kx = 111_320 * math.cos(math.radians(lat))
    ky = 110_574.0
    best_distance = math.inf
    best_point = (lat, lon)
    for way in ways:
        geometry = way.get("geometry") or []
        for a, b in zip(geometry, geometry[1:]):
            ax, ay = (a["lon"] - lon) * kx, (a["lat"] - lat) * ky
            bx, by = (b["lon"] - lon) * kx, (b["lat"] - lat) * ky
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
            px, py = ax + t * dx, ay + t * dy
            distance = math.hypot(px, py)
            if distance < best_distance:
                best_distance = distance
                best_point = (lat + py / ky, lon + px / kx)
    if math.isinf(best_distance) or best_distance == 0:
        return math.nan, best_distance
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2, lo2 = math.radians(best_point[0]), math.radians(best_point[1])
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360, best_distance


def angular_difference(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


async def run_comparison() -> list[dict]:
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=40) as http_client:
        client = CoastOrientationClient(http_client=http_client, servers=servers())
        for name, lat, lon in preset_points():
            result = await client.resolve(lat, lon)
            ways = await fetch_coastline_ways(http_client, lat, lon)
            reference, coast_m = reference_seaward_bearing(ways, lat, lon)
            row = {
                "spot": name,
                "status": result.status,
                "api_deg": result.orientation_deg,
                "reference_deg": None if math.isnan(reference) else round(reference, 1),
                "coast_m": round(coast_m, 1),
                "error_deg": None,
            }
            if (
                result.status == "resolved"
                and result.orientation_deg is not None
                and not math.isnan(reference)
                and coast_m <= VERIFIED_MAX_COAST_M
            ):
                row["error_deg"] = round(angular_difference(result.orientation_deg, reference), 1)
            rows.append(row)
    return rows


def test_api_orientation_matches_osm_coastline_geometry() -> None:
    rows = asyncio.run(run_comparison())

    print("\nspot | status | api_deg | reference_deg | coast_m | error_deg")
    for row in rows:
        print(
            f"{row['spot']} | {row['status']} | {row['api_deg']} | "
            f"{row['reference_deg']} | {row['coast_m']} | {row['error_deg']}"
        )

    comparable = [row for row in rows if row["error_deg"] is not None]
    print(f"comparable (resolved and coast <= {VERIFIED_MAX_COAST_M:.0f} m): {len(comparable)}/{len(rows)}")

    assert comparable, "no preset produced a verified orientation to compare against OSM"
    worst = max(row["error_deg"] for row in comparable)
    assert worst <= ANGLE_TOLERANCE_DEG, f"worst orientation error {worst}° exceeds {ANGLE_TOLERANCE_DEG}°"
