from spotdata.domain.models import AnglerProfile, SpotProfile
from spotdata.domain.policy import safety_thresholds


def test_rocky_and_cliff_thresholds_are_more_conservative() -> None:
    angler = AnglerProfile(experience="intermediate")
    sand = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="sandy"), angler)
    rock = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="rocky"), angler)
    cliff = safety_thresholds(SpotProfile(seaward_orientation_deg=90, shore_type="cliff"), angler)
    assert cliff.wave_no_go_m < rock.wave_no_go_m < sand.wave_no_go_m


def test_experience_changes_policy_but_not_thunder_rule() -> None:
    spot = SpotProfile(seaward_orientation_deg=90)
    beginner = safety_thresholds(spot, AnglerProfile(experience="beginner"))
    advanced = safety_thresholds(spot, AnglerProfile(experience="advanced"))
    assert beginner.wave_no_go_m < advanced.wave_no_go_m
    assert beginner.gust_no_go_kmh < advanced.gust_no_go_kmh
