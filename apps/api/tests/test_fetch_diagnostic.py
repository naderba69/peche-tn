"""Diagnostic builder checks on synthetic geometry. Decisions are never touched."""

from datetime import UTC, datetime

from spotdata.services.fetch_exposure import build_wave_fetch_diagnostic

ORIGIN_LAT = 36.4
ORIGIN_LON = 10.6
M_PER_DEG_LAT = 111_195.0


def _seg_m(
    a: tuple[float, float], b: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    def to_ll(x: float, y: float) -> tuple[float, float]:
        import math

        return (
            ORIGIN_LAT + y / M_PER_DEG_LAT,
            ORIGIN_LON + x / (M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))),
        )

    return to_ll(*a), to_ll(*b)


def test_unavailable_without_geometry_keeps_samples_empty() -> None:
    diag = build_wave_fetch_diagnostic(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=147.5,
        segments=None,
        search_radius_m=30_000.0,
        hourly_wave_from=[(datetime(2026, 10, 13, 0, tzinfo=UTC), 24.0)],
    )
    assert diag.status == "unavailable"
    assert diag.samples == []


def test_land_side_and_missing_hours_are_handled() -> None:
    hours = [
        (datetime(2026, 10, 13, 0, tzinfo=UTC), 180.0),  # from the land side
        (datetime(2026, 10, 13, 1, tzinfo=UTC), 0.0),  # from the sea side
        (datetime(2026, 10, 13, 2, tzinfo=UTC), None),  # missing: no sample
    ]
    diag = build_wave_fetch_diagnostic(
        latitude=ORIGIN_LAT,
        longitude=ORIGIN_LON,
        seaward_deg=0.0,
        segments=[_seg_m((-50_000.0, 0.0), (50_000.0, 0.0))],
        search_radius_m=30_000.0,
        hourly_wave_from=hours,
    )
    assert diag.status == "resolved"
    assert len(diag.samples) == 2
    assert diag.samples[0].in_seaward_sector is False
    assert diag.samples[0].fetch_km is None
    assert diag.samples[1].in_seaward_sector is True
    assert diag.samples[1].fetch_km == 30.0
    assert diag.samples[1].hit_coastline is False
