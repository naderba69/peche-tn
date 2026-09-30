from dataclasses import dataclass

from .enums import ShoreType
from .models import AnglerProfile, SpotProfile


@dataclass(frozen=True, slots=True)
class SafetyThresholds:
    sustained_wind_caution_kmh: float
    sustained_wind_no_go_kmh: float
    gust_caution_kmh: float
    gust_no_go_kmh: float
    wave_caution_m: float
    wave_no_go_m: float
    steepness_caution: float = 0.065
    steepness_no_go: float = 0.090
    visibility_caution_m: float = 1_000.0
    visibility_no_go_m: float = 200.0


# One physical safety envelope applies to every experience level. Experience can
# inform gear and technique recommendations, but must never relax wind, gust or
# wave safety gates. These values are the existing most-conservative profile;
# they remain operational policy thresholds, not field-calibrated guarantees.
_UNIVERSAL_SAFETY_BASE = (28.0, 38.0, 36.0, 50.0, 0.9, 1.55)

OPERATIONAL_HORIZON_HOURS = 72

# Applies to the wave-height thresholds only, not to wind: standing on rock,
# a jetty or a cliff changes the tolerable breaking-wave height, whereas wind
# exposure does not vary with shore type in the same physical way
# (audit 2026-09-14, item D6).
_SHORE_WAVE_MULTIPLIER: dict[ShoreType, float] = {
    ShoreType.SANDY: 1.00,
    ShoreType.ROCKY: 0.80,
    ShoreType.JETTY: 0.72,
    ShoreType.CLIFF: 0.68,
}


def safety_thresholds(spot: SpotProfile, angler: AnglerProfile) -> SafetyThresholds:
    wind_caution, wind_no_go, gust_caution, gust_no_go, wave_caution, wave_no_go = (
        _UNIVERSAL_SAFETY_BASE
    )
    # If OSM has no explicit shore type, apply the lowest existing wave threshold
    # without claiming the real shore is a cliff. The final decision is separately
    # forced to NO_GO until the type is documented.
    multiplier = (
        _SHORE_WAVE_MULTIPLIER[spot.shore_type]
        if spot.shore_type is not None
        else min(_SHORE_WAVE_MULTIPLIER.values())
    )
    return SafetyThresholds(
        sustained_wind_caution_kmh=wind_caution,
        sustained_wind_no_go_kmh=wind_no_go,
        gust_caution_kmh=gust_caution,
        gust_no_go_kmh=gust_no_go,
        wave_caution_m=round(wave_caution * multiplier, 2),
        wave_no_go_m=round(wave_no_go * multiplier, 2),
    )


CRITICAL_FIELDS: tuple[str, ...] = (
    "wind_speed_kmh",
    "wind_gust_kmh",
    "wave_height_m",
    "weather_code",
    "visibility_m",
)

# WMO weather interpretation codes representing thunderstorms.
THUNDERSTORM_CODES: frozenset[int] = frozenset({95, 96, 99})
