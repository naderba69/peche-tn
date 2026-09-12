from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from itertools import pairwise

from .enums import (
    CatalogStatus,
    ConfidenceBand,
    DecisionLevel,
    DecisionReasonCode,
    FactorAssessmentStatus,
    FactorBasis,
    FactorImpact,
    FieldFeasibilityLevel,
    ForceMajeureKind,
    ObservationMatchStatus,
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
from .factor_catalog import MATRIX_FACTORS, factor_catalog_summary
from .gear import recommend_gear
from .labels import DECISION_LABEL_AR, TIDE_STATE_AR, WAVE_INCIDENCE_AR, WIND_RELATION_AR
from .math import (
    alongshore_wave_proxy,
    alongshore_wave_signed_proxy,
    circular_difference_deg,
    classify_spring_neap,
    classify_wave,
    classify_wind,
    daily_sea_level_ranges,
    deep_water_wave_steepness,
    deep_water_wavelength_m,
    detect_tide_events,
    gust_factor,
    in_gabes_zone,
    incoming_direction_components,
    incoming_direction_signed_components,
    kmh_to_mps,
    knots_to_kmh,
    near_bottom_orbital_velocity_ms,
    neutral_wind_drag_coefficient,
    project_current,
    sea_level_rates,
    secondary_wave_energy_share,
    tide_states,
    tunisian_zone,
    wave_energy_proxy,
    weighted_directional_coherence,
    wind_stress_signed_components,
)
from .models import (
    ConfidenceResult,
    DecisionResponse,
    DecisionWindow,
    DerivedConditions,
    Factor,
    FactorAssessment,
    FieldFeasibilityResult,
    FieldReport,
    ForecastConditions,
    ForecastDataset,
    ForecastHour,
    FoulingEvidence,
    GearRecommendation,
    HoldingBreakdown,
    HourActivity,
    HourDecision,
    ObservationComparison,
    PeriodActivity,
    RankedSpot,
    RankSpotsResponse,
    SpeciesActivity,
    SpeciesAxes,
    SpeciesAxisValue,
    SpeciesMatch,
    SpotCandidate,
    SpringNeap,
    TripRuinFactor,
)
from .policy import CRITICAL_FIELDS, THUNDERSTORM_CODES, safety_thresholds
from .species import (
    MONTHS_AR,
    PRESENCE_LABELS_AR,
    SEA_STATE_LABELS_AR,
    SOURCE_REGISTRY,
    SPECIES_PROFILES,
    ZONE_LABELS_AR,
    SpeciesProfile,
    classify_sea_state,
    sea_state_fit_for,
)

ENGINE_VERSION = "1.6.8"

# --------------------------------------------------------------------------- #
# Trip-ruining factor thresholds (v1.9.8, evidence-gated; see SOURCES-AUDIT §3.6)
# Operational, reviewable thresholds — never in-situ measurements:
#   - chlorophyll-a bloom levels (mg/m³) from the CMEMS ocean-colour NRT product
#     (Sentinel-2/3-derived daily mosaic); dense bloom + onshore transport is the
#     satellite force-majeure path for the fouling ladder.
#   - turbidity (FNU) caution bands from the same product; turbidity never blocks
#     alone (turbid water does not make casting impossible).
#   - marine heatwave: SST anomaly vs a reviewable coastal monthly climatology.
# --------------------------------------------------------------------------- #
_CHL_BLOOM_MODERATE_MG_M3 = 5.0
_CHL_BLOOM_DENSE_MG_M3 = 10.0
_TUR_MODERATE_FNU = 2.0
_TUR_HIGH_FNU = 5.0
_MHW_MODERATE_ANOMALY_C = 2.0
_MHW_STRONG_ANOMALY_C = 3.0
# Reviewable monthly reference SST (°C) for Tunisian coastal waters.
_COASTAL_SST_CLIMATOLOGY_C = (
    14.5, 14.0, 14.8, 16.2, 18.5, 21.8, 24.8, 26.4, 25.6, 22.8, 19.2, 16.2,
)


class InsufficientDataError(ValueError):
    """Raised when no usable forecast hours exist for the requested local date."""


_FIELD_LABELS_AR: dict[str, str] = {
    "wind_speed_kmh": "سرعة الرياح",
    "wind_gust_kmh": "هبّات الرياح",
    "wind_direction_deg": "اتجاه الرياح",
    "wave_height_m": "ارتفاع الموج",
    "wave_period_s": "فترة الموج",
    "wave_direction_deg": "اتجاه الموج",
    "weather_code": "حالة الطقس",
    "visibility_m": "مدى الرؤية",
    "sea_level_height_msl_m": "مستوى البحر",
    "ocean_current_velocity_kmh": "سرعة التيار البحري",
    "sea_surface_temperature_c": "حرارة سطح البحر",
    "pressure_msl_hpa": "الضغط الجوي",
}

_COMPLETENESS_WEIGHTS: dict[str, float] = {
    "wave_height_m": 0.17,
    "wave_period_s": 0.08,
    "wave_direction_deg": 0.07,
    "wind_speed_kmh": 0.16,
    "wind_gust_kmh": 0.13,
    "wind_direction_deg": 0.08,
    "weather_code": 0.08,
    "visibility_m": 0.05,
    "ocean_current_velocity_kmh": 0.05,
    "sea_level_height_msl_m": 0.05,
    "sea_surface_temperature_c": 0.03,
    "pressure_msl_hpa": 0.03,
    "precipitation_mm": 0.02,
}

_ORIENTATION_QUALITY = {
    "surveyed": 0.95,
    "manual": 0.85,
    "map": 0.70,
    "overpass": 0.78,
    "estimated": 0.55,
}

_SHORE_TYPE_LABELS_AR = {
    "sandy": "شاطئ رملي",
    "rocky": "وقوف صخري",
    "cliff": "حافة أو جرف",
    "jetty": "رصيف أو حاجز بحري",
}

_ORIENTATION_SOURCE_LABELS_AR = {
    "surveyed": "مقاس ميدانياً",
    "manual": "مدخل يدوياً",
    "map": "مستخرج من الخريطة",
    "overpass": "محسوب من OpenStreetMap Overpass",
    "estimated": "تقدير أولي",
}

_FIELD_FEASIBILITY_RANK = {
    FieldFeasibilityLevel.UNKNOWN: 0,
    FieldFeasibilityLevel.DIFFICULT: 1,
    FieldFeasibilityLevel.WORKABLE: 2,
    FieldFeasibilityLevel.FAVORABLE: 3,
}


def _time_range_ar(start: datetime, end: datetime) -> str:
    next_day = " من اليوم التالي" if end.date() > start.date() else ""
    return f"{start:%H:%M} إلى {end:%H:%M}{next_day}"


# --------------------------------------------------------------------------- #
# Reporting-only daily species-activity indicator (v1.9.9). Six presentation
# buckets over the local day; the hourly scores behind them already carry the
# twilight/night feeding-window priors from the model sunrise/sunset.
# --------------------------------------------------------------------------- #
_ACTIVITY_PERIODS: tuple[tuple[str, str, str, int, int], ...] = (
    ("dawn", "الفجر", "04:00-06:59", 4, 7),
    ("morning", "الصباح", "07:00-10:59", 7, 11),
    ("midday", "الظهيرة", "11:00-13:59", 11, 14),
    ("afternoon", "العصر", "14:00-17:59", 14, 18),
    ("dusk", "الغسق", "18:00-20:59", 18, 21),
    ("night", "الليل", "21:00-03:59", 21, 4),
)


def _in_activity_period(hour_of_day: int, from_hour: int, to_hour: int) -> bool:
    if from_hour < to_hour:
        return from_hour <= hour_of_day < to_hour
    return hour_of_day >= from_hour or hour_of_day < to_hour


def _species_hour_activity(
    profile: SpeciesProfile,
    hour: HourDecision,
    *,
    sst: float | None,
    sea_state: str,
    zone: str,
    month: int,
    shore_type: ShoreType,
) -> tuple[int, list[tuple[str, int]]]:
    """Relative activity score (0-100) for one species at one hour.

    Base 50 plus the same documented, low-weight priors used elsewhere in the
    engine: feeding window, water temperature, seasonal availability from
    published studies (dominant), shore match, and sea-state fit. Never a catch
    probability and never fed into the binary decision (D10/D11).
    """
    score = 50
    contributions: list[tuple[str, int]] = []
    if hour.derived.is_twilight and profile.twilight_bonus:
        score += profile.twilight_bonus
        contributions.append(("نافذة الغسق", profile.twilight_bonus))
    elif hour.derived.is_night and profile.night_bonus:
        score += profile.night_bonus
        contributions.append(("نافذة الليل", profile.night_bonus))
    if profile.preferred_sst_c is not None and sst is not None:
        pref_low, pref_high = profile.preferred_sst_c
        tol_low, tol_high = profile.tolerated_sst_c or (pref_low, pref_high)
        if pref_low <= sst <= pref_high:
            score += 6
            contributions.append(("حرارة الماء مفضلة", 6))
        elif not tol_low <= sst <= tol_high:
            score -= 8
            contributions.append(("حرارة الماء بعيدة", -8))
    if profile.preferred_shores:
        if shore_type in profile.preferred_shores:
            score += 3
            contributions.append(("القاع ملائم", 3))
        else:
            score -= 3
            contributions.append(("القاع خارج التفضيل", -3))
    presence = profile.monthly_presence(zone, month)
    if presence is not None:
        delta = {3: 15, 2: 6, 1: -6, 0: -20}[presence]
        score += delta
        contributions.append((f"التوفر الموسمي ({PRESENCE_LABELS_AR[presence]})", delta))
    if profile.sea_state_preference is not None and sea_state != "unknown":
        fit = sea_state_fit_for(profile.sea_state_preference, sea_state)
        if fit == "favorable":
            score += 5
            contributions.append(("حالة البحر مناسبة", 5))
    return max(0, min(100, score)), contributions


def _activity_top_factor(contributions: list[tuple[str, int]]) -> str:
    if not contributions:
        return "توازن بلا أفضلية قوية"
    label, _delta = max(contributions, key=lambda item: abs(item[1]))
    return label


def _activity_periods(entries: list[tuple[HourActivity, str]]) -> list[PeriodActivity]:
    periods: list[PeriodActivity] = []
    for key, label, range_ar, from_hour, to_hour in _ACTIVITY_PERIODS:
        members = [
            (item, top)
            for item, top in entries
            if _in_activity_period(item.time.hour, from_hour, to_hour)
        ]
        if not members:
            periods.append(
                PeriodActivity(key=key, label_ar=label, range_ar=range_ar, score=None)
            )
            continue
        average_score = round(sum(item.score for item, _top in members) / len(members))
        peak_item, peak_top = max(members, key=lambda pair: pair[0].score)
        periods.append(
            PeriodActivity(
                key=key,
                label_ar=label,
                range_ar=range_ar,
                score=average_score,
                peak_hour_ar=peak_item.time.strftime("%H:%M"),
                top_factor_ar=peak_top,
            )
        )
    return periods


def _activity_basis_ar(profile: SpeciesProfile) -> list[str]:
    lines = [
        "مؤشر نشاط نسبي (0-100) يبدأ من 50 ويجمع أوزاناً أولية موثقة: نافذة التغذية (غسق/ليل)، حرارة الماء، التوفر الموسمي من دراسات منشورة (الأثقل)، توافق القاع، وحالة البحر.",
    ]
    if profile.label_ar == "صيد عام":
        lines.append("صيد عام بلا ملف موسمي أو حراري أو قاع: يدخل في مؤشره بونص الغسق والليل فقط.")
    lines.append(
        "هذا مؤشر ترتيب نسبي وليس احتمالاً إحصائياً لوجود السمك أو وعداً بالمصيد؛ تحويله إلى نسبة يتطلب سجل مصيد تونسي معايراً يشمل الحصص الصفرية."
    )
    return lines


class DecisionEngine:
    """Safety-first, deterministic and explainable surfcasting guidance.

    The engine never calls an LLM. The same input always produces the same decision.
    Safety gates and fishing-opportunity ranking are intentionally separate.
    """

    def evaluate(self, dataset: ForecastDataset) -> DecisionResponse:
        all_hours = sorted(dataset.hours, key=lambda item: item.time)
        actionable_from = _actionable_cutoff(dataset)
        target_hours = [
            item
            for item in all_hours
            if item.time.date() == dataset.target_date and item.time >= actionable_from
        ]
        if len(target_hours) < dataset.angler.session_hours:
            raise InsufficientDataError(
                "لا توجد ساعات كافية في التاريخ المطلوب لبناء نافذة صيد موثوقة."
            )
        antecedent_start = target_hours[0].time - timedelta(hours=72)
        antecedent_hours = [
            item for item in all_hours if antecedent_start <= item.time < target_hours[0].time
        ][-72:]

        tide_by_time = {
            item.time: state
            for item, state in zip(
                all_hours, tide_states(all_hours, dataset.target_date), strict=True
            )
        }
        pressure_by_time = {
            item.time: item.pressure_msl_hpa
            for item in all_hours
            if item.pressure_msl_hpa is not None
        }
        sst_by_time = {
            item.time: item.sea_surface_temperature_c
            for item in all_hours
            if item.sea_surface_temperature_c is not None
        }
        target_levels = [
            item.sea_level_height_msl_m
            for item in all_hours
            if item.time.date() == dataset.target_date and item.sea_level_height_msl_m is not None
        ]
        target_level_range = max(target_levels) - min(target_levels) if target_levels else None
        observation_comparison = _compare_current_weather_observation(dataset, all_hours)

        hourly = [
            self._evaluate_hour(
                dataset,
                all_hours,
                item,
                tide_by_time[item.time],
                pressure_by_time,
                sst_by_time,
                target_level_range,
                observation_comparison,
            )
            for item in target_hours
        ]
        recommended = self._recommended_windows(hourly, dataset.angler.session_hours)
        avoid = self._avoid_windows(hourly)
        opportunity = (
            recommended[0].opportunity_score
            if recommended
            else max(item.opportunity_score for item in hourly)
        )
        confidence = self._overall_confidence(hourly, recommended)
        field_feasibility = self._overall_field_feasibility(hourly, recommended)
        decision, decision_reason_code = self._day_decision(
            hourly,
            recommended,
            field_feasibility,
            confidence,
        )
        fouling_evidence = self._fouling_evidence(dataset, field_feasibility)
        trip_ruin_factors = self._trip_ruin_factors(dataset, field_feasibility, fouling_evidence)
        spring_neap = self._spring_neap(dataset, all_hours)
        species_axes = self._species_axes(dataset, spring_neap, field_feasibility, recommended)
        species_activity = self._species_activity(dataset, hourly)
        if dataset.official_warning is not None:
            # A valid official warning (INM bulletin, D14) is a hard no-go above
            # every local threshold; safety stays the top authority.
            decision = DecisionLevel.NO_GO
            decision_reason_code = DecisionReasonCode.OFFICIAL_WARNING
        elif decision == DecisionLevel.GO and fouling_evidence.is_force_majeure:
            decision = DecisionLevel.NO_GO
            decision_reason_code = DecisionReasonCode.FOULING_CONFIRMED
        elif decision == DecisionLevel.GO and any(
            factor.is_force_majeure and factor.factor in {"jellyfish", "storm_debris", "turbidity"}
            for factor in trip_ruin_factors
        ):
            decision = DecisionLevel.NO_GO
            decision_reason_code = DecisionReasonCode.TRIP_RUIN_CONFIRMED
        if decision == DecisionLevel.NO_GO:
            recommended = []
        force_majeure_kind = _force_majeure_for(decision_reason_code)
        gear = self._gear_recommendation(hourly, recommended, field_feasibility)
        summary = self._summary(
            decision,
            recommended,
            hourly,
            opportunity,
            confidence.score,
            field_feasibility,
            decision_reason_code,
        )

        limitations = [
            "درجة الفرصة مؤشر مقارن من صفر إلى مائة وليست احتمالاً إحصائياً لصيد سمكة.",
            "نماذج البحر والتيار والمدّ المجانية تقارب دقتها الأفقية 8 كم؛ دقتها محدودة جداً داخل الخلجان وقرب الشاطئ.",
            "المحرك يرى إشارة ساتلية للازدهار/العكارة على بعد ~1كم من الشاطئ (Copernicus)، لكنه لا يرى الكسرة المحلية أو الصوفة الفعلية عند الحافة أو الصخور المغمورة؛ عاين المكان قبل نصب العتاد.",
            "مؤشرات جرّ الخط ونقل الأعشاب أو الحطام والعكارة والتيار الساحبي فحص احتمالي منخفض الثقة، وليست رصداً لحالة البقعة أو قياس NTU.",
            "احتمالا الصوفة والعكارة النموذجيان تنبيهان للفحص ولا يمنعان وحدهما نافذة آمنة بلا تأكيد ميداني.",
            "حدود السلامة سياسة محافظة قابلة للمعايرة وليست بديلاً عن نشرات الحماية المدنية والحرس البحري أو تقديرك الميداني.",
            "كل القيم الجوية والبحرية الساعية القادمة من Open-Meteo توقعات نموذجية؛ رصد METAR منفصل وفي محطة مطار لا داخل البقعة.",
            "تفضيلات الأنواع أوزان أولية منخفضة التأثير، وتحتاج إلى معايرة بسجل مصيد تونسي محلي.",
            "دُققت 63 عاملاً من المصفوفة، لكن التسجيل لا يعني التنقيط: غير المتاح يبقى Unknown وغير المدعوم مستبعد.",
        ]
        for source in dataset.sources:
            limitations.extend(source.limitations_ar)
        factor_assessments = self._factor_assessments(
            dataset, hourly, field_feasibility, decision, decision_reason_code
        )

        return DecisionResponse(
            engine_version=ENGINE_VERSION,
            decision=decision,
            decision_reason_code=decision_reason_code,
            decision_label_ar=DECISION_LABEL_AR[decision],
            summary_ar=summary,
            opportunity_score=opportunity,
            confidence=confidence,
            field_feasibility=field_feasibility,
            gear_recommendation=gear,
            fouling_evidence=fouling_evidence,
            trip_ruin_factors=trip_ruin_factors,
            spring_neap=spring_neap,
            species_axes=species_axes,
            species_activity=species_activity,
            force_majeure_kind=force_majeure_kind,
            sunrise=dataset.sunrise,
            sunset=dataset.sunset,
            recommended_windows=recommended,
            avoid_windows=avoid,
            tide_events=detect_tide_events(all_hours, dataset.target_date),
            hourly=hourly,
            antecedent_hours=antecedent_hours,
            sources=dataset.sources,
            current_weather_observation=dataset.current_weather_observation,
            coastal_water_context=dataset.coastal_water_context,
            observation_comparison=observation_comparison,
            factor_coverage=factor_catalog_summary(),
            factor_assessments=factor_assessments,
            limitations_ar=_unique(limitations),
            generated_at=datetime.now(dataset.fetched_at.tzinfo),
        )

    def rank_spots(
        self,
        datasets: list[tuple[SpotCandidate, ForecastDataset | None]],
        target_date: date,
    ) -> RankSpotsResponse:
        """Evaluate several spots and rank them best-to-weakest (D13).

        A spot whose dataset is None (fetch failed) or whose evaluation raises
        InsufficientDataError is kept last with an explanatory error instead of
        failing the whole sweep. The ranking is go/no-go first, then field
        feasibility, then the relative opportunity indicator (never a catch
        probability).
        """
        species_status_ar = {
            "favorable": "مناسب",
            "neutral": "محايد",
            "unfavorable": "غير مناسب",
            "unknown": "غير معروف",
        }

        def error_entry(candidate: SpotCandidate, message: str) -> RankedSpot:
            return RankedSpot(
                spot_id=candidate.spot_id,
                name_ar=candidate.name_ar,
                decision=DecisionLevel.NO_GO,
                decision_reason_code=DecisionReasonCode.CRITICAL_DATA_MISSING,
                force_majeure_kind=ForceMajeureKind.DATA,
                opportunity_score=0,
                field_status=FieldFeasibilityLevel.UNKNOWN,
                holding_difficulty=PotentialLevel.UNKNOWN,
                summary_ar="لا توجد بيانات كافية لهذه البقعة في التاريخ المطلوب.",
                error_ar=message,
            )

        ranked: list[RankedSpot] = []
        for candidate, dataset in datasets:
            if dataset is None:
                ranked.append(
                    error_entry(candidate, "تعذر جلب بيانات هذه البقعة من المزوّد.")
                )
                continue
            try:
                result = self.evaluate(dataset)
            except InsufficientDataError:
                ranked.append(
                    error_entry(candidate, "لا توجد ساعات كافية في التاريخ المطلوب.")
                )
                continue

            lead = result.recommended_windows[0] if result.recommended_windows else None
            spring = result.spring_neap
            species = result.species_axes
            fouling = result.fouling_evidence
            species_summary = (
                [
                    f"{axis.label_ar}: {species_status_ar[axis.status]}"
                    for axis in species.axes
                    if axis.status in {"favorable", "unfavorable"}
                ][:3]
                if species
                else []
            )
            ranked.append(
                RankedSpot(
                    spot_id=candidate.spot_id,
                    name_ar=candidate.name_ar,
                    decision=result.decision,
                    decision_reason_code=result.decision_reason_code,
                    force_majeure_kind=result.force_majeure_kind,
                    best_window_start=lead.start if lead else None,
                    best_window_end=lead.end if lead else None,
                    opportunity_score=result.opportunity_score,
                    field_status=result.field_feasibility.status,
                    holding_difficulty=result.field_feasibility.holding_difficulty,
                    fouling_level=fouling.level if fouling else None,
                    fouling_force_majeure=fouling.is_force_majeure if fouling else False,
                    spring_classification=spring.classification if spring else None,
                    spring_folk_label=spring.folk_label_ar if spring else None,
                    spring_gabes_zone=spring.gabes_zone if spring else False,
                    species_label_ar=species.label_ar if species else None,
                    species_axes_summary=species_summary,
                    species_confidence=species.confidence if species else None,
                    summary_ar=result.summary_ar,
                    key_factors_ar=lead.key_factors_ar[:4] if lead else [],
                )
            )

        ranked.sort(
            key=lambda item: (
                1 if item.decision == DecisionLevel.GO else 0,
                _FIELD_FEASIBILITY_RANK.get(item.field_status, 0),
                item.opportunity_score,
            ),
            reverse=True,
        )
        timezone = next(
            (dataset.fetched_at.tzinfo for _, dataset in datasets if dataset is not None),
            None,
        )
        return RankSpotsResponse(
            target_date=target_date,
            generated_at=datetime.now(timezone),
            ranked=ranked,
            notes_ar=[
                "الترتيب من الأحسن إلى الأضعف: القرار الثنائي أولاً ثم قابلية التنفيذ ثم مؤشر الفرصة النسبي.",
                "مؤشر الفرصة ترتيب نسبي وليس احتمال مصيد؛ ومعطيات كل بقعة نماذج أفقية نحو 8 كم وتحتاج معاينة ميدانية قبل القرار.",
            ],
        )

    def _evaluate_hour(
        self,
        dataset: ForecastDataset,
        all_hours: list[ForecastHour],
        hour: ForecastHour,
        tide: tuple[TideState, float | None, float | None],
        pressure_by_time: dict[datetime, float],
        sst_by_time: dict[datetime, float],
        target_level_range: float | None,
        observation_comparison: ObservationComparison,
    ) -> HourDecision:
        wind_relation, wind_angle = classify_wind(
            hour.wind_direction_deg, dataset.spot.seaward_orientation_deg
        )
        wave_incidence, wave_angle = classify_wave(
            hour.wave_direction_deg, dataset.spot.seaward_orientation_deg
        )
        wind_shoreward, wind_alongshore = incoming_direction_components(
            hour.wind_speed_kmh,
            hour.wind_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        _, wind_alongshore_signed = incoming_direction_signed_components(
            hour.wind_speed_kmh,
            hour.wind_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        wave_shoreward, wave_alongshore = incoming_direction_components(
            1.0 if hour.wave_direction_deg is not None else None,
            hour.wave_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        _, wave_alongshore_signed = incoming_direction_signed_components(
            1.0 if hour.wave_direction_deg is not None else None,
            hour.wave_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        stress, stress_shoreward, stress_alongshore = wind_stress_signed_components(
            hour.wind_speed_kmh,
            hour.wind_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        drag_coefficient = neutral_wind_drag_coefficient(
            kmh_to_mps(hour.wind_speed_kmh) if hour.wind_speed_kmh is not None else None
        )
        wavelength = deep_water_wavelength_m(hour.wave_period_s)
        steepness = deep_water_wave_steepness(hour.wave_height_m, hour.wave_period_s)
        energy = wave_energy_proxy(hour.wave_height_m, hour.wave_period_s)
        longshore = alongshore_wave_proxy(
            hour.wave_height_m,
            hour.wave_period_s,
            hour.wave_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        longshore_signed = alongshore_wave_signed_proxy(
            hour.wave_height_m,
            hour.wave_period_s,
            hour.wave_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        current_along, current_cross = project_current(
            hour.ocean_current_velocity_kmh,
            hour.ocean_current_direction_deg,
            dataset.spot.seaward_orientation_deg,
        )
        previous_pressure_3h = pressure_by_time.get(hour.time - timedelta(hours=3))
        previous_pressure_24h = pressure_by_time.get(hour.time - timedelta(hours=24))
        pressure_change_3h = (
            hour.pressure_msl_hpa - previous_pressure_3h
            if hour.pressure_msl_hpa is not None and previous_pressure_3h is not None
            else None
        )
        pressure_change_24h = (
            hour.pressure_msl_hpa - previous_pressure_24h
            if hour.pressure_msl_hpa is not None and previous_pressure_24h is not None
            else None
        )
        previous_sst_24h = sst_by_time.get(hour.time - timedelta(hours=24))
        sst_change_24h = (
            hour.sea_surface_temperature_c - previous_sst_24h
            if hour.sea_surface_temperature_c is not None and previous_sst_24h is not None
            else None
        )
        is_twilight = _is_twilight(hour.time, dataset.sunrise, dataset.sunset)
        is_night = _is_night(hour.time, dataset.sunrise, dataset.sunset)
        history_72h = _trailing_hours(all_hours, hour.time, 72)
        history_48h = _trailing_hours(all_hours, hour.time, 48)
        history_24h = _trailing_hours(all_hours, hour.time, 24)
        history_12h = _trailing_hours(all_hours, hour.time, 12)
        history_6h = _trailing_hours(all_hours, hour.time, 6)
        rain_24h = _rain_total_mm(history_24h)
        rain_48h = _rain_total_mm(history_48h)
        rain_72h = _rain_total_mm(history_72h)
        max_wind_24h = _maximum(item.wind_speed_kmh for item in history_24h)
        max_wave_24h = _maximum(item.wave_height_m for item in history_24h)
        max_wave_48h = _maximum(item.wave_height_m for item in history_48h)
        max_wave_72h = _maximum(item.wave_height_m for item in history_72h)
        strong_wind_threshold_kmh = knots_to_kmh(25.0)
        strong_wind_hours_24h = sum(
            item.wind_speed_kmh is not None and item.wind_speed_kmh >= strong_wind_threshold_kmh
            for item in history_24h
        )
        direction_shift_6h = _max_consecutive_wind_shift_deg(history_6h)
        direction_coherence_6h, direction_data_hours_6h = weighted_directional_coherence(
            (item.wind_speed_kmh, item.wind_direction_deg) for item in history_6h
        )
        rain_data_hours = sum(item.precipitation_mm is not None for item in history_24h)
        rain_data_hours_48h = sum(item.precipitation_mm is not None for item in history_48h)
        wind_data_hours = sum(
            item.wind_speed_kmh is not None and item.wind_direction_deg is not None
            for item in history_12h
        )
        wind_data_hours_48h = sum(
            item.wind_speed_kmh is not None and item.wind_direction_deg is not None
            for item in history_48h
        )
        wave_energy_data_hours = sum(
            wave_energy_proxy(item.wave_height_m, item.wave_period_s) is not None
            for item in history_12h
        )
        wave_energy_data_hours_48h = sum(
            wave_energy_proxy(item.wave_height_m, item.wave_period_s) is not None
            for item in history_48h
        )
        current_data_hours_48h = sum(
            item.ocean_current_velocity_kmh is not None
            and item.ocean_current_direction_deg is not None
            for item in history_48h
        )
        onshore_fraction = _onshore_wind_fraction(
            history_12h,
            dataset.spot.seaward_orientation_deg,
        )
        onshore_fraction_48h = _onshore_wind_fraction(
            history_48h,
            dataset.spot.seaward_orientation_deg,
        )
        energetic_fraction = _energetic_wave_fraction(history_12h)
        energetic_fraction_48h = _energetic_wave_fraction(history_48h)
        wave_energy_integral_48h = _wave_energy_integral(history_48h)
        onshore_wind_impulse_48h = _onshore_wind_impulse(
            history_48h, dataset.spot.seaward_orientation_deg
        )
        onshore_wind_stress_impulse_48h = _onshore_wind_stress_impulse(
            history_48h, dataset.spot.seaward_orientation_deg
        )
        shoreward_current_impulse_48h = _shoreward_current_impulse(
            history_48h, dataset.spot.seaward_orientation_deg
        )
        strong_wave_hours_48h = sum(
            item.wave_height_m is not None and item.wave_height_m >= 1.0 for item in history_48h
        )
        component_angle = (
            circular_difference_deg(hour.wind_wave_direction_deg, hour.swell_direction_deg)
            if hour.wind_wave_direction_deg is not None and hour.swell_direction_deg is not None
            else None
        )
        component_secondary_share = secondary_wave_energy_share(
            hour.wind_wave_height_m, hour.swell_height_m
        )
        air_sea_temperature_difference = (
            hour.air_temperature_c - hour.sea_surface_temperature_c
            if hour.air_temperature_c is not None and hour.sea_surface_temperature_c is not None
            else None
        )
        dew_point_depression = (
            hour.air_temperature_c - hour.dew_point_c
            if hour.air_temperature_c is not None and hour.dew_point_c is not None
            else None
        )
        derived = DerivedConditions(
            wind_relation=wind_relation,
            wind_angle_deg=_rounded(wind_angle, 1),
            wind_shoreward_component_kmh=_rounded(wind_shoreward, 2),
            wind_alongshore_component_kmh=_rounded(wind_alongshore, 2),
            wind_alongshore_signed_component_kmh=_rounded(wind_alongshore_signed, 2),
            alongshore_positive_bearing_deg=(dataset.spot.seaward_orientation_deg + 90.0) % 360.0,
            wind_drag_coefficient=_rounded(drag_coefficient, 6),
            wind_stress_pa=_rounded(stress, 4),
            wind_stress_shoreward_pa=_rounded(stress_shoreward, 4),
            wind_stress_alongshore_pa=_rounded(stress_alongshore, 4),
            wave_incidence=wave_incidence,
            wave_angle_deg=_rounded(wave_angle, 1),
            wave_shoreward_alignment=_rounded(wave_shoreward, 3),
            wave_alongshore_alignment=_rounded(wave_alongshore, 3),
            wave_alongshore_signed_alignment=_rounded(wave_alongshore_signed, 3),
            deep_water_wavelength_m=_rounded(wavelength, 1),
            wave_steepness=_rounded(steepness, 4),
            wave_energy_proxy=_rounded(energy, 3),
            alongshore_wave_proxy=_rounded(longshore, 3),
            alongshore_wave_signed_proxy=_rounded(longshore_signed, 3),
            wave_component_angle_deg=_rounded(component_angle, 1),
            wave_component_secondary_energy_share=_rounded(component_secondary_share, 3),
            gust_factor=_rounded(gust_factor(hour.wind_speed_kmh, hour.wind_gust_kmh), 2),
            max_wind_direction_shift_6h_deg=_rounded(direction_shift_6h, 1),
            wind_direction_coherence_6h=_rounded(direction_coherence_6h, 3),
            wind_direction_data_hours_6h=min(6, direction_data_hours_6h),
            current_alongshore_kmh=_rounded(current_along, 2),
            current_cross_shore_kmh=_rounded(current_cross, 2),
            tide_state=tide[0],
            sea_level_rate_m_per_h=_rounded(tide[1], 3),
            tide_movement_index=_rounded(tide[2], 2),
            pressure_change_3h_hpa=_rounded(pressure_change_3h, 1),
            pressure_change_24h_hpa=_rounded(pressure_change_24h, 1),
            sea_surface_temperature_change_24h_c=_rounded(sst_change_24h, 1),
            max_wind_speed_24h_kmh=_rounded(max_wind_24h, 1),
            max_wave_height_24h_m=_rounded(max_wave_24h, 2),
            strong_wind_hours_24h=min(24, strong_wind_hours_24h),
            sea_level_range_target_day_m=_rounded(target_level_range, 3),
            rain_24h_mm=_rounded(rain_24h, 1),
            rain_48h_mm=_rounded(rain_48h, 1),
            rain_72h_mm=_rounded(rain_72h, 1),
            max_wave_height_48h_m=_rounded(max_wave_48h, 2),
            max_wave_height_72h_m=_rounded(max_wave_72h, 2),
            wave_energy_integral_48h=_rounded(wave_energy_integral_48h, 2),
            onshore_wind_impulse_48h_kmh_h=_rounded(onshore_wind_impulse_48h, 1),
            onshore_wind_stress_impulse_48h_pa_h=_rounded(onshore_wind_stress_impulse_48h, 3),
            shoreward_current_impulse_48h_kmh_h=_rounded(shoreward_current_impulse_48h, 2),
            strong_wave_hours_48h=min(48, strong_wave_hours_48h),
            history_hours_72h=min(72, len(history_72h)),
            history_hours_48h=min(48, len(history_48h)),
            history_hours_24h=min(24, len(history_24h)),
            history_hours_12h=min(12, len(history_12h)),
            rain_data_hours_48h=min(48, rain_data_hours_48h),
            rain_data_hours_24h=min(24, rain_data_hours),
            wind_data_hours_48h=min(48, wind_data_hours_48h),
            wind_data_hours_12h=min(12, wind_data_hours),
            wave_energy_data_hours_48h=min(48, wave_energy_data_hours_48h),
            wave_energy_data_hours_12h=min(12, wave_energy_data_hours),
            current_data_hours_48h=min(48, current_data_hours_48h),
            onshore_wind_fraction_48h=_rounded(onshore_fraction_48h, 2),
            onshore_wind_fraction_12h=_rounded(onshore_fraction, 2),
            energetic_wave_fraction_48h=_rounded(energetic_fraction_48h, 2),
            energetic_wave_fraction_12h=_rounded(energetic_fraction, 2),
            air_sea_temperature_difference_c=_rounded(air_sea_temperature_difference, 1),
            dew_point_depression_c=_rounded(dew_point_depression, 1),
            is_twilight=is_twilight,
            is_night=is_night,
        )
        field_feasibility = self._field_feasibility(dataset, hour, derived)
        safety, safety_factors = self._safety(dataset, hour, derived, field_feasibility)
        safety, observation_factors = self._apply_observation_context(
            dataset,
            hour,
            safety,
            observation_comparison,
        )
        safety_factors.extend(observation_factors)
        score, opportunity_factors = self._opportunity(
            dataset,
            hour,
            derived,
            safety,
            field_feasibility,
        )
        confidence = self._confidence(dataset, hour, derived, observation_comparison)
        forecast = ForecastConditions(
            wind_speed_kmh=hour.wind_speed_kmh,
            wind_gust_kmh=hour.wind_gust_kmh,
            wind_direction_deg=hour.wind_direction_deg,
            wave_height_m=hour.wave_height_m,
            wave_period_s=hour.wave_period_s,
            wave_direction_deg=hour.wave_direction_deg,
            wind_wave_height_m=hour.wind_wave_height_m,
            wind_wave_period_s=hour.wind_wave_period_s,
            wind_wave_direction_deg=hour.wind_wave_direction_deg,
            swell_height_m=hour.swell_height_m,
            swell_period_s=hour.swell_period_s,
            swell_direction_deg=hour.swell_direction_deg,
            sea_surface_temperature_c=hour.sea_surface_temperature_c,
            ocean_current_velocity_kmh=hour.ocean_current_velocity_kmh,
            ocean_current_direction_deg=hour.ocean_current_direction_deg,
            sea_level_height_msl_m=hour.sea_level_height_msl_m,
            air_temperature_c=hour.air_temperature_c,
            apparent_temperature_c=hour.apparent_temperature_c,
            relative_humidity_pct=hour.relative_humidity_pct,
            dew_point_c=hour.dew_point_c,
            cloud_cover_pct=hour.cloud_cover_pct,
            shortwave_radiation_wm2=hour.shortwave_radiation_wm2,
            uv_index=hour.uv_index,
            lightning_potential_jkg=hour.lightning_potential_jkg,
            cape_jkg=hour.cape_jkg,
            precipitation_mm=hour.precipitation_mm,
            precipitation_probability_pct=hour.precipitation_probability_pct,
            weather_code=hour.weather_code,
            pressure_msl_hpa=hour.pressure_msl_hpa,
            visibility_m=hour.visibility_m,
        )
        return HourDecision(
            time=hour.time,
            safety=safety,
            opportunity_score=score,
            confidence=confidence,
            field_feasibility=field_feasibility,
            factors=safety_factors + opportunity_factors,
            forecast=forecast,
            derived=derived,
        )

    def _field_feasibility(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        derived: DerivedConditions,
    ) -> FieldFeasibilityResult:
        """Screen line holding, transport/fouling and rip-current potential.

        This is deliberately a low-confidence proxy. It cannot observe weed, debris,
        breaking-wave height, sandbars or rip channels at the surf zone.
        """
        if (
            hour.wave_height_m is None
            or hour.wave_period_s is None
            or hour.wave_direction_deg is None
            or hour.wind_speed_kmh is None
            or hour.wind_direction_deg is None
        ):
            return FieldFeasibilityResult(
                status=FieldFeasibilityLevel.UNKNOWN,
                score=0,
                confidence=10,
                holding_difficulty=PotentialLevel.UNKNOWN,
                holding_breakdown=HoldingBreakdown(
                    longshore_current=PotentialLevel.UNKNOWN,
                    orbital_motion=PotentialLevel.UNKNOWN,
                    return_flow=PotentialLevel.UNKNOWN,
                    tidal_current=PotentialLevel.UNKNOWN,
                    dominant="none",
                    confidence=0,
                    reasons_ar=[
                        "تعذّر تفكيك أسباب تثبيت الخط لغياب متغيرات الموج أو الريح الأساسية."
                    ],
                ),
                fouling_transport_potential=PotentialLevel.UNKNOWN,
                turbidity_potential=PotentialLevel.UNKNOWN,
                rip_current_potential=PotentialLevel.UNKNOWN,
                reasons_ar=["تنقص متغيرات أساسية لفحص قابلية تثبيت الخط ونقل الأعشاب أو الحطام."],
                limitations_ar=_field_feasibility_limitations(),
            )

        holding_points = 0
        if hour.wave_height_m >= 1.2:
            holding_points += 3
        elif hour.wave_height_m >= 0.8:
            holding_points += 2
        elif hour.wave_height_m >= 0.5:
            holding_points += 1
        if derived.wave_incidence == WaveIncidence.ALONGSHORE:
            holding_points += 2
        elif derived.wave_incidence == WaveIncidence.OBLIQUE:
            holding_points += 1
        if derived.alongshore_wave_proxy is not None:
            if derived.alongshore_wave_proxy >= 6:
                holding_points += 2
            elif derived.alongshore_wave_proxy >= 2:
                holding_points += 1
        if derived.current_alongshore_kmh is not None:
            current_along = abs(derived.current_alongshore_kmh)
            if current_along >= 1.0:
                holding_points += 2
            elif current_along >= 0.5:
                holding_points += 1
        if hour.wind_speed_kmh >= 25:
            holding_points += 1
        holding = _potential_level(holding_points, moderate_at=3, high_at=6)

        energetic_48h = derived.wave_energy_data_hours_48h >= 24 and (
            derived.strong_wave_hours_48h >= 6
            or (
                derived.wave_energy_integral_48h is not None
                and derived.wave_energy_integral_48h >= 180
            )
        )
        wind_transport_48h = (
            derived.wind_data_hours_48h >= 24
            and derived.onshore_wind_impulse_48h_kmh_h is not None
            and derived.onshore_wind_impulse_48h_kmh_h >= 120
        )
        current_transport_48h = (
            derived.current_data_hours_48h >= 18
            and derived.shoreward_current_impulse_48h_kmh_h is not None
            and derived.shoreward_current_impulse_48h_kmh_h >= 6
        )
        runoff_48h = (
            derived.rain_data_hours_48h >= 24
            and derived.rain_48h_mm is not None
            and derived.rain_48h_mm >= 5
        )
        fouling_evidence_count = sum(
            (energetic_48h, wind_transport_48h, current_transport_48h, runoff_48h)
        )
        fouling_points = (
            (3 if energetic_48h else 0)
            + (2 if wind_transport_48h else 0)
            + (2 if current_transport_48h else 0)
            + (2 if runoff_48h else 0)
            + (1 if dataset.spot.exposure.value == "sheltered" else 0)
        )
        if fouling_evidence_count >= 3 and fouling_points >= 7:
            fouling = PotentialLevel.HIGH
        elif fouling_evidence_count >= 2 and fouling_points >= 4:
            fouling = PotentialLevel.MODERATE
        elif fouling_evidence_count >= 1 or all(
            (
                derived.wave_energy_data_hours_48h >= 24,
                derived.wind_data_hours_48h >= 24,
                derived.rain_data_hours_48h >= 24,
            )
        ):
            fouling = PotentialLevel.LOW
        else:
            fouling = PotentialLevel.UNKNOWN

        turbidity_evidence_count = sum(
            (energetic_48h, runoff_48h, current_transport_48h, wind_transport_48h)
        )
        turbidity_points = (
            (3 if energetic_48h else 0)
            + (3 if runoff_48h else 0)
            + (2 if current_transport_48h else 0)
            + (1 if wind_transport_48h else 0)
            + (1 if dataset.spot.shore_type.value == "sandy" else 0)
        )
        if turbidity_evidence_count >= 3 and turbidity_points >= 7:
            turbidity = PotentialLevel.HIGH
        elif turbidity_evidence_count >= 2 and turbidity_points >= 5:
            turbidity = PotentialLevel.MODERATE
        elif turbidity_evidence_count >= 1 or all(
            (
                derived.wave_energy_data_hours_48h >= 24,
                derived.rain_data_hours_48h >= 24,
            )
        ):
            turbidity = PotentialLevel.LOW
        else:
            turbidity = PotentialLevel.UNKNOWN

        rip_points = 0
        if hour.wave_height_m >= 1.2:
            rip_points += 3
        elif hour.wave_height_m >= 0.7:
            rip_points += 2
        elif hour.wave_height_m >= 0.4:
            rip_points += 1
        if hour.wave_period_s >= 8:
            rip_points += 2
        elif hour.wave_period_s >= 5:
            rip_points += 1
        if derived.wave_incidence in {WaveIncidence.DIRECT, WaveIncidence.OBLIQUE}:
            rip_points += 1
        if dataset.spot.exposure.value == "open":
            rip_points += 1
        if dataset.spot.shore_type.value == "jetty":
            rip_points += 2
        elif dataset.spot.shore_type.value == "sandy":
            rip_points += 1
        if energetic_48h:
            rip_points += 1
        rip = _potential_level(rip_points, moderate_at=4, high_at=7)

        deductions = {
            PotentialLevel.LOW: 0,
            PotentialLevel.MODERATE: 15,
            PotentialLevel.HIGH: 35,
            PotentialLevel.UNKNOWN: 25,
        }
        score = max(
            0,
            100
            - deductions[holding]
            - {
                PotentialLevel.LOW: 0,
                PotentialLevel.MODERATE: 12,
                PotentialLevel.HIGH: 30,
                PotentialLevel.UNKNOWN: 15,
            }[fouling]
            - {
                PotentialLevel.LOW: 0,
                PotentialLevel.MODERATE: 10,
                PotentialLevel.HIGH: 25,
                PotentialLevel.UNKNOWN: 15,
            }[turbidity]
            - {
                PotentialLevel.LOW: 0,
                PotentialLevel.MODERATE: 8,
                PotentialLevel.HIGH: 20,
                PotentialLevel.UNKNOWN: 15,
            }[rip],
        )
        # Once the core wind/wave guard above has passed, missing antecedent
        # proxy history is not critical safety data. Keep the proxy itself Unknown,
        # apply its transparent uncertainty deduction, and retain a usable field status.
        status = (
            FieldFeasibilityLevel.FAVORABLE
            if score >= 75
            else FieldFeasibilityLevel.WORKABLE
            if score >= 50
            else FieldFeasibilityLevel.DIFFICULT
        )

        confidence = 8
        confidence += 10  # core wave fields are present after the guard above
        confidence += 8  # core wind fields are present after the guard above
        if (
            hour.ocean_current_velocity_kmh is not None
            and hour.ocean_current_direction_deg is not None
        ):
            confidence += 4
        if derived.rain_48h_mm is not None and derived.rain_data_hours_48h >= 24:
            confidence += 6
        if derived.wind_data_hours_48h >= 24:
            confidence += 4
        if derived.wave_energy_data_hours_48h >= 24:
            confidence += 4
        if (
            hour.wind_wave_height_m is not None
            and hour.wind_wave_direction_deg is not None
            and hour.swell_height_m is not None
            and hour.swell_direction_deg is not None
        ):
            confidence += 4
        confidence += {
            "surveyed": 2,
            "manual": 2,
            "map": 1,
            "overpass": 1,
            "estimated": 0,
        }[dataset.spot.orientation_source.value]
        confidence = min(50, confidence)

        rain_text = "غير متوفر" if derived.rain_48h_mm is None else f"{derived.rain_48h_mm:.1f} مم"
        wind_fraction_text = (
            "غير متوفر"
            if derived.onshore_wind_fraction_48h is None
            else f"{derived.onshore_wind_fraction_48h * 100:.0f}%"
        )
        energy_text = (
            "غير متوفر"
            if derived.wave_energy_integral_48h is None
            else f"{derived.wave_energy_integral_48h:.1f} (Hs²T·h نسبي)"
        )
        reasons = [
            f"صعوبة تثبيت الخط: {_potential_label_ar(holding)}.",
            f"احتمال نقل الصوفة/الحطام: {_potential_label_ar(fouling)} لا رصد وجود؛ {fouling_evidence_count} عائلات قرائن تشغيلية مختلفة خلال 48 ساعة (وليست أرصاداً أو مصادر مستقلة)، مطر {rain_text} ({derived.rain_data_hours_48h}/48)، وريح بحرية {wind_fraction_text} ({derived.wind_data_hours_48h}/48)، وطاقة موج تراكمية {energy_text} ({derived.wave_energy_data_hours_48h}/48).",
            f"احتمال العكارة: {_potential_label_ar(turbidity)} لا قياس NTU؛ {turbidity_evidence_count} عائلات قرائن تشغيلية مختلفة خلال 48 ساعة، وليست قياسات مستقلة للماء.",
            f"تيار ساحبي محتمل: {_potential_label_ar(rip)}؛ التقدير لا يرى الحواجز الرملية أو قنوات الكسرة.",
        ]
        if derived.wave_component_angle_deg is not None:
            share_text = (
                "Unknown"
                if derived.wave_component_secondary_energy_share is None
                else f"{derived.wave_component_secondary_energy_share * 100:.0f}%"
            )
            reasons.append(
                f"فرق اتجاه السويل وموج الريح {derived.wave_component_angle_deg:.0f}° وحصة طاقة النظام الأضعف {share_text}؛ عرض تشخيصي بلا عتبة خطر أو وزن قرار."
            )
        return FieldFeasibilityResult(
            status=status,
            score=score,
            confidence=confidence,
            holding_difficulty=holding,
            holding_breakdown=self._holding_breakdown(dataset, hour, derived),
            fouling_transport_potential=fouling,
            turbidity_potential=turbidity,
            rip_current_potential=rip,
            fouling_evidence_count=fouling_evidence_count,
            turbidity_evidence_count=turbidity_evidence_count,
            reasons_ar=reasons,
            limitations_ar=_field_feasibility_limitations(),
        )

    def _holding_breakdown(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        derived: DerivedConditions,
    ) -> HoldingBreakdown:
        """Split line-holding difficulty into its four physical mechanisms.

        Diagnostic only: the `holding_difficulty` gate above keeps its original
        computation, so this breakdown never changes the binary decision.
        """
        # 1. Alongshore forcing (oblique/alongshore waves + model current + wind).
        longshore_points = 0
        if derived.wave_incidence == WaveIncidence.ALONGSHORE:
            longshore_points += 3
        elif derived.wave_incidence == WaveIncidence.OBLIQUE:
            longshore_points += 2
        if derived.alongshore_wave_proxy is not None:
            if derived.alongshore_wave_proxy >= 6:
                longshore_points += 2
            elif derived.alongshore_wave_proxy >= 2:
                longshore_points += 1
        if derived.current_alongshore_kmh is not None:
            current_along = abs(derived.current_alongshore_kmh)
            if current_along >= 1.0:
                longshore_points += 2
            elif current_along >= 0.5:
                longshore_points += 1
        if (
            derived.wind_alongshore_component_kmh is not None
            and derived.wind_alongshore_component_kmh >= 15
        ):
            longshore_points += 1
        longshore = _potential_level(longshore_points, moderate_at=3, high_at=6)

        # 2. Near-bed orbital motion across a declared depth band (no real bathymetry).
        shallow_depth_m = 1.5
        deep_depth_m = 5.0
        orbital_shallow = near_bottom_orbital_velocity_ms(
            hour.wave_height_m, hour.wave_period_s, shallow_depth_m
        )
        orbital_deep = near_bottom_orbital_velocity_ms(
            hour.wave_height_m, hour.wave_period_s, deep_depth_m
        )
        if orbital_shallow is None or orbital_deep is None:
            orbital = PotentialLevel.UNKNOWN
            orbital_band = None
        else:
            orbital_band = (
                f"{min(orbital_shallow, orbital_deep):.2f} إلى {max(orbital_shallow, orbital_deep):.2f}"
            )
            if orbital_shallow >= 0.50:
                orbital = PotentialLevel.HIGH
            elif orbital_shallow >= 0.25:
                orbital = PotentialLevel.MODERATE
            else:
                orbital = PotentialLevel.LOW

        # 3. Return flow under the breaker (proxy: shoreward water pushed by waves/wind).
        return_points = 0
        if hour.wave_height_m is not None:
            if hour.wave_height_m >= 1.5:
                return_points += 3
            elif hour.wave_height_m >= 1.0:
                return_points += 2
            elif hour.wave_height_m >= 0.6:
                return_points += 1
        if derived.wave_incidence == WaveIncidence.DIRECT:
            return_points += 2
        elif derived.wave_incidence == WaveIncidence.OBLIQUE:
            return_points += 1
        if hour.wave_period_s is not None and hour.wave_period_s >= 8:
            return_points += 1
        if (
            derived.wind_shoreward_component_kmh is not None
            and derived.wind_shoreward_component_kmh >= 10
        ):
            return_points += 1
        return_flow = _potential_level(return_points, moderate_at=3, high_at=6)

        # 4. Tidal current (sea-level movement and daily range; matters most in Gabès).
        tidal_points = 0
        if derived.tide_state in {TideState.RISING, TideState.FALLING}:
            tidal_points += 1
        if derived.sea_level_rate_m_per_h is not None:
            if abs(derived.sea_level_rate_m_per_h) >= 0.15:
                tidal_points += 2
            elif abs(derived.sea_level_rate_m_per_h) >= 0.08:
                tidal_points += 1
        if derived.sea_level_range_target_day_m is not None:
            if derived.sea_level_range_target_day_m >= 1.5:
                tidal_points += 3
            elif derived.sea_level_range_target_day_m >= 0.8:
                tidal_points += 2
            elif derived.sea_level_range_target_day_m >= 0.4:
                tidal_points += 1
        tidal = _potential_level(tidal_points, moderate_at=3, high_at=6)

        rank = {
            PotentialLevel.HIGH: 3,
            PotentialLevel.MODERATE: 2,
            PotentialLevel.LOW: 1,
            PotentialLevel.UNKNOWN: 0,
        }
        mechanisms = (
            ("longshore_current", longshore),
            ("orbital_motion", orbital),
            ("return_flow", return_flow),
            ("tidal_current", tidal),
        )
        dominant_key, dominant_level = max(mechanisms, key=lambda item: rank[item[1]])
        dominant = dominant_key if dominant_level != PotentialLevel.UNKNOWN else "none"

        confidence = 0
        if (
            hour.wave_height_m is not None
            and hour.wave_period_s is not None
            and hour.wave_direction_deg is not None
        ):
            confidence += 8
        if hour.wind_speed_kmh is not None and hour.wind_direction_deg is not None:
            confidence += 6
        if (
            hour.ocean_current_velocity_kmh is not None
            and hour.ocean_current_direction_deg is not None
        ):
            confidence += 4
        if derived.sea_level_rate_m_per_h is not None:
            confidence += 6
        confidence += {
            "surveyed": 2,
            "manual": 2,
            "map": 1,
            "overpass": 1,
            "estimated": 0,
        }[dataset.spot.orientation_source.value]
        confidence = min(30, confidence)

        band_text = orbital_band if orbital_band is not None else "غير متوفرة"
        range_text = (
            "غير متوفر"
            if derived.sea_level_range_target_day_m is None
            else f"{derived.sea_level_range_target_day_m:.2f} م"
        )
        dominant_labels = {
            "longshore_current": "الجرّ الجانبي",
            "orbital_motion": "الحركة المدارية قرب القاع",
            "return_flow": "الرجوع البحري قرب القاع",
            "tidal_current": "التيار المدّي",
            "none": "لا سبب غلب واضح",
        }
        reasons = [
            f"الجرّ الجانبي: {_potential_label_ar(longshore)} (موج مائل/موازٍ وتيار موازٍ للشاطئ).",
            f"الحركة المدارية قرب القاع: {_potential_label_ar(orbital)}؛ سرعة تقديرية {band_text} م/ث داخل نطاق عمق مفترض 1.5 إلى 5.0 م.",
            f"الرجوع البحري قرب القاع: {_potential_label_ar(return_flow)} (بروكسي من دفع الموج نحو الشاطئ).",
            f"التيار المدّي: {_potential_label_ar(tidal)}؛ مدى اليوم {range_text}.",
            f"السبب الغالب: {dominant_labels[dominant]}.",
        ]
        return HoldingBreakdown(
            longshore_current=longshore,
            orbital_motion=orbital,
            return_flow=return_flow,
            tidal_current=tidal,
            dominant=dominant,
            confidence=confidence,
            orbital_velocity_band_ms=orbital_band,
            reasons_ar=reasons,
        )

    def _safety(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        derived: DerivedConditions,
        field_feasibility: FieldFeasibilityResult,
    ) -> tuple[DecisionLevel, list[Factor]]:
        thresholds = safety_thresholds(dataset.spot, dataset.angler)
        factors: list[Factor] = []
        has_critical = False
        has_caution = False

        missing_critical = [name for name in CRITICAL_FIELDS if getattr(hour, name) is None]
        if missing_critical:
            factors.append(
                Factor(
                    code="missing_critical_safety_data",
                    label_ar="نقص في معطيات السلامة",
                    impact=FactorImpact.DATA_GAP,
                    severity=RiskSeverity.CRITICAL,
                    basis=FactorBasis.MODEL_FORECAST,
                    rule_nature=RuleNature.DATA_QUALITY,
                    value="، ".join(_FIELD_LABELS_AR[name] for name in missing_critical),
                    explanation_ar="لن يحوّل المحرك القيمة المفقودة إلى بحر هادئ؛ القرار يبقى غير محسوم.",
                )
            )

        if hour.weather_code in THUNDERSTORM_CODES:
            has_critical = True
            factors.append(
                Factor(
                    code="thunderstorm",
                    label_ar="خطر رعد وصواعق",
                    impact=FactorImpact.SAFETY,
                    severity=RiskSeverity.CRITICAL,
                    basis=FactorBasis.MODEL_FORECAST,
                    rule_nature=RuleNature.SAFETY_POLICY,
                    value=f"رمز الطقس المتوقع {hour.weather_code}",
                    explanation_ar="النموذج يتوقع عاصفة رعدية؛ القصبة والخيط في مكان مكشوف يرفعان خطر الصواعق. ألغِ الحصة وتحقق من التنبيه الرسمي.",
                )
            )

        if hour.wind_speed_kmh is not None:
            if hour.wind_speed_kmh >= thresholds.sustained_wind_no_go_kmh:
                has_critical = True
                factors.append(
                    _risk_factor(
                        "sustained_wind_no_go",
                        "رياح متواصلة خطرة",
                        RiskSeverity.CRITICAL,
                        f"{hour.wind_speed_kmh:.0f} كم/س",
                        f"تجاوزت حدّ {thresholds.sustained_wind_no_go_kmh:.0f} كم/س لملفك والمكان.",
                    )
                )
            elif hour.wind_speed_kmh >= thresholds.sustained_wind_caution_kmh:
                has_caution = True
                factors.append(
                    _risk_factor(
                        "sustained_wind_caution",
                        "رياح قوية",
                        RiskSeverity.CAUTION,
                        f"{hour.wind_speed_kmh:.0f} كم/س",
                        "الرمي والتحكم في الخيط يصبحان أصعب، وقد تتغير حالة البحر سريعاً.",
                    )
                )

        if hour.wind_gust_kmh is not None:
            if hour.wind_gust_kmh >= thresholds.gust_no_go_kmh:
                has_critical = True
                factors.append(
                    _risk_factor(
                        "gust_no_go",
                        "هبّات خطرة",
                        RiskSeverity.CRITICAL,
                        f"{hour.wind_gust_kmh:.0f} كم/س",
                        f"تجاوزت حدّ {thresholds.gust_no_go_kmh:.0f} كم/س لملفك والمكان.",
                    )
                )
            elif hour.wind_gust_kmh >= thresholds.gust_caution_kmh:
                has_caution = True
                factors.append(
                    _risk_factor(
                        "gust_caution",
                        "هبّات قوية",
                        RiskSeverity.CAUTION,
                        f"{hour.wind_gust_kmh:.0f} كم/س",
                        "ثبّت المعدات وابتعد عن الحواف والمناطق المكشوفة.",
                    )
                )

        if (
            derived.max_wind_direction_shift_6h_deg is not None
            and derived.max_wind_direction_shift_6h_deg >= 60.0
        ):
            has_caution = True
            factors.append(
                _risk_factor(
                    "abrupt_forecast_wind_shift",
                    "تحول سريع متوقع في اتجاه الريح",
                    RiskSeverity.CAUTION,
                    f"حتى {derived.max_wind_direction_shift_6h_deg:.0f}° خلال ساعة",
                    "أكبر فرق دائري بين ساعتين متجاورتين في آخر 6 ساعات من النموذج؛ راقب الواقع ولا تفترض ثبات الريح.",
                    basis=FactorBasis.DERIVED_FORECAST,
                )
            )

        if hour.uv_index is not None and hour.uv_index >= 8.0:
            has_caution = True
            factors.append(
                _risk_factor(
                    "very_high_uv",
                    "أشعة فوق بنفسجية مرتفعة جداً",
                    RiskSeverity.CAUTION,
                    f"UV {hour.uv_index:.1f}",
                    "استعمل حماية إضافية وقلّل التعرض المباشر؛ هذا خطر صحي للصياد ولا يرفع فرصة المصيد.",
                )
            )

        if hour.wave_height_m is not None:
            if hour.wave_height_m >= thresholds.wave_no_go_m:
                has_critical = True
                factors.append(
                    _risk_factor(
                        "wave_height_no_go",
                        "موج أعلى من حدّ السلامة",
                        RiskSeverity.CRITICAL,
                        f"{hour.wave_height_m:.2f} م",
                        f"حدّ ملفك والمكان {thresholds.wave_no_go_m:.2f} م قبل المعاينة المحلية.",
                    )
                )
            elif hour.wave_height_m >= thresholds.wave_caution_m:
                has_caution = True
                factors.append(
                    _risk_factor(
                        "wave_height_caution",
                        "موج يستوجب الحذر",
                        RiskSeverity.CAUTION,
                        f"{hour.wave_height_m:.2f} م",
                        "ارتفاع الموج من نموذج بحري؛ الكسرة على الشاطئ قد تكون أعلى.",
                    )
                )

        if derived.wave_steepness is not None and hour.wave_height_m is not None:
            if derived.wave_steepness >= thresholds.steepness_no_go and hour.wave_height_m >= 0.8:
                has_critical = True
                factors.append(
                    _risk_factor(
                        "steep_wave_no_go",
                        "موج قصير وحاد جداً",
                        RiskSeverity.CRITICAL,
                        f"انحدار {derived.wave_steepness:.3f}",
                        "مؤشر مياه عميقة للخشونة مرتفع؛ لا تعتمد عليه كتوقع لارتفاع الكسرة.",
                        basis=FactorBasis.DERIVED_FORECAST,
                        rule_nature=RuleNature.PHYSICAL_DERIVATION,
                    )
                )
            elif (
                derived.wave_steepness >= thresholds.steepness_caution and hour.wave_height_m >= 0.5
            ):
                has_caution = True
                factors.append(
                    _risk_factor(
                        "steep_wave_caution",
                        "موج قصير ومتقارب",
                        RiskSeverity.CAUTION,
                        f"انحدار {derived.wave_steepness:.3f}",
                        "مؤشر المياه العميقة قد يصف موجاً قصيراً، لكنه لا يحسب التحول والانكسار قرب القاع.",
                        basis=FactorBasis.DERIVED_FORECAST,
                        rule_nature=RuleNature.PHYSICAL_DERIVATION,
                    )
                )

        if hour.visibility_m is not None:
            if hour.visibility_m < thresholds.visibility_no_go_m:
                has_critical = True
                factors.append(
                    _risk_factor(
                        "visibility_no_go",
                        "رؤية شبه منعدمة",
                        RiskSeverity.CRITICAL,
                        f"{hour.visibility_m:.0f} م",
                        "يصعب رؤية الموج والمخارج والأشخاص؛ ألغِ الحصة.",
                    )
                )
            elif hour.visibility_m < thresholds.visibility_caution_m:
                has_caution = True
                factors.append(
                    _risk_factor(
                        "visibility_caution",
                        "رؤية محدودة",
                        RiskSeverity.CAUTION,
                        f"{hour.visibility_m:.0f} م",
                        "لا تدخل بقعة غير مألوفة وحافظ على مسار خروج واضح.",
                    )
                )

        onshore = derived.wind_relation in {
            WindRelation.ONSHORE,
            WindRelation.CROSS_ONSHORE,
        }
        # Near-limit escalation: several independent gates simultaneously within
        # 10% of their no-go threshold (but still inside the caution band) are
        # treated as a hard no-go for that hour. A single near-limit caution stays
        # a caution, so a lone strong-but-sub-limit signal never cancels the day.
        near_limit_codes: list[str] = []
        if (
            hour.wind_speed_kmh is not None
            and thresholds.sustained_wind_no_go_kmh * 0.90
            <= hour.wind_speed_kmh
            < thresholds.sustained_wind_no_go_kmh
        ):
            near_limit_codes.append("sustained_wind")
        if (
            hour.wind_gust_kmh is not None
            and thresholds.gust_no_go_kmh * 0.90
            <= hour.wind_gust_kmh
            < thresholds.gust_no_go_kmh
        ):
            near_limit_codes.append("gust")
        if (
            hour.wave_height_m is not None
            and thresholds.wave_no_go_m * 0.90
            <= hour.wave_height_m
            < thresholds.wave_no_go_m
        ):
            near_limit_codes.append("wave_height")
        if (
            derived.wave_steepness is not None
            and hour.wave_height_m is not None
            and hour.wave_height_m >= 0.8
            and thresholds.steepness_no_go * 0.90
            <= derived.wave_steepness
            < thresholds.steepness_no_go
        ):
            near_limit_codes.append("steepness")
        if (
            hour.visibility_m is not None
            and thresholds.visibility_no_go_m
            < hour.visibility_m
            <= thresholds.visibility_no_go_m * 1.10
        ):
            near_limit_codes.append("visibility")
        if len(near_limit_codes) >= 2:
            has_critical = True
            factors.append(
                _risk_factor(
                    "multiple_near_limit_cautions",
                    "تقارب عوامل خطر من الحدود القصوى",
                    RiskSeverity.CRITICAL,
                    "، ".join(near_limit_codes),
                    "عاملان أو أكثر في آنٍ واحد ضمن 10% من حدود منع الخروج الخاصة بملفك ومكانك؛ يُعامل هذا التزامن كمنع احترازي.",
                    rule_nature=RuleNature.SAFETY_POLICY,
                )
            )

        if (
            onshore
            and hour.wave_height_m is not None
            and hour.wind_gust_kmh is not None
            and hour.wave_height_m >= max(0.8, thresholds.wave_caution_m * 0.8)
            and hour.wind_gust_kmh >= max(30.0, thresholds.gust_caution_kmh * 0.8)
        ):
            has_caution = True
            factors.append(
                _risk_factor(
                    "onshore_wind_wave_combination",
                    "تزامن موج ورياح بحرية",
                    RiskSeverity.CAUTION,
                    f"{hour.wave_height_m:.2f} م / هبّات {hour.wind_gust_kmh:.0f} كم/س",
                    "تزامن الريح البحرية والموج يرفع التحفظ؛ لا يحسب ارتفاع الكسرة أو التيار الراجع محلياً.",
                    basis=FactorBasis.DERIVED_FORECAST,
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )
            )

        if field_feasibility.rip_current_potential == PotentialLevel.HIGH:
            has_caution = True
            factors.append(
                _risk_factor(
                    "elevated_rip_current_potential",
                    "مؤشرات تيار ساحبي محتمل",
                    RiskSeverity.CAUTION,
                    "فحص أولي عالي",
                    "الموج واتجاهه ونوع الوقوف يرفعون إشارة الفحص فقط؛ هذا ليس رصداً، فابحث عن قناة رغوة أو أعشاب تتحرك نحو عرض البحر.",
                    basis=FactorBasis.DERIVED_FORECAST,
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )
            )

        if hour.precipitation_mm is not None and hour.precipitation_mm >= 15.0:
            has_caution = True
            factors.append(
                _risk_factor(
                    "heavy_rain",
                    "أمطار غزيرة",
                    RiskSeverity.CAUTION,
                    f"{hour.precipitation_mm:.1f} مم/س",
                    "انتبه للسيول، الطرق الزلقة، وتغيّر عكارة الماء والحطام قرب المصبات.",
                )
            )

        rain_signal = (hour.precipitation_mm or 0) > 0 or (
            hour.precipitation_probability_pct or 0
        ) >= 30
        if hour.cape_jkg is not None and hour.cape_jkg >= 1_000 and rain_signal:
            has_caution = True
            factors.append(
                _risk_factor(
                    "convective_instability",
                    "قابلية لتكوّن سحب رعدية",
                    RiskSeverity.CAUTION,
                    f"طاقة حمل {hour.cape_jkg:.0f} جول/كغ",
                    "هذا توقع لقابلية الحمل وليس برقاً مرصوداً؛ راقب الرادار والنشرة الرسمية.",
                    basis=FactorBasis.DERIVED_FORECAST,
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )
            )

        if derived.wave_incidence == WaveIncidence.INCONSISTENT:
            factors.append(
                Factor(
                    code="wave_direction_inconsistent",
                    label_ar="اتجاه الموج يحتاج تحققاً",
                    impact=FactorImpact.DATA_GAP,
                    severity=RiskSeverity.CAUTION,
                    basis=FactorBasis.DERIVED_FORECAST,
                    rule_nature=RuleNature.DATA_QUALITY,
                    value=WAVE_INCIDENCE_AR[derived.wave_incidence],
                    explanation_ar="قد تكون خلية النموذج خلف حاجز ساحلي أو أن اتجاه الشاطئ غير دقيق.",
                )
            )
            has_caution = True

        if has_critical:
            return DecisionLevel.NO_GO, factors
        if missing_critical:
            return DecisionLevel.UNKNOWN, factors
        if has_caution:
            return DecisionLevel.CAUTION, factors
        return DecisionLevel.GO, factors

    def _apply_observation_context(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        safety: DecisionLevel,
        comparison: ObservationComparison,
    ) -> tuple[DecisionLevel, list[Factor]]:
        """Use fresh nearby station evidence conservatively without relocating it to the spot."""
        observation = dataset.current_weather_observation
        if observation is None or comparison.status in {
            ObservationMatchStatus.UNAVAILABLE,
            ObservationMatchStatus.NOT_APPLICABLE,
            ObservationMatchStatus.STALE,
            ObservationMatchStatus.DISTANT,
        }:
            return safety, []
        if observation.distance_to_spot_km > 75.0:
            return safety, []
        if abs((hour.time - observation.observed_at).total_seconds()) > 2 * 3600:
            return safety, []

        factors: list[Factor] = []
        observed_thunder = any(
            "TS" in token.upper() for token in observation.raw_report.split()[1:]
        )
        if observed_thunder:
            severity = (
                RiskSeverity.CRITICAL
                if observation.distance_to_spot_km <= 30.0
                else RiskSeverity.CAUTION
            )
            factors.append(
                _risk_factor(
                    "nearby_metar_thunderstorm",
                    "عاصفة رعدية مرصودة في محطة قريبة",
                    severity,
                    f"{observation.station_id} على بعد {observation.distance_to_spot_km:.1f} كم",
                    "METAR رصد محطة لا رصد داخل البقعة؛ قرب العاصفة يفرض إلغاء النافذة إذا كانت المحطة ضمن 30 كم، وإلا تحقق فوراً من الرادار والتنبيه الرسمي.",
                    basis=FactorBasis.DIRECT_OBSERVATION,
                    rule_nature=RuleNature.SAFETY_POLICY,
                )
            )
            if severity == RiskSeverity.CRITICAL:
                safety = DecisionLevel.NO_GO
            elif safety == DecisionLevel.GO:
                safety = DecisionLevel.CAUTION

        thresholds = safety_thresholds(dataset.spot, dataset.angler)
        observed_wind_hazard = (
            observation.wind_speed_kmh is not None
            and observation.wind_speed_kmh >= thresholds.sustained_wind_no_go_kmh
        ) or (
            observation.wind_gust_kmh is not None
            and observation.wind_gust_kmh >= thresholds.gust_no_go_kmh
        )
        if observed_wind_hazard:
            wind_text = (
                f"ريح {observation.wind_speed_kmh:.0f} كم/س"
                if observation.wind_speed_kmh is not None
                else "ريح غير متوفرة"
            )
            gust_text = (
                f"هبّة {observation.wind_gust_kmh:.0f} كم/س"
                if observation.wind_gust_kmh is not None
                else "هبّة غير متوفرة"
            )
            factors.append(
                _risk_factor(
                    "nearby_observed_wind_hazard",
                    "ريح خطرة مرصودة في محطة قريبة",
                    RiskSeverity.CAUTION,
                    f"{wind_text}، {gust_text} — {observation.distance_to_spot_km:.1f} كم",
                    "الرصد يثبت الريح في المطار فقط ولا يثبتها على الشاطئ؛ لكنه يمنع تجاهل احتمال اختلاف الواقع عن التوقع ويستوجب تحققاً قبل الانطلاق.",
                    basis=FactorBasis.DIRECT_OBSERVATION,
                    rule_nature=RuleNature.SAFETY_POLICY,
                )
            )
            if safety == DecisionLevel.GO:
                safety = DecisionLevel.CAUTION

        if comparison.status == ObservationMatchStatus.DIVERGENT:
            factors.append(
                Factor(
                    code="station_model_divergence",
                    label_ar="اختلاف مهم بين المحطة والنموذج",
                    impact=FactorImpact.DATA_GAP,
                    severity=RiskSeverity.CAUTION,
                    basis=FactorBasis.DIRECT_OBSERVATION,
                    rule_nature=RuleNature.DATA_QUALITY,
                    value=f"{observation.station_id} على بعد {observation.distance_to_spot_km:.1f} كم",
                    explanation_ar="الرصد والنموذج لا يتفقان قرب وقت الجلب. لا يُصحح المحرك الشاطئ تلقائياً من محطة المطار؛ يخفض الثقة ويرفع التحفظ.",
                    is_direct_observation=True,
                )
            )
            if safety == DecisionLevel.GO:
                safety = DecisionLevel.CAUTION

        return safety, factors

    def _opportunity(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        derived: DerivedConditions,
        safety: DecisionLevel,
        field_feasibility: FieldFeasibilityResult,
    ) -> tuple[int, list[Factor]]:
        score = 50
        factors: list[Factor] = []

        def add(
            code: str,
            label: str,
            delta: int,
            value: str,
            explanation: str,
            *,
            basis: FactorBasis = FactorBasis.DERIVED_FORECAST,
            rule_nature: RuleNature = RuleNature.EXPERT_PRIOR,
        ) -> None:
            nonlocal score
            score += delta
            factors.append(
                Factor(
                    code=code,
                    label_ar=label,
                    impact=FactorImpact.POSITIVE if delta > 0 else FactorImpact.NEGATIVE,
                    severity=RiskSeverity.INFO,
                    basis=basis,
                    rule_nature=rule_nature,
                    value=value,
                    score_delta=delta,
                    explanation_ar=explanation,
                )
            )

        def context(
            code: str,
            label: str,
            value: str,
            explanation: str,
            *,
            basis: FactorBasis = FactorBasis.DERIVED_FORECAST,
            rule_nature: RuleNature = RuleNature.DATA_QUALITY,
        ) -> None:
            factors.append(
                Factor(
                    code=code,
                    label_ar=label,
                    impact=FactorImpact.NEUTRAL,
                    severity=RiskSeverity.INFO,
                    basis=basis,
                    rule_nature=rule_nature,
                    value=value,
                    explanation_ar=explanation,
                )
            )

        if hour.wave_height_m is not None:
            if hour.wave_height_m < 0.15:
                context(
                    "flat_sea_context",
                    "بحر شبه مسطح",
                    f"{hour.wave_height_m:.2f} م",
                    "لا يُخصم تلقائياً: أثر البحر المسطح يتغير مع الضوء وشفافية الماء والهدف، وشفافية الماء غير مقاسة.",
                    basis=FactorBasis.MODEL_FORECAST,
                )
            elif hour.wave_height_m < 0.35:
                add(
                    "light_water_movement",
                    "حركة ماء خفيفة",
                    2,
                    f"{hour.wave_height_m:.2f} م",
                    "وزن أولي صغير لحركة الماء؛ يحتاج معايرة بمصيد محلي ولا يثبت نشاط السمك.",
                )
            elif hour.wave_height_m <= 1.0:
                add(
                    "useful_wave_band",
                    "حركة موج مناسبة للسيرفكاست",
                    12,
                    f"{hour.wave_height_m:.2f} م",
                    "نطاق تشغيلي أولي للسيرفكاست بعد بوابة السلامة؛ علاقته بالمصيد غير معايرة محلياً.",
                )
            elif hour.wave_height_m <= 1.3:
                add(
                    "energetic_wave_band",
                    "موج نشيط",
                    4,
                    f"{hour.wave_height_m:.2f} م",
                    "وزن أولي محدود؛ الأثر الفعلي يتوقف على الكسرة والقاع والهدف ويحتاج تحققاً محلياً.",
                )
            else:
                add(
                    "excess_wave_energy",
                    "طاقة موج مرتفعة",
                    -12,
                    f"{hour.wave_height_m:.2f} م",
                    "تثبيت الرصاص وقراءة الضربة يصبحان أصعب كفرضية تشغيلية تحتاج تحققاً في الرمية الأولى.",
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )

        if hour.wind_speed_kmh is not None:
            relation_label = WIND_RELATION_AR[derived.wind_relation]
            if derived.wind_relation == WindRelation.ONSHORE and 5 <= hour.wind_speed_kmh <= 22:
                add(
                    "light_onshore_wind",
                    "رياح بحرية خفيفة",
                    7,
                    f"{hour.wind_speed_kmh:.0f} كم/س — {relation_label}",
                    "prior منخفض الوزن لحركة سطح قابلة للتعامل؛ لا يثبت زيادة المصيد.",
                )
            elif (
                derived.wind_relation == WindRelation.CROSS_ONSHORE
                and 5 <= hour.wind_speed_kmh <= 20
            ):
                add(
                    "light_cross_onshore_wind",
                    "رياح جانبية بحرية خفيفة",
                    4,
                    f"{hour.wind_speed_kmh:.0f} كم/س — {relation_label}",
                    "prior تشغيلي أولي منخفض الوزن؛ أثره على الرمي والمصيد يحتاج بيانات محلية.",
                )
            elif hour.wind_speed_kmh > 30:
                add(
                    "difficult_casting_wind",
                    "رياح تعقّد الرمي",
                    -9,
                    f"{hour.wind_speed_kmh:.0f} كم/س — {relation_label}",
                    "التحكم في القوس والخيط وحساسية الضربة قد يتراجع؛ التقدير لا يعرف العتاد أو قدرة الرامي.",
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )

        if derived.gust_factor is not None:
            context(
                "gust_factor_context",
                "معامل الهبّات",
                f"{derived.gust_factor:.2f} مرّة",
                "نسبة الهبة إلى الريح المتوسطة؛ حُجبت عند ريح أقل من 5 كم/س لتجنب نسبة غير مستقرة، ولا تعوض قيمة الهبة المطلقة.",
                rule_nature=RuleNature.PHYSICAL_DERIVATION,
            )

        if hour.lightning_potential_jkg is not None and hour.lightning_potential_jkg > 0:
            context(
                "lightning_potential_context",
                "جهد برق نموذجي",
                f"{hour.lightning_potential_jkg:.0f} جول/كغ",
                "متغير نموذجي وليس رصداً لضربة قريبة؛ رمز العاصفة والتنبيه الرسمي والمعاينة هي أساس السلامة.",
                basis=FactorBasis.MODEL_FORECAST,
                rule_nature=RuleNature.DATA_QUALITY,
            )

        if derived.strong_wind_hours_24h > 0:
            context(
                "recent_strong_wind_context",
                "ريح قوية في سياق 24 ساعة",
                f"{derived.strong_wind_hours_24h} ساعة ≥25 عقدة",
                "سياق لحالة البحر السابقة فقط؛ لا تُطبق قاعدة انتظار 48 ساعة ثابتة ولا مكافأة مصيد.",
            )

        if derived.wave_incidence == WaveIncidence.DIRECT:
            add(
                "direct_wave_incidence",
                "الموج داخل على البقعة مباشرة",
                3,
                WAVE_INCIDENCE_AR[derived.wave_incidence],
                "prior اتجاهي صغير؛ النموذج لا يرى التحول والانكسار أمام الشاطئ.",
            )
        elif derived.wave_incidence == WaveIncidence.OBLIQUE:
            add(
                "oblique_wave_incidence",
                "الموج مائل على الشاطئ",
                3,
                WAVE_INCIDENCE_AR[derived.wave_incidence],
                "prior اتجاهي صغير غير معاير؛ قد يترافق أيضاً مع جرّ الخيط ويحتاج معاينة.",
            )
        elif derived.wave_incidence == WaveIncidence.ALONGSHORE:
            add(
                "alongshore_wave_incidence",
                "موج جانبي",
                -5,
                WAVE_INCIDENCE_AR[derived.wave_incidence],
                "يرفع مؤشر جرّ الرصاص والخيط على طول الساحل؛ الرمية الاختبارية هي الحكم.",
                rule_nature=RuleNature.OPERATIONAL_PROXY,
            )

        if derived.tide_movement_index is not None:
            if derived.tide_movement_index >= 0.35:
                add(
                    "modelled_water_level_movement",
                    "حركة واضحة في مستوى البحر",
                    6,
                    TIDE_STATE_AR[derived.tide_state],
                    "prior منخفض الوزن مبني على تغير مستوى البحر النموذجي، لا توقيت قمري ولا احتمال مصيد.",
                )
            elif derived.tide_state == TideState.SLACK:
                add(
                    "modelled_slack_water",
                    "حركة مستوى البحر ضعيفة",
                    -3,
                    TIDE_STATE_AR[derived.tide_state],
                    "مؤشر الحركة في النموذج قريب من السكون المحلي لليوم.",
                )

        if hour.ocean_current_velocity_kmh is not None:
            if 0.15 <= hour.ocean_current_velocity_kmh <= 1.5:
                add(
                    "moderate_model_current",
                    "تيار بحري نموذجي متوسط",
                    5,
                    f"{hour.ocean_current_velocity_kmh:.2f} كم/س",
                    "prior منخفض الوزن غير معاير؛ التيار البحري النموذجي لا يمثل بالضرورة تيار منطقة الكسرة.",
                )
            elif hour.ocean_current_velocity_kmh > 2.0:
                add(
                    "strong_model_current",
                    "تيار نموذجي قوي",
                    -5,
                    f"{hour.ocean_current_velocity_kmh:.2f} كم/س",
                    "قد يصعّب تثبيت الخط، لكن دقة النموذج قرب الساحل محدودة ولا تمثل منطقة الكسرة.",
                    rule_nature=RuleNature.OPERATIONAL_PROXY,
                )

        if field_feasibility.holding_difficulty == PotentialLevel.HIGH:
            add(
                "line_holding_high",
                "صعوبة عالية محتملة في تثبيت الخط",
                -10,
                f"قابلية الميدان {field_feasibility.score}/100",
                "تجميع الموج الجانبي والتيار والريح يرفع مؤشر الجر؛ لا يثبت جرّ الرصاص في العتاد الفعلي.",
                rule_nature=RuleNature.OPERATIONAL_PROXY,
            )
        elif field_feasibility.holding_difficulty == PotentialLevel.MODERATE:
            add(
                "line_holding_moderate",
                "تثبيت الخط يحتاج انتباهاً",
                -4,
                f"قابلية الميدان {field_feasibility.score}/100",
                "توجد مؤشرات جرّ متوسطة؛ رمية اختبارية أقصر من خطة الحصة ضرورية.",
                rule_nature=RuleNature.OPERATIONAL_PROXY,
            )

        if field_feasibility.fouling_transport_potential == PotentialLevel.HIGH:
            add(
                "fouling_transport_high",
                "قابلية مرتفعة لنقل أعشاب أو حطام موجود",
                -12,
                f"مطر سياقي {derived.rain_24h_mm:.1f} مم"
                if derived.rain_24h_mm is not None
                else "مطر السياق غير متوفر",
                "هذه قابلية نقل وليست دليلاً على وجود الصوفة؛ إذا علقت الرمية الاختبارية أجّل الحصة.",
                rule_nature=RuleNature.OPERATIONAL_PROXY,
            )
        elif field_feasibility.fouling_transport_potential == PotentialLevel.MODERATE:
            add(
                "fouling_transport_moderate",
                "قابلية متوسطة لنقل أعشاب أو حطام موجود",
                -4,
                f"استمرار ريح بحرية {(derived.onshore_wind_fraction_12h or 0) * 100:.0f}%",
                "توجد عوامل نقل متزامنة، لكن مصدر الأعشاب أو الحطام غير معروف.",
                rule_nature=RuleNature.OPERATIONAL_PROXY,
            )

        species = SPECIES_PROFILES[dataset.angler.target_species]
        if derived.is_twilight:
            add(
                "twilight_window",
                "قرب الشروق أو الغروب",
                species.twilight_bonus,
                species.label_ar,
                "نافذة ضوئية انتقالية بوزن أولي غير معاير محلياً؛ ليست وعداً بنشاط السمك.",
                basis=FactorBasis.EXPERT_PRIOR,
                rule_nature=RuleNature.EXPERT_PRIOR,
            )
        elif derived.is_night and species.night_bonus:
            add(
                "night_window",
                "فترة ليلية",
                species.night_bonus,
                species.label_ar,
                "وزن ليلي أولي صغير غير معاير محلياً للنوع المختار.",
                basis=FactorBasis.EXPERT_PRIOR,
                rule_nature=RuleNature.EXPERT_PRIOR,
            )

        if species.preferred_sst_c is not None and hour.sea_surface_temperature_c is not None:
            low, high = species.preferred_sst_c
            tolerated_low, tolerated_high = species.tolerated_sst_c or (low, high)
            if low <= hour.sea_surface_temperature_c <= high:
                add(
                    "species_preferred_sst",
                    "حرارة ماء ضمن المجال المفضّل الأولي",
                    5,
                    f"{hour.sea_surface_temperature_c:.1f}°م — {species.label_ar}",
                    "prior منخفض الوزن وغير معاير محلياً؛ الحرارة وحدها لا تتنبأ بالمصيد.",
                    basis=FactorBasis.EXPERT_PRIOR,
                    rule_nature=RuleNature.EXPERT_PRIOR,
                )
            elif not tolerated_low <= hour.sea_surface_temperature_c <= tolerated_high:
                add(
                    "species_sst_outside_tolerance",
                    "حرارة ماء بعيدة عن المجال الأولي",
                    -6,
                    f"{hour.sea_surface_temperature_c:.1f}°م — {species.label_ar}",
                    "prior سلبي صغير يحتاج إلى معايرة محلية قبل اعتباره علاقة تنبؤية.",
                    basis=FactorBasis.EXPERT_PRIOR,
                    rule_nature=RuleNature.EXPERT_PRIOR,
                )

        if species.preferred_shores and dataset.spot.shore_type in species.preferred_shores:
            add(
                "species_shore_match",
                "نوع القاع مناسب لملف السمكة",
                2,
                species.label_ar,
                "تطابق عام أولي منخفض الوزن ولا يصف البنية الدقيقة تحت الماء.",
                basis=FactorBasis.SPOT_PROFILE,
                rule_nature=RuleNature.EXPERT_PRIOR,
            )

        if derived.pressure_change_3h_hpa is not None:
            context(
                "pressure_tendency_context",
                "اتجاه تغير الضغط",
                f"{derived.pressure_change_3h_hpa:+.1f} هكتوباسكال/3س",
                "سياق لتبدل الطقس فقط؛ لم يُمنح أي وزن للمصيد لأن العلاقة العامة غير حاسمة.",
            )

        if derived.pressure_change_24h_hpa is not None:
            context(
                "pressure_24h_context",
                "تغير الضغط خلال 24 ساعة",
                f"{derived.pressure_change_24h_hpa:+.1f} هكتوباسكال/24س",
                "فرق زمني من سلسلة التوقع نفسها، لا قياس محطة ولا سبب مباشر لنشاط السمك.",
            )

        if derived.sea_surface_temperature_change_24h_c is not None:
            context(
                "sst_change_24h_context",
                "تغير حرارة سطح البحر خلال 24 ساعة",
                f"{derived.sea_surface_temperature_change_24h_c:+.1f}°م",
                "تغير سطحي نموذجي؛ لا يثبت صدمة حرارية أو رفعاً ساحلياً من دون ملف أعماق ورصد.",
            )

        score = max(0, min(100, score))
        if safety == DecisionLevel.NO_GO:
            score = min(score, 25)
        elif safety == DecisionLevel.UNKNOWN:
            score = min(score, 40)
        elif safety == DecisionLevel.CAUTION:
            score = min(score, 70)
        return score, factors

    def _confidence(
        self,
        dataset: ForecastDataset,
        hour: ForecastHour,
        derived: DerivedConditions,
        observation_comparison: ObservationComparison,
    ) -> ConfidenceResult:
        completeness = sum(
            weight
            for field_name, weight in _COMPLETENESS_WEIGHTS.items()
            if getattr(hour, field_name) is not None
        )
        missing = [
            _FIELD_LABELS_AR.get(field_name, field_name)
            for field_name in _COMPLETENESS_WEIGHTS
            if getattr(hour, field_name) is None
        ]
        lead_hours = max(0.0, (hour.time - dataset.fetched_at).total_seconds() / 3600.0)
        if lead_hours <= 24:
            horizon_quality = 1.0
            horizon_reason = "أفق التوقع قصير (حتى 24 ساعة)."
        elif lead_hours <= 48:
            horizon_quality = 0.90
            horizon_reason = "أفق التوقع بين 24 و48 ساعة."
        elif lead_hours <= 72:
            horizon_quality = 0.80
            horizon_reason = "أفق التوقع بين 48 و72 ساعة."
        elif lead_hours <= 120:
            horizon_quality = 0.65
            horizon_reason = "أفق التوقع بين 72 و120 ساعة."
        else:
            horizon_quality = 0.50
            horizon_reason = "أفق التوقع يتجاوز 120 ساعة."

        decision_sources = [
            source
            for source in dataset.sources
            if source.data_kind != SourceDataKind.REMOTE_SENSING_ESTIMATE
        ]
        source_quality = 0.72 if decision_sources else 0.60
        orientation_quality = _ORIENTATION_QUALITY[dataset.spot.orientation_source.value]
        raw = 100 * (
            completeness * 0.55
            + horizon_quality * 0.20
            + source_quality * 0.15
            + orientation_quality * 0.10
        )
        score = min(85, round(raw))  # one model family + no surf-zone observation
        critical_missing = [name for name in CRITICAL_FIELDS if getattr(hour, name) is None]
        if critical_missing:
            score = min(score, 45)
        if derived.wave_incidence == WaveIncidence.INCONSISTENT:
            score = min(score, 55)
        if observation_comparison.affects_confidence:
            score = min(score, 55)

        reasons = [
            horizon_reason,
            "درجة الثقة تقيس اكتمال المدخلات وأفقها واتساقها، لا دقة ميدانية متحققة. وهي مقيدة لأن القرار يعتمد على نماذج مجانية لا على قياس مباشر في منطقة الكسرة.",
        ]
        if missing:
            reasons.append("معطيات ناقصة: " + "، ".join(missing) + ".")
        else:
            reasons.append("كل المتغيرات الأساسية والساندة متوفرة لهذه الساعة.")
        if dataset.spot.orientation_source.value in {"map", "estimated"}:
            reasons.append("اتجاه الشاطئ تقديري ويؤثر في تصنيف الرياح والموج.")
        if derived.wave_incidence == WaveIncidence.INCONSISTENT:
            reasons.append("اتجاه الموج غير متسق مع اتجاه البحر في البقعة.")
        if observation_comparison.affects_confidence:
            reasons.append(
                "يوجد اختلاف مهم بين رصد محطة الطقس القريبة والنموذج عند وقت الجلب؛ خُفضت الثقة ولم تُنقل قراءة المطار إلى الشاطئ."
            )
        elif observation_comparison.status == ObservationMatchStatus.CONSISTENT:
            reasons.append(
                "لم يظهر اختلاف كبير بين أقرب محطة والنموذج قرب وقت الجلب، لكن المحطة ليست داخل البقعة."
            )
        elif observation_comparison.status in {
            ObservationMatchStatus.LIMITED,
            ObservationMatchStatus.DISTANT,
        }:
            reasons.append("رصد المحطة بعيد مكانياً ولا يثبت حالة الشاطئ المختار.")

        return ConfidenceResult(
            score=score,
            band=_confidence_band(score),
            reasons_ar=reasons,
        )

    def _recommended_windows(
        self, hourly: list[HourDecision], session_hours: int
    ) -> list[DecisionWindow]:
        candidates: list[DecisionWindow] = []
        for start_index in range(0, len(hourly) - session_hours + 1):
            group = hourly[start_index : start_index + session_hours]
            if not _is_consecutive(group):
                continue
            safety = _worst_safety(item.safety for item in group)
            if safety in {DecisionLevel.NO_GO, DecisionLevel.UNKNOWN}:
                continue
            field_feasibility = _worst_field_feasibility(
                item.field_feasibility.status for item in group
            )
            field_score = min(item.field_feasibility.score for item in group)
            score = round(sum(item.opportunity_score for item in group) / len(group))
            confidence = min(item.confidence.score for item in group)
            start = group[0].time
            end = group[-1].time + timedelta(hours=1)
            key_factors = _window_key_factors(group)
            time_range = _time_range_ar(start, end)
            headline = (
                f"نافذة ببيانات تنفيذ ناقصة من {time_range}"
                if field_feasibility == FieldFeasibilityLevel.UNKNOWN
                else f"نافذة صعبة ميدانياً من {time_range}"
                if field_feasibility == FieldFeasibilityLevel.DIFFICULT
                else f"نافذة قابلة بشرط ضبط العتاد من {time_range}"
                if field_feasibility == FieldFeasibilityLevel.WORKABLE
                else f"نافذة مناسبة من {time_range}"
                if safety == DecisionLevel.GO
                else f"نافذة ممكنة بحذر من {time_range}"
            )
            candidates.append(
                DecisionWindow(
                    start=start,
                    end=end,
                    safety=safety,
                    field_feasibility=field_feasibility,
                    field_score=field_score,
                    opportunity_score=score,
                    confidence_score=confidence,
                    headline_ar=headline,
                    key_factors_ar=key_factors,
                )
            )

        candidates.sort(
            key=lambda item: (
                1 if item.safety == DecisionLevel.GO else 0,
                _FIELD_FEASIBILITY_RANK[item.field_feasibility],
                item.field_score,
                item.opportunity_score,
                item.confidence_score,
            ),
            reverse=True,
        )
        selected: list[DecisionWindow] = []
        for candidate in candidates:
            if all(
                candidate.end <= existing.start or candidate.start >= existing.end
                for existing in selected
            ):
                selected.append(candidate)
            if len(selected) == 3:
                break
        return selected

    def _avoid_windows(self, hourly: list[HourDecision]) -> list[DecisionWindow]:
        bad = {DecisionLevel.NO_GO, DecisionLevel.UNKNOWN}
        groups: list[list[HourDecision]] = []
        current: list[HourDecision] = []
        for item in hourly:
            if item.safety in bad:
                if current and item.time - current[-1].time > timedelta(hours=1, minutes=5):
                    groups.append(current)
                    current = []
                current.append(item)
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        windows: list[DecisionWindow] = []
        for group in groups:
            safety = _worst_safety(item.safety for item in group)
            labels = _critical_factor_labels(group)
            headline = (
                "فترة ممنوعة" if safety == DecisionLevel.NO_GO else "فترة بلا معطيات سلامة كافية"
            )
            windows.append(
                DecisionWindow(
                    start=group[0].time,
                    end=group[-1].time + timedelta(hours=1),
                    safety=safety,
                    field_feasibility=_worst_field_feasibility(
                        item.field_feasibility.status for item in group
                    ),
                    field_score=min(item.field_feasibility.score for item in group),
                    opportunity_score=round(
                        sum(item.opportunity_score for item in group) / len(group)
                    ),
                    confidence_score=min(item.confidence.score for item in group),
                    headline_ar=f"{headline} من {group[0].time:%H:%M} إلى {(group[-1].time + timedelta(hours=1)):%H:%M}",
                    key_factors_ar=labels[:5],
                )
            )
        return windows

    def _day_decision(
        self,
        hourly: list[HourDecision],
        recommended: list[DecisionWindow],
        field_feasibility: FieldFeasibilityResult,
        confidence: ConfidenceResult,
    ) -> tuple[DecisionLevel, DecisionReasonCode]:
        """Return the explicit pre-trip binary decision.

        Opportunity and unconfirmed fouling/turbidity proxies never veto a trip that
        passed the available automated safety and physical execution gates. Missing
        critical evidence remains a conservative NO_GO rather than being displayed as
        a third headline state.
        """
        if not recommended:
            if any(item.safety == DecisionLevel.UNKNOWN for item in hourly):
                return DecisionLevel.NO_GO, DecisionReasonCode.CRITICAL_DATA_MISSING
            if any(item.safety == DecisionLevel.NO_GO for item in hourly):
                return DecisionLevel.NO_GO, DecisionReasonCode.SAFETY_HAZARD
            return DecisionLevel.NO_GO, DecisionReasonCode.CONSERVATIVE_UNCERTAINTY

        best = recommended[0]
        # A CAUTION window is still a "go with caution" recommendation: its caution
        # factors stay visible in the summary and key factors. Only a NO_GO window
        # (defensive; recommended windows never carry NO_GO) is a hard block here.
        if best.safety == DecisionLevel.NO_GO:
            return DecisionLevel.NO_GO, DecisionReasonCode.SAFETY_HAZARD
        if field_feasibility.status == FieldFeasibilityLevel.UNKNOWN:
            return DecisionLevel.NO_GO, DecisionReasonCode.CRITICAL_DATA_MISSING
        # A high line-holding difficulty is a direct execution blocker because the
        # forecasted forcing can make the planned setup unusable. Fouling and turbidity
        # remain low-confidence transport proxies: without a field observation they may
        # lower the field score and require a check, but they cannot veto a safe window.
        if field_feasibility.holding_difficulty == PotentialLevel.HIGH:
            return DecisionLevel.NO_GO, DecisionReasonCode.FIELD_INFEASIBLE
        if confidence.score < 50:
            return DecisionLevel.NO_GO, DecisionReasonCode.CONSERVATIVE_UNCERTAINTY
        return DecisionLevel.GO, DecisionReasonCode.SAFE_WINDOW

    def _overall_field_feasibility(
        self,
        hourly: list[HourDecision],
        recommended: list[DecisionWindow],
    ) -> FieldFeasibilityResult:
        if recommended:
            window = recommended[0]
            covered = [item for item in hourly if window.start <= item.time < window.end]
        else:
            covered = hourly
        results = [item.field_feasibility for item in covered]
        holding = _worst_potential(item.holding_difficulty for item in results)
        fouling = _worst_potential(item.fouling_transport_potential for item in results)
        turbidity = _worst_potential(item.turbidity_potential for item in results)
        rip = _worst_potential(item.rip_current_potential for item in results)
        scope = "أفضل نافذة" if recommended else "الساعات المتاحة"
        reasons = [
            f"اعتمد التجميع أضعف ساعة داخل {scope} كإجراء محافظ.",
            f"صعوبة تثبيت الخط: {_potential_label_ar(holding)}.",
            f"احتمال نقل الصوفة/الحطام إن كانت موجودة: {_potential_label_ar(fouling)}؛ لا يتوفر رصد مباشر لوجودها.",
            f"احتمال العكارة: {_potential_label_ar(turbidity)}؛ لا توجد قراءة NTU داخل البقعة.",
            f"تيار ساحبي محتمل: {_potential_label_ar(rip)}؛ لا تتوفر خريطة قاع أو مشاهدة لمنطقة الكسرة.",
        ]
        return FieldFeasibilityResult(
            status=_worst_field_feasibility(item.status for item in results),
            score=min(item.score for item in results),
            confidence=min(item.confidence for item in results),
            holding_difficulty=holding,
            holding_breakdown=_combine_holding_breakdowns(
                [item.holding_breakdown for item in results]
            ),
            fouling_transport_potential=fouling,
            turbidity_potential=turbidity,
            rip_current_potential=rip,
            fouling_evidence_count=max(item.fouling_evidence_count for item in results),
            turbidity_evidence_count=max(item.turbidity_evidence_count for item in results),
            reasons_ar=reasons,
            limitations_ar=_field_feasibility_limitations(),
        )

    def _gear_recommendation(
        self,
        hourly: list[HourDecision],
        recommended: list[DecisionWindow],
        field_feasibility: FieldFeasibilityResult,
    ) -> GearRecommendation:
        """Propose surfcasting gear bands from the catalog (recommendation, not inventory)."""
        if recommended:
            window = recommended[0]
            covered = [item for item in hourly if window.start <= item.time < window.end]
        else:
            covered = hourly
        wave_values = [
            item.forecast.wave_height_m
            for item in covered
            if item.forecast.wave_height_m is not None
        ]
        wind_values = [
            item.forecast.wind_speed_kmh
            for item in covered
            if item.forecast.wind_speed_kmh is not None
        ]
        return recommend_gear(
            holding=field_feasibility.holding_difficulty,
            breakdown=field_feasibility.holding_breakdown,
            fouling=field_feasibility.fouling_transport_potential,
            wave_height_m=max(wave_values) if wave_values else None,
            wind_speed_kmh=max(wind_values) if wind_values else None,
        )

    def _fouling_evidence(
        self,
        dataset: ForecastDataset,
        field_feasibility: FieldFeasibilityResult,
    ) -> FoulingEvidence:
        """Build the five-rung fouling evidence ladder (phase 4).

        The transport proxy (levels 1-2) never vetoes. Confirmed evidence —
        several consistent recent reports, an official report, or a fouled test
        cast (levels 4-5) — becomes a force-majeure candidate that overrides a
        safe window.
        """
        level = 0
        basis: list[str] = []
        notes: list[str] = []
        fouling = field_feasibility.fouling_transport_potential
        if fouling == PotentialLevel.HIGH:
            level = max(level, 2)
            basis.append(
                "نموذج النقل يقدّر قابلية صوفة/حطام مرتفعة خلال 48 ساعة (طاقة موج ودفع ريح/تيار) — تنبيه لا رصد."
            )
        elif fouling == PotentialLevel.MODERATE:
            level = max(level, 1)
            basis.append("نموذج النقل يقدّر قابلية صوفة/حطام متوسطة خلال 48 ساعة — تنبيه لا رصد.")
        elif fouling == PotentialLevel.LOW:
            level = max(level, 1)
            basis.append("قابلية نقل الصوفة منخفضة في النموذج؛ لا دليل على وجود مادة.")
        else:
            notes.append("نموذج الصوفة غير متاح.")

        # Satellite bloom signal (CMEMS ocean-colour NRT, 1 km seaward sample):
        # remote-sensing evidence of organic matter, not proof the rig fouls.
        water = dataset.coastal_water_context
        if water is not None and water.availability == "available":
            chl = water.chlorophyll_a_mg_m3
            if chl is not None and chl >= _CHL_BLOOM_DENSE_MG_M3:
                if fouling == PotentialLevel.HIGH:
                    level = max(level, 4)
                    basis.append(
                        f"إشارة ساتلية لازدهار كثيف (CHL-a {chl:.1f} mg/m³) مع نقل بحري مرتفع نحو الشاطئ — دليل قوي مرشح للقاهر."
                    )
                else:
                    level = max(level, 3)
                    basis.append(
                        f"إشارة ساتلية لازدهار كثيف (CHL-a {chl:.1f} mg/m³) لكن نقل الشاطئ غير مرتفع — تأكيد ميداني مطلوب."
                    )
            elif chl is not None and chl >= _CHL_BLOOM_MODERATE_MG_M3:
                level = max(level, 3)
                basis.append(
                    f"إشارة ساتلية لكتلة عضوية معتدلة (CHL-a {chl:.1f} mg/m³) — تنبيه مرتفع لا دليل قاهر."
                )
            elif chl is not None:
                notes.append(
                    f"إشارة ساتلية منخفضة للكلوروفيل (CHL-a {chl:.1f} mg/m³)؛ لا مؤشر ازدهار."
                )
        elif water is not None and water.availability == "unavailable":
            notes.append(f"السياق الساتلي غير متاح: {water.reason_ar}")

        valid: list[FieldReport] = []
        for report in dataset.field_reports:
            fresh, note = _report_freshness(report.reported_at, dataset.fetched_at)
            if not fresh:
                notes.append(note)
                continue
            valid.append(report)

        official_fouling = [
            report
            for report in valid
            if report.kind == "fouling" and report.source == "official"
        ]
        user_fouling = [
            report
            for report in valid
            if report.kind == "fouling" and report.source in {"user", "community"}
        ]
        if official_fouling:
            level = 5
            basis.append(f"{len(official_fouling)} بلاغ رسمي حديث يؤكد وجود الصوفة/الحطام.")
        elif len(user_fouling) >= 2:
            level = max(level, 4)
            basis.append(f"{len(user_fouling)} بلاغات حديثة متسقة من نفس البقعة؛ الصوفة مرشحة للقاهر.")
        elif user_fouling:
            level = max(level, 3)
            basis.append("بلاغ حديث موثق من نفس البقعة؛ الصوفة محتملة وتطلب التأكيد.")

        cast = dataset.test_cast
        if cast is not None:
            fresh, note = _report_freshness(cast.cast_at, dataset.fetched_at)
            if fresh and cast.hooked:
                level = 5
                basis.append("رمية اختبار فعلية تعلّقت مؤخراً — دليل مباشر.")
            elif fresh and not cast.hooked:
                notes.append("رمية اختبار نظيفة حديثاً؛ تُخفض تقدير الصوفة الكثيفة.")
                level = min(level, 2)
            else:
                notes.append(note)

        return FoulingEvidence(
            level=level,
            is_force_majeure=level >= 4,
            basis_ar=basis,
            notes_ar=notes,
        )

    def _trip_ruin_factors(
        self,
        dataset: ForecastDataset,
        field_feasibility: FieldFeasibilityResult,
        fouling_evidence: FoulingEvidence,
    ) -> list[TripRuinFactor]:
        """Evidence-gated trip-ruining factors (v1.9.8).

        Each factor carries its level, basis, whether it force-majeures, and the
        age of the live datum behind it. Policy: confirmed evidence (a strong
        satellite signal for fouling, or a fresh dense field report for
        jellyfish/debris/turbidity) may block; forecast/proxy stays a caution;
        unsupported stays Unknown (D11).
        """
        factors: list[TripRuinFactor] = []
        water = dataset.coastal_water_context
        water_age_ar: str | None = None
        if (
            water is not None
            and water.availability == "available"
            and water.valid_time is not None
        ):
            age = water.age_hours
            water_age_ar = (
                f"صورة ساتلية بتاريخ {water.valid_time.date().isoformat()} (عمر ~{age:.0f} ساعة)"
                if age is not None
                else f"صورة ساتلية بتاريخ {water.valid_time.date().isoformat()}"
            )

        # 1) dense fouling — mirrors the fouling ladder (+ satellite bloom).
        level = fouling_evidence.level
        foul_level = "unknown"
        if level >= 4:
            foul_level = "high"
        elif level >= 3:
            foul_level = "moderate"
        elif level >= 1:
            foul_level = "low"
        chl = (
            water.chlorophyll_a_mg_m3
            if water is not None and water.availability == "available"
            else None
        )
        satellite_bloom = chl is not None and chl >= _CHL_BLOOM_MODERATE_MG_M3
        has_fouling_report = any(r.kind == "fouling" for r in dataset.field_reports)
        if satellite_bloom:
            foul_basis = "satellite"
        elif has_fouling_report or fouling_evidence.is_force_majeure:
            foul_basis = "field_report"
        elif field_feasibility.fouling_transport_potential != PotentialLevel.UNKNOWN:
            foul_basis = "forecast_proxy"
        else:
            foul_basis = "unknown"
        factors.append(
            TripRuinFactor(
                factor="dense_fouling",
                label_ar="الصوفة / الطحالب الكثيفة (تخبّل المونتاج)",
                level=foul_level,
                basis=foul_basis,
                is_force_majeure=fouling_evidence.is_force_majeure,
                evidence_ar=fouling_evidence.basis_ar,
                age_ar=water_age_ar if foul_basis == "satellite" else None,
                source_ar="Copernicus Marine (OCEANCOLOUR MED) + بلاغات ميدانية",
            )
        )

        # 2) turbidity — satellite caution + fresh dense field report can block.
        tur = (
            water.turbidity_fnu
            if water is not None and water.availability == "available"
            else None
        )
        spm = (
            water.suspended_particulate_matter_g_m3
            if water is not None and water.availability == "available"
            else None
        )
        tur_proxy = field_feasibility.turbidity_potential
        turbidity_evidence: list[str] = []
        tur_level = "unknown"
        tur_basis: str = "unknown"
        tur_fm = False
        fresh_turbidity = [
            r
            for r in dataset.field_reports
            if r.kind == "turbidity"
            and _report_freshness(r.reported_at, dataset.fetched_at)[0]
        ]
        if fresh_turbidity and any(r.severity == "dense" for r in fresh_turbidity):
            tur_level = "high"
            tur_basis = "field_report"
            tur_fm = True
            turbidity_evidence.append("بلاغ ميداني حديث يؤكد تعكراً كثيفاً في البقعة.")
        elif fresh_turbidity:
            tur_level = "moderate"
            tur_basis = "field_report"
            turbidity_evidence.append("بلاغ ميداني حديث يذكر تعكراً في البقعة.")
        elif tur is not None:
            tur_basis = "satellite"
            if tur >= _TUR_HIGH_FNU:
                tur_level = "high"
                turbidity_evidence.append(f"إشارة ساتلية لتعكر مرتفع (TUR {tur:.1f} FNU) — تنبيه لا منع آلي.")
            elif tur >= _TUR_MODERATE_FNU:
                tur_level = "moderate"
                turbidity_evidence.append(f"إشارة ساتلية لتعكر معتدل (TUR {tur:.1f} FNU).")
            else:
                tur_level = "low"
                turbidity_evidence.append(f"إشارة ساتلية منخفضة للتعكر (TUR {tur:.1f} FNU).")
            if spm is not None:
                turbidity_evidence.append(f"عوالق معلّقة SPM {spm:.1f} g/m³ (ساتلي).")
        elif tur_proxy == PotentialLevel.HIGH:
            tur_level = "moderate"
            tur_basis = "forecast_proxy"
            turbidity_evidence.append("نموذج التعكير يقدّر قابلية مرتفعة (أمطار/ريح/طاقة موج) — تنبيه لا قياس.")
        elif tur_proxy == PotentialLevel.MODERATE:
            tur_level = "low"
            tur_basis = "forecast_proxy"
            turbidity_evidence.append("نموذج التعكير يقدّر قابلية متوسطة — تنبيه لا قياس.")
        else:
            tur_basis = "unknown"
            turbidity_evidence.append("لا قياس تعكر ساتلي أو ميداني؛ القيمة Unknown.")
        if not tur_fm and tur_basis in {"satellite", "forecast_proxy"}:
            turbidity_evidence.append("التعكر وحده لا يمنع الرمي آلياً؛ يبقى تنبيهاً.")
        factors.append(
            TripRuinFactor(
                factor="turbidity",
                label_ar="العكارة / التعكر",
                level=tur_level,
                basis=tur_basis,
                is_force_majeure=tur_fm,
                evidence_ar=turbidity_evidence,
                age_ar=water_age_ar if tur_basis == "satellite" else None,
                source_ar="Copernicus Marine (TUR/SPM) + بلاغات ميدانية",
            )
        )

        # 3) jellyfish — no operational satellite product; field reports only.
        fresh_jelly = [
            r
            for r in dataset.field_reports
            if r.kind == "jellyfish"
            and _report_freshness(r.reported_at, dataset.fetched_at)[0]
        ]
        if fresh_jelly and any(r.severity == "dense" for r in fresh_jelly):
            factors.append(
                TripRuinFactor(
                    factor="jellyfish",
                    label_ar="قناديل البحر",
                    level="high",
                    basis="field_report",
                    is_force_majeure=True,
                    evidence_ar=["بلاغ ميداني حديث يؤكد وجود قناديل كثيفة في البقعة — تُفسد الخرجة."],
                    age_ar=None,
                    source_ar="بلاغ ميداني (لا منتج ساتلي تشغيلي لقناديل البحر)",
                )
            )
        elif fresh_jelly:
            factors.append(
                TripRuinFactor(
                    factor="jellyfish",
                    label_ar="قناديل البحر",
                    level="moderate",
                    basis="field_report",
                    is_force_majeure=False,
                    evidence_ar=["بلاغ ميداني حديث يذكر قناديل بحر في البقعة — تنبيه لا منع."],
                    age_ar=None,
                    source_ar="بلاغ ميداني (لا منتج ساتلي تشغيلي لقناديل البحر)",
                )
            )
        else:
            factors.append(
                TripRuinFactor(
                    factor="jellyfish",
                    label_ar="قناديل البحر",
                    level="unknown",
                    basis="unknown",
                    is_force_majeure=False,
                    evidence_ar=[
                        "لا منتج ساتلي تشغيلي لقناديل البحر ولا بلاغ ميداني حديث؛ القيمة Unknown."
                    ],
                    age_ar=None,
                    source_ar="غير متاح",
                )
            )

        # 4) marine heatwave — satellite SST (or model) anomaly vs climatology.
        sat_sst = water.sea_surface_temperature_c if water is not None else None
        if sat_sst is None:
            sst_values = [
                hour.sea_surface_temperature_c
                for hour in dataset.hours
                if hour.time.date() == dataset.target_date
                and hour.sea_surface_temperature_c is not None
            ]
            model_sst = round(sum(sst_values) / len(sst_values), 1) if sst_values else None
        else:
            model_sst = sat_sst
        mhw_level = "unknown"
        mhw_basis: str = "unknown"
        mhw_evidence: list[str] = []
        if model_sst is not None:
            mhw_basis = "satellite" if sat_sst is not None else "forecast_proxy"
            climatology = _COASTAL_SST_CLIMATOLOGY_C[dataset.target_date.month - 1]
            anomaly = model_sst - climatology
            if anomaly >= _MHW_STRONG_ANOMALY_C:
                mhw_level = "high"
                mhw_evidence.append(
                    f"حرارة سطح {model_sst:.1f}°م أعلى من المعدل المرجعي ({climatology:.1f}°م) بـ{anomaly:+.1f}°م — شذوذ قوي."
                )
            elif anomaly >= _MHW_MODERATE_ANOMALY_C:
                mhw_level = "moderate"
                mhw_evidence.append(
                    f"حرارة سطح {model_sst:.1f}°م أعلى من المعدل المرجعي ({climatology:.1f}°م) بـ{anomaly:+.1f}°م — شذوذ معتدل."
                )
            else:
                mhw_level = "low"
                mhw_evidence.append(
                    f"حرارة سطح {model_sst:.1f}°م قرب المعدل المرجعي ({climatology:.1f}°م) — لا شذوذ."
                )
            mhw_evidence.append(
                "المعدل المرجعي جدول مناخي ساحلي قابل للمراجعة؛ الشذوذ يغيّر توفر السمك ولا يمنع الخرجة آلياً."
            )
        else:
            mhw_evidence.append("لا حرارة سطح ساتلية أو نموذجية؛ القيمة Unknown.")
        factors.append(
            TripRuinFactor(
                factor="marine_heatwave",
                label_ar="موجة حر بحرية (شذوذ الحرارة)",
                level=mhw_level,
                basis=mhw_basis,
                is_force_majeure=False,
                evidence_ar=mhw_evidence,
                age_ar=water_age_ar if sat_sst is not None else None,
                source_ar=(
                    "ساتلي (SST)" if sat_sst is not None else "نموذج (SST) — ليس قياساً ساتلياً"
                ),
            )
        )

        # 5) storm debris — field reports only (no reliable satellite method).
        fresh_debris = [
            r
            for r in dataset.field_reports
            if r.kind == "debris"
            and _report_freshness(r.reported_at, dataset.fetched_at)[0]
        ]
        if fresh_debris and any(r.severity == "dense" for r in fresh_debris):
            factors.append(
                TripRuinFactor(
                    factor="storm_debris",
                    label_ar="حطام / فضلات الأودية",
                    level="high",
                    basis="field_report",
                    is_force_majeure=True,
                    evidence_ar=["بلاغ ميداني حديث يؤكد حطاماً كثيفاً (فضلات أودية) في البقعة — يُفسد الخرجة."],
                    age_ar=None,
                    source_ar="بلاغ ميداني (لا قياس ساتلي موثوق للحطام)",
                )
            )
        elif fresh_debris:
            factors.append(
                TripRuinFactor(
                    factor="storm_debris",
                    label_ar="حطام / فضلات الأودية",
                    level="moderate",
                    basis="field_report",
                    is_force_majeure=False,
                    evidence_ar=["بلاغ ميداني حديث يذكر حطاماً في البقعة — تنبيه لا منع."],
                    age_ar=None,
                    source_ar="بلاغ ميداني (لا قياس ساتلي موثوق للحطام)",
                )
            )
        else:
            factors.append(
                TripRuinFactor(
                    factor="storm_debris",
                    label_ar="حطام / فضلات الأودية",
                    level="unknown",
                    basis="unknown",
                    is_force_majeure=False,
                    evidence_ar=["لا بلاغ ميداني حديث ولا قياس ساتلي موثوق؛ القيمة Unknown."],
                    age_ar=None,
                    source_ar="غير متاح",
                )
            )

        return factors

    def _spring_neap(
        self,
        dataset: ForecastDataset,
        all_hours: list[ForecastHour],
    ) -> SpringNeap:
        """Classify spring/neap from the modelled sea-level series (phase 5).

        The classification is relative to the forecast's own daily ranges, never
        the moon phase, and its decision channel is the tidal-current rating in
        the holding breakdown. A tiny model range (which misses the Gulf of
        Gabès ≈2 m tide) lowers the confidence instead of inventing a value.
        """
        ranges = daily_sea_level_ranges(all_hours)
        target_range = ranges.get(dataset.target_date)
        classification, ratio, reference = classify_spring_neap(
            target_range, list(ranges.values())
        )
        rates = sea_level_rates(all_hours)
        target_rates = [
            abs(rate)
            for item, rate in zip(all_hours, rates, strict=True)
            if item.time.date() == dataset.target_date and rate is not None
        ]
        max_rate = round(max(target_rates), 3) if target_rates else None

        folk = {
            "spring": "حيّة",
            "neap": "مات",
            "intermediate": "وسط",
            "unknown": "غير معروف",
        }[classification]

        gabes = in_gabes_zone(dataset.location.latitude, dataset.location.longitude)
        confidence = 30
        notes: list[str] = []
        limitations: list[str] = []

        if target_range is None:
            confidence = min(confidence, 5)
            notes.append("لا توجد سلسلة مستوى بحر كافية لتصنيف الحيّة/المات.")
        if reference is not None and reference < 0.10:
            confidence = min(confidence, 10)
            notes.append(
                "مدى مستوى البحر في النموذج ضعيف جداً؛ قد لا يلتقط المدّ الفلكي الحقيقي."
            )
        if gabes:
            confidence = min(confidence, 12)
            limitations.append(
                "البقعة في منطقة خليج قابس ذات المدّ الأقوى في المتوسط (≈2.1-2.3 م في الحيّة)؛ "
                "إن لم يلتقط النموذج هذا المدى فالتصنيف والثقة منخفضان."
            )
        limitations.append(
            "التصنيف محسوب من المدى الفعلي النموذجي لا من طور القمر؛ اسم الحيّة/المات عرض شعبي والقيمة الفيزيائية وحدها تدخل أي حساب."
        )
        limitations.append(
            "سلسلة مستوى البحر في Open-Meteo عالية الدقة فقط في أوروبا الوسطى وأمريكا الشمالية؛ في تونس تُحلَّل من نموذج عالمي أخشن، فالمدى ومعدل الارتفاع تقديرات وليست قياس مدّ محلي."
        )
        notes.append(
            "الاستجابة السمكية للحيّة/المات تظهر في محور الأنواع (قابلية الاقتراب من السيرف) وتبقى Unknown لكل نوع حتى معايرة سجل مصيد تونسي."
        )
        return SpringNeap(
            classification=classification,
            folk_label_ar=folk,
            range_target_day_m=target_range,
            range_reference_m=reference,
            range_ratio=ratio,
            max_level_rate_m_per_h=max_rate,
            gabes_zone=gabes,
            confidence=confidence,
            notes_ar=notes,
            limitations_ar=limitations,
        )

    def _species_axes(
        self,
        dataset: ForecastDataset,
        spring_neap: SpringNeap,
        field_feasibility: FieldFeasibilityResult,
        recommended: list[DecisionWindow],
    ) -> SpeciesAxes:
        """Build the reporting-only seven-axis species block (phase 6 / E7).

        The axes stay separate and never feed the binary go/no_go: a weak fish
        profile must not block a safe executable window. Spring/neap enters the
        surf-approach axis as a physical factor (range, current, timing); the
        per-species response to it stays Unknown until a Tunisian catch log is
        calibrated. No catch probability, no legal sizes, no seasonal bans (D10).
        """
        profile = SPECIES_PROFILES[dataset.angler.target_species]
        axes: list[SpeciesAxisValue] = []
        unknown_axes: list[str] = []

        # ── seasonal availability: month x Tunisian zone (audited, phase 1) ──
        zone = tunisian_zone(dataset.location.latitude, dataset.location.longitude)
        month = dataset.target_date.month
        presence = profile.monthly_presence(zone, month)
        if presence is None:
            unknown_axes.append("seasonal")
            seasonal_status = "unknown"
            seasonal_evidence: list[str] = []
            seasonal_basis = "unknown"
            seasonal_conf = 5
        else:
            seasonal_status = {
                3: "favorable",
                2: "neutral",
                1: "unfavorable",
                0: "unfavorable",
            }[presence]
            seasonal_evidence = [
                f"شهر {MONTHS_AR[month - 1]} في منطقة {ZONE_LABELS_AR.get(zone, zone)}: توفر {PRESENCE_LABELS_AR[presence]}.",
                "مشتق من دراسات تونسية منشورة (بيولوجيا التكاثر والتجمع الساحلي) — انظر مصادر النوع أدناه — وليس سجل مصيد تونسي.",
            ]
            seasonal_basis = "expert_prior"
            seasonal_conf = 15
        axes.append(
            SpeciesAxisValue(
                axis="seasonal",
                status=seasonal_status,
                label_ar="التوفر الموسمي",
                evidence_ar=seasonal_evidence,
                basis=seasonal_basis,
                confidence=seasonal_conf,
            )
        )

        # ── habitat match (declared shore type vs species prior) ──
        if profile.preferred_shores and dataset.spot.shore_type in profile.preferred_shores:
            habitat_status = "favorable"
            habitat_evidence = [
                f"نوع القاع المُعلن ({_shore_label_ar(dataset.spot.shore_type)}) ضمن تفضيلات {profile.label_ar} الأولية.",
                profile.habitat_ar,
            ]
            habitat_conf = 20
        elif profile.preferred_shores:
            habitat_status = "neutral"
            habitat_evidence = [
                f"نوع القاع المُعلن ({_shore_label_ar(dataset.spot.shore_type)}) خارج التفضيلات الأولية؛ تفضيل منخفض الوزن غير معاير محلياً.",
                profile.habitat_ar,
            ]
            habitat_conf = 20
        else:
            habitat_status = "neutral"
            habitat_evidence = ["هدف عام بلا تفضيل موطن محدد."]
            habitat_conf = 15
        axes.append(
            SpeciesAxisValue(
                axis="habitat",
                status=habitat_status,
                label_ar="توافق الموطن",
                evidence_ar=habitat_evidence,
                basis="spot_profile",
                confidence=habitat_conf,
            )
        )

        # ── surf approach (physical tide/current; species response Unknown) ──
        breakdown = field_feasibility.holding_breakdown
        tidal = breakdown.tidal_current if breakdown else PotentialLevel.UNKNOWN
        if tidal == PotentialLevel.HIGH:
            surf_status = "unfavorable"
        elif tidal == PotentialLevel.LOW and spring_neap.classification in {"neap", "intermediate"}:
            surf_status = "favorable"
        elif tidal == PotentialLevel.MODERATE:
            surf_status = "neutral"
        else:
            surf_status = "neutral"
        range_text = (
            f"{spring_neap.range_target_day_m:.2f} م"
            if spring_neap.range_target_day_m is not None
            else "غير متاح"
        )
        rate_text = (
            f"{spring_neap.max_level_rate_m_per_h:.2f} م/س"
            if spring_neap.max_level_rate_m_per_h is not None
            else "غير متاح"
        )
        surf_evidence = [
            f"تصنيف المد: {spring_neap.folk_label_ar} ({spring_neap.classification}) — مدى اليوم {range_text}، أقصى معدل ارتفاع {rate_text}.",
            f"تيار المدّ النموذجي: {_potential_label_ar(tidal)}.",
            "شرط فيزيائي للنشاط المائي قرب الكسرة، لا ادعاء بسلوك السمك.",
        ]
        if spring_neap.gabes_zone:
            surf_evidence.append("منطقة خليج قابس: تيار مدّي أقوى من المعتاد.")
        axes.append(
            SpeciesAxisValue(
                axis="surf_approach",
                status=surf_status,
                label_ar="قابلية الاقتراب من السيرف",
                evidence_ar=surf_evidence,
                basis="model_forecast",
                confidence=25,
            )
        )

        # ── feeding window (twilight/night priors; no Solunar) ──
        lead = recommended[0] if recommended else None
        twilight_lead = (
            lead is not None
            and _window_overlaps_twilight(lead, dataset.sunrise, dataset.sunset)
        )
        night_lead = (
            lead is not None
            and _window_overlaps_night(lead, dataset.sunrise, dataset.sunset)
        )
        if dataset.sunrise is None or dataset.sunset is None:
            feeding_status = "unknown"
            unknown_axes.append("feeding_window")
            feeding_evidence: list[str] = []
            feeding_conf = 5
        elif twilight_lead:
            feeding_status = "favorable"
            feeding_evidence = [
                f"النافذة الأفضل تلامس الغسق (بونص أولي {profile.twilight_bonus} للغسق).",
                f"الشروق {_hm(dataset.sunrise)} · الغروب {_hm(dataset.sunset)} — بلا قاعدة قمرية أو Solunar.",
            ]
            feeding_conf = 20
        elif night_lead and profile.night_bonus:
            feeding_status = "favorable"
            feeding_evidence = [
                f"النافذة الأفضل ليلية (بونص ليلي أولي {profile.night_bonus}).",
                f"الشروق {_hm(dataset.sunrise)} · الغروب {_hm(dataset.sunset)} — بلا قاعدة قمرية أو Solunar.",
            ]
            feeding_conf = 20
        else:
            feeding_status = "neutral"
            feeding_evidence = [
                f"النافذة الأفضل خارج الغسق والليل (بونص الغسق الأولي {profile.twilight_bonus}).",
                f"الشروق {_hm(dataset.sunrise)} · الغروب {_hm(dataset.sunset)} — بلا قاعدة قمرية أو Solunar.",
            ]
            feeding_conf = 20
        axes.append(
            SpeciesAxisValue(
                axis="feeding_window",
                status=feeding_status,
                label_ar="نافذة التغذية",
                evidence_ar=feeding_evidence,
                basis="expert_prior",
                confidence=feeding_conf,
            )
        )

        # ── prey evidence: always Unknown until a catch log / field observation ──
        unknown_axes.append("prey_evidence")
        axes.append(
            SpeciesAxisValue(
                axis="prey_evidence",
                status="unknown",
                label_ar="دليل الفرائس",
                evidence_ar=[],
                basis="unknown",
                confidence=0,
            )
        )

        overall_confidence = min(
            (axis.confidence for axis in axes if axis.status != "unknown"), default=5
        )
        notes = [
            "محور الأنواع تقريري ولا يغيّر القرار الثنائي؛ ضعف فرصة السمك لا يمنع نافذة آمنة قابلة للتنفيذ.",
            "لا احتمال مصيد، ولا أحجام قانونية، ولا فترات منع موسمية (D10).",
            "الأوزان أوزان أولية غير معايرة محلياً؛ تحتاج سجل مصيد تونسي يشمل الحصص الصفرية.",
            "بُعد حالة البحر (هادئ/معتدل/هائج مع الرغوة) تقريري من أنماط متوسطية منشورة، والرغوة تقدير نموذجي لا رصد؛ لا يدخل ترتيب الأنواع ولا القرار.",
        ]
        if profile.spring_neap_response_ar is None:
            notes.append(
                "استجابة النوع للحيّة/المات (spring_neap_response) تبقى Unknown لكل نوع/موقع حتى المعايرة؛ القيمة الفيزيائية وحدها تدخل محور الاقتراب."
            )
        else:
            notes.append(profile.spring_neap_response_ar)

        # ── availability + match for every profiled species (reporting only) ──
        # Answers "ما الأسماك المتوافرة الآن والتي تتماشى مع العوامل الحالية؟"
        # Seasonal presence is the primary signal; thermal and habitat are
        # low-weight expert priors. Never a catch probability (D10/D11).
        sst_values = [
            hour.sea_surface_temperature_c
            for hour in dataset.hours
            if hour.time.date() == dataset.target_date
            and hour.sea_surface_temperature_c is not None
        ]
        sst = round(sum(sst_values) / len(sst_values), 1) if sst_values else None

        # ── sea state x month (reporting only, published Mediterranean patterns) ──
        day_hours = [
            hour for hour in dataset.hours if hour.time.date() == dataset.target_date
        ]
        day_wave_values = [
            hour.wave_height_m for hour in day_hours if hour.wave_height_m is not None
        ]
        day_wind_values = [
            hour.wind_speed_kmh for hour in day_hours if hour.wind_speed_kmh is not None
        ]
        day_wave = round(sum(day_wave_values) / len(day_wave_values), 2) if day_wave_values else None
        day_wind = max(day_wind_values) if day_wind_values else None
        sea_state, foam_estimate = classify_sea_state(day_wave, day_wind)
        if sea_state == "unknown":
            sea_state_ar = "حالة البحر غير متاحة (لا بيانات موج نموذجية لهذا اليوم)"
            foam_text = ""
        else:
            foam_text = "، رغوة محتملة (تقدير نموذجي)" if foam_estimate else ""
            sea_state_ar = (
                f"{SEA_STATE_LABELS_AR[sea_state]} (موج نموذجي ~{day_wave:.1f} م{foam_text})"
            )

        species_matches: list[SpeciesMatch] = []
        for species_key, species_profile in SPECIES_PROFILES.items():
            if species_key == TargetSpecies.GENERAL:
                continue
            presence = species_profile.monthly_presence(zone, month)
            availability = _availability_for(presence)
            if sst is None or species_profile.preferred_sst_c is None:
                thermal = "unknown"
            else:
                pref_low, pref_high = species_profile.preferred_sst_c
                tol_low, tol_high = species_profile.tolerated_sst_c or (pref_low, pref_high)
                if pref_low <= sst <= pref_high:
                    thermal = "preferred"
                elif tol_low <= sst <= tol_high:
                    thermal = "tolerated"
                else:
                    thermal = "outside"

            if species_profile.preferred_shores:
                habitat_match = dataset.spot.shore_type in species_profile.preferred_shores
            else:
                habitat_match = None

            status = _species_match_status(presence, thermal, habitat_match)

            sea_pref = species_profile.sea_state_preference
            sea_state_fit = sea_state_fit_for(sea_pref, sea_state)
            sea_state_preference_ar = sea_pref.label_ar if sea_pref else ""

            reasons: list[str] = []
            zone_label = ZONE_LABELS_AR.get(zone, zone)
            month_label = MONTHS_AR[month - 1]
            if presence is None:
                reasons.append(f"التوفر الموسمي غير مدقق بعد لمنطقة {zone_label}.")
            elif presence == 0:
                reasons.append(f"غير متوفر موسمياً في {zone_label} خلال {month_label}.")
            else:
                reasons.append(
                    f"توفر موسمي {PRESENCE_LABELS_AR[presence]} في {zone_label} خلال {month_label}."
                )
            if sst is not None and species_profile.preferred_sst_c is not None:
                if thermal == "preferred":
                    reasons.append(f"حرارة الماء {sst}°م ضمن المجال المفضّل الأولي.")
                elif thermal == "tolerated":
                    reasons.append(f"حرارة الماء {sst}°م ضمن مجال التحمل الأولي.")
                elif thermal == "outside":
                    reasons.append(f"حرارة الماء {sst}°م خارج مجال التحمل الأولي.")
            elif sst is None:
                reasons.append("حرارة سطح البحر غير متوفرة؛ حُذف محور الحرارة.")
            if habitat_match is True:
                reasons.append("نوع القاع ضمن تفضيلات النوع الأولية.")
            elif habitat_match is False:
                reasons.append("نوع القاع خارج تفضيلات النوع الأولية.")
            if sea_state == "unknown":
                reasons.append("حالة البحر غير متاحة لهذا اليوم؛ بُعد حالة البحر Unknown.")
            elif sea_state_fit == "favorable":
                reasons.append(
                    f"حالة البحر اليوم {SEA_STATE_LABELS_AR[sea_state]}{foam_text} — نمط مناسب لهذا النوع ({sea_state_preference_ar or 'بلا تفضيل منشور'})."
                )
            else:
                reasons.append(
                    f"حالة البحر اليوم {SEA_STATE_LABELS_AR[sea_state]}{foam_text} — خارج التفضيل المنشور ({sea_state_preference_ar or 'بلا تفضيل منشور'})، يُعامل محايداً."
                )

            match_sources: list[str] = []
            for source_key in species_profile.sources:
                source = SOURCE_REGISTRY.get(source_key)
                if source is None:
                    continue
                label = source["label_ar"]
                citation = source["citation"]
                url = source.get("url", "")
                url_suffix = f" — {url}" if url else ""
                match_sources.append(f"{label}: {citation}{url_suffix}")

            species_matches.append(
                SpeciesMatch(
                    species=species_key.value,
                    label_ar=species_profile.label_ar,
                    availability=availability,
                    thermal=thermal,
                    habitat_match=habitat_match,
                    status=status,
                    reasons_ar=reasons,
                    sources_ar=match_sources,
                    sea_state_ar=sea_state_ar,
                    sea_state_preference_ar=sea_state_preference_ar,
                    sea_state_fit=sea_state_fit,
                )
            )

        status_rank = {"favorable": 3, "neutral": 2, "unfavorable": 1, "unknown": 0}
        availability_rank = {"strong": 3, "medium": 2, "weak": 1, "unavailable": 0, "unknown": -1}
        species_matches.sort(key=lambda match: match.label_ar)
        species_matches.sort(
            key=lambda match: (status_rank[match.status], availability_rank[match.availability]),
            reverse=True,
        )

        # Aggregate bibliography: every study backing any profiled species.
        bibliography: list[str] = []
        for _source_key, source in SOURCE_REGISTRY.items():
            label = source["label_ar"]
            citation = source["citation"]
            url = source.get("url", "")
            url_suffix = f" — {url}" if url else ""
            bibliography.append(f"{label}: {citation}{url_suffix}")

        return SpeciesAxes(
            target_species=dataset.angler.target_species,
            label_ar=profile.label_ar,
            axes=axes,
            unknown_axes=unknown_axes,
            confidence=overall_confidence,
            notes_ar=notes,
            species_matches=species_matches,
            sources_ar=bibliography,
            sea_state_ar=sea_state_ar,
        )

    def _species_activity(
        self,
        dataset: ForecastDataset,
        hourly: list[HourDecision],
    ) -> list[SpeciesActivity]:
        """Reporting-only relative activity indicator (0-100) per species per hour.

        Uses the same documented low-weight priors as the rest of the engine and
        the same day-level SST/sea-state values as the species matches, so the
        panel stays consistent with the rest of the report. Never a catch
        probability and never feeds the binary decision (D10/D11).
        """
        zone = tunisian_zone(dataset.location.latitude, dataset.location.longitude)
        month = dataset.target_date.month
        shore_type = dataset.spot.shore_type

        day_hours = [
            item for item in dataset.hours if item.time.date() == dataset.target_date
        ]
        day_wave_values = [
            item.wave_height_m for item in day_hours if item.wave_height_m is not None
        ]
        day_wind_values = [
            item.wind_speed_kmh for item in day_hours if item.wind_speed_kmh is not None
        ]
        day_wave = (
            round(sum(day_wave_values) / len(day_wave_values), 2) if day_wave_values else None
        )
        day_wind = max(day_wind_values) if day_wind_values else None
        sea_state, _foam = classify_sea_state(day_wave, day_wind)

        sst_values = [
            item.sea_surface_temperature_c
            for item in dataset.hours
            if item.time.date() == dataset.target_date
            and item.sea_surface_temperature_c is not None
        ]
        sst = round(sum(sst_values) / len(sst_values), 1) if sst_values else None

        ordered_keys = [
            key for key in SPECIES_PROFILES if key != TargetSpecies.GENERAL
        ] + [TargetSpecies.GENERAL]
        activities: list[SpeciesActivity] = []
        for species_key in ordered_keys:
            profile = SPECIES_PROFILES[species_key]
            entries: list[tuple[HourActivity, str]] = []
            for hour in hourly:
                score, contributions = _species_hour_activity(
                    profile,
                    hour,
                    sst=sst,
                    sea_state=sea_state,
                    zone=zone,
                    month=month,
                    shore_type=shore_type,
                )
                activity = HourActivity(
                    time=hour.time,
                    score=score,
                    is_twilight=hour.derived.is_twilight,
                    is_night=hour.derived.is_night,
                )
                entries.append((activity, _activity_top_factor(contributions)))
            activities.append(
                SpeciesActivity(
                    species=species_key.value,
                    label_ar=profile.label_ar,
                    basis_ar=_activity_basis_ar(profile),
                    periods=_activity_periods(entries),
                    hourly=[activity for activity, _top in entries],
                )
            )
        return activities

    def _overall_confidence(
        self, hourly: list[HourDecision], recommended: list[DecisionWindow]
    ) -> ConfidenceResult:
        if recommended:
            window = recommended[0]
            covered = [item for item in hourly if window.start <= item.time < window.end]
            score = min(item.confidence.score for item in covered)
            reasons = _unique(reason for item in covered for reason in item.confidence.reasons_ar)
            reasons.insert(0, "القيمة هي أضعف ثقة ساعية داخل أفضل نافذة، كإجراء محافظ.")
        else:
            score = min(item.confidence.score for item in hourly)
            reasons = _unique(reason for item in hourly for reason in item.confidence.reasons_ar)
            reasons.insert(0, "لا توجد نافذة موصى بها؛ عُرضت أضعف ثقة خلال اليوم.")
        return ConfidenceResult(
            score=score,
            band=_confidence_band(score),
            reasons_ar=reasons[:6],
        )

    def _factor_assessments(
        self,
        dataset: ForecastDataset,
        hourly: list[HourDecision],
        field_feasibility: FieldFeasibilityResult,
        decision: DecisionLevel,
        reason_code: DecisionReasonCode,
    ) -> list[FactorAssessment]:
        """Materialize one explicit runtime assessment for every audited matrix row."""

        def forecast_values(name: str) -> list[float]:
            return [
                float(value)
                for item in hourly
                if (value := getattr(item.forecast, name)) is not None
            ]

        def derived_values(name: str) -> list[float]:
            return [
                float(value)
                for item in hourly
                if (value := getattr(item.derived, name)) is not None
                and not isinstance(value, bool)
            ]

        def span(
            name: str,
            unit: str,
            *,
            derived: bool = False,
            digits: int = 1,
            divisor: float = 1.0,
        ) -> str:
            raw_values = derived_values(name) if derived else forecast_values(name)
            if not raw_values:
                return "Unknown — المتغير غير متوفر في الساعات المقيمة"
            values = [value / divisor for value in raw_values]
            low, high = min(values), max(values)
            if abs(high - low) < 10 ** (-digits):
                return f"{high:.{digits}f} {unit}".strip()
            return f"{low:.{digits}f}-{high:.{digits}f} {unit}".strip()

        def signed_span(values: list[float], unit: str, digits: int = 1) -> str:
            if not values:
                return "Unknown — المتغير غير متوفر في الساعات المقيمة"
            low, high = min(values), max(values)
            if abs(high - low) < 10 ** (-digits):
                return f"{high:+.{digits}f} {unit}"
            return f"{low:+.{digits}f} إلى {high:+.{digits}f} {unit}"

        derived_reference = hourly[0].derived
        relation_values = _unique([WIND_RELATION_AR[item.derived.wind_relation] for item in hourly])
        incidence_values = _unique(
            [WAVE_INCIDENCE_AR[item.derived.wave_incidence] for item in hourly]
        )
        tide_values = _unique([TIDE_STATE_AR[item.derived.tide_state] for item in hourly])
        orientation = dataset.spot.seaward_orientation_deg
        rain_48 = derived_reference.rain_48h_mm
        energy_48 = derived_reference.wave_energy_integral_48h
        wind_fraction_48 = derived_reference.onshore_wind_fraction_48h
        current_impulse_48 = derived_reference.shoreward_current_impulse_48h_kmh_h
        max_wave_48 = derived_reference.max_wave_height_48h_m
        pressure_changes_3h = derived_values("pressure_change_3h_hpa")
        pressure_change_text = signed_span(pressure_changes_3h, "hPa/3س")
        pressure_drops_3h = [value for value in pressure_changes_3h if value < 0]
        pressure_drop_text = (
            f"أكبر هبوط {abs(min(pressure_drops_3h)):.1f} hPa خلال 3س؛ نطاق التغير {pressure_change_text}"
            if pressure_drops_3h
            else f"لم يظهر هبوط؛ نطاق التغير {pressure_change_text}"
            if pressure_changes_3h
            else pressure_change_text
        )
        source_count = len(dataset.sources)
        shore_label = _SHORE_TYPE_LABELS_AR[dataset.spot.shore_type.value]
        orientation_source_label = _ORIENTATION_SOURCE_LABELS_AR[
            dataset.spot.orientation_source.value
        ]
        current_impulse_text = (
            f"{current_impulse_48:.1f} كم/س·س" if current_impulse_48 is not None else "Unknown"
        )
        max_wave_text = f"{max_wave_48:.2f} م" if max_wave_48 is not None else "Unknown"
        energy_text = f"{energy_48:.1f} Hs²T·h" if energy_48 is not None else "Unknown"
        water_context = dataset.coastal_water_context
        satellite_text = "Unknown — لا توجد استعادة Sentinel-2 صالحة عند نقطة العينة الثابتة"
        if water_context is not None and water_context.availability == "unavailable":
            satellite_text = f"Unknown — {water_context.reason_ar}"
        if water_context is not None and water_context.availability == "available":
            satellite_values = []
            if water_context.turbidity_fnu is not None:
                satellite_values.append(f"TUR {water_context.turbidity_fnu:.2f} FNU")
            if water_context.suspended_particulate_matter_g_m3 is not None:
                satellite_values.append(
                    f"SPM {water_context.suspended_particulate_matter_g_m3:.2f} g/m³"
                )
            if water_context.chlorophyll_a_mg_m3 is not None:
                satellite_values.append(f"CHL-a {water_context.chlorophyll_a_mg_m3:.2f} mg/m³")
            valid_date_text = (
                water_context.valid_time.date().isoformat()
                if water_context.valid_time is not None
                else "Unknown"
            )
            age_text = (
                f"{water_context.age_hours:.0f}س"
                if water_context.age_hours is not None
                else "Unknown"
            )
            satellite_text = (
                f"Sentinel-2 سياقي بتاريخ {valid_date_text} وعمر {age_text}: "
                f"{'؛ '.join(satellite_values)}. "
                "استعادة أقمار صناعية وليست قياساً ميدانياً أو توقعاً"
            )
        values: dict[str, str] = {
            "1.1": span("wind_speed_kmh", "كم/س"),
            "1.2": f"الريح {span('wind_speed_kmh', 'كم/س')}؛ الهبّات {span('wind_gust_kmh', 'كم/س')}",
            "1.3": (
                f"أقصى تحول ساعي {span('max_wind_direction_shift_6h_deg', '°/ساعة', derived=True, digits=0)}؛ "
                f"تماسك دائري R {span('wind_direction_coherence_6h', '', derived=True, digits=2)} مع استبعاد الريح دون 5 كم/س"
            ),
            "1.4": (
                f"{span('wind_speed_kmh', 'كم/س')}؛ التصنيف: {'، '.join(relation_values)}؛ "
                f"إجهاد ريح تشخيصي {span('wind_stress_pa', 'Pa', derived=True, digits=4)}"
            ),
            "1.6": f"اتجاه البحر {orientation:.1f}°؛ {'، '.join(relation_values)}",
            "1.7": "تسلسل ساعي متاح؛ " + "، ".join(relation_values),
            "1.8": span("pressure_msl_hpa", "hPa"),
            "1.9": pressure_drop_text,
            "1.10": pressure_change_text,
            "1.11": f"اتجاه الريح {span('wind_direction_deg', '°', digits=0)}",
            "1.12": f"حرارة {span('air_temperature_c', '°C')}؛ رطوبة {span('relative_humidity_pct', '%', digits=0)}",
            "1.14": span("visibility_m", "كم", digits=1, divisor=1_000.0),
            "1.15": f"رموز الطقس {span('weather_code', '', digits=0)}؛ CAPE {span('cape_jkg', 'جول/كغ', digits=0)}؛ مؤشر lightning_potential {span('lightning_potential_jkg', 'جول/كغ', digits=0)}. غياب مؤشر فرعي لا يعني غياب البرق؛ يلزم تحقق رسمي وميداني",
            "1.16": f"UV {span('uv_index', '')}؛ إشعاع {span('shortwave_radiation_wm2', 'W/m²', digits=0)}",
            "2.1": (
                f"ارتفاع {span('wave_height_m', 'م')}؛ فترة {span('wave_period_s', 'ث')}؛ {'، '.join(incidence_values)}؛ "
                f"زاوية موج الريح/السويل {span('wave_component_angle_deg', '°', derived=True, digits=0)}؛ "
                f"حصة النظام الأضعف {span('wave_component_secondary_energy_share', '', derived=True, digits=2)} (تشخيص بلا عتبة)"
            ),
            "2.2": f"احتمال {_potential_label_ar(field_feasibility.fouling_transport_potential)}؛ {field_feasibility.fouling_evidence_count} عائلات قرائن تشغيلية مختلفة/48س وليست مصادر مستقلة؛ لا رصد وجود؛ تنبيه غير مانع وحده",
            "2.3": f"سرعة التيار {span('ocean_current_velocity_kmh', 'كم/س')}؛ دفع شاطئي تراكمي 48س {current_impulse_text}",
            "2.4": f"ارتفاع الموج {span('wave_height_m', 'م')}؛ إشعاع {span('shortwave_radiation_wm2', 'W/m²', digits=0)}",
            "2.5": f"احتمال {_potential_label_ar(field_feasibility.rip_current_potential)}؛ بلا باتيمتريا أو مشاهدة للكسرة",
            "2.6": (
                f"احتمال {_potential_label_ar(field_feasibility.turbidity_potential)} من {field_feasibility.turbidity_evidence_count} عائلات قرائن تشغيلية مختلفة/48س وليست مصادر مستقلة؛ "
                f"NTU غير مقاس وتنبيه غير مانع وحده؛ {satellite_text}"
            ),
            "2.7": f"مستوى البحر النموذجي {span('sea_level_height_msl_m', 'م MSL', digits=2)}؛ لا يمكن فصل ارتفاع عاصفي عن المد والمرجع بهذا المتغير وحده",
            "2.8": f"أقصى موج سابق 48س {max_wave_text}؛ طاقة تراكمية {energy_text}",
            "2.9": span("sea_surface_temperature_c", "°C"),
            "3.2": span("sea_level_height_msl_m", "م MSL"),
            "3.3": f"{span('sea_level_rate_m_per_h', 'م/ساعة', derived=True, digits=3)}؛ حالات: {'، '.join(tide_values)}",
            "3.5": f"الشروق {dataset.sunrise:%H:%M}"
            if dataset.sunrise
            else "Unknown — الشروق غير متوفر",
            "4.1": f"حرارة السطح {span('sea_surface_temperature_c', '°م')}؛ تغير 24س {span('sea_surface_temperature_change_24h_c', '°م/24س', derived=True)}",
            "4.5": satellite_text,
            "6.4": f"نوع الوقوف المدخل: {shore_label}",
            "8.6": f"ثقة المدخلات {min(item.confidence.score for item in hourly)}/100؛ {source_count} مصادر موثقة؛ اتجاه البحر {orientation_source_label}",
        }
        values["3.5"] += (
            f"؛ الغروب {dataset.sunset:%H:%M}" if dataset.sunset else "؛ الغروب Unknown"
        )
        values["2.2"] += (
            f"؛ مطر 48س {rain_48:.1f} مم" if rain_48 is not None else "؛ مطر 48س Unknown"
        )
        values["2.2"] += (
            f"؛ ريح بحرية {wind_fraction_48 * 100:.0f}%"
            if wind_fraction_48 is not None
            else "؛ ريح بحرية Unknown"
        )

        active_codes = {factor.code for hour in hourly for factor in hour.factors}
        active_factor_ids: set[str] = set()
        if reason_code == DecisionReasonCode.SAFE_WINDOW:
            active_factor_ids.update({"1.1", "1.6", "1.14", "1.15", "2.1", "2.2", "2.6", "8.6"})
        elif reason_code == DecisionReasonCode.FIELD_INFEASIBLE:
            if field_feasibility.holding_difficulty == PotentialLevel.HIGH:
                active_factor_ids.update({"2.1", "2.3"})
        elif reason_code == DecisionReasonCode.CRITICAL_DATA_MISSING:
            active_factor_ids.add("8.6")
            if any(item.forecast.wind_speed_kmh is None for item in hourly):
                active_factor_ids.add("1.1")
            if any(item.forecast.wind_direction_deg is None for item in hourly):
                active_factor_ids.add("1.6")
            if any(
                item.forecast.wave_height_m is None
                or item.forecast.wave_period_s is None
                or item.forecast.wave_direction_deg is None
                for item in hourly
            ):
                active_factor_ids.add("2.1")
            if field_feasibility.fouling_transport_potential == PotentialLevel.UNKNOWN:
                active_factor_ids.add("2.2")
            if field_feasibility.turbidity_potential == PotentialLevel.UNKNOWN:
                active_factor_ids.add("2.6")
        else:
            active_factor_ids.add("8.6")

        if reason_code == DecisionReasonCode.SAFETY_HAZARD:
            code_groups = {
                "1.1": ("sustained_wind", "nearby_observed_wind"),
                "1.2": ("gust_",),
                "1.3": ("abrupt_forecast_wind_shift",),
                "1.4": ("onshore_wind_wave",),
                "1.6": ("onshore_wind_wave",),
                "1.14": ("visibility_",),
                "1.15": ("thunderstorm", "convective_", "nearby_metar_thunderstorm"),
                "1.16": ("very_high_uv",),
                "2.1": ("wave_height_", "steep_wave_"),
                "2.5": ("elevated_rip_current",),
                "8.6": ("station_model_divergence", "missing_critical"),
            }
            for matrix_id, prefixes in code_groups.items():
                if any(code.startswith(prefix) for code in active_codes for prefix in prefixes):
                    active_factor_ids.add(matrix_id)

        assessments: list[FactorAssessment] = []
        for item in MATRIX_FACTORS:
            value = values.get(item.matrix_id)
            if item.status == CatalogStatus.EXCLUDED_UNSUPPORTED:
                status = FactorAssessmentStatus.EXCLUDED
                value = "مستبعد من القرار: لا توجد علاقة سببية عامة قابلة للدفاع أو بيانات تشغيلية كافية."
            elif item.matrix_id == "2.6":
                if field_feasibility.turbidity_potential != PotentialLevel.UNKNOWN:
                    status = FactorAssessmentStatus.PROXY
                elif water_context is not None and water_context.availability == "available":
                    status = FactorAssessmentStatus.CONTEXT
                else:
                    status = FactorAssessmentStatus.UNKNOWN
            elif item.matrix_id == "4.5":
                status = (
                    FactorAssessmentStatus.CONTEXT
                    if water_context is not None and water_context.availability == "available"
                    else FactorAssessmentStatus.UNKNOWN
                )
            elif item.status == CatalogStatus.FIELD_OR_EXTERNAL_REQUIRED:
                status = FactorAssessmentStatus.UNKNOWN
                value = f"Unknown — يلزم رصد ميداني أو مصدر خارجي: {item.data_basis_ar}"
            elif item.status == CatalogStatus.PROXY_REQUIRES_FIELD_CHECK:
                status = (
                    FactorAssessmentStatus.PROXY
                    if value is not None and "Unknown" not in value[:15]
                    else FactorAssessmentStatus.UNKNOWN
                )
            elif item.status == CatalogStatus.AUTOMATED_DECISION:
                status = (
                    FactorAssessmentStatus.DECISION
                    if value is not None and not value.startswith("Unknown")
                    else FactorAssessmentStatus.UNKNOWN
                )
            else:
                status = (
                    FactorAssessmentStatus.CONTEXT
                    if value is not None and not value.startswith("Unknown")
                    else FactorAssessmentStatus.UNKNOWN
                )
            if value is None:
                value = "Unknown — لا توجد قيمة تشغيلية موثوقة لهذا العامل في Evidence Packet."
                status = FactorAssessmentStatus.UNKNOWN
            affects = item.matrix_id in active_factor_ids and status in {
                FactorAssessmentStatus.DECISION,
                FactorAssessmentStatus.PROXY,
            }
            assessments.append(
                FactorAssessment(
                    matrix_id=item.matrix_id,
                    chapter_ar=item.chapter_ar,
                    title_ar=item.title_ar,
                    status=status,
                    decision_axis=item.decision_axis,
                    value_ar=value,
                    evidence_variables=list(item.variables),
                    rationale_ar=item.rationale_ar,
                    affects_final_decision=affects,
                )
            )
        return assessments

    def _summary(
        self,
        decision: DecisionLevel,
        recommended: list[DecisionWindow],
        hourly: list[HourDecision],
        opportunity: int,
        confidence: int,
        field_feasibility: FieldFeasibilityResult,
        reason_code: DecisionReasonCode,
    ) -> str:
        if decision == DecisionLevel.GO and recommended:
            best = recommended[0]
            opportunity_note = (
                " فرصة الصيد ضعيفة نسبياً لكنها لا تلغي نافذة اجتازت الحدود الآلية المتاحة."
                if opportunity < 45
                else ""
            )
            elevated_proxy_labels = [
                label
                for potential, label in (
                    (
                        field_feasibility.fouling_transport_potential,
                        "قابلية نقل الصوفة أو الحطام",
                    ),
                    (field_feasibility.turbidity_potential, "قابلية التعكير"),
                )
                if potential == PotentialLevel.HIGH
            ]
            proxy_note = (
                " تنبيه غير مانع آلياً: "
                + " و".join(elevated_proxy_labels)
                + " مرتفعة كنموذج نقل غير معاير وليست رصداً؛ يلزم فحص الماء ورمية اختبارية."
                if elevated_proxy_labels
                else ""
            )
            return (
                f"التوصية: {'اذهب بحذر' if best.safety == DecisionLevel.CAUTION else 'اذهب'} فقط في النافذة من {_time_range_ar(best.start, best.end)}؛ "
                "هذا اجتياز لحدود المحرك وليس شهادة سلامة ميدانية. "
                f"مؤشر الفرصة {opportunity}/100، قابلية التنفيذ {field_feasibility.score}/100، وثقة المدخلات {confidence}/100."
                f"{opportunity_note}{proxy_note} تحقق ميدانياً من الكسرة والتيار الساحبي والصوفة قبل بدء الصيد."
            )

        reason_labels = {
            DecisionReasonCode.SAFETY_HAZARD: "خطر سلامة أو تجاوز محافظ داخل النافذة",
            DecisionReasonCode.FIELD_INFEASIBLE: "صعوبة مرتفعة متوقعة في تثبيت الخط داخل أفضل نافذة",
            DecisionReasonCode.CRITICAL_DATA_MISSING: "نقص بيانات حرجة للسلامة أو قابلية التنفيذ",
            DecisionReasonCode.CONSERVATIVE_UNCERTAINTY: "تحفظ محافظ لأن الثقة لا تكفي للحسم الإيجابي",
            DecisionReasonCode.SAFE_WINDOW: "نافذة اجتازت الحدود الآلية وقابلة للتنفيذ مبدئياً",
            DecisionReasonCode.FOULING_CONFIRMED: "صوفة أو حطام كثيف مؤكد حديثاً في البقعة",
            DecisionReasonCode.OFFICIAL_WARNING: "تحذير رسمي ساري يلغي الرحلة",
            DecisionReasonCode.TRIP_RUIN_CONFIRMED: "عامل مُفسِد مؤكد (قناديل/حطام/تعكر كثيف) يجعل الخرجة غير مجدية",
        }
        detail = reason_labels[reason_code]
        causes = _critical_factor_labels(hourly)
        if causes and reason_code == DecisionReasonCode.SAFETY_HAZARD:
            detail += ": " + "، ".join(causes[:3])
        return (
            f"التوصية: لا تذهب. السبب الرئيسي: {detail}. "
            "لا تسمح درجة فرصة الصيد بتجاوز بوابة السلامة أو نقص البيانات الحرجة أو قابلية التنفيذ."
        )


def _compare_current_weather_observation(
    dataset: ForecastDataset,
    all_hours: list[ForecastHour],
) -> ObservationComparison:
    observation = dataset.current_weather_observation
    if observation is None:
        return ObservationComparison(
            status=ObservationMatchStatus.UNAVAILABLE,
            reasons_ar=[
                "لا يتوفر رصد METAR صالح الآن؛ تبقى السلسلة الجوية والبحرية توقعاً نموذجياً."
            ],
        )

    clock_offset_minutes = (observation.observed_at - dataset.fetched_at).total_seconds() / 60.0
    age_minutes = max(0.0, -clock_offset_minutes)
    common = {
        "observation_age_minutes": round(age_minutes, 1),
        "station_distance_km": observation.distance_to_spot_km,
    }
    if clock_offset_minutes > 10.0:
        return ObservationComparison(
            status=ObservationMatchStatus.NOT_APPLICABLE,
            reasons_ar=[
                "زمن رصد المحطة يتقدم وقت الجلب بأكثر من 10 دقائق؛ عُزل كسجل غير صالح زمنياً."
            ],
            **common,
        )
    if dataset.target_date != dataset.fetched_at.date():
        return ObservationComparison(
            status=ObservationMatchStatus.NOT_APPLICABLE,
            reasons_ar=["رصد المحطة لقطة حالية ولا يُعامل كرصد لتاريخ مستقبلي أو ماضٍ."],
            **common,
        )
    if age_minutes > 120.0:
        return ObservationComparison(
            status=ObservationMatchStatus.STALE,
            reasons_ar=[f"آخر رصد متاح عمره {age_minutes:.0f} دقيقة؛ لم يدخل بوابة القرار."],
            **common,
        )
    if observation.distance_to_spot_km > 150.0:
        return ObservationComparison(
            status=ObservationMatchStatus.DISTANT,
            reasons_ar=[
                f"أقرب محطة متاحة تبعد {observation.distance_to_spot_km:.1f} كم؛ لا تمثل البقعة مكانياً."
            ],
            **common,
        )
    if not all_hours:
        return ObservationComparison(
            status=ObservationMatchStatus.NOT_APPLICABLE,
            reasons_ar=["لا توجد ساعة نموذجية قريبة لمقارنة رصد المحطة بها."],
            **common,
        )

    closest = min(
        all_hours,
        key=lambda item: abs((item.time - observation.observed_at).total_seconds()),
    )
    time_gap_minutes = abs((closest.time - observation.observed_at).total_seconds()) / 60.0
    if time_gap_minutes > 90.0:
        return ObservationComparison(
            status=ObservationMatchStatus.NOT_APPLICABLE,
            reasons_ar=["لا توجد ساعة نموذجية ضمن 90 دقيقة من زمن الرصد."],
            **common,
        )

    wind_difference = _absolute_difference(
        observation.wind_speed_kmh,
        closest.wind_speed_kmh,
    )
    direction_difference = (
        circular_difference_deg(observation.wind_direction_deg, closest.wind_direction_deg)
        if observation.wind_direction_deg is not None
        and closest.wind_direction_deg is not None
        and (observation.wind_speed_kmh or 0.0) >= 5.0
        and (closest.wind_speed_kmh or 0.0) >= 5.0
        else None
    )
    temperature_difference = _absolute_difference(
        observation.air_temperature_c,
        closest.air_temperature_c,
    )
    # QNH (altimeter setting) is not physically comparable to model mean sea-level
    # pressure, so the pressure check only runs for stations reporting real SLP.
    pressure_difference = (
        _absolute_difference(observation.pressure_hpa, closest.pressure_msl_hpa)
        if observation.pressure_kind == "sea_level_pressure"
        else None
    )
    comparable = {
        "compared_forecast_time": closest.time,
        "wind_speed_difference_kmh": _rounded(wind_difference, 1),
        "wind_direction_difference_deg": _rounded(direction_difference, 1),
        "temperature_difference_c": _rounded(temperature_difference, 1),
        "pressure_difference_hpa": _rounded(pressure_difference, 1),
        **common,
    }

    divergence_signals: list[str] = []
    pressure_note = (
        "حُجبت مقارنة الضغط لأن METAR وفر إعداد مقياس الارتفاع QNH لا قيمة SLP مستقلة؛ لا يُقارن QNH بضغط سطح البحر النموذجي."
        if observation.pressure_kind == "altimeter_setting"
        else ""
    )
    if wind_difference is not None and wind_difference >= 15.0:
        divergence_signals.append(f"فرق سرعة الريح {wind_difference:.1f} كم/س")
    if direction_difference is not None and direction_difference >= 60.0:
        divergence_signals.append(f"فرق اتجاه الريح {direction_difference:.0f}°")
    if temperature_difference is not None and temperature_difference >= 8.0:
        divergence_signals.append(f"فرق الحرارة {temperature_difference:.1f}°م")
    if pressure_difference is not None and pressure_difference >= 8.0:
        divergence_signals.append(f"فرق الضغط {pressure_difference:.1f} هكتوباسكال")

    if observation.distance_to_spot_km > 75.0:
        reasons = [
            f"المقارنة حسابية فقط لأن المحطة تبعد {observation.distance_to_spot_km:.1f} كم؛ لم تعدّل ثقة القرار."
        ]
        if divergence_signals:
            reasons.append("الفروق المرصودة: " + "، ".join(divergence_signals) + ".")
        if pressure_note:
            reasons.append(pressure_note)
        return ObservationComparison(
            status=ObservationMatchStatus.LIMITED,
            affects_confidence=False,
            reasons_ar=reasons,
            **comparable,
        )
    if divergence_signals:
        reasons = [
            "ظهر اختلاف مهم بين رصد المحطة والنموذج: "
            + "، ".join(divergence_signals)
            + ". لا يعني ذلك أن قراءة المطار هي حالة الشاطئ."
        ]
        if pressure_note:
            reasons.append(pressure_note)
        return ObservationComparison(
            status=ObservationMatchStatus.DIVERGENT,
            affects_confidence=True,
            reasons_ar=reasons,
            **comparable,
        )
    reasons = [
        "لا يوجد اختلاف كبير ضمن المتغيرات القابلة للمقارنة، مع بقاء محدودية المسافة واختلاف موقع المطار عن الساحل."
    ]
    if pressure_note:
        reasons.append(pressure_note)
    return ObservationComparison(
        status=ObservationMatchStatus.CONSISTENT,
        affects_confidence=False,
        reasons_ar=reasons,
        **comparable,
    )


def _absolute_difference(left: float | None, right: float | None) -> float | None:
    return abs(left - right) if left is not None and right is not None else None


def _trailing_hours(
    hours: list[ForecastHour],
    moment: datetime,
    window_hours: int,
) -> list[ForecastHour]:
    start = moment - timedelta(hours=window_hours)
    return [item for item in hours if start < item.time <= moment]


def _rain_total_mm(hours: list[ForecastHour]) -> float | None:
    values = [item.precipitation_mm for item in hours if item.precipitation_mm is not None]
    return sum(values) if values else None


def _maximum(values: Iterable[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return max(available) if available else None


def _max_consecutive_wind_shift_deg(hours: list[ForecastHour]) -> float | None:
    """Largest adjacent-hour direction change with meaningful wind on both ends."""
    valid_pairs = [
        circular_difference_deg(previous.wind_direction_deg, current.wind_direction_deg)
        for previous, current in pairwise(hours)
        if previous.wind_speed_kmh is not None
        and current.wind_speed_kmh is not None
        and previous.wind_speed_kmh >= 5.0
        and current.wind_speed_kmh >= 5.0
        and previous.wind_direction_deg is not None
        and current.wind_direction_deg is not None
        and timedelta(minutes=30) <= current.time - previous.time <= timedelta(minutes=90)
    ]
    return max(valid_pairs) if valid_pairs else None


def _onshore_wind_fraction(
    hours: list[ForecastHour],
    seaward_orientation_deg: float,
) -> float | None:
    valid = [
        item
        for item in hours
        if item.wind_speed_kmh is not None and item.wind_direction_deg is not None
    ]
    if not valid:
        return None
    onshore = {WindRelation.ONSHORE, WindRelation.CROSS_ONSHORE}
    transporting = sum(
        item.wind_speed_kmh >= 8
        and classify_wind(item.wind_direction_deg, seaward_orientation_deg)[0] in onshore
        for item in valid
        if item.wind_speed_kmh is not None
    )
    return transporting / len(valid)


def _energetic_wave_fraction(hours: list[ForecastHour]) -> float | None:
    energies = [
        value
        for item in hours
        if (value := wave_energy_proxy(item.wave_height_m, item.wave_period_s)) is not None
    ]
    if not energies:
        return None
    return sum(value >= 2.0 for value in energies) / len(energies)


def _wave_energy_integral(hours: list[ForecastHour]) -> float | None:
    """Hourly integral of the transparent relative wave-energy proxy Hs²T.

    Forecast samples are hourly. The unit is therefore a relative m²·s·h index, not
    measured energy or bottom stress.
    """
    values = [
        value
        for item in hours
        if (value := wave_energy_proxy(item.wave_height_m, item.wave_period_s)) is not None
    ]
    return sum(values) if values else None


def _onshore_wind_impulse(
    hours: list[ForecastHour], seaward_orientation_deg: float
) -> float | None:
    values: list[float] = []
    for item in hours:
        shoreward, _ = incoming_direction_components(
            item.wind_speed_kmh,
            item.wind_direction_deg,
            seaward_orientation_deg,
        )
        if shoreward is not None:
            values.append(max(0.0, shoreward))
    return sum(values) if values else None


def _onshore_wind_stress_impulse(
    hours: list[ForecastHour], seaward_orientation_deg: float
) -> float | None:
    """Hourly sum of positive shoreward neutral wind stress, in Pa·h."""
    values: list[float] = []
    for item in hours:
        _, shoreward, _ = wind_stress_signed_components(
            item.wind_speed_kmh,
            item.wind_direction_deg,
            seaward_orientation_deg,
        )
        if shoreward is not None:
            values.append(max(0.0, shoreward))
    return sum(values) if values else None


def _shoreward_current_impulse(
    hours: list[ForecastHour], seaward_orientation_deg: float
) -> float | None:
    values: list[float] = []
    for item in hours:
        _, cross_shore = project_current(
            item.ocean_current_velocity_kmh,
            item.ocean_current_direction_deg,
            seaward_orientation_deg,
        )
        if cross_shore is not None:
            # Current direction is "towards"; negative cross-shore points towards land.
            values.append(max(0.0, -cross_shore))
    return sum(values) if values else None


def _potential_level(points: int, *, moderate_at: int, high_at: int) -> PotentialLevel:
    if points >= high_at:
        return PotentialLevel.HIGH
    if points >= moderate_at:
        return PotentialLevel.MODERATE
    return PotentialLevel.LOW


def _potential_label_ar(value: PotentialLevel) -> str:
    return {
        PotentialLevel.LOW: "منخفض في الفحص الآلي ولا ينفي الخطر",
        PotentialLevel.MODERATE: "متوسط ويحتاج تحققاً ميدانياً",
        PotentialLevel.HIGH: "مرتفع ويستوجب الحذر",
        PotentialLevel.UNKNOWN: "غير معروف لنقص البيانات",
    }[value]


_AVAILABILITY_LABELS_AR = {
    "strong": "قوي",
    "medium": "متوسط",
    "weak": "ضعيف",
    "unavailable": "غير متوفر",
    "unknown": "غير معروف",
}


def _availability_for(presence: int | None) -> str:
    return {
        None: "unknown",
        0: "unavailable",
        1: "weak",
        2: "medium",
        3: "strong",
    }[presence]


def _species_match_status(presence: int | None, thermal: str, habitat_match: bool | None) -> str:
    """Combine seasonal presence (primary) with thermal and habitat priors.

    Seasonal presence dominates: absence (0) is unfavourable, absence of data
    is unknown. Thermal and habitat are low-weight adjustments only.
    """
    if presence is None:
        return "unknown"
    if presence == 0:
        return "unfavorable"
    points = presence
    if thermal == "preferred":
        points += 1
    elif thermal == "outside":
        points -= 2
    if habitat_match is True:
        points += 1
    elif habitat_match is False:
        points -= 1
    if points >= 4:
        return "favorable"
    if points >= 2:
        return "neutral"
    return "unfavorable"



def _shore_label_ar(value: ShoreType) -> str:
    return {
        ShoreType.SANDY: "رملي",
        ShoreType.ROCKY: "صخري",
        ShoreType.CLIFF: "منحدر صخري (جرف)",
        ShoreType.JETTY: "رصيف/حاجز",
    }[value]


def _hm(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def _window_overlaps_twilight(
    window: DecisionWindow, sunrise: datetime | None, sunset: datetime | None
) -> bool:
    margin = timedelta(minutes=90)
    return any(
        event is not None and window.start - margin <= event <= window.end + margin
        for event in (sunrise, sunset)
    )


def _window_overlaps_night(
    window: DecisionWindow, sunrise: datetime | None, sunset: datetime | None
) -> bool:
    if sunrise is None or sunset is None:
        return False
    return window.start < sunrise or window.end > sunset


def _field_feasibility_limitations() -> list[str]:
    return [
        "هذا فحص مؤشرات منخفض الثقة وليس رصداً مباشراً للأعشاب أو الأوساخ أو عكارة الماء أو التيار الساحبي.",
        "النموذج لا يملك شكل القاع، انحدار الشاطئ، الحواجز الرملية، تصريف الوديان أو مصدر الأعشاب والحطام.",
        "مؤشرا النقل والعكارة يصفان احتمالاً فقط؛ لا يثبتان وجود أعشاب أو حطام ولا يقدمان قيمة NTU.",
        "الصوفة والعكارة النموذجيتان لا تلغيان نافذة اجتازت السلامة وحدهما؛ تتحولان إلى تنبيه وفحص ميداني ما لم يوجد رصد فعلي.",
        "درجة ثقة الفحص تصف تغطية المدخلات واتجاه البقعة، وليست دقة تنبؤية متحققة ميدانياً.",
        "الإشارة المنخفضة لا تعني غياب الخطر؛ عاين الكسرة واعمل رمية اختبارية قبل تثبيت العتاد.",
    ]


def _risk_factor(
    code: str,
    label: str,
    severity: RiskSeverity,
    value: str,
    explanation: str,
    *,
    basis: FactorBasis = FactorBasis.MODEL_FORECAST,
    rule_nature: RuleNature = RuleNature.SAFETY_POLICY,
) -> Factor:
    return Factor(
        code=code,
        label_ar=label,
        impact=FactorImpact.SAFETY,
        severity=severity,
        basis=basis,
        rule_nature=rule_nature,
        value=value,
        explanation_ar=explanation,
        is_direct_observation=basis == FactorBasis.DIRECT_OBSERVATION,
    )


def _confidence_band(score: int) -> ConfidenceBand:
    if score >= 75:
        return ConfidenceBand.HIGH
    if score >= 55:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def _actionable_cutoff(dataset: ForecastDataset) -> datetime:
    """For today's request, begin at the next complete forecast hour."""
    if dataset.target_date != dataset.fetched_at.date():
        return datetime.combine(
            dataset.target_date,
            datetime.min.time(),
            tzinfo=dataset.fetched_at.tzinfo,
        )
    rounded = dataset.fetched_at.replace(minute=0, second=0, microsecond=0)
    return rounded if dataset.fetched_at == rounded else rounded + timedelta(hours=1)


def _is_twilight(moment: datetime, sunrise: datetime | None, sunset: datetime | None) -> bool:
    margin = timedelta(minutes=90)
    return any(event is not None and abs(moment - event) <= margin for event in (sunrise, sunset))


def _is_night(moment: datetime, sunrise: datetime | None, sunset: datetime | None) -> bool:
    if sunrise is None or sunset is None:
        return False
    return moment < sunrise or moment > sunset


def _rounded(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _worst_safety(values: Iterable[DecisionLevel]) -> DecisionLevel:
    order = {
        DecisionLevel.GO: 0,
        DecisionLevel.CAUTION: 1,
        DecisionLevel.UNKNOWN: 2,
        DecisionLevel.NO_GO: 3,
    }
    return max(values, key=order.__getitem__)


def _worst_field_feasibility(
    values: Iterable[FieldFeasibilityLevel],
) -> FieldFeasibilityLevel:
    return min(values, key=_FIELD_FEASIBILITY_RANK.__getitem__)


def _force_majeure_for(reason_code: DecisionReasonCode) -> ForceMajeureKind:
    """Map the reason code to the single hard blocker behind the decision.

    access_legal carries the official marine warning (INM bulletin, D14).
    """
    return {
        DecisionReasonCode.SAFE_WINDOW: ForceMajeureKind.NONE,
        DecisionReasonCode.SAFETY_HAZARD: ForceMajeureKind.SAFETY,
        DecisionReasonCode.FIELD_INFEASIBLE: ForceMajeureKind.HOLDING,
        DecisionReasonCode.CRITICAL_DATA_MISSING: ForceMajeureKind.DATA,
        DecisionReasonCode.CONSERVATIVE_UNCERTAINTY: ForceMajeureKind.DATA,
        DecisionReasonCode.FOULING_CONFIRMED: ForceMajeureKind.FOULING,
        DecisionReasonCode.OFFICIAL_WARNING: ForceMajeureKind.ACCESS_LEGAL,
        DecisionReasonCode.TRIP_RUIN_CONFIRMED: ForceMajeureKind.TRIP_RUIN,
    }[reason_code]


def _report_freshness(
    reported_at: datetime, fetched_at: datetime
) -> tuple[bool, str]:
    """Time-based validity of a field report or test cast (24-hour window).

    Binding validity to wave-regime change since the report is a documented
    later refinement; until then the ladder is time-based only.
    """
    age_hours = (fetched_at - reported_at).total_seconds() / 3600.0
    if age_hours < -1.0:
        return False, "بلاغ بتاريخ لاحق لوقت الجلب؛ مُهمل."
    if age_hours > 24.0:
        return False, f"بلاغ عمره {age_hours:.0f} ساعة؛ تجاوز حد الصلاحية 24 ساعة."
    return True, ""


def _worst_potential(values: Iterable[PotentialLevel]) -> PotentialLevel:
    # Preserve a known high warning instead of letting an unknown hour hide it.
    order = {
        PotentialLevel.LOW: 0,
        PotentialLevel.MODERATE: 1,
        PotentialLevel.UNKNOWN: 2,
        PotentialLevel.HIGH: 3,
    }
    return max(values, key=order.__getitem__)


def _combine_holding_breakdowns(
    breakdowns: Iterable[HoldingBreakdown | None],
) -> HoldingBreakdown | None:
    """Aggregate per-hour holding breakdowns conservatively across a window.

    The single `holding_difficulty` gate is untouched; this only carries the
    diagnostic four-mechanism split over to the aggregated result.
    """
    present = [item for item in breakdowns if item is not None]
    if not present:
        return None
    longshore = _worst_potential(item.longshore_current for item in present)
    orbital = _worst_potential(item.orbital_motion for item in present)
    return_flow = _worst_potential(item.return_flow for item in present)
    tidal = _worst_potential(item.tidal_current for item in present)
    rank = {
        PotentialLevel.HIGH: 3,
        PotentialLevel.MODERATE: 2,
        PotentialLevel.LOW: 1,
        PotentialLevel.UNKNOWN: 0,
    }
    mechanisms = (
        ("longshore_current", longshore),
        ("orbital_motion", orbital),
        ("return_flow", return_flow),
        ("tidal_current", tidal),
    )
    dominant_key, dominant_level = max(mechanisms, key=lambda item: rank[item[1]])
    dominant = dominant_key if dominant_level != PotentialLevel.UNKNOWN else "none"
    representative = next(
        (item for item in present if item.orbital_motion == orbital), present[0]
    )
    dominant_labels = {
        "longshore_current": "الجرّ الجانبي",
        "orbital_motion": "الحركة المدارية قرب القاع",
        "return_flow": "الرجوع البحري قرب القاع",
        "tidal_current": "التيار المدّي",
        "none": "لا سبب غلب واضح",
    }
    reasons = [
        f"الجرّ الجانبي: {_potential_label_ar(longshore)}.",
        f"الحركة المدارية قرب القاع: {_potential_label_ar(orbital)} (نطاق عمق مفترض 1.5 إلى 5.0 م).",
        f"الرجوع البحري قرب القاع: {_potential_label_ar(return_flow)}.",
        f"التيار المدّي: {_potential_label_ar(tidal)}.",
        f"السبب الغالب داخل النافذة: {dominant_labels[dominant]}.",
    ]
    return HoldingBreakdown(
        longshore_current=longshore,
        orbital_motion=orbital,
        return_flow=return_flow,
        tidal_current=tidal,
        dominant=dominant,
        confidence=min(item.confidence for item in present),
        orbital_velocity_band_ms=representative.orbital_velocity_band_ms,
        reasons_ar=reasons,
    )


def _is_consecutive(group: list[HourDecision]) -> bool:
    return all(
        timedelta(minutes=55) <= current.time - previous.time <= timedelta(minutes=65)
        for previous, current in pairwise(group)
    )


def _window_key_factors(group: list[HourDecision]) -> list[str]:
    positive: list[str] = []
    caution: list[str] = []
    for hour in group:
        for factor in hour.factors:
            if factor.impact == FactorImpact.POSITIVE and factor.score_delta > 0:
                positive.append(factor.label_ar)
            elif factor.severity in {RiskSeverity.CAUTION, RiskSeverity.CRITICAL} or (
                factor.impact == FactorImpact.NEGATIVE and factor.score_delta <= -4
            ):
                caution.append(factor.label_ar)
    return (_unique(positive)[:3] + _unique(caution)[:2]) or ["ظروف متوازنة بلا أفضلية قوية"]


def _critical_factor_labels(hours: Iterable[HourDecision]) -> list[str]:
    labels = [
        factor.label_ar
        for hour in hours
        for factor in hour.factors
        if factor.severity == RiskSeverity.CRITICAL or factor.impact == FactorImpact.DATA_GAP
    ]
    return _unique(labels)
