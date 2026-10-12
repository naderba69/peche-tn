from spotdata.domain.enums import TargetSpecies
from spotdata.domain.fish_activity import AFTER_STORM_MULT, SST_TRAP, WEIGHTS, trapezoid


def test_trapezoid_peaks_at_documented_bass_range() -> None:
    a, b, c, d = SST_TRAP[TargetSpecies.EUROPEAN_SEABASS]
    assert trapezoid(16.0, a, b, c, d) == 1.0
    assert trapezoid(14.0, a, b, c, d) == 1.0
    assert trapezoid(19.0, a, b, c, d) == 1.0
    assert trapezoid(8.0, a, b, c, d) == 0.0
    assert trapezoid(24.0, a, b, c, d) == 0.0
    assert 0.0 < trapezoid(11.0, a, b, c, d) < 1.0


def test_lead_weights_sum_to_one() -> None:
    for weights in WEIGHTS.values():
        assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_after_storm_multiplier_is_documented() -> None:
    assert AFTER_STORM_MULT == 1.5


def test_forecast_uses_reference_note(dataset_factory) -> None:
    from spotdata.domain.engine import DecisionEngine

    report = DecisionEngine().evaluate(dataset_factory()).fisherman_report
    assert report is not None
    assert "40" in report.fish_forecast_note_ar
    assert "ليس احتمال" in report.fish_forecast_note_ar
    bass = next(row for row in report.fish_forecasts if row.species == "european_seabass")
    if bass.score is not None:
        assert 0 <= bass.score <= 100
