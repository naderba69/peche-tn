from dataclasses import dataclass

from .enums import ExperienceLevel, ShoreType
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


_EXPERIENCE_BASE: dict[ExperienceLevel, tuple[float, float, float, float, float, float]] = {
    # sustained caution/no-go, gust caution/no-go, wave caution/no-go on open sand
    ExperienceLevel.BEGINNER: (28.0, 38.0, 36.0, 50.0, 0.9, 1.55),
    ExperienceLevel.INTERMEDIATE: (32.0, 44.0, 42.0, 58.0, 1.1, 1.85),
    ExperienceLevel.ADVANCED: (36.0, 50.0, 48.0, 65.0, 1.3, 2.10),
}

_SHORE_WAVE_MULTIPLIER: dict[ShoreType, float] = {
    ShoreType.SANDY: 1.00,
    ShoreType.ROCKY: 0.80,
    ShoreType.JETTY: 0.72,
    ShoreType.CLIFF: 0.68,
}


def safety_thresholds(spot: SpotProfile, angler: AnglerProfile) -> SafetyThresholds:
    wind_caution, wind_no_go, gust_caution, gust_no_go, wave_caution, wave_no_go = _EXPERIENCE_BASE[
        angler.experience
    ]
    multiplier = _SHORE_WAVE_MULTIPLIER[spot.shore_type]
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
)

# WMO weather interpretation codes representing thunderstorms.
THUNDERSTORM_CODES: frozenset[int] = frozenset({95, 96, 99})
