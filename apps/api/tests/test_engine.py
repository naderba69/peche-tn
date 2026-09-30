from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.engine import DecisionEngine, InsufficientDataError
from spotdata.domain.enums import (
    DecisionLevel,
    DecisionReasonCode,
    FactorBasis,
    FactorImpact,
    FieldFeasibilityLevel,
    InmCheckStatus,
    PotentialLevel,
    RuleNature,
    TideState,
)
from spotdata.domain.models import (
    CoastalWaterContext,
    ForecastDataset,
    InmWarningAudit,
    SourceMetadata,
)

engine = DecisionEngine()


def test_unknown_shore_type_still_analyzes_full_day_but_never_reaches_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    unknown_shore = dataset_factory(spot_updates={"shore_type": None})
    result = engine.evaluate(unknown_shore)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CRITICAL_DATA_MISSING
    assert len(result.hourly) == 24
    assert result.recommended_windows == []
    assert "نوع الساحل لم يوثّقه OSM" in result.summary_ar

    unknown_orientation = dataset_factory(spot_updates={"seaward_orientation_deg": None})
    with pytest.raises(InsufficientDataError, match="اتجاه الساحل Unknown"):
        engine.evaluate(unknown_orientation)

    # Personal skill/duration fields are intentionally ignored; every analysis is 24 h.
    fixed_full_day = engine.evaluate(
        dataset_factory(angler_updates={"experience": None, "session_hours": None})
    )
    assert len(fixed_full_day.hourly) == 24


def test_good_day_returns_ranked_explainable_window(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
    )
    result = engine.evaluate(dataset)
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert result.recommended_windows
    assert result.opportunity_score >= 55
    assert result.score_is_success_probability is False
    assert result.confidence.is_accuracy_probability is False
    assert result.field_feasibility.is_direct_observation is False
    assert result.field_feasibility.confidence <= 50
    assert result.field_feasibility.status == FieldFeasibilityLevel.FAVORABLE
    assert all(window.field_score >= 0 for window in result.recommended_windows)
    assert result.sunrise == dataset.sunrise
    assert result.sunset == dataset.sunset
    assert any("ليست احتمال" in text for text in result.limitations_ar)
    assert all(hour.factors for hour in result.hourly)
    assert len(result.antecedent_hours) == 72
    assert len(result.factor_assessments) == 63
    assert len({item.matrix_id for item in result.factor_assessments}) == 63
    assert {item.status.value for item in result.factor_assessments} >= {
        "decision",
        "context",
        "proxy",
        "unknown",
        "excluded",
    }


def test_inm_gate_blocks_preliminary_go_when_clear_status_is_unverified(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory()
    preliminary = engine.evaluate(dataset)
    assert preliminary.decision == DecisionLevel.GO
    now = dataset.fetched_at
    unverified = InmWarningAudit(
        status=InmCheckStatus.UNVERIFIED,
        checked_at=now,
        coverage_status="unknown",
        coverage_ar="غير معروف",
        reason_code="source_conflict",
        explanation_ar="تعارض مصدري اختباري.",
    )
    gated = engine.apply_official_warning_check(dataset, preliminary, unverified)
    assert gated.decision == DecisionLevel.NO_GO
    assert gated.decision_reason_code == DecisionReasonCode.OFFICIAL_WARNING_UNVERIFIED
    assert gated.recommended_windows == []
    assert gated.gear_recommendation is None
    assert gated.official_warning_check == unverified
    assert "تعذر إثبات خلو نشرة INM" in gated.summary_ar


def test_verified_clear_inm_check_preserves_weather_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory()
    preliminary = engine.evaluate(dataset)
    audit = InmWarningAudit(
        status=InmCheckStatus.VERIFIED_CLEAR,
        checked_at=dataset.fetched_at,
        http_status_code=200,
        server_date=dataset.fetched_at,
        response_age_seconds=0,
        cache_control="no-cache",
        age_header_seconds=0,
        response_sha256="b" * 64,
        coverage_status="verified_tunisian_coasts",
        coverage_ar="تغطية وطنية اختباريّة",
        reason_code="explicit_clear",
        explanation_ar="لا يوجد تحذير في اختبار الوحدة.",
    )
    final = engine.apply_official_warning_check(dataset, preliminary, audit)
    assert final.decision == DecisionLevel.GO
    assert final.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert final.recommended_windows
    assert final.official_warning_check == audit


def test_weather_no_go_remains_no_go_without_requiring_inm_override(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(hour_updates={"wind_speed_kmh": 60.0, "wind_gust_kmh": 75.0})
    preliminary = engine.evaluate(dataset)
    assert preliminary.decision == DecisionLevel.NO_GO
    audit = InmWarningAudit(
        status=InmCheckStatus.NOT_CHECKED,
        checked_at=dataset.fetched_at,
        coverage_status="not_checked",
        coverage_ar="لم يُطلب الفحص.",
        reason_code="no_candidate_window",
        explanation_ar="فشل حاجز الطقس أولاً.",
    )
    final = engine.apply_official_warning_check(dataset, preliminary, audit)
    assert final.decision == DecisionLevel.NO_GO
    assert final.decision_reason_code == preliminary.decision_reason_code
    assert final.official_warning_check == audit


def test_engine_exposes_auditable_shore_relative_direction_components(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wind_speed_kmh": 10.0,
                "wind_direction_deg": 90.0,
                "wave_direction_deg": 90.0,
            },
            spot_updates={"seaward_orientation_deg": 90.0},
        )
    )
    derived = result.hourly[0].derived
    assert derived.wind_shoreward_component_kmh == 10.0
    assert derived.wind_alongshore_component_kmh == 0.0
    assert derived.wind_alongshore_signed_component_kmh == 0.0
    assert derived.alongshore_positive_bearing_deg == 180.0
    assert derived.wave_shoreward_alignment == 1.0
    assert derived.wave_alongshore_alignment == 0.0
    assert derived.wave_alongshore_signed_alignment == 0.0
    assert derived.wind_stress_pa == pytest.approx(0.0113, abs=0.0001)
    assert derived.wind_stress_shoreward_pa == derived.wind_stress_pa
    assert derived.wind_drag_coefficient == pytest.approx(0.0012)
    assert derived.air_sea_temperature_difference_c == 2.0
    assert derived.dew_point_depression_c == 7.0


def test_signed_direction_fields_and_missing_inputs_are_not_synthesized(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    signed = (
        engine.evaluate(
            dataset_factory(
                hour_updates={"wind_speed_kmh": 16.0, "wind_direction_deg": 93.0},
                spot_updates={"seaward_orientation_deg": 90.0},
            )
        )
        .hourly[0]
        .derived
    )
    assert signed.wind_alongshore_component_kmh == 0.84
    assert signed.wind_alongshore_signed_component_kmh == -0.84
    assert signed.wind_stress_alongshore_pa is not None
    assert signed.wind_stress_alongshore_pa < 0

    unknown = (
        engine.evaluate(dataset_factory(hour_updates={"wind_speed_kmh": None})).hourly[0].derived
    )
    assert unknown.wind_stress_pa is None
    assert unknown.wind_stress_shoreward_pa is None
    assert unknown.wind_alongshore_signed_component_kmh is None


def test_missing_wave_is_unknown_not_false_calm(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"wave_height_m": None}))
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CRITICAL_DATA_MISSING
    assert not result.recommended_windows
    assert all(hour.safety == DecisionLevel.UNKNOWN for hour in result.hourly)
    assert all(hour.confidence.score <= 45 for hour in result.hourly)
    assert all(
        hour.field_feasibility.status == FieldFeasibilityLevel.UNKNOWN for hour in result.hourly
    )
    assert result.field_feasibility.status == FieldFeasibilityLevel.UNKNOWN
    assert any(
        factor.code == "missing_critical_safety_data" and factor.impact == FactorImpact.DATA_GAP
        for factor in result.hourly[0].factors
    )


def test_missing_field_direction_blocks_trip_as_critical_execution_unknown(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"wind_direction_deg": None}))
    assert not result.recommended_windows
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CRITICAL_DATA_MISSING
    assert result.field_feasibility.status == FieldFeasibilityLevel.UNKNOWN
    assert "نقص بيانات حرجة" in result.summary_ar


def test_missing_visibility_is_critical_for_the_full_day(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            per_hour=lambda index, values: (
                values.update({"visibility_m": None}) if index < 3 else None
            )
        )
    )
    assert result.decision == DecisionLevel.NO_GO
    assert all(hour.safety == DecisionLevel.UNKNOWN for hour in result.hourly[:3])
    assert all(hour.safety == DecisionLevel.GO for hour in result.hourly[3:])
    assert result.recommended_windows == []


def test_stale_cache_fallback_is_a_hard_no_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(cache_fallback_used=True, cache_fallback_age_seconds=18_000)
    )
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.STALE_FORECAST_DATA
    assert not result.recommended_windows
    assert result.cache_fallback_used is True
    assert result.cache_fallback_age_seconds == 18_000
    assert all(hour.safety == DecisionLevel.UNKNOWN for hour in result.hourly)


def test_forecast_beyond_72_hours_is_a_hard_no_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    target = datetime(2026, 9, 11, 0, tzinfo=ZoneInfo("Africa/Tunis"))
    result = engine.evaluate(
        dataset_factory(
            count=24,
            start_at=target,
            target_date=target.date(),
            fetched_at=datetime(2026, 9, 7, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.FORECAST_HORIZON_EXCEEDED
    assert not result.recommended_windows
    assert all(hour.safety == DecisionLevel.UNKNOWN for hour in result.hourly)
    assert all(hour.confidence.score == 0 for hour in result.hourly)


def test_thunderstorm_cannot_be_overridden_by_fishing_score(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"weather_code": 95}))
    assert result.decision == DecisionLevel.NO_GO
    assert all(hour.safety == DecisionLevel.NO_GO for hour in result.hourly)
    assert all(hour.opportunity_score <= 25 for hour in result.hourly)
    assert "لا تذهب" in result.summary_ar


def test_rocky_spot_is_more_conservative_than_sand(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    rough = {"wave_height_m": 1.3, "wave_period_s": 8.0}
    rocky = engine.evaluate(
        dataset_factory(hour_updates=rough, spot_updates={"shore_type": "rocky"})
    )
    sandy = engine.evaluate(
        dataset_factory(hour_updates=rough, spot_updates={"shore_type": "sandy"})
    )
    assert all(hour.safety == DecisionLevel.NO_GO for hour in rocky.hourly)
    assert any(hour.safety == DecisionLevel.CAUTION for hour in sandy.hourly)


def test_real_modelled_sea_level_drives_rising_and_falling_states(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory())
    states = {hour.derived.tide_state for hour in result.hourly}
    assert TideState.RISING in states
    assert TideState.FALLING in states
    assert result.tide_events
    assert all("نموذج" in event.disclaimer_ar for event in result.tide_events)


def test_best_windows_are_non_overlapping(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    windows = engine.evaluate(dataset_factory()).recommended_windows
    for index, first in enumerate(windows):
        for second in windows[index + 1 :]:
            assert first.end <= second.start or first.start >= second.end


def test_window_field_score_uses_weakest_hour_and_rank_is_conservative(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def update(index: int, values: dict[str, object]) -> None:
        if index in {7, 8}:
            values["wave_height_m"] = 0.85
            values["wave_direction_deg"] = 20.0

    result = engine.evaluate(dataset_factory(per_hour=update))
    field_rank = {
        FieldFeasibilityLevel.UNKNOWN: 0,
        FieldFeasibilityLevel.DIFFICULT: 1,
        FieldFeasibilityLevel.WORKABLE: 2,
        FieldFeasibilityLevel.FAVORABLE: 3,
    }
    safety_rank = {
        DecisionLevel.NO_GO: 0,
        DecisionLevel.UNKNOWN: 1,
        DecisionLevel.CAUTION: 2,
        DecisionLevel.GO: 3,
    }
    window_ranks: list[tuple[int, int, int, int, int]] = []
    for window in result.recommended_windows:
        covered = [hour for hour in result.hourly if window.start <= hour.time < window.end]
        assert window.field_score == min(hour.field_feasibility.score for hour in covered)
        assert field_rank[window.field_feasibility] == min(
            field_rank[hour.field_feasibility.status] for hour in covered
        )
        window_ranks.append(
            (
                safety_rank[window.safety],
                field_rank[window.field_feasibility],
                window.field_score,
                window.opportunity_score,
                window.confidence_score,
            )
        )
    assert window_ranks == sorted(window_ranks, reverse=True)


def test_single_danger_period_makes_full_day_no_go_but_is_identified(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def update(index: int, values: dict[str, object]) -> None:
        if 82 <= index <= 84:
            values["wind_gust_kmh"] = 80.0

    result = engine.evaluate(
        dataset_factory(
            per_hour=update,
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    assert result.decision == DecisionLevel.NO_GO
    assert result.avoid_windows
    assert any(window.safety == DecisionLevel.NO_GO for window in result.avoid_windows)
    assert result.recommended_windows == []


def test_localized_thunder_is_avoided_while_high_turbidity_proxy_stays_caution_only(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def update(index: int, values: dict[str, object]) -> None:
        values.update(
            {
                "wave_height_m": 0.4,
                "wave_period_s": 4.0,
                "wave_direction_deg": 90.0,
                "wind_speed_kmh": 12.0,
                "wind_gust_kmh": 18.0,
                "wind_direction_deg": 90.0,
                "ocean_current_velocity_kmh": 0.2,
                "ocean_current_direction_deg": 270.0,
                "precipitation_mm": 0.2,
                "weather_code": 1,
            }
        )
        if index == 89:  # 17:00 on the target day.
            values["weather_code"] = 96
            values["precipitation_mm"] = 2.0

    result = engine.evaluate(
        dataset_factory(
            per_hour=update,
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )

    assert result.field_feasibility.turbidity_potential == PotentialLevel.MODERATE
    assert result.field_feasibility.turbidity_evidence_count == 3
    assert result.decision == DecisionLevel.NO_GO
    assert result.recommended_windows == []
    assert any(window.start.hour == 17 for window in result.avoid_windows)
    assert any("ليس رصداً" in item for item in result.field_feasibility.limitations_ar)


def test_inconsistent_wave_direction_reduces_confidence_and_warns(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"wave_direction_deg": 270.0}))
    assert all(hour.confidence.score <= 55 for hour in result.hourly)
    assert all(hour.safety == DecisionLevel.CAUTION for hour in result.hourly)
    assert any(factor.code == "wave_direction_inconsistent" for factor in result.hourly[0].factors)


def test_target_species_weights_are_small_and_explained(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={"sea_surface_temperature_c": 18.0},
            angler_updates={"target_species": "european_seabass"},
        )
    )
    species_factors = [
        factor
        for factor in result.hourly[6].factors
        if factor.code in {"species_preferred_sst", "twilight_window", "species_shore_match"}
    ]
    assert species_factors
    assert all(abs(factor.score_delta) <= 11 for factor in species_factors)


def test_today_requires_24_complete_hours_after_now(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory().model_copy(
        update={"fetched_at": datetime(2026, 9, 7, 12, 10, tzinfo=ZoneInfo("Africa/Tunis"))}
    )
    with pytest.raises(InsufficientDataError, match="24 ساعة متصلة"):
        engine.evaluate(dataset)


def test_partial_history_is_reported_but_not_treated_as_persistence_or_critical_gap(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory())
    first = result.hourly[0]
    assert first.derived.history_hours_12h == 1
    assert first.derived.rain_data_hours_24h == 1
    assert first.derived.wind_data_hours_12h == 1
    assert first.derived.wave_energy_data_hours_12h == 1
    assert first.derived.onshore_wind_fraction_12h == 1.0
    assert first.derived.history_hours_48h == 1
    assert first.field_feasibility.fouling_transport_potential == PotentialLevel.UNKNOWN
    assert first.field_feasibility.turbidity_potential == PotentialLevel.UNKNOWN
    assert first.field_feasibility.status == FieldFeasibilityLevel.WORKABLE
    assert first.field_feasibility.confidence < 50
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert "1/48" in first.field_feasibility.reasons_ar[1]


def test_previous_rain_and_persistent_onshore_energy_raise_transport_screen(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def update(index: int, values: dict[str, object]) -> None:
        values["wave_height_m"] = 1.0
        values["wave_period_s"] = 7.0
        values["ocean_current_velocity_kmh"] = 1.0
        values["precipitation_mm"] = 3.0 if 12 <= index <= 20 else 0.0

    result = engine.evaluate(
        dataset_factory(
            per_hour=update,
            count=48,
            start_at=datetime(2026, 9, 6, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    midnight = result.hourly[0]
    assert midnight.derived.history_hours_24h == 24
    assert midnight.derived.history_hours_12h == 12
    assert midnight.derived.rain_data_hours_24h == 24
    assert midnight.derived.wind_data_hours_12h == 12
    assert midnight.derived.wave_energy_data_hours_12h == 12
    assert midnight.derived.rain_24h_mm == 27.0
    assert midnight.derived.onshore_wind_fraction_12h == 1.0
    assert midnight.field_feasibility.fouling_transport_potential == PotentialLevel.HIGH
    assert midnight.field_feasibility.rip_current_potential == PotentialLevel.MODERATE
    assert midnight.safety == DecisionLevel.CAUTION
    assert not any(factor.code == "elevated_rip_current_potential" for factor in midnight.factors)
    assert midnight.field_feasibility.confidence == 50
    assert midnight.field_feasibility.is_direct_observation is False
    assert any("ليس رصداً" in item for item in midnight.field_feasibility.limitations_ar)


def test_exposure_alone_cannot_create_a_multi_evidence_transport_block(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    common = {
        "hour_updates": {
            "wave_height_m": 0.4,
            "wave_period_s": 6.0,
            "ocean_current_velocity_kmh": 0.6,
        },
        "count": 48,
        "start_at": datetime(2026, 9, 6, 0, tzinfo=ZoneInfo("Africa/Tunis")),
    }
    open_result = engine.evaluate(dataset_factory(**common, spot_updates={"exposure": "open"}))
    sheltered_result = engine.evaluate(
        dataset_factory(**common, spot_updates={"exposure": "sheltered"})
    )
    unknown_result = engine.evaluate(dataset_factory(**common, spot_updates={"exposure": None}))
    open_field = open_result.hourly[0].field_feasibility
    sheltered_field = sheltered_result.hourly[0].field_feasibility
    unknown_field = unknown_result.hourly[0].field_feasibility
    assert open_field.fouling_transport_potential == PotentialLevel.LOW
    assert sheltered_field.fouling_transport_potential == PotentialLevel.LOW
    assert open_field.fouling_evidence_count == 1
    assert sheltered_field.fouling_evidence_count == 1
    assert open_field.rip_current_potential == sheltered_field.rip_current_potential
    assert open_field.rip_current_potential == unknown_field.rip_current_potential
    assert open_result.decision == sheltered_result.decision == unknown_result.decision
    assert open_result.decision != DecisionLevel.NO_GO or (
        open_result.decision_reason_code != DecisionReasonCode.FIELD_INFEASIBLE
    )


def test_crossing_swell_and_wind_wave_are_separate_shadow_diagnostics(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.6,
                "wind_wave_height_m": 0.3,
                "wind_wave_direction_deg": 270.0,
                "swell_height_m": 0.4,
                "swell_direction_deg": 90.0,
            }
        )
    )
    hour = result.hourly[0]
    assert hour.forecast.wind_wave_height_m == 0.3
    assert hour.forecast.swell_direction_deg == 90.0
    assert hour.derived.wave_component_angle_deg == 180.0
    assert hour.derived.wave_component_secondary_energy_share == 0.36
    assert hour.safety == DecisionLevel.GO
    assert not any(
        "crossing" in factor.code or "cross_sea" in factor.code for factor in hour.factors
    )


def test_satellite_water_context_updates_ledger_but_not_decision_or_scores(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory()
    baseline = engine.evaluate(dataset)
    context = CoastalWaterContext(
        availability="available",
        sample_latitude=36.81,
        sample_longitude=10.31,
        sample_distance_from_spot_m=1_000,
        pixel_latitude=36.8102,
        pixel_longitude=10.3104,
        pixel_distance_from_spot_m=1_015,
        pixel_distance_from_sample_m=41,
        valid_time=datetime(2026, 9, 6, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
        age_hours=72,
        turbidity_fnu=0.32,
        suspended_particulate_matter_g_m3=0.18,
        chlorophyll_a_mg_m3=0.54,
        reason_ar="اختبار سياق فضائي ثابت.",
    )
    with_context = engine.evaluate(dataset.model_copy(update={"coastal_water_context": context}))

    assert with_context.decision == baseline.decision
    assert with_context.decision_reason_code == baseline.decision_reason_code
    assert with_context.opportunity_score == baseline.opportunity_score
    assert [item.safety for item in with_context.hourly] == [
        item.safety for item in baseline.hourly
    ]
    assert [item.confidence.score for item in with_context.hourly] == [
        item.confidence.score for item in baseline.hourly
    ]
    assert with_context.coastal_water_context == context
    clarity = next(item for item in with_context.factor_assessments if item.matrix_id == "4.5")
    assert clarity.status.value == "context"
    assert clarity.affects_final_decision is False
    assert "0.32 FNU" in clarity.value_ar

    no_source = dataset.model_copy(update={"sources": []})
    no_source_baseline = engine.evaluate(no_source)
    remote_source = SourceMetadata(
        provider="Copernicus Marine Service / Sentinel-2",
        product="test ocean-colour layer",
        data_kind="remote_sensing_estimate",
        variables=["turbidity_fnu"],
        horizontal_resolution_km=0.1,
        retrieved_at=context.retrieved_at,
        limitations_ar=["سياق اختبار فقط."],
    )
    remote_only = engine.evaluate(
        no_source.model_copy(update={"sources": [remote_source], "coastal_water_context": context})
    )
    assert [item.confidence.score for item in remote_only.hourly] == [
        item.confidence.score for item in no_source_baseline.hourly
    ]


def test_high_line_holding_screen_blocks_an_otherwise_safe_window(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.8,
                "wave_period_s": 7.0,
                "wave_direction_deg": 0.0,
                "ocean_current_velocity_kmh": 1.1,
                "wind_speed_kmh": 12.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    assert result.field_feasibility.holding_difficulty == PotentialLevel.HIGH
    assert result.field_feasibility.status != FieldFeasibilityLevel.FAVORABLE
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.FIELD_INFEASIBLE
    assert any(
        factor.code == "line_holding_high" for hour in result.hourly for factor in hour.factors
    )


def test_holding_breakdown_exposes_four_mechanisms_without_changing_the_gate(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 1.1,
                "wave_period_s": 9.0,
                "wave_direction_deg": 30.0,  # oblique relative to a 90° shore normal
                "ocean_current_velocity_kmh": 0.9,
                "wind_speed_kmh": 14.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    breakdown = result.field_feasibility.holding_breakdown
    assert breakdown is not None
    assert breakdown.longshore_current != PotentialLevel.UNKNOWN
    assert breakdown.orbital_motion != PotentialLevel.UNKNOWN
    assert breakdown.return_flow != PotentialLevel.UNKNOWN
    assert breakdown.tidal_current != PotentialLevel.UNKNOWN
    assert breakdown.dominant in {
        "longshore_current",
        "orbital_motion",
        "return_flow",
        "tidal_current",
        "none",
    }
    assert 0 <= breakdown.confidence <= 30
    assert breakdown.orbital_velocity_band_ms is not None
    assert len(breakdown.reasons_ar) == 5
    # The diagnostic split must not alter the single gate or the binary decision.
    gate = result.field_feasibility.holding_difficulty
    assert gate == PotentialLevel.HIGH


def test_holding_breakdown_missing_wave_data_stays_unknown(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": None,
                "wave_period_s": None,
                "wave_direction_deg": None,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    breakdown = result.field_feasibility.holding_breakdown
    assert breakdown is not None
    assert breakdown.orbital_motion == PotentialLevel.UNKNOWN
    assert breakdown.orbital_velocity_band_ms is None


def test_low_proxy_signal_explicitly_does_not_claim_absence(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.2,
                "wave_period_s": 4.0,
                "ocean_current_velocity_kmh": 0.1,
            },
            spot_updates={"shore_type": "cliff", "exposure": "sheltered"},
        )
    )
    field = result.field_feasibility
    assert field.rip_current_potential == PotentialLevel.LOW
    assert any("لا ينفي الخطر" in reason for reason in field.reasons_ar)
    assert any("ليس رصداً" in limitation for limitation in field.limitations_ar)


def test_not_enough_hours_raises(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    with pytest.raises(InsufficientDataError):
        engine.evaluate(dataset_factory(count=2))


def test_factor_lineage_never_mislabels_model_output_as_observation(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory())
    assert result.factor_coverage.audited_total == 63
    assert result.factor_coverage.source_claimed_total == 62
    factors = [factor for hour in result.hourly for factor in hour.factors]
    assert factors
    assert all(factor.is_direct_observation is False for factor in factors)
    assert all(factor.basis in FactorBasis for factor in factors)
    assert all(factor.rule_nature in RuleNature for factor in factors)


def test_factor_ledger_uses_correct_units_localization_and_signal_language(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def rising_pressure(index: int, values: dict[str, object]) -> None:
        values["pressure_msl_hpa"] = 1_000.0 + index * 0.2

    dataset = dataset_factory(
        count=48,
        per_hour=rising_pressure,
        start_at=datetime(2026, 9, 6, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        spot_updates={"orientation_source": "manual", "shore_type": "sandy"},
    )
    result = engine.evaluate(dataset)
    factors = {item.matrix_id: item for item in result.factor_assessments}

    assert "لم يظهر هبوط" in factors["1.9"].value_ar
    assert "+0.6" in factors["1.10"].value_ar
    assert factors["1.14"].value_ar == "20.0 كم"
    assert "CAPE 50 جول/كغ" in factors["1.15"].value_ar
    assert "غياب مؤشر فرعي لا يعني غياب البرق" in factors["1.15"].value_ar
    assert "عائلات قرائن تشغيلية" in factors["2.2"].value_ar
    assert "مصادر مستقلة" in factors["2.2"].value_ar
    assert "أدلة مستقلة" not in factors["2.2"].value_ar
    assert "عائلات قرائن تشغيلية" in factors["2.6"].value_ar
    assert "مصادر مستقلة" in factors["2.6"].value_ar
    assert "أدلة مستقلة" not in factors["2.6"].value_ar
    assert "كم/س·س" in factors["2.3"].value_ar
    assert "لا يمكن فصل ارتفاع عاصفي" in factors["2.7"].value_ar
    assert "م/ساعة" in factors["3.3"].value_ar
    assert "تغير 24س" in factors["4.1"].value_ar
    assert "°م/24س" in factors["4.1"].value_ar
    assert factors["6.4"].value_ar == "نوع الوقوف المدخل: شاطئ رملي"
    assert "مدخل يدوياً" in factors["8.6"].value_ar
    assert "provenance" not in factors["8.6"].value_ar
    assert sum(reason.startswith("أفق التوقع") for reason in result.confidence.reasons_ar) == 1


def test_full_day_window_crosses_midnight_when_needed(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    timezone = ZoneInfo("Africa/Tunis")
    dataset = dataset_factory(
        count=120,
        start_at=datetime(2026, 9, 4, 0, tzinfo=timezone),
    ).model_copy(update={"fetched_at": datetime(2026, 9, 7, 20, 50, tzinfo=timezone)})
    result = engine.evaluate(dataset)

    assert result.recommended_windows
    best = result.recommended_windows[0]
    assert best.start.hour == 21
    assert best.end.hour == 21
    assert best.end.date() > best.start.date()
    assert best.end - best.start == timedelta(hours=24)
    assert "اليوم التالي" in best.headline_ar
    assert "شهادة سلامة ميدانية" in result.summary_ar


def test_flat_sea_is_context_not_an_unverified_catch_penalty(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"wave_height_m": 0.1}))
    flat = next(factor for factor in result.hourly[0].factors if factor.code == "flat_sea_context")
    assert flat.impact == FactorImpact.NEUTRAL
    assert flat.score_delta == 0
    assert all(factor.code != "mirror_sea" for factor in result.hourly[0].factors)


def test_pressure_tendency_is_context_only_and_has_no_score_delta(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def update(index: int, values: dict[str, object]) -> None:
        values["pressure_msl_hpa"] = 1018.0 - index * 2.0

    result = engine.evaluate(dataset_factory(per_hour=update))
    factors = [factor for factor in result.hourly[3].factors if factor.code.startswith("pressure_")]
    assert factors
    assert all(factor.impact == FactorImpact.NEUTRAL for factor in factors)
    assert all(factor.score_delta == 0 for factor in factors)


def test_24h_context_and_direction_wrap_are_derived_with_explicit_units(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    start = datetime(2026, 9, 6, 0, tzinfo=ZoneInfo("Africa/Tunis"))

    def update(index: int, values: dict[str, object]) -> None:
        values["wind_direction_deg"] = 350.0 if index % 2 == 0 else 10.0
        values["pressure_msl_hpa"] = 1000.0 + index
        values["sea_surface_temperature_c"] = 20.0 + index * 0.1

    result = engine.evaluate(dataset_factory(per_hour=update, count=48, start_at=start))
    midnight = result.hourly[0]
    assert midnight.derived.max_wind_direction_shift_6h_deg == 20.0
    assert midnight.derived.wind_direction_coherence_6h == pytest.approx(0.985, abs=0.001)
    assert midnight.derived.wind_direction_data_hours_6h == 6
    assert midnight.derived.onshore_wind_stress_impulse_48h_pa_h is not None
    assert midnight.derived.pressure_change_24h_hpa == 24.0
    assert midnight.derived.sea_surface_temperature_change_24h_c == 2.4
    assert midnight.derived.history_hours_72h == 25
    assert midnight.derived.deep_water_wavelength_m is not None
    assert midnight.forecast.relative_humidity_pct == 65.0


def test_very_high_uv_is_health_caution_not_opportunity_bonus(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"uv_index": 9.0}))
    assert all(hour.safety == DecisionLevel.CAUTION for hour in result.hourly)
    factors = [
        factor for hour in result.hourly for factor in hour.factors if factor.code == "very_high_uv"
    ]
    assert factors
    assert all(factor.impact == FactorImpact.SAFETY for factor in factors)
    assert all(factor.score_delta == 0 for factor in factors)


def test_weak_fishing_opportunity_alone_does_not_veto_safe_trip(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    def weak_opportunity(_: int, values: dict[str, object]) -> None:
        values.update(
            wave_height_m=0.05,
            wave_period_s=2.0,
            wind_speed_kmh=12.0,
            wind_gust_kmh=15.0,
            wind_direction_deg=270.0,
            sea_surface_temperature_c=35.0,
            pressure_msl_hpa=980.0,
            sea_level_height_msl_m=0.0,
            ocean_current_velocity_kmh=0.05,
        )

    dataset = dataset_factory(
        per_hour=weak_opportunity,
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        angler_updates={"target_species": "european_seabass"},
        spot_updates={"shore_type": "cliff"},
    ).model_copy(update={"sunrise": None, "sunset": None})
    result = engine.evaluate(dataset)
    assert result.opportunity_score < 45
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert "ضعيفة" in result.summary_ar


def test_high_fouling_proxy_requires_three_families_but_cannot_veto_without_observation(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.65,
                "wave_period_s": 9.0,
                "wave_direction_deg": 0.0,
                "wind_speed_kmh": 5.0,
                "wind_gust_kmh": 8.0,
                "wind_direction_deg": 90.0,
                "ocean_current_velocity_kmh": 0.2,
                "ocean_current_direction_deg": 270.0,
                "precipitation_mm": 0.0,
            },
            spot_updates={"shore_type": "sandy", "exposure": "sheltered"},
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    field = result.field_feasibility
    assert field.fouling_transport_potential == PotentialLevel.HIGH
    assert field.fouling_evidence_count == 3
    assert result.decision == DecisionLevel.GO
    assert result.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
    assert result.recommended_windows
    assert "تنبيه غير مانع" in result.summary_ar


def test_single_antecedent_signal_is_only_a_potential_and_does_not_block(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.65,
                "wave_period_s": 9.0,
                "wave_direction_deg": 0.0,
                "wind_speed_kmh": 5.0,
                "wind_gust_kmh": 8.0,
                "wind_direction_deg": 270.0,
                "ocean_current_velocity_kmh": 0.2,
                "ocean_current_direction_deg": 0.0,
                "precipitation_mm": 0.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    field = result.field_feasibility
    assert field.fouling_transport_potential == PotentialLevel.LOW
    assert field.turbidity_potential == PotentialLevel.LOW
    assert field.fouling_evidence_count == 1
    assert result.decision == DecisionLevel.GO


def test_antecedent_48_to_72_hour_derivatives_are_explicit_and_directional(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.5,
                "wave_period_s": 8.0,
                "wind_speed_kmh": 10.0,
                "wind_direction_deg": 90.0,
                "ocean_current_velocity_kmh": 0.25,
                "ocean_current_direction_deg": 270.0,
                "precipitation_mm": 1.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    derived = result.hourly[0].derived
    assert derived.history_hours_48h == 48
    assert derived.history_hours_72h == 72
    assert derived.rain_48h_mm == 48.0
    assert derived.rain_72h_mm == 72.0
    assert derived.wave_energy_integral_48h == 96.0
    assert derived.onshore_wind_impulse_48h_kmh_h == 480.0
    assert derived.shoreward_current_impulse_48h_kmh_h == 12.0
    assert derived.wave_energy_data_hours_48h == 48
    assert derived.current_data_hours_48h == 48


def test_force_majeure_kind_tracks_the_reason_code(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    from spotdata.domain.enums import ForceMajeureKind

    go = engine.evaluate(
        dataset_factory(
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    assert go.force_majeure_kind == ForceMajeureKind.NONE
    assert go.gear_recommendation is not None
    assert len(go.gear_recommendation.scenarios) >= 1

    blocked = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.8,
                "wave_period_s": 7.0,
                "wave_direction_deg": 0.0,
                "ocean_current_velocity_kmh": 1.1,
                "wind_speed_kmh": 12.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    assert blocked.force_majeure_kind == ForceMajeureKind.HOLDING


def test_gear_recommendation_reflects_dominant_mechanism(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    from spotdata.domain.enums import LeadShape

    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 1.1,
                "wave_period_s": 9.0,
                "wave_direction_deg": 30.0,
                "ocean_current_velocity_kmh": 0.9,
                "wind_speed_kmh": 14.0,
            },
            count=96,
            start_at=datetime(2026, 9, 4, 0, tzinfo=ZoneInfo("Africa/Tunis")),
        )
    )
    recommendation = result.gear_recommendation
    assert recommendation is not None
    # The recommendation must mirror the breakdown's dominant mechanism.
    breakdown_dominant = result.field_feasibility.holding_breakdown.dominant
    assert recommendation.dominant_mechanism == breakdown_dominant
    assert (
        recommendation.scenarios[0].shape
        == {
            "longshore_current": LeadShape.BREAKAWAY_GRAPNEL,
            "orbital_motion": LeadShape.PYRAMID,
            "return_flow": LeadShape.STREAMLINED,
            "tidal_current": LeadShape.PYRAMID,
            "none": LeadShape.PYRAMID,
        }[breakdown_dominant]
    )
    assert recommendation.scenarios[-1].shape == LeadShape.ROCKY
    assert recommendation.confidence <= 30


def test_all_caution_day_is_no_go_without_a_go_window(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # A caution-only day has no window that passes the safety gate.
    result = engine.evaluate(
        dataset_factory(hour_updates={"wind_speed_kmh": 33.0, "wind_direction_deg": 90.0})
    )
    assert all(hour.safety == DecisionLevel.CAUTION for hour in result.hourly)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CONSERVATIVE_UNCERTAINTY
    assert result.recommended_windows == []


def test_high_uv_all_day_is_no_go_without_a_go_window(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(hour_updates={"uv_index": 9.0}))
    assert all(hour.safety == DecisionLevel.CAUTION for hour in result.hourly)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CONSERVATIVE_UNCERTAINTY
    assert result.recommended_windows == []


def test_multiple_near_limit_cautions_escalate_to_no_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # Two or more independent gates simultaneously within 10% of their no-go
    # threshold (but inside the caution band) are treated as a hard no-go.
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wind_speed_kmh": 35.0,
                "wind_gust_kmh": 46.0,
                "wave_height_m": 1.4,
                "wind_direction_deg": 90.0,
            }
        )
    )
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.SAFETY_HAZARD
    assert any(
        factor.code == "multiple_near_limit_cautions"
        for hour in result.hourly
        for factor in hour.factors
    )


def test_single_near_limit_caution_without_any_go_window_is_no_go(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(
        dataset_factory(hour_updates={"wind_speed_kmh": 35.0, "wind_direction_deg": 90.0})
    )
    assert all(hour.safety == DecisionLevel.CAUTION for hour in result.hourly)
    assert result.decision == DecisionLevel.NO_GO
    assert result.decision_reason_code == DecisionReasonCode.CONSERVATIVE_UNCERTAINTY
    assert result.recommended_windows == []


def test_alongshore_wind_channel_is_visible_to_the_holding_gate(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    """The gate and the displayed breakdown must agree (audit 2026-09-14).

    Before the fix, alongshore wind of 15-25 km/h was counted by the four-
    mechanism breakdown (medium lateral drag) but ignored by the holding gate
    (magnitude >= 25 km/h only), which could print "100/100" next to a
    "متوسط" sub-indicator. Now the gate uses the alongshore component >= 15
    km/h and the same wave-incidence weights as the breakdown.
    """
    result = engine.evaluate(
        dataset_factory(
            hour_updates={
                "wave_height_m": 0.4,  # below the 0.5m gate step
                "wave_direction_deg": 170.0,  # 80° from seaward normal → ALONGSHORE
                "wind_speed_kmh": 18.0,  # < 25, so old gate ignored it
                "wind_direction_deg": 180.0,  # alongshore wind ≈ 18 km/h
                "ocean_current_velocity_kmh": 0.3,
            }
        )
    )
    assert result.field_feasibility.holding_difficulty == PotentialLevel.MODERATE
    assert result.field_feasibility.holding_breakdown is not None
    assert result.field_feasibility.holding_breakdown.longshore_current == PotentialLevel.MODERATE
    assert result.field_feasibility.score < 100
