from enum import StrEnum


class DecisionLevel(StrEnum):
    GO = "go"
    CAUTION = "caution"
    NO_GO = "no_go"
    UNKNOWN = "unknown"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FactorImpact(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    SAFETY = "safety"
    DATA_GAP = "data_gap"


class FactorBasis(StrEnum):
    MODEL_FORECAST = "model_forecast"
    DIRECT_OBSERVATION = "direct_observation"
    REMOTE_SENSING_ESTIMATE = "remote_sensing_estimate"
    DERIVED_FORECAST = "derived_forecast"
    SPOT_PROFILE = "spot_profile"
    EXPERT_PRIOR = "expert_prior"


class RuleNature(StrEnum):
    PHYSICAL_DERIVATION = "physical_derivation"
    SAFETY_POLICY = "safety_policy"
    OPERATIONAL_PROXY = "operational_proxy"
    EXPERT_PRIOR = "expert_prior"
    DATA_QUALITY = "data_quality"


class CatalogStatus(StrEnum):
    AUTOMATED_DECISION = "automated_decision"
    AUTOMATED_CONTEXT = "automated_context"
    PROXY_REQUIRES_FIELD_CHECK = "proxy_requires_field_check"
    FIELD_OR_EXTERNAL_REQUIRED = "field_or_external_required"
    EXCLUDED_UNSUPPORTED = "excluded_unsupported"


class FactorAssessmentStatus(StrEnum):
    DECISION = "decision"
    CONTEXT = "context"
    PROXY = "proxy"
    UNKNOWN = "unknown"
    EXCLUDED = "excluded"


class SourceDataKind(StrEnum):
    MODEL_FORECAST = "model_forecast"
    DIRECT_OBSERVATION = "direct_observation"
    REMOTE_SENSING_ESTIMATE = "remote_sensing_estimate"
    USER_SUPPLIED = "user_supplied"
    SYNTHETIC_TEST = "synthetic_test"


class ObservationMatchStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    STALE = "stale"
    DISTANT = "distant"
    LIMITED = "limited"
    CONSISTENT = "consistent"
    DIVERGENT = "divergent"


class RiskSeverity(StrEnum):
    INFO = "info"
    CAUTION = "caution"
    CRITICAL = "critical"


class ShoreType(StrEnum):
    SANDY = "sandy"
    ROCKY = "rocky"
    CLIFF = "cliff"
    JETTY = "jetty"


class Exposure(StrEnum):
    OPEN = "open"
    PARTLY_SHELTERED = "partly_sheltered"
    SHELTERED = "sheltered"


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class OrientationSource(StrEnum):
    SURVEYED = "surveyed"
    MANUAL = "manual"
    MAP = "map"
    OVERPASS = "overpass"
    ESTIMATED = "estimated"


class DecisionReasonCode(StrEnum):
    SAFE_WINDOW = "safe_window"
    SAFETY_HAZARD = "safety_hazard"
    FIELD_INFEASIBLE = "field_infeasible"
    CRITICAL_DATA_MISSING = "critical_data_missing"
    CONSERVATIVE_UNCERTAINTY = "conservative_uncertainty"
    FOULING_CONFIRMED = "fouling_confirmed"
    OFFICIAL_WARNING = "official_warning"
    TRIP_RUIN_CONFIRMED = "trip_ruin_confirmed"


class TargetSpecies(StrEnum):
    GENERAL = "general"
    EUROPEAN_SEABASS = "european_seabass"
    GILTHEAD_SEABREAM = "gilthead_seabream"
    WHITE_SEABREAM = "white_seabream"
    STRIPED_SEABREAM = "striped_seabream"


class WindRelation(StrEnum):
    ONSHORE = "onshore"
    OFFSHORE = "offshore"
    CROSS_ONSHORE = "cross_onshore"
    ALONGSHORE = "alongshore"
    CROSS_OFFSHORE = "cross_offshore"
    UNKNOWN = "unknown"


class WaveIncidence(StrEnum):
    DIRECT = "direct"
    OBLIQUE = "oblique"
    ALONGSHORE = "alongshore"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class TideState(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    SLACK = "slack"
    UNKNOWN = "unknown"


class FieldFeasibilityLevel(StrEnum):
    FAVORABLE = "favorable"
    WORKABLE = "workable"
    DIFFICULT = "difficult"
    UNKNOWN = "unknown"


class PotentialLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class ForceMajeureKind(StrEnum):
    """The single hard blocker behind a NO_GO, or none for a GO.

    Fouling and access_legal are reserved for the evidence ladder (phase 4) and the
    official INM bulletin (phase 7); the engine cannot emit them yet.
    """

    NONE = "none"
    SAFETY = "safety"
    HOLDING = "holding"
    FOULING = "fouling"
    ACCESS_LEGAL = "access_legal"
    TRIP_RUIN = "trip_ruin"
    DATA = "data"


class LeadShape(StrEnum):
    STREAMLINED = "streamlined"
    PYRAMID = "pyramid"
    GRAPNEL = "grapnel"
    BREAKAWAY_GRAPNEL = "breakaway_grapnel"
    ROCKY = "rocky"


class MontageClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
