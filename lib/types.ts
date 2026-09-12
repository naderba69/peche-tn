export type DecisionLevel = "go" | "caution" | "no_go" | "unknown";
export type BinaryDecision = "go" | "no_go";
export type DecisionReasonCode =
  | "safe_window"
  | "safety_hazard"
  | "field_infeasible"
  | "critical_data_missing"
  | "conservative_uncertainty"
  | "fouling_confirmed"
  | "official_warning"
  | "trip_ruin_confirmed";
export type ConfidenceBand = "high" | "medium" | "low";
export type ShoreType = "sandy" | "rocky" | "cliff" | "jetty";
export type ExperienceLevel = "beginner" | "intermediate" | "advanced";
export type FieldFeasibilityLevel = "favorable" | "workable" | "difficult" | "unknown";
export type PotentialLevel = "low" | "moderate" | "high" | "unknown";
export type TargetSpecies =
  | "general"
  | "european_seabass"
  | "gilthead_seabream"
  | "white_seabream"
  | "striped_seabream";

export interface Coordinates {
  latitude: number;
  longitude: number;
  name?: string;
}

export interface OrientationEvidence {
  orientation_deg: number;
  coastline_tangent_deg: number;
  coastline_distance_m: number;
  search_radius_m: number;
  segments_used: number;
  confidence: "high" | "medium" | "low";
  provider: "OpenStreetMap Overpass";
  server: string;
  calculated_at: string;
  limitations_ar: string[];
}

export interface AutoOrientationResponse {
  status: "resolved" | "unavailable";
  orientation_deg: number | null;
  evidence: OrientationEvidence | null;
  reasons_ar: string[];
}

export interface SpotProfile {
  seaward_orientation_deg: number;
  orientation_source: "surveyed" | "manual" | "map" | "overpass" | "estimated";
  orientation_evidence?: OrientationEvidence | null;
  shore_type: ShoreType;
  exposure: "open" | "partly_sheltered" | "sheltered";
}

export interface AnglerProfile {
  experience: ExperienceLevel;
  target_species: TargetSpecies;
  session_hours: number;
}

export interface ForecastDecisionRequest {
  location: Coordinates;
  target_date: string;
  spot: SpotProfile;
  angler: AnglerProfile;
  field_reports?: FieldReport[];
  test_cast?: TestCast | null;
  official_warning?: OfficialWarning | null;
}

export type FieldReportKind = "fouling" | "turbidity" | "rip_current" | "visibility";

export interface FieldReport {
  kind: FieldReportKind;
  severity: "present" | "dense";
  source: "user" | "community" | "official";
  reported_at: string;
  note_ar?: string | null;
}

export interface TestCast {
  cast_at: string;
  hooked: boolean;
}

export interface OfficialWarning {
  source: "inm" | "other_official";
  kind: "strong_wind" | "rough_sea" | "heavy_rain" | "other";
  level: "warning" | "alert";
  issued_at: string;
  text_ar?: string;
}

export interface FoulingEvidence {
  level: number;
  is_force_majeure: boolean;
  basis_ar: string[];
  notes_ar: string[];
}

export type TripRuinFactorKey =
  | "dense_fouling"
  | "turbidity"
  | "jellyfish"
  | "marine_heatwave"
  | "storm_debris";

export interface TripRuinFactor {
  factor: TripRuinFactorKey;
  label_ar: string;
  level: "unknown" | "low" | "moderate" | "high";
  basis: "satellite" | "forecast_proxy" | "field_report" | "unknown";
  is_force_majeure: boolean;
  evidence_ar: string[];
  age_ar?: string | null;
  source_ar: string;
}

export type SpringNeapClass = "spring" | "neap" | "intermediate" | "unknown";

export interface SpringNeap {
  classification: SpringNeapClass;
  folk_label_ar: string;
  range_target_day_m: number | null;
  range_reference_m: number | null;
  range_ratio: number | null;
  max_level_rate_m_per_h: number | null;
  gabes_zone: boolean;
  confidence: number;
  notes_ar: string[];
  limitations_ar: string[];
}

export type FactorBasis =
  | "model_forecast"
  | "direct_observation"
  | "remote_sensing_estimate"
  | "derived_forecast"
  | "spot_profile"
  | "expert_prior";

export type ObservationMatchStatus =
  | "unavailable"
  | "not_applicable"
  | "stale"
  | "distant"
  | "limited"
  | "consistent"
  | "divergent";
export type RuleNature = "physical_derivation" | "safety_policy" | "operational_proxy" | "expert_prior" | "data_quality";

export interface Factor {
  code: string;
  label_ar: string;
  impact: "positive" | "negative" | "neutral" | "safety" | "data_gap";
  severity: "info" | "caution" | "critical";
  basis: FactorBasis;
  rule_nature: RuleNature;
  value: string | null;
  score_delta: number;
  explanation_ar: string;
  is_direct_observation: boolean;
}

export interface ForecastConditions {
  wind_speed_kmh: number | null;
  wind_gust_kmh: number | null;
  wind_direction_deg: number | null;
  wave_height_m: number | null;
  wave_period_s: number | null;
  wave_direction_deg: number | null;
  wind_wave_height_m: number | null;
  wind_wave_period_s: number | null;
  wind_wave_direction_deg: number | null;
  swell_height_m: number | null;
  swell_period_s: number | null;
  swell_direction_deg: number | null;
  sea_surface_temperature_c: number | null;
  ocean_current_velocity_kmh: number | null;
  ocean_current_direction_deg: number | null;
  sea_level_height_msl_m: number | null;
  air_temperature_c: number | null;
  apparent_temperature_c: number | null;
  relative_humidity_pct: number | null;
  dew_point_c: number | null;
  cloud_cover_pct: number | null;
  shortwave_radiation_wm2: number | null;
  uv_index: number | null;
  lightning_potential_jkg: number | null;
  cape_jkg: number | null;
  precipitation_mm: number | null;
  precipitation_probability_pct: number | null;
  weather_code: number | null;
  pressure_msl_hpa: number | null;
  visibility_m: number | null;
}

export interface NormalizedForecastHour extends ForecastConditions {
  time: string;
}

export interface DerivedConditions {
  wind_relation: string;
  wind_angle_deg: number | null;
  wind_shoreward_component_kmh: number | null;
  wind_alongshore_component_kmh: number | null;
  wind_alongshore_signed_component_kmh: number | null;
  alongshore_positive_bearing_deg: number;
  wind_drag_coefficient: number | null;
  wind_stress_pa: number | null;
  wind_stress_shoreward_pa: number | null;
  wind_stress_alongshore_pa: number | null;
  wave_incidence: string;
  wave_angle_deg: number | null;
  wave_shoreward_alignment: number | null;
  wave_alongshore_alignment: number | null;
  wave_alongshore_signed_alignment: number | null;
  deep_water_wavelength_m: number | null;
  wave_steepness: number | null;
  wave_energy_proxy: number | null;
  alongshore_wave_proxy: number | null;
  alongshore_wave_signed_proxy: number | null;
  wave_component_angle_deg: number | null;
  wave_component_secondary_energy_share: number | null;
  gust_factor: number | null;
  max_wind_direction_shift_6h_deg: number | null;
  wind_direction_coherence_6h: number | null;
  wind_direction_data_hours_6h: number;
  current_alongshore_kmh: number | null;
  current_cross_shore_kmh: number | null;
  tide_state: "rising" | "falling" | "slack" | "unknown";
  sea_level_rate_m_per_h: number | null;
  tide_movement_index: number | null;
  pressure_change_3h_hpa: number | null;
  pressure_change_24h_hpa: number | null;
  sea_surface_temperature_change_24h_c: number | null;
  max_wind_speed_24h_kmh: number | null;
  max_wave_height_24h_m: number | null;
  strong_wind_hours_24h: number;
  sea_level_range_target_day_m: number | null;
  rain_24h_mm: number | null;
  rain_48h_mm: number | null;
  rain_72h_mm: number | null;
  max_wave_height_48h_m: number | null;
  max_wave_height_72h_m: number | null;
  wave_energy_integral_48h: number | null;
  onshore_wind_impulse_48h_kmh_h: number | null;
  onshore_wind_stress_impulse_48h_pa_h: number | null;
  shoreward_current_impulse_48h_kmh_h: number | null;
  strong_wave_hours_48h: number;
  history_hours_72h: number;
  history_hours_48h: number;
  history_hours_24h: number;
  history_hours_12h: number;
  rain_data_hours_48h: number;
  rain_data_hours_24h: number;
  wind_data_hours_48h: number;
  wind_data_hours_12h: number;
  wave_energy_data_hours_48h: number;
  wave_energy_data_hours_12h: number;
  current_data_hours_48h: number;
  onshore_wind_fraction_48h: number | null;
  onshore_wind_fraction_12h: number | null;
  energetic_wave_fraction_48h: number | null;
  energetic_wave_fraction_12h: number | null;
  air_sea_temperature_difference_c: number | null;
  dew_point_depression_c: number | null;
  is_twilight: boolean;
  is_night: boolean;
}

export interface ConfidenceResult {
  score: number;
  band: ConfidenceBand;
  reasons_ar: string[];
  is_accuracy_probability: false;
}

export type HoldingMechanism =
  | "longshore_current"
  | "orbital_motion"
  | "return_flow"
  | "tidal_current"
  | "none";

export type ForceMajeureKind =
  | "none"
  | "safety"
  | "holding"
  | "fouling"
  | "access_legal"
  | "trip_ruin"
  | "data";

export type LeadShape =
  | "streamlined"
  | "pyramid"
  | "grapnel"
  | "breakaway_grapnel"
  | "rocky";

export type MontageClass = "low" | "medium" | "high";

export interface LeadScenario {
  shape: LeadShape;
  shape_ar: string;
  bottom_ar: string;
  weight_min_g: number;
  weight_max_g: number;
  weight_band_ar: string;
  montage_class: MontageClass;
  montage_ar: string;
  lateral_hold: PotentialLevel;
  snag_risk: PotentialLevel;
  note_ar: string;
  rationale_ar: string;
}

export interface GearRecommendation {
  scenarios: LeadScenario[];
  dominant_mechanism: HoldingMechanism;
  required_rod_rating_note_ar: string;
  casting_advice_ar: string;
  confidence: number;
  limitations_ar: string[];
}

export interface HoldingBreakdown {
  longshore_current: PotentialLevel;
  orbital_motion: PotentialLevel;
  return_flow: PotentialLevel;
  tidal_current: PotentialLevel;
  dominant: HoldingMechanism;
  confidence: number;
  orbital_velocity_band_ms: string | null;
  depth_band_m: string;
  reasons_ar: string[];
}

export interface FieldFeasibilityResult {
  status: FieldFeasibilityLevel;
  score: number;
  confidence: number;
  holding_difficulty: PotentialLevel;
  holding_breakdown?: HoldingBreakdown | null;
  fouling_transport_potential: PotentialLevel;
  turbidity_potential: PotentialLevel;
  rip_current_potential: PotentialLevel;
  fouling_evidence_count: number;
  turbidity_evidence_count: number;
  antecedent_window_hours: 48;
  reasons_ar: string[];
  limitations_ar: string[];
  is_direct_observation: false;
}

export interface HourDecision {
  time: string;
  safety: DecisionLevel;
  opportunity_score: number;
  confidence: ConfidenceResult;
  field_feasibility: FieldFeasibilityResult;
  factors: Factor[];
  forecast: ForecastConditions;
  derived: DerivedConditions;
}

export interface DecisionWindow {
  start: string;
  end: string;
  safety: DecisionLevel;
  field_feasibility: FieldFeasibilityLevel;
  field_score: number;
  opportunity_score: number;
  confidence_score: number;
  headline_ar: string;
  key_factors_ar: string[];
}

export interface TideEvent {
  time: string;
  kind: "high" | "low";
  level_msl_m: number;
  disclaimer_ar: string;
}

export interface SourceMetadata {
  provider: string;
  product: string;
  data_kind: "model_forecast" | "direct_observation" | "remote_sensing_estimate" | "user_supplied" | "synthetic_test";
  variables: string[];
  horizontal_resolution_km: number | null;
  retrieved_at: string;
  limitations_ar: string[];
}

export interface WeatherStationObservation {
  provider: string;
  station_id: string;
  station_name: string;
  station_latitude: number;
  station_longitude: number;
  station_elevation_m: number | null;
  observed_at: string;
  retrieved_at: string;
  distance_to_spot_km: number;
  wind_speed_kmh: number | null;
  wind_gust_kmh: number | null;
  wind_direction_deg: number | null;
  air_temperature_c: number | null;
  dew_point_c: number | null;
  pressure_hpa: number | null;
  pressure_kind: "sea_level_pressure" | "altimeter_setting" | null;
  visibility_m: number | null;
  visibility_is_lower_bound: boolean;
  weather_text: string | null;
  cloud_cover_code: string | null;
  raw_report: string;
  quality_control_flag: number | null;
  is_direct_observation: true;
  is_spot_observation: false;
}

export interface CoastalWaterContext {
  availability: "available" | "unavailable";
  provider: "Copernicus Marine Service";
  product_id: "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205";
  dataset_id: "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107";
  data_kind: "remote_sensing_estimate";
  sample_strategy: "fixed_1000m_seaward_axis";
  sample_latitude: number;
  sample_longitude: number;
  sample_distance_from_spot_m: number;
  pixel_latitude: number | null;
  pixel_longitude: number | null;
  pixel_distance_from_spot_m: number | null;
  pixel_distance_from_sample_m: number | null;
  spatial_resolution_m: 100;
  valid_time: string | null;
  retrieved_at: string;
  age_hours: number | null;
  search_days: number;
  turbidity_fnu: number | null;
  turbidity_unit: "FNU";
  suspended_particulate_matter_g_m3: number | null;
  suspended_particulate_matter_unit: "g/m³";
  chlorophyll_a_mg_m3: number | null;
  chlorophyll_a_unit: "mg/m³";
  sea_surface_temperature_c: number | null;
  reason_ar: string;
  affects_final_decision: false;
  is_direct_observation: false;
  is_spot_observation: false;
  is_forecast: false;
}

export interface ObservationComparison {
  status: ObservationMatchStatus;
  compared_forecast_time: string | null;
  observation_age_minutes: number | null;
  station_distance_km: number | null;
  wind_speed_difference_kmh: number | null;
  wind_direction_difference_deg: number | null;
  temperature_difference_c: number | null;
  pressure_difference_hpa: number | null;
  affects_confidence: boolean;
  reasons_ar: string[];
}

export interface FactorCoverageSummary {
  catalog_version: string;
  matrix_version: string;
  source_claimed_total: number;
  audited_total: number;
  automated_decision: number;
  automated_context: number;
  proxy_requires_field_check: number;
  field_or_external_required: number;
  excluded_unsupported: number;
  note_ar: string;
}

export type FactorAssessmentStatus = "decision" | "context" | "proxy" | "unknown" | "excluded";

export interface FactorAssessment {
  matrix_id: string;
  chapter_ar: string;
  title_ar: string;
  status: FactorAssessmentStatus;
  decision_axis: string;
  value_ar: string;
  evidence_variables: string[];
  rationale_ar: string;
  affects_final_decision: boolean;
}

export type SpeciesAxisKey =
  | "seasonal"
  | "habitat"
  | "surf_approach"
  | "feeding_window"
  | "prey_evidence";

export type SpeciesAxisStatus = "favorable" | "neutral" | "unfavorable" | "unknown";

export type SpeciesAxisBasis = "expert_prior" | "model_forecast" | "spot_profile" | "unknown";

export interface SpeciesAxisValue {
  axis: SpeciesAxisKey;
  status: SpeciesAxisStatus;
  label_ar: string;
  evidence_ar: string[];
  basis: SpeciesAxisBasis;
  confidence: number;
}

export interface SpeciesAxes {
  target_species: string;
  label_ar: string;
  axes: SpeciesAxisValue[];
  unknown_axes: string[];
  confidence: number;
  notes_ar: string[];
  species_matches?: SpeciesMatch[];
  sources_ar?: string[];
  sea_state_ar?: string | null;
}

export type ActivityPeriodKey = "dawn" | "morning" | "midday" | "afternoon" | "dusk" | "night";

export interface PeriodActivity {
  key: ActivityPeriodKey;
  label_ar: string;
  range_ar: string;
  score: number | null;
  peak_hour_ar: string | null;
  top_factor_ar: string | null;
}

export interface HourActivity {
  time: string;
  score: number;
  is_twilight: boolean;
  is_night: boolean;
}

export interface SpeciesActivity {
  species: string;
  label_ar: string;
  basis_ar: string[];
  periods: PeriodActivity[];
  hourly: HourActivity[];
  is_probability: false;
}

export type SpeciesAvailability = "strong" | "medium" | "weak" | "unavailable" | "unknown";
export type SpeciesThermal = "preferred" | "tolerated" | "outside" | "unknown";

export interface SpeciesMatch {
  species: string;
  label_ar: string;
  availability: SpeciesAvailability;
  thermal: SpeciesThermal;
  habitat_match: boolean | null;
  status: SpeciesAxisStatus;
  reasons_ar: string[];
  sources_ar?: string[];
  sea_state_ar?: string;
  sea_state_preference_ar?: string;
  sea_state_fit?: "favorable" | "neutral" | "unknown";
}

export interface SpotCandidate {
  spot_id: string;
  name_ar: string;
  location: Coordinates;
  spot: SpotProfile;
}

export interface RankSpotsRequest {
  target_date: string;
  angler: AnglerProfile;
  spots: SpotCandidate[];
  field_reports?: FieldReport[];
  test_cast?: TestCast | null;
  official_warning?: OfficialWarning | null;
}

export interface RankedSpot {
  spot_id: string;
  name_ar: string;
  decision: BinaryDecision;
  decision_reason_code: DecisionReasonCode;
  force_majeure_kind: ForceMajeureKind;
  best_window_start: string | null;
  best_window_end: string | null;
  opportunity_score: number;
  field_status: FieldFeasibilityLevel;
  holding_difficulty: PotentialLevel;
  fouling_level: number | null;
  fouling_force_majeure: boolean;
  spring_classification: string | null;
  spring_folk_label: string | null;
  spring_gabes_zone: boolean;
  species_label_ar: string | null;
  species_axes_summary: string[];
  species_confidence: number | null;
  summary_ar: string;
  key_factors_ar: string[];
  error_ar: string | null;
}

export interface RankSpotsResponse {
  target_date: string;
  generated_at: string;
  ranked: RankedSpot[];
  notes_ar: string[];
}

export interface DecisionResponse {
  schema_version: "3.9";
  engine_version: string;
  decision: BinaryDecision;
  decision_reason_code: DecisionReasonCode;
  decision_label_ar: string;
  summary_ar: string;
  opportunity_score: number;
  score_is_success_probability: false;
  confidence: ConfidenceResult;
  field_feasibility: FieldFeasibilityResult;
  gear_recommendation?: GearRecommendation | null;
  fouling_evidence?: FoulingEvidence | null;
  trip_ruin_factors?: TripRuinFactor[];
  spring_neap?: SpringNeap | null;
  species_axes?: SpeciesAxes | null;
  species_activity?: SpeciesActivity[];
  force_majeure_kind?: ForceMajeureKind;
  sunrise: string | null;
  sunset: string | null;
  recommended_windows: DecisionWindow[];
  avoid_windows: DecisionWindow[];
  tide_events: TideEvent[];
  hourly: HourDecision[];
  antecedent_hours: NormalizedForecastHour[];
  sources: SourceMetadata[];
  current_weather_observation: WeatherStationObservation | null;
  coastal_water_context: CoastalWaterContext | null;
  observation_comparison: ObservationComparison;
  factor_coverage: FactorCoverageSummary;
  factor_assessments: FactorAssessment[];
  limitations_ar: string[];
  generated_at: string;
}

export interface GeminiNarrative {
  executive_summary_ar: string;
  timing_and_water_ar: string[];
  temporal_analysis_ar: string[];
  factor_interactions_ar: string[];
  field_tactics_ar: string[];
  unknowns_ar: string[];
}

export interface GeminiReportResponse {
  narrative: GeminiNarrative;
  report_text: string;
  metadata: {
    generated_by: "google_gemini";
    model: string;
    prompt_version: string;
    template_version: string;
    generated_at: string;
    input_sha256: string;
    decision_was_modified: false;
    numbers_are_server_rendered: true;
  };
}

export interface GeminiKeyVerificationResponse {
  valid: true;
  provider: "Google Gemini";
  model: string;
  message_ar: string;
}

export interface SpotPreset {
  id: string;
  name: string;
  governorate: string;
  latitude: number;
  longitude: number;
  orientation: number;
  shoreType: ShoreType;
  note: string;
}
