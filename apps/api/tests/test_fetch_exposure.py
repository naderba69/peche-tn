"""Synthetic-geometry checks for fetch exposure. No live data is used."""

import math

from spotdata.services.fetch_exposure import (
    fetch_profile,
    fetch_toward_wave_source,
)

M_PER_DEG_LAT = 111_195.0  # approx metres per degree of latitude


def _metres_to_latlon(x_m: float, y_m: float, origin_lat: float) -> tuple[float, float]:
    """East/north metres -> (lat, lon) around the origin, for building test geometry."""
    lat = y_m / M_PER_DEG_LAT
    lon = x_m / (M_PER_DEG_LAT * math.cos(math.radians(origin_lat)))
    return origin_lat + lat, ORIGIN_LON + lon


ORIGIN_LAT = 36.4
ORIGIN_LON = 10.6


def _segment(
    a_m: tuple[float, float], b_m: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        _metres_to_latlon(a_m[0], a_m[1], ORIGIN_LAT)[0],
        _metres_to_latlon(a_m[0], a_m[1], ORIGIN_LAT)[1],
    ), (
        _metres_to_latlon(b_m[0], b_m[1], ORIGIN_LAT)[0],
        _metres_to_latlon(b_m[0], b_m[1], ORIGIN_LAT)[1],
    )


def _seg(a: tuple[float, float], b: tuple[float, float]):  # type: ignore[no-untyped-def]
    la1, lo1 = _metres_to_latlon(a[0], a[1], ORIGIN_LAT)
    la2, lo2 = _metres_to_latlon(b[0], b[1], ORIGIN_LAT)
    return (la1, lo1), (la2, lo2)


def test_open_coast_has_long_fetch_in_seaward_half_plane() -> None:
    # Spot on a straight E-W coast; sea to the north (seaward = 0°). No other land.
    rays = fetch_profile(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        coastline_segments=[_seg((-50_000.0, 0.0), (50_000.0, 0.0))],
        search_radius_m=50_000.0,
    )
    assert rays, "seaward rays must be produced"
    # Only the seaward half-plane is sampled: no bearing from the land side.
    assert all(abs(((ray.bearing_deg + 180) % 360) - 180) <= 90 for ray in rays)
    northward = next(ray for ray in rays if ray.bearing_deg == 0.0)
    assert northward.fetch_m == 50_000.0  # nothing crossed within radius
    assert not northward.hit_coastline


def test_headland_to_the_north_shortens_fetch_in_that_sector() -> None:
    # A land barrier 10 km north of the spot, spanning x = -50..+50 km.
    barrier = _seg((-50_000.0, 10_000.0), (50_000.0, 10_000.0))
    rays = fetch_profile(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        coastline_segments=[barrier],
        search_radius_m=50_000.0,
    )
    north = next(ray for ray in rays if ray.bearing_deg == 0.0)
    assert north.hit_coastline
    assert abs(north.fetch_m - 10_000.0) < 1.0
    # 30° off north still hits the barrier at 10 km / cos(30°).
    thirty = next(ray for ray in rays if ray.bearing_deg == 30.0)
    assert abs(thirty.fetch_m - 10_000.0 / math.cos(math.radians(30))) < 5.0


def test_wave_from_land_side_is_outside_the_seaward_sector() -> None:
    rays = fetch_profile(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        coastline_segments=[_seg((-50_000.0, 0.0), (50_000.0, 0.0))],
        search_radius_m=50_000.0,
    )
    assert fetch_toward_wave_source(rays, 180.0) is None
    assert fetch_toward_wave_source(rays, 24.0) is not None


def test_spot_on_coastline_ignores_its_own_segment() -> None:
    # Spot sits on the coastline (own segment at t≈0 must not count as fetch).
    rays = fetch_profile(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        coastline_segments=[_seg((-50_000.0, 0.0), (50_000.0, 0.0))],
        search_radius_m=20_000.0,
    )
    assert all(ray.fetch_m > 1_000.0 for ray in rays)


def test_wave_from_blocked_sector_reports_short_fetch() -> None:
    barrier = _seg((-50_000.0, 2_000.0), (50_000.0, 2_000.0))
    rays = fetch_profile(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        coastline_segments=[barrier],
        search_radius_m=50_000.0,
    )
    ray = fetch_toward_wave_source(rays, 0.0)
    assert ray is not None
    assert ray.hit_coastline
    assert ray.fetch_m < 3_000.0
