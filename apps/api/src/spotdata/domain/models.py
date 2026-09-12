from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ConfidenceBand,
    DecisionLevel,
    DecisionReasonCode,
    ExperienceLevel,
    Exposure,
    FactorAssessmentStatus,
    FactorBasis,
    FactorImpact,
    FieldFeasibilityLevel,
    ForceMajeureKind,
    LeadShape,
    MontageClass,
    ObservationMatchStatus,
    OrientationSource,
    PotentialLevel,
    RiskSeverity,
    RuleNature,
    ShoreType,
    SourceDataKind,
    TargetSpecies,
    TideState,
    WaveIncidence,
    WindRelation,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Coordinates(StrictModel):
    latitude: float = Field(ge=30.0, le=38.5, description="Tunisia-focused latitude")
    longitude: float = Field(ge=7.0, le=12.5, description="Tunisia-focused longitude")
    name: str | None = Field(default=None, max_length=120)


class OrientationEvidence(StrictModel):
    orientation_deg: float = Field(ge=0, lt=360)
    coastline_tangent_deg: float = Field(ge=0, lt=360)
    coastline_distance_m: float = Field(ge=0)
    search_radius_m: int = Field(ge=100, le=20_000)
    segments_used: int = Field(ge=1, le=25)
    confidence: Literal["high", "medium", "low"]
    provider: Literal["OpenStreetMap Overpass"] = "OpenStreetMap Overpass"
    server: str = Field(min_length=8, max_length=200)
    calculated_at: datetime
    limitations_ar: list[str] = Field(default_factory=list)

    @field_validator("calculated_at")
    @classmethod
    def calculated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("orientation calculation time must include a timezone")
        return value


class AutoOrientationRequest(StrictModel):
    latitude: float = Field(ge=30.0, le=38.5)
    longitude: float = Field(ge=7.0, le=12.5)


class AutoOrientationResponse(StrictModel):
    status: Literal["resolved", "unavailable"]
    orientation_deg: float | None = Field(default=None, ge=0, lt=360)
    evidence: OrientationEvidence | None = None
    reasons_ar: list[str]

    @model_validator(mode="after")
    def resolved_response_requires_evidence(self) -> AutoOrientationResponse:
        if self.status == "resolved" and (self.orientation_deg is None or self.evidence is None):
            raise ValueError("resolved orientation requires a value and evidence")
        if self.status == "unavailable" and (
            self.orientation_deg is not None or self.evidence is not None
        ):
            raise ValueError("unavailable orientation cannot contain resolved evidence")
        return self


class SpotProfile(StrictModel):
    seaward_orientation_deg: float = Field(
        ge=0.0,
        le=360.0,
        description="Bearing from shore towards open water; 0=N, 90=E.",
    )
    orientation_source: OrientationSource = OrientationSource.MANUAL
    orientation_evidence: OrientationEvidence | None = None
    shore_type: ShoreType = ShoreType.SANDY
    exposure: Exposure = Exposure.OPEN

    @field_validator("seaward_orientation_deg")
    @classmethod
    def normalize_orientation(cls, value: float) -> float:
        return 0.0 if value == 360.0 else value

    @model_validator(mode="after")
    def overpass_source_requires_matching_evidence(self) -> SpotProfile:
        if self.orientation_source == OrientationSource.OVERPASS:
            if self.orientation_evidence is None:
                raise ValueError("overpass orientation requires evidence")
            difference = abs(
                (self.seaward_orientation_deg - self.orientation_evidence.orientation_deg + 180)
                % 360
                - 180
            )
            if difference > 0.11:
                raise ValueError("spot orientation does not match overpass evidence")
        elif self.orientation_evidence is not None:
            raise ValueError("orientation evidence is only valid for an overpass source")
        return self


class AnglerProfile(StrictModel):
    experience: ExperienceLevel = ExperienceLevel.INTERMEDIATE
    target_species: TargetSpecies = TargetSpecies.GENERAL
    session_hours: int = Field(default=3, ge=2, le=4)


class ForecastHour(StrictModel):
    time: datetime
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    wind_gust_kmh: float | None = Field(default=None, ge=0)
    wind_direction_deg: float | None = Field(
        default=None, ge=0, le=360, description="Wind source/from bearing; 0=N, 90=E."
    )
    wave_height_m: float | None = Field(default=None, ge=0)
    wave_period_s: float | None = Field(default=None, ge=0)
    wave_direction_deg: float | None = Field(
        default=None, ge=0, le=360, description="Wave source/from bearing; 0=N, 90=E."
    )
    wind_wave_height_m: float | None = Field(default=None, ge=0)
    wind_wave_period_s: float | None = Field(default=None, ge=0)
    wind_wave_direction_deg: float | None = Field(default=None, ge=0, le=360)
    swell_height_m: float | None = Field(default=None, ge=0)
    swell_period_s: float | None = Field(default=None, ge=0)
    swell_direction_deg: float | None = Field(default=None, ge=0, le=360)
    sea_surface_temperature_c: float | None = Field(default=None, ge=-3, le=45)
    ocean_current_velocity_kmh: float | None = Field(default=None, ge=0)
    ocean_current_direction_deg: float | None = Field(
        default=None, ge=0, le=360, description="Current destination/towards bearing; 0=N, 90=E."
    )
    sea_level_height_msl_m: float | None = None
    air_temperature_c: float | None = Field(default=None, ge=-30, le=60)
    apparent_temperature_c: float | None = Field(default=None, ge=-60, le=70)
    relative_humidity_pct: float | None = Field(default=None, ge=0, le=100)
    dew_point_c: float | None = Field(default=None, ge=-60, le=60)
    cloud_cover_pct: float | None = Field(default=None, ge=0, le=100)
    shortwave_radiation_wm2: float | None = Field(default=None, ge=0, le=2_000)
    uv_index: float | None = Field(default=None, ge=0, le=30)
    lightning_potential_jkg: float | None = Field(default=None, ge=0)
    precipitation_mm: float | None = Field(default=None, ge=0)
    precipitation_probability_pct: float | None = Field(default=None, ge=0, le=100)
    weather_code: int | None = Field(default=None, ge=0, le=99)
    pressure_msl_hpa: float | None = Field(default=None, ge=850, le=1100)
    visibility_m: float | None = Field(default=None, ge=0)
    cape_jkg: float | None = Field(default=None, ge=0)

    @field_validator("time")
    @classmethod
    def time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forecast time must include a timezone")
        return value

    @field_validator(
        "wind_direction_deg",
        "wave_direction_deg",
        "wind_wave_direction_deg",
        "swell_direction_deg",
        "ocean_current_direction_deg",
    )
    @classmethod
    def normalize_direction(cls, value: float | None) -> float | None:
        return 0.0 if value == 360.0 else value


class SourceMetadata(StrictModel):
    provider: str
    product: str
    data_kind: SourceDataKind = SourceDataKind.USER_SUPPLIED
    variables: list[str]
    horizontal_resolution_km: float | None = None
    retrieved_at: datetime
    limitations_ar: list[str] = Field(default_factory=list)


class WeatherStationObservation(StrictModel):
    provider: str
    station_id: str
    station_name: str
    station_latitude: float
    station_longitude: float
    station_elevation_m: float | None = None
    observed_at: datetime
    retrieved_at: datetime
    distance_to_spot_km: float = Field(ge=0)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    wind_gust_kmh: float | None = Field(default=None, ge=0)
    wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    air_temperature_c: float | None = Field(default=None, ge=-40, le=60)
    dew_point_c: float | None = Field(default=None, ge=-60, le=60)
    pressure_hpa: float | None = Field(default=None, ge=850, le=1100)
    pressure_kind: Literal["sea_level_pressure", "altimeter_setting"] | None = None
    visibility_m: float | None = Field(default=None, ge=0)
    visibility_is_lower_bound: bool = False
    weather_text: str | None = None
    cloud_cover_code: str | None = None
    raw_report: str
    quality_control_flag: int | None = None
    is_direct_observation: Literal[True] = True
    is_spot_observation: Literal[False] = False

    @field_validator("observed_at", "retrieved_at")
    @classmethod
    def observation_times_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation times must include a timezone")
        return value

    @field_validator("wind_direction_deg")
    @classmethod
    def normalize_observed_direction(cls, value: float | None) -> float | None:
        return 0.0 if value == 360.0 else value


class CoastalWaterContext(StrictModel):
    """Optional Sentinel-2 coastal-water context, never an in-situ or forecast value."""

    availability: Literal["available", "unavailable"]
    provider: Literal["Copernicus Marine Service"] = "Copernicus Marine Service"
    product_id: Literal["OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205"] = (
        "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205"
    )
    dataset_id: Literal["cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107"] = (
        "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107"
    )
    data_kind: Literal["remote_sensing_estimate"] = "remote_sensing_estimate"
    sample_strategy: Literal["fixed_1000m_seaward_axis"] = "fixed_1000m_seaward_axis"
    sample_latitude: float = Field(ge=-90, le=90)
    sample_longitude: float = Field(ge=-180, le=180)
    sample_distance_from_spot_m: float = Field(ge=0)
    pixel_latitude: float | None = Field(default=None, ge=-90, le=90)
    pixel_longitude: float | None = Field(default=None, ge=-180, le=180)
    pixel_distance_from_spot_m: float | None = Field(default=None, ge=0)
    pixel_distance_from_sample_m: float | None = Field(default=None, ge=0)
    spatial_resolution_m: Literal[100] = 100
    valid_time: datetime | None = None
    retrieved_at: datetime
    age_hours: float | None = Field(default=None, ge=0)
    search_days: int = Field(default=10, ge=1, le=31)
    turbidity_fnu: float | None = Field(default=None, ge=0)
    turbidity_unit: Literal["FNU"] = "FNU"
    suspended_particulate_matter_g_m3: float | None = Field(default=None, ge=0)
    suspended_particulate_matter_unit: Literal["g/m³"] = "g/m³"
    chlorophyll_a_mg_m3: float | None = Field(default=None, ge=0)
    chlorophyll_a_unit: Literal["mg/m³"] = "mg/m³"
    sea_surface_temperature_c: float | None = Field(default=None, ge=-3, le=45)
    reason_ar: str
    affects_final_decision: Literal[False] = False
    is_direct_observation: Literal[False] = False
    is_spot_observation: Literal[False] = False
    is_forecast: Literal[False] = False

    @field_validator("valid_time", "retrieved_at")
    @classmethod
    def water_context_times_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("coastal-water context times must include a timezone")
        return value

    @model_validator(mode="after")
    def availability_must_match_values_and_provenance(self) -> CoastalWaterContext:
        optional_values = (
            self.suspended_particulate_matter_g_m3,
            self.chlorophyll_a_mg_m3,
            self.sea_surface_temperature_c,
        )
        retrieval_provenance = (
            self.valid_time,
            self.age_hours,
            self.pixel_latitude,
            self.pixel_longitude,
            self.pixel_distance_from_spot_m,
            self.pixel_distance_from_sample_m,
        )
        if self.availability == "available":
            if self.turbidity_fnu is None or any(value is None for value in retrieval_provenance):
                raise ValueError("available coastal-water context requires TUR and provenance")
            assert self.valid_time is not None and self.age_hours is not None
            actual_age_hours = (self.retrieved_at - self.valid_time).total_seconds() / 3_600.0
            if actual_age_hours < 0 or abs(self.age_hours - actual_age_hours) > 0.11:
                raise ValueError("coastal-water age must match valid and retrieval times")
        elif (
            self.turbidity_fnu is not None
            or any(value is not None for value in optional_values)
            or any(value is not None for value in retrieval_provenance)
        ):
            raise ValueError("unavailable coastal-water context cannot expose retrieval values")
        return self


class ObservationComparison(StrictModel):
    status: ObservationMatchStatus
    compared_forecast_time: datetime | None = None
    observation_age_minutes: float | None = Field(default=None, ge=0)
    station_distance_km: float | None = Field(default=None, ge=0)
    wind_speed_difference_kmh: float | None = Field(default=None, ge=0)
    wind_direction_difference_deg: float | None = Field(default=None, ge=0, le=180)
    temperature_difference_c: float | None = Field(default=None, ge=0)
    pressure_difference_hpa: float | None = Field(default=None, ge=0)
    affects_confidence: bool = False
    reasons_ar: list[str]

    @field_validator("compared_forecast_time")
    @classmethod
    def compared_time_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("compared forecast time must include a timezone")
        return value


class ForecastDataset(StrictModel):
    location: Coordinates
    target_date: date
    spot: SpotProfile
    angler: AnglerProfile = Field(default_factory=AnglerProfile)
    hours: list[ForecastHour]
    sunrise: datetime | None = None
    sunset: datetime | None = None
    fetched_at: datetime
    sources: list[SourceMetadata] = Field(default_factory=list)
    current_weather_observation: WeatherStationObservation | None = None
    coastal_water_context: CoastalWaterContext | None = None
    field_reports: list[FieldReport] = Field(default_factory=list, max_length=10)
    test_cast: TestCast | None = None
    official_warning: OfficialWarning | None = None

    @model_validator(mode="after")
    def validate_dataset(self) -> ForecastDataset:
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must include a timezone")
        if self.sunrise is not None and self.sunrise.tzinfo is None:
            raise ValueError("sunrise must include a timezone")
        if self.sunset is not None and self.sunset.tzinfo is None:
            raise ValueError("sunset must include a timezone")
        if len(self.hours) > 240:
            raise ValueError("at most 240 forecast hours are accepted")
        return self


class Factor(StrictModel):
    code: str
    label_ar: str
    impact: FactorImpact
    severity: RiskSeverity = RiskSeverity.INFO
    basis: FactorBasis
    rule_nature: RuleNature
    value: str | None = None
    score_delta: int = 0
    explanation_ar: str
    is_direct_observation: bool = False

    @model_validator(mode="after")
    def direct_observation_lineage_must_match_basis(self) -> Factor:
        expected = self.basis == FactorBasis.DIRECT_OBSERVATION
        if self.is_direct_observation != expected:
            raise ValueError("is_direct_observation must match the factor basis")
        return self


class DerivedConditions(StrictModel):
    wind_relation: WindRelation = WindRelation.UNKNOWN
    wind_angle_deg: float | None = None
    wind_shoreward_component_kmh: float | None = None
    wind_alongshore_component_kmh: float | None = Field(default=None, ge=0)
    wind_alongshore_signed_component_kmh: float | None = None
    alongshore_positive_bearing_deg: float = Field(ge=0, lt=360)
    wind_drag_coefficient: float | None = Field(default=None, ge=0)
    wind_stress_pa: float | None = Field(default=None, ge=0)
    wind_stress_shoreward_pa: float | None = None
    wind_stress_alongshore_pa: float | None = None
    wave_incidence: WaveIncidence = WaveIncidence.UNKNOWN
    wave_angle_deg: float | None = None
    wave_shoreward_alignment: float | None = Field(default=None, ge=-1, le=1)
    wave_alongshore_alignment: float | None = Field(default=None, ge=0, le=1)
    wave_alongshore_signed_alignment: float | None = Field(default=None, ge=-1, le=1)
    deep_water_wavelength_m: float | None = Field(default=None, ge=0)
    wave_steepness: float | None = Field(default=None, ge=0)
    wave_energy_proxy: float | None = Field(default=None, ge=0)
    alongshore_wave_proxy: float | None = Field(default=None, ge=0)
    alongshore_wave_signed_proxy: float | None = None
    wave_component_angle_deg: float | None = Field(default=None, ge=0, le=180)
    wave_component_secondary_energy_share: float | None = Field(default=None, ge=0, le=0.5)
    gust_factor: float | None = Field(default=None, ge=0)
    max_wind_direction_shift_6h_deg: float | None = Field(default=None, ge=0, le=180)
    wind_direction_coherence_6h: float | None = Field(default=None, ge=0, le=1)
    wind_direction_data_hours_6h: int = Field(default=0, ge=0, le=6)
    current_alongshore_kmh: float | None = None
    current_cross_shore_kmh: float | None = None
    tide_state: TideState = TideState.UNKNOWN
    sea_level_rate_m_per_h: float | None = None
    tide_movement_index: float | None = Field(default=None, ge=0, le=1)
    pressure_change_3h_hpa: float | None = None
    pressure_change_24h_hpa: float | None = None
    sea_surface_temperature_change_24h_c: float | None = None
    max_wind_speed_24h_kmh: float | None = Field(default=None, ge=0)
    max_wave_height_24h_m: float | None = Field(default=None, ge=0)
    strong_wind_hours_24h: int = Field(default=0, ge=0, le=24)
    sea_level_range_target_day_m: float | None = Field(default=None, ge=0)
    rain_24h_mm: float | None = None
    rain_48h_mm: float | None = None
    rain_72h_mm: float | None = None
    max_wave_height_48h_m: float | None = Field(default=None, ge=0)
    max_wave_height_72h_m: float | None = Field(default=None, ge=0)
    wave_energy_integral_48h: float | None = Field(default=None, ge=0)
    onshore_wind_impulse_48h_kmh_h: float | None = Field(default=None, ge=0)
    onshore_wind_stress_impulse_48h_pa_h: float | None = Field(default=None, ge=0)
    shoreward_current_impulse_48h_kmh_h: float | None = Field(default=None, ge=0)
    strong_wave_hours_48h: int = Field(default=0, ge=0, le=48)
    history_hours_72h: int = Field(default=0, ge=0, le=72)
    history_hours_48h: int = Field(default=0, ge=0, le=48)
    history_hours_24h: int = Field(default=0, ge=0, le=24)
    history_hours_12h: int = Field(default=0, ge=0, le=12)
    rain_data_hours_48h: int = Field(default=0, ge=0, le=48)
    rain_data_hours_24h: int = Field(default=0, ge=0, le=24)
    wind_data_hours_48h: int = Field(default=0, ge=0, le=48)
    wind_data_hours_12h: int = Field(default=0, ge=0, le=12)
    wave_energy_data_hours_48h: int = Field(default=0, ge=0, le=48)
    wave_energy_data_hours_12h: int = Field(default=0, ge=0, le=12)
    current_data_hours_48h: int = Field(default=0, ge=0, le=48)
    onshore_wind_fraction_48h: float | None = Field(default=None, ge=0, le=1)
    onshore_wind_fraction_12h: float | None = Field(default=None, ge=0, le=1)
    energetic_wave_fraction_48h: float | None = Field(default=None, ge=0, le=1)
    energetic_wave_fraction_12h: float | None = Field(default=None, ge=0, le=1)
    air_sea_temperature_difference_c: float | None = None
    dew_point_depression_c: float | None = None
    is_twilight: bool = False
    is_night: bool = False


class ConfidenceResult(StrictModel):
    score: int = Field(ge=0, le=100)
    band: ConfidenceBand
    reasons_ar: list[str]
    is_accuracy_probability: Literal[False] = False


class ForecastConditions(StrictModel):
    wind_speed_kmh: float | None = None
    wind_gust_kmh: float | None = None
    wind_direction_deg: float | None = None
    wave_height_m: float | None = None
    wave_period_s: float | None = None
    wave_direction_deg: float | None = None
    wind_wave_height_m: float | None = None
    wind_wave_period_s: float | None = None
    wind_wave_direction_deg: float | None = None
    swell_height_m: float | None = None
    swell_period_s: float | None = None
    swell_direction_deg: float | None = None
    sea_surface_temperature_c: float | None = None
    ocean_current_velocity_kmh: float | None = None
    ocean_current_direction_deg: float | None = None
    sea_level_height_msl_m: float | None = None
    air_temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    dew_point_c: float | None = None
    cloud_cover_pct: float | None = None
    shortwave_radiation_wm2: float | None = None
    uv_index: float | None = None
    lightning_potential_jkg: float | None = None
    cape_jkg: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability_pct: float | None = None
    weather_code: int | None = None
    pressure_msl_hpa: float | None = None
    visibility_m: float | None = None


class HoldingBreakdown(StrictModel):
    """Separate the four physical mechanisms behind line-holding difficulty.

    This is diagnostic only: the single `holding_difficulty` gate keeps its original
    computation, so exposing these mechanisms never changes the binary decision.
    """

    longshore_current: PotentialLevel
    orbital_motion: PotentialLevel
    return_flow: PotentialLevel
    tidal_current: PotentialLevel
    dominant: Literal[
        "longshore_current", "orbital_motion", "return_flow", "tidal_current", "none"
    ]
    confidence: int = Field(ge=0, le=50)
    orbital_velocity_band_ms: str | None = None
    depth_band_m: str = "1.5 إلى 5.0"
    reasons_ar: list[str]


class FieldFeasibilityResult(StrictModel):
    status: FieldFeasibilityLevel
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=50)
    holding_difficulty: PotentialLevel
    holding_breakdown: HoldingBreakdown | None = None
    fouling_transport_potential: PotentialLevel
    turbidity_potential: PotentialLevel
    rip_current_potential: PotentialLevel
    fouling_evidence_count: int = Field(default=0, ge=0, le=8)
    turbidity_evidence_count: int = Field(default=0, ge=0, le=8)
    antecedent_window_hours: Literal[48] = 48
    reasons_ar: list[str]
    limitations_ar: list[str]
    is_direct_observation: Literal[False] = False


class LeadScenario(StrictModel):
    shape: LeadShape
    shape_ar: str
    bottom_ar: str
    weight_min_g: int = Field(ge=20, le=400)
    weight_max_g: int = Field(ge=20, le=400)
    weight_band_ar: str
    montage_class: MontageClass
    montage_ar: str
    lateral_hold: PotentialLevel
    snag_risk: PotentialLevel
    note_ar: str
    rationale_ar: str

    @model_validator(mode="after")
    def weight_band_is_ordered(self) -> LeadScenario:
        if self.weight_min_g > self.weight_max_g:
            raise ValueError("weight band minimum must not exceed maximum")
        return self


class GearRecommendation(StrictModel):
    scenarios: list[LeadScenario] = Field(min_length=1, max_length=3)
    dominant_mechanism: Literal[
        "longshore_current", "orbital_motion", "return_flow", "tidal_current", "none"
    ]
    required_rod_rating_note_ar: str
    casting_advice_ar: str
    confidence: int = Field(ge=0, le=30)
    limitations_ar: list[str]


class HourDecision(StrictModel):
    time: datetime
    safety: DecisionLevel
    opportunity_score: int = Field(ge=0, le=100)
    confidence: ConfidenceResult
    field_feasibility: FieldFeasibilityResult
    factors: list[Factor]
    forecast: ForecastConditions
    derived: DerivedConditions


class DecisionWindow(StrictModel):
    start: datetime
    end: datetime
    safety: DecisionLevel
    field_feasibility: FieldFeasibilityLevel
    field_score: int = Field(ge=0, le=100)
    opportunity_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    headline_ar: str
    key_factors_ar: list[str]


class TideEvent(StrictModel):
    time: datetime
    kind: str = Field(pattern="^(high|low)$")
    level_msl_m: float
    disclaimer_ar: str


class FactorCoverageSummary(StrictModel):
    catalog_version: str
    matrix_version: str
    source_claimed_total: int = Field(ge=0)
    audited_total: int = Field(ge=0)
    automated_decision: int = Field(ge=0)
    automated_context: int = Field(ge=0)
    proxy_requires_field_check: int = Field(ge=0)
    field_or_external_required: int = Field(ge=0)
    excluded_unsupported: int = Field(ge=0)
    note_ar: str


class FactorAssessment(StrictModel):
    matrix_id: str
    chapter_ar: str
    title_ar: str
    status: FactorAssessmentStatus
    decision_axis: str
    value_ar: str
    evidence_variables: list[str]
    rationale_ar: str
    affects_final_decision: bool = False


SCHEMA_VERSION: Literal["3.9"] = "3.9"


class SpeciesAxisValue(StrictModel):
    """One reporting-only species axis (E7). Never changes the binary decision."""

    axis: Literal["seasonal", "habitat", "surf_approach", "feeding_window", "prey_evidence"]
    status: Literal["favorable", "neutral", "unfavorable", "unknown"]
    label_ar: str
    evidence_ar: list[str] = Field(default_factory=list)
    basis: Literal["expert_prior", "model_forecast", "spot_profile", "unknown"]
    confidence: int = Field(ge=0, le=50)


class SpeciesMatch(StrictModel):
    """One profiled species matched against today's conditions (reporting only).

    Availability is the month x zone presence level (قوي/متوسط/ضعيف/غير متوفر)
    derived from published Tunisian studies (see `sources_ar`); thermal and
    habitat are low-weight expert priors. Never a catch probability and never a
    legal rule (D10/D11). The combined `status` ranks how well the species fits
    the current factors, informational only.
    """

    species: str
    label_ar: str
    availability: Literal["strong", "medium", "weak", "unavailable", "unknown"]
    thermal: Literal["preferred", "tolerated", "outside", "unknown"]
    habitat_match: bool | None = None
    status: Literal["favorable", "neutral", "unfavorable", "unknown"]
    reasons_ar: list[str] = Field(default_factory=list)
    sources_ar: list[str] = Field(default_factory=list)
    # Sea-state x month (reporting only): the day's classified sea state, the
    # species' published preference, and their fit. Never changes the decision.
    sea_state_ar: str = ""
    sea_state_preference_ar: str = ""
    sea_state_fit: Literal["favorable", "neutral", "unknown"] = "unknown"


class SpeciesAxes(StrictModel):
    """The seven E7 outputs: five substantive axes + confidence + unknown list.

    Deliberately no aggregation into a single "fish probability": the axes stay
    separate, report-only, and never veto a safe executable window.
    """

    target_species: str
    label_ar: str
    axes: list[SpeciesAxisValue]
    unknown_axes: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=50)
    notes_ar: list[str] = Field(default_factory=list)
    species_matches: list[SpeciesMatch] = Field(default_factory=list)
    sources_ar: list[str] = Field(default_factory=list)
    sea_state_ar: str | None = None


class PeriodActivity(StrictModel):
    """One day-period bucket of the reporting-only species activity indicator."""

    key: Literal["dawn", "morning", "midday", "afternoon", "dusk", "night"]
    label_ar: str
    range_ar: str
    score: int | None = Field(default=None, ge=0, le=100)
    peak_hour_ar: str | None = None
    top_factor_ar: str | None = None


class HourActivity(StrictModel):
    """One hour of the reporting-only species activity indicator (never a probability)."""

    time: datetime
    score: int = Field(ge=0, le=100)
    is_twilight: bool = False
    is_night: bool = False


class SpeciesActivity(StrictModel):
    """Reporting-only relative activity indicator (0-100) for one species across the day.

    Built from documented factors — feeding window (twilight/night), water
    temperature, seasonal availability from published studies (dominant), shore
    match, and sea-state fit — with the same low-weight priors as the rest of
    the engine. It is a relative indicator, never a statistical probability of
    presence or a catch promise (D10/D11).
    """

    species: str
    label_ar: str
    basis_ar: list[str] = Field(default_factory=list)
    periods: list[PeriodActivity]
    hourly: list[HourActivity]
    is_probability: Literal[False] = False


class DecisionResponse(StrictModel):
    schema_version: Literal["3.9"] = SCHEMA_VERSION
    engine_version: str
    decision: DecisionLevel
    decision_reason_code: DecisionReasonCode
    decision_label_ar: str
    summary_ar: str
    opportunity_score: int = Field(ge=0, le=100)
    score_is_success_probability: Literal[False] = False
    confidence: ConfidenceResult
    field_feasibility: FieldFeasibilityResult
    gear_recommendation: GearRecommendation | None = None
    fouling_evidence: FoulingEvidence | None = None
    trip_ruin_factors: list[TripRuinFactor] = Field(default_factory=list)
    spring_neap: SpringNeap | None = None
    species_axes: SpeciesAxes | None = None
    species_activity: list[SpeciesActivity] = Field(default_factory=list)
    force_majeure_kind: ForceMajeureKind
    sunrise: datetime | None = None
    sunset: datetime | None = None
    recommended_windows: list[DecisionWindow]
    avoid_windows: list[DecisionWindow]
    tide_events: list[TideEvent]
    hourly: list[HourDecision]
    antecedent_hours: list[ForecastHour] = Field(max_length=72)
    sources: list[SourceMetadata]
    current_weather_observation: WeatherStationObservation | None = None
    coastal_water_context: CoastalWaterContext | None = None
    observation_comparison: ObservationComparison
    factor_coverage: FactorCoverageSummary
    factor_assessments: list[FactorAssessment]
    limitations_ar: list[str]
    generated_at: datetime

    @field_validator("sunrise", "sunset")
    @classmethod
    def sun_times_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("sun times must include a timezone")
        return value

    @model_validator(mode="after")
    def headline_decision_is_binary_and_ledger_is_complete(self) -> DecisionResponse:
        if self.decision not in {DecisionLevel.GO, DecisionLevel.NO_GO}:
            raise ValueError("headline decision must be binary")
        if (
            self.decision == DecisionLevel.GO
            and self.decision_reason_code != DecisionReasonCode.SAFE_WINDOW
        ):
            raise ValueError("GO requires the SAFE_WINDOW reason code")
        if (
            self.decision == DecisionLevel.NO_GO
            and self.decision_reason_code == DecisionReasonCode.SAFE_WINDOW
        ):
            raise ValueError("NO_GO cannot use the SAFE_WINDOW reason code")
        if self.decision == DecisionLevel.GO and not self.recommended_windows:
            raise ValueError("GO requires at least one recommended gate-passing window")
        if self.decision == DecisionLevel.NO_GO and self.recommended_windows:
            raise ValueError("NO_GO cannot expose a recommended window")
        expected_label = "اذهب" if self.decision == DecisionLevel.GO else "لا تذهب"
        if self.decision_label_ar != expected_label:
            raise ValueError("headline decision label must be the exact binary Arabic label")
        if len(self.factor_assessments) != 63:
            raise ValueError("factor assessment ledger must contain all 63 matrix factors")
        if len({item.matrix_id for item in self.factor_assessments}) != 63:
            raise ValueError("factor assessment ledger matrix ids must be unique")
        return self


class FieldReport(StrictModel):
    """A recent field observation attached to the spot (fouling ladder input).

    Validity is time-based (24 hours from fetch) and the report carries no
    coordinates: it is assumed to describe the spot being evaluated.
    """

    kind: Literal["fouling", "turbidity", "rip_current", "visibility", "jellyfish", "debris"]
    severity: Literal["present", "dense"]
    source: Literal["user", "community", "official"]
    reported_at: datetime
    note_ar: str | None = Field(default=None, max_length=300)

    @field_validator("reported_at")
    @classmethod
    def reported_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("field report time must include a timezone")
        return value


class TestCast(StrictModel):
    """A real casting test result: did the rig foul (hook) or come back clean?"""

    cast_at: datetime
    hooked: bool

    @field_validator("cast_at")
    @classmethod
    def cast_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("test cast time must include a timezone")
        return value


class OfficialWarning(StrictModel):
    """A currently-valid official marine warning (e.g. the INM bulletin, D14).

    Any valid official warning is a hard no-go that overrides every local
    threshold: safety remains the top authority.
    """

    source: Literal["inm", "other_official"] = "inm"
    kind: Literal["strong_wind", "rough_sea", "heavy_rain", "other"]
    level: Literal["warning", "alert"] = "warning"
    issued_at: datetime
    text_ar: str = Field(default="", max_length=300)

    @field_validator("issued_at")
    @classmethod
    def issued_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("official warning time must include a timezone")
        return value


class ForecastDecisionRequest(StrictModel):
    location: Coordinates
    target_date: date
    spot: SpotProfile
    angler: AnglerProfile = Field(default_factory=AnglerProfile)
    field_reports: list[FieldReport] = Field(default_factory=list, max_length=10)
    test_cast: TestCast | None = None
    official_warning: OfficialWarning | None = None


class FoulingEvidence(StrictModel):
    """The five-rung fouling evidence ladder (phase 4).

    Levels 1-3 are caution-only; level 4 or 5 (consistent recent reports, an
    official report, or a fouled test cast) is a force-majeure candidate.
    """

    level: int = Field(ge=0, le=5)
    is_force_majeure: bool
    basis_ar: list[str]
    notes_ar: list[str]


class TripRuinFactor(StrictModel):
    """One trip-ruining factor (v1.9.8): what can make a surfcasting outing
    practically impossible. Evidence-gated per policy: confirmed evidence
    (satellite strong signal or recent field report) may force majeure;
    forecast/proxy stays a caution; unsupported stays Unknown (D11)."""

    factor: Literal["dense_fouling", "turbidity", "jellyfish", "marine_heatwave", "storm_debris"]
    label_ar: str
    level: Literal["unknown", "low", "moderate", "high"]
    basis: Literal["satellite", "forecast_proxy", "field_report", "unknown"]
    is_force_majeure: bool
    evidence_ar: list[str] = Field(default_factory=list)
    age_ar: str | None = None
    source_ar: str = ""


class SpringNeap(StrictModel):
    """Spring/neap classification from the modelled sea-level series (phase 5).

    Computed from the actual daily range, never from the moon phase. The folk
    label is displayed beside the physical value; only the physical value feeds
    any decision channel (the tidal-current rating inside holding_breakdown).
    """

    classification: Literal["spring", "neap", "intermediate", "unknown"]
    folk_label_ar: str
    range_target_day_m: float | None = None
    range_reference_m: float | None = None
    range_ratio: float | None = None
    max_level_rate_m_per_h: float | None = None
    gabes_zone: bool = False
    confidence: int = Field(ge=0, le=50)
    notes_ar: list[str]
    limitations_ar: list[str]


class GeminiReportRequest(StrictModel):
    request: ForecastDecisionRequest
    decision: DecisionResponse


class GeminiNarrative(StrictModel):
    executive_summary_ar: str = Field(min_length=10, max_length=1_500)
    timing_and_water_ar: list[str] = Field(min_length=1, max_length=8)
    temporal_analysis_ar: list[str] = Field(min_length=1, max_length=8)
    factor_interactions_ar: list[str] = Field(min_length=1, max_length=10)
    field_tactics_ar: list[str] = Field(min_length=1, max_length=10)
    unknowns_ar: list[str] = Field(min_length=1, max_length=10)

    @field_validator(
        "timing_and_water_ar",
        "temporal_analysis_ar",
        "factor_interactions_ar",
        "field_tactics_ar",
        "unknowns_ar",
    )
    @classmethod
    def narrative_items_are_bounded(cls, value: list[str]) -> list[str]:
        if any(len(item) < 3 or len(item) > 700 for item in value):
            raise ValueError("narrative items must contain between 3 and 700 characters")
        return value


class GeminiReportMetadata(StrictModel):
    generated_by: Literal["google_gemini"] = "google_gemini"
    model: str
    prompt_version: str
    template_version: str
    generated_at: datetime
    input_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    decision_was_modified: Literal[False] = False
    numbers_are_server_rendered: Literal[True] = True


class GeminiReportResponse(StrictModel):
    narrative: GeminiNarrative
    report_text: str = Field(min_length=100, max_length=40_000)
    metadata: GeminiReportMetadata


class GeminiKeyVerificationResponse(StrictModel):
    valid: Literal[True] = True
    provider: Literal["Google Gemini"] = "Google Gemini"
    model: str
    message_ar: str


class ErrorBody(BaseModel):
    code: str
    message_ar: str
    details: dict[str, Any] | None = None


class SpotCandidate(StrictModel):
    """One named spot to rank inside a wilaya sweep (D13)."""

    spot_id: str = Field(min_length=1, max_length=64)
    name_ar: str = Field(max_length=120)
    location: Coordinates
    spot: SpotProfile


class RankSpotsRequest(StrictModel):
    """Analyze several known spots for one day and rank them best-to-weakest."""

    target_date: date
    angler: AnglerProfile = Field(default_factory=AnglerProfile)
    spots: list[SpotCandidate] = Field(min_length=1, max_length=12)
    field_reports: list[FieldReport] = Field(default_factory=list, max_length=10)
    test_cast: TestCast | None = None
    official_warning: OfficialWarning | None = None


class RankedSpot(StrictModel):
    """Compact per-spot result: decision + best hour + fish-presence axes."""

    spot_id: str
    name_ar: str
    decision: DecisionLevel
    decision_reason_code: DecisionReasonCode
    force_majeure_kind: ForceMajeureKind
    best_window_start: datetime | None = None
    best_window_end: datetime | None = None
    opportunity_score: int
    field_status: FieldFeasibilityLevel
    holding_difficulty: PotentialLevel
    fouling_level: int | None = None
    fouling_force_majeure: bool = False
    spring_classification: str | None = None
    spring_folk_label: str | None = None
    spring_gabes_zone: bool = False
    species_label_ar: str | None = None
    species_axes_summary: list[str] = Field(default_factory=list)
    species_confidence: int | None = None
    summary_ar: str
    key_factors_ar: list[str] = Field(default_factory=list)
    error_ar: str | None = None


class RankSpotsResponse(StrictModel):
    target_date: date
    generated_at: datetime
    ranked: list[RankedSpot]
    notes_ar: list[str] = Field(default_factory=list)
