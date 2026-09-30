from spotdata.domain.models import AnglerProfile, SpotProfile
from spotdata.domain.policy import safety_thresholds


def test_rocky_and_cliff_thresholds_are_more_conservative() -> None:
    angler = AnglerProfile(experience="intermediate")
    sand = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="sandy"), angler)
    rock = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="rocky"), angler)
    cliff = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="cliff"), angler)
    assert cliff.wave_no_go_m < rock.wave_no_go_m < sand.wave_no_go_m


def test_unknown_shore_type_uses_the_most_conservative_threshold_without_inference() -> None:
    unknown = safety_thresholds(SpotProfile(seaward_orientation_deg=90), AnglerProfile())
    cliff = safety_thresholds(
        SpotProfile(seaward_orientation_deg=90, shore_type="cliff"), AnglerProfile()
    )
    assert unknown.wave_no_go_m == cliff.wave_no_go_m
    assert unknown.sustained_wind_no_go_kmh == cliff.sustained_wind_no_go_kmh


def test_experience_never_relaxes_physical_safety_thresholds() -> None:
    spot = SpotProfile(seaward_orientation_deg=90, shore_type="sandy")
    beginner = safety_thresholds(spot, AnglerProfile(experience="beginner"))
    intermediate = safety_thresholds(spot, AnglerProfile(experience="intermediate"))
    advanced = safety_thresholds(spot, AnglerProfile(experience="advanced"))
    assert beginner == intermediate == advanced
