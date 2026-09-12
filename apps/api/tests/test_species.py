from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionLevel, DecisionReasonCode
from spotdata.domain.models import ForecastDataset

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")

AXIS_KEYS = ["seasonal", "habitat", "surf_approach", "feeding_window", "prey_evidence"]


def _default(dataset_factory: Callable[..., ForecastDataset]) -> ForecastDataset:
    return dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))


def test_species_axes_present_with_five_reporting_only_axes(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    axes = result.species_axes
    assert axes is not None
    assert axes.target_species == "general"
    assert axes.label_ar == "صيد عام"
    assert [axis.axis for axis in axes.axes] == AXIS_KEYS
    assert "seasonal" in axes.unknown_axes
    assert "prey_evidence" in axes.unknown_axes
    # Overall confidence reflects the computed axes only (not the Unknown ones).
    assert 15 <= axes.confidence <= 25
    # The species block is report-only: no catch probability anywhere.
    assert result.score_is_success_probability is False
    # And it never changes the binary decision on a good day.
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW


def test_habitat_axis_reflects_shore_match(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    mismatch = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        spot_updates={"shore_type": "sandy"},
        angler_updates={"target_species": "white_seabream"},
    )
    mismatch_axis = next(
        axis for axis in engine.evaluate(mismatch).species_axes.axes if axis.axis == "habitat"
    )
    assert mismatch_axis.status == "neutral"

    match = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        spot_updates={"shore_type": "rocky"},
        angler_updates={"target_species": "white_seabream"},
    )
    match_axis = next(
        axis for axis in engine.evaluate(match).species_axes.axes if axis.axis == "habitat"
    )
    assert match_axis.status == "favorable"
    assert match_axis.basis == "spot_profile"


def test_surf_approach_carries_spring_neap_physical_channel(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    assert result.spring_neap is not None
    axes = result.species_axes
    assert axes is not None
    surf = next(axis for axis in axes.axes if axis.axis == "surf_approach")
    assert surf.basis == "model_forecast"
    assert surf.status in {"favorable", "neutral", "unfavorable"}
    assert any(result.spring_neap.folk_label_ar in line for line in surf.evidence_ar)
    # Species-specific spring/neap response remains Unknown until calibration.
    assert any("spring_neap_response" in note for note in axes.notes_ar)


def test_feeding_window_is_expert_prior_without_solunar(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    axes = result.species_axes
    assert axes is not None
    feeding = next(axis for axis in axes.axes if axis.axis == "feeding_window")
    assert feeding.basis == "expert_prior"
    assert feeding.status in {"favorable", "neutral", "unknown"}
    # Grounded in sunrise/sunset, with the no-lunar/Solunar rule stated explicitly.
    assert any("الشروق" in line or "الغروب" in line for line in feeding.evidence_ar)
    assert any("بلا قاعدة قمرية" in line for line in feeding.evidence_ar)


def test_weak_species_axes_never_veto_a_safe_window(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # White seabream on a sandy shore at 30 °C: habitat mismatch plus SST outside
    # tolerance. The species priors are weak, yet a safe executable window stays GO.
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"sea_surface_temperature_c": 30.0},
        spot_updates={"shore_type": "sandy"},
        angler_updates={"target_species": "white_seabream"},
    )
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert result.species_axes is not None
    habitat = next(
        axis for axis in result.species_axes.axes if axis.axis == "habitat"
    )
    assert habitat.status == "neutral"


def test_species_axes_do_not_change_the_binary_decision(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = engine.evaluate(_default(dataset_factory))
    # Same day with a different (all-unfavourable) species must not flip the decision.
    white = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"sea_surface_temperature_c": 30.0},
        spot_updates={"shore_type": "sandy"},
        angler_updates={"target_species": "white_seabream"},
    )
    result = engine.evaluate(white)
    assert result.decision == base.decision
    assert result.decision_reason_code == base.decision_reason_code


def test_seasonal_axis_computed_from_audited_month_x_zone(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # September on a Gabès sandy spot for striped seabream: the audited matrix
    # marks the Gulf of Gabès autumn spawning (Sep-Nov) as strong.
    base = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        spot_updates={"shore_type": "sandy"},
        angler_updates={"target_species": "striped_seabream"},
    )
    dataset = base.model_copy(
        update={"location": base.location.model_copy(update={"latitude": 33.899, "longitude": 10.119})}
    )
    result = engine.evaluate(dataset)
    axes = result.species_axes
    assert axes is not None
    seasonal = next(axis for axis in axes.axes if axis.axis == "seasonal")
    assert seasonal.status == "favorable"
    assert seasonal.basis == "expert_prior"
    assert "سبتمبر" in seasonal.evidence_ar[0]
    assert "خليج قابس" in seasonal.evidence_ar[0]


def test_seasonal_axis_stays_unknown_for_general_target(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        )
    )
    axes = result.species_axes
    assert axes is not None
    assert "seasonal" in axes.unknown_axes
    seasonal = next(axis for axis in axes.axes if axis.axis == "seasonal")
    assert seasonal.status == "unknown"


def test_tunisian_zone_classification() -> None:
    from spotdata.domain.math import tunisian_zone

    assert tunisian_zone(36.9544, 8.7581) == "northwest"   # Tabarka
    assert tunisian_zone(37.1908, 10.1835) == "bizerte_tunis"  # Rafraf
    assert tunisian_zone(36.8368, 11.1197) == "cap_bon_hammamet"  # Kelibia
    assert tunisian_zone(35.5047, 11.0622) == "sahel"  # Mahdia
    assert tunisian_zone(34.799, 10.856) == "gabes"  # Sfax
    assert tunisian_zone(33.768, 11.012) == "south"  # Djerba


def test_tunisian_zone_northwest_past_37n() -> None:
    """The northwest (سراط) coast climbs north of 37°N; longitude must win."""
    from spotdata.domain.math import tunisian_zone

    assert tunisian_zone(37.22, 9.01) == "northwest"  # Cap Serrat
    assert tunisian_zone(37.10, 8.99) == "northwest"  # Sidi Mechreg
    assert tunisian_zone(37.276, 9.872) == "bizerte_tunis"  # Bizerte stays gulf


def test_tunisian_zone_cap_bon_tip_and_djerba_stability() -> None:
    """Cap Bon tip must not fall into the gulf; all of Djerba stays south."""
    from spotdata.domain.math import tunisian_zone

    assert tunisian_zone(37.056, 11.015) == "cap_bon_hammamet"  # Haouaria
    assert tunisian_zone(33.89, 10.86) == "south"  # Djerba north
    assert tunisian_zone(33.878, 10.857) == "south"  # Djerba Houmt Souk
    assert tunisian_zone(33.81, 10.85) == "south"  # Djerba (former flip point)
    assert tunisian_zone(33.899, 10.119) == "gabes"  # Gabès city stays gulf


def test_species_matches_report_availability_and_match_for_all_profiled_species(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(_default(dataset_factory))
    axes = result.species_axes
    assert axes is not None
    matches = axes.species_matches
    # Four profiled species, no "general", no catch probability anywhere.
    assert {m.species for m in matches} == {
        "gilthead_seabream",
        "striped_seabream",
        "european_seabass",
        "white_seabream",
    }
    assert all(m.status in {"favorable", "neutral", "unfavorable", "unknown"} for m in matches)
    assert all(m.availability in {"strong", "medium", "weak", "unavailable", "unknown"} for m in matches)
    # Sorted favourable first, then by availability, with Arabic reasons.
    statuses = [m.status for m in matches]
    rank = {"favorable": 0, "neutral": 1, "unfavorable": 2, "unknown": 3}
    assert statuses == sorted(statuses, key=rank.get)
    assert all(len(m.reasons_ar) >= 1 for m in matches)
    # Every match carries its published scientific sources.
    assert all(len(m.sources_ar) >= 1 for m in matches)
    # Never a catch probability and never changes the binary decision.
    assert result.score_is_success_probability is False
    assert result.decision == DecisionLevel.GO


def test_species_matches_availability_reflects_zone_x_month(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    base = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        spot_updates={"shore_type": "sandy"},
    )
    # Gabès in September: striped seabream (المرمار) availability is strong (3).
    dataset = base.model_copy(
        update={"location": base.location.model_copy(update={"latitude": 33.899, "longitude": 10.119})}
    )
    matches = {m.species: m for m in engine.evaluate(dataset).species_axes.species_matches}
    assert matches["striped_seabream"].availability == "strong"
    assert matches["striped_seabream"].status == "favorable"
    assert any("خليج قابس" in line for line in matches["striped_seabream"].reasons_ar)


def test_species_matches_thermal_and_habitat_priors(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # White seabream on a sandy shore at 30 °C: habitat mismatch + SST outside
    # tolerance -> unfavourable, while the decision stays GO.
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"sea_surface_temperature_c": 30.0},
        spot_updates={"shore_type": "sandy"},
    )
    result = engine.evaluate(dataset)
    matches = {m.species: m for m in result.species_axes.species_matches}
    white = matches["white_seabream"]
    assert white.thermal == "outside"
    assert white.habitat_match is False
    assert white.status == "unfavorable"
    assert result.decision == DecisionLevel.GO


def test_species_matches_honour_missing_sst_without_fabricating_thermal(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"sea_surface_temperature_c": None},
    )
    matches = engine.evaluate(dataset).species_axes.species_matches
    assert matches
    assert all(m.thermal == "unknown" for m in matches)
    assert all(any("حرارة" in line for line in m.reasons_ar) for m in matches)


def test_sea_state_fit_tracks_wave_and_wind(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # Rough sea (1.4 m + strong wind): seabass and sargus favour the surf/foam,
    # the calm-sand mormyrus stays neutral — while the decision stays GO.
    rough = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"wave_height_m": 1.4, "wind_speed_kmh": 30.0},
    )
    rough_result = engine.evaluate(rough)
    assert rough_result.decision == DecisionLevel.GO
    rough_by_species = {m.species: m for m in rough_result.species_axes.species_matches}
    assert rough_by_species["european_seabass"].sea_state_fit == "favorable"
    assert rough_by_species["white_seabream"].sea_state_fit == "favorable"
    assert rough_by_species["striped_seabream"].sea_state_fit == "neutral"
    assert "هائج" in rough_result.species_axes.sea_state_ar
    assert "رغوة" in rough_result.species_axes.sea_state_ar

    # Calm sea (0.3 m): the calm-sand mormyrus is favoured; the seabass stays neutral.
    calm = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        hour_updates={"wave_height_m": 0.3, "wind_speed_kmh": 8.0},
    )
    calm_result = engine.evaluate(calm)
    calm_by_species = {m.species: m for m in calm_result.species_axes.species_matches}
    assert calm_by_species["striped_seabream"].sea_state_fit == "favorable"
    assert calm_by_species["european_seabass"].sea_state_fit == "neutral"
    assert "هادئ" in calm_result.species_axes.sea_state_ar


def test_sea_state_is_report_only_and_disclosed(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    axes = result.species_axes
    assert axes.sea_state_ar
    for match in axes.species_matches:
        # Every profiled species carries its sea-state preference + citation.
        assert match.sea_state_ar
        assert match.sea_state_preference_ar
        assert match.sea_state_fit in {"favorable", "neutral", "unknown"}
        assert any(
            "متوسطي عام" in source or "FishBase" in source or "PLOS" in source or "JMSE" in source
            for source in match.sources_ar
        )
    assert any("حالة البحر" in note for note in axes.notes_ar)
