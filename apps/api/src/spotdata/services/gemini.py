from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from spotdata.domain.models import (
    DecisionResponse,
    ForecastDecisionRequest,
    GeminiKeyVerificationResponse,
    GeminiNarrative,
    GeminiReportMetadata,
    GeminiReportResponse,
)

PROMPT_VERSION = "peche-tn-writer-v6"
TEMPLATE_VERSION = "original-corrected-v3"
LOGGER = logging.getLogger(__name__)
_KEY_PATTERN = re.compile(r"^[^\s\x00-\x1f]{20,200}$")
_DIGIT_PATTERN = re.compile(r"\d")
_JSON_FENCE_PATTERN = re.compile(r"\A```(?:json)?\s*(.*?)\s*```\Z", re.IGNORECASE | re.DOTALL)
_DECISION_COMMANDS = (
    "اذهب",
    "تذهب",
    "الذهاب",
    "اخرج",
    "تخرج",
    "الخروج",
    "انطلق",
    "امتنع",
    "توجه",
    "توجّه",
    "أجّل",
    "اجّل",
    "التأجيل",
    "ألغ",
    "الإلغاء",
)
_ENGLISH_DECISION_PATTERN = re.compile(
    r"\b(?:GO|NO[_-]?GO|PROCEED|CANCEL|POSTPONE)\b", re.IGNORECASE
)
_BLOCKED_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "LANGUAGE", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
)
_MAX_PROVIDER_ATTEMPTS = 4
_MAX_STRUCTURED_GENERATIONS = 2
_MAX_RETRY_DELAY_SECONDS = 2.0
_MAX_OUTPUT_TOKENS = 8_192
_MAX_ITEMS_PER_SECTION = 4
_MAX_EVIDENCE_PACKET_BYTES = 64_000
_VERIFY_TOTAL_TIMEOUT_SECONDS = 20.0
_GENERATION_REQUEST_TIMEOUT_SECONDS = 35.0
_GENERATION_TOTAL_TIMEOUT_SECONDS = 40.0
_TUNIS_TZ = ZoneInfo("Africa/Tunis")


def _is_transient_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code <= 599


def _retry_delay_seconds(attempt: int, response: httpx.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), _MAX_RETRY_DELAY_SECONDS)
            except ValueError:
                pass
    base = min(float(2**attempt), _MAX_RETRY_DELAY_SECONDS)
    return float(base + random.uniform(0.0, 0.25))


class GeminiServiceError(RuntimeError):
    def __init__(self, code: str, message_ar: str, status_code: int = 502) -> None:
        super().__init__(message_ar)
        self.code = code
        self.message_ar = message_ar
        self.status_code = status_code


class _StructuredOutputValidationError(ValueError):
    """Internal shape failure whose details must never expose provider prose or the API key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_runtime_key(api_key: str) -> str:
    key = api_key.strip()
    if not _KEY_PATTERN.fullmatch(key):
        raise GeminiServiceError(
            "invalid_gemini_key_format",
            "صيغة مفتاح Gemini غير صالحة. لم يُحفظ المفتاح في الخادم.",
            400,
        )
    return key


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _day_part(value: datetime) -> str:
    hour = value.astimezone(_TUNIS_TZ).hour
    if hour < 4:
        return "late_night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_evidence_packet(
    request: ForecastDecisionRequest, decision: DecisionResponse
) -> dict[str, object]:
    """Build a compact writer-only packet without copying the full numeric decision payload.

    The complete forecast, hourly equations and numbers remain in the deterministic response and
    server-rendered report. Gemini receives only the categorical context needed for prose, every
    audited factor in compact form, provenance boundaries and explicit Unknowns.
    """
    windows = [
        {
            "start_day_part": _day_part(window.start),
            "end_day_part": _day_part(window.end),
            "safety": window.safety.value,
            "field_feasibility": window.field_feasibility.value,
            "headline_ar": window.headline_ar,
            "key_factors_ar": window.key_factors_ar,
        }
        for window in decision.recommended_windows
    ]
    avoid_windows = [
        {
            "start_day_part": _day_part(window.start),
            "end_day_part": _day_part(window.end),
            "safety": window.safety.value,
            "field_feasibility": window.field_feasibility.value,
            "key_factors_ar": window.key_factors_ar,
        }
        for window in decision.avoid_windows
    ]
    hourly_context = [
        {
            "sequence": index,
            "day_part": _day_part(item.time),
            "safety": item.safety.value,
            "field_feasibility": item.field_feasibility.status.value,
            "wind_relation": item.derived.wind_relation.value,
            "wave_incidence": item.derived.wave_incidence.value,
            "modelled_water_state": item.derived.tide_state.value,
            "is_twilight": item.derived.is_twilight,
            "is_night": item.derived.is_night,
        }
        for index, item in enumerate(decision.hourly)
    ]
    factor_assessments = [
        {
            "matrix_id": item.matrix_id,
            "title_ar": item.title_ar,
            "status": item.status.value,
            "decision_axis": item.decision_axis,
            "value_ar": item.value_ar,
            "affects_final_decision": item.affects_final_decision,
        }
        for item in decision.factor_assessments
    ]
    unknowns = _ordered_unique(
        [
            f"[{item.matrix_id}] {item.title_ar}: {item.value_ar}"
            for item in decision.factor_assessments
            if item.status.value == "unknown"
        ]
        + (
            decision.observation_comparison.reasons_ar
            if decision.current_weather_observation is None
            else []
        )
        + (
            [decision.coastal_water_context.reason_ar]
            if decision.coastal_water_context is not None
            and decision.coastal_water_context.availability == "unavailable"
            else []
        )
    )
    observation_context: dict[str, object]
    if decision.current_weather_observation is None:
        observation_context = {
            "availability": "unavailable",
            "comparison_status": decision.observation_comparison.status.value,
            "reasons_ar": decision.observation_comparison.reasons_ar,
        }
    else:
        observation = decision.current_weather_observation
        observation_context = {
            "availability": "available",
            "provider": observation.provider,
            "station_id": observation.station_id,
            "comparison_status": decision.observation_comparison.status.value,
            "affects_confidence": decision.observation_comparison.affects_confidence,
            "is_direct_observation": observation.is_direct_observation,
            "is_spot_observation": observation.is_spot_observation,
            "weather_text": observation.weather_text,
            "quality_control_flag": observation.quality_control_flag,
            "reasons_ar": decision.observation_comparison.reasons_ar,
        }
    water_context: dict[str, object]
    if decision.coastal_water_context is None:
        water_context = {"availability": "not_provided"}
    else:
        water = decision.coastal_water_context
        water_context = {
            "availability": water.availability,
            "data_kind": water.data_kind,
            "is_forecast": water.is_forecast,
            "is_spot_observation": water.is_spot_observation,
            "affects_final_decision": water.affects_final_decision,
            "available_variables": [
                name
                for name, value in (
                    ("TUR/FNU", water.turbidity_fnu),
                    ("SPM/g/m3", water.suspended_particulate_matter_g_m3),
                    ("CHL-a/mg/m3", water.chlorophyll_a_mg_m3),
                )
                if value is not None
            ],
            "reason_ar": water.reason_ar,
        }
    packet: dict[str, object] = {
        "authority": {
            "numeric_authority": "Peche TN deterministic engine only",
            "writer_may_change_decision": False,
            "writer_may_add_numbers": False,
            "decision": decision.decision.value,
            "decision_label_ar": decision.decision_label_ar,
            "decision_reason_code": decision.decision_reason_code.value,
        },
        "data_minimization": {
            "purpose": "categorical prose context only",
            "coordinates_sent_to_writer": False,
            "raw_hourly_numbers_sent_to_writer": False,
            "raw_antecedent_hours_sent_to_writer": False,
            "complete_numbers_remain_server_rendered": True,
        },
        "request_context": {
            "location_name": request.location.name,
            "target_date": request.target_date.isoformat(),
            "spot": {
                "orientation_source": request.spot.orientation_source.value,
                "shore_type": request.spot.shore_type.value,
                "exposure": request.spot.exposure.value,
            },
            "angler": {
                "experience": request.angler.experience.value,
                "target_species": request.angler.target_species.value,
                "session_hours": request.angler.session_hours,
            },
        },
        "decision_context": {
            "schema_version": decision.schema_version,
            "engine_version": decision.engine_version,
            "decision": decision.decision.value,
            "decision_reason_code": decision.decision_reason_code.value,
            "decision_label_ar": decision.decision_label_ar,
            "summary_ar": decision.summary_ar,
            "confidence_band": decision.confidence.band.value,
            "confidence_reasons_ar": decision.confidence.reasons_ar,
            "recommended_windows": windows,
            "avoid_windows": avoid_windows,
        },
        "field_context": {
            "status": decision.field_feasibility.status.value,
            "holding_difficulty": decision.field_feasibility.holding_difficulty.value,
            "fouling_transport_potential": (
                decision.field_feasibility.fouling_transport_potential.value
            ),
            "turbidity_potential": decision.field_feasibility.turbidity_potential.value,
            "rip_current_potential": decision.field_feasibility.rip_current_potential.value,
            "is_direct_observation": decision.field_feasibility.is_direct_observation,
            "reasons_ar": decision.field_feasibility.reasons_ar,
            "limitations_ar": decision.field_feasibility.limitations_ar,
        },
        "hourly_categorical_context": hourly_context,
        "modelled_water_events": [
            {"day_part": _day_part(event.time), "kind": event.kind}
            for event in decision.tide_events
        ],
        "observation_context": observation_context,
        "sentinel_2_context": water_context,
        "sources": [
            {
                "provider": source.provider,
                "product": source.product,
                "data_kind": source.data_kind.value,
                "variables": source.variables,
                "limitations_ar": source.limitations_ar,
            }
            for source in decision.sources
        ],
        "factor_coverage": {
            "catalog_version": decision.factor_coverage.catalog_version,
            "matrix_version": decision.factor_coverage.matrix_version,
            "audited_total": decision.factor_coverage.audited_total,
            "note_ar": decision.factor_coverage.note_ar,
        },
        "all_factor_assessments": factor_assessments,
        "explicit_unknowns_ar": unknowns,
        "global_limitations_ar": decision.limitations_ar,
    }
    encoded_size = len(_canonical_json(packet).encode("utf-8"))
    if encoded_size > _MAX_EVIDENCE_PACKET_BYTES:
        raise GeminiServiceError(
            "gemini_evidence_packet_too_large",
            "تعذر بناء حزمة سرد مصغرة ضمن الحد الآمن؛ بقي التقرير الحتمي كاملاً.",
            422,
        )
    return packet


def _writer_prompt(packet_json: str, *, structured_retry: bool = False) -> str:
    retry_instruction = (
        "- هذه إعادة توليد من الصفر بعد خرج غير مطابق. أعد الكائن كاملاً مرة واحدة ولا تشرح الخطأ.\n"
        if structured_retry
        else ""
    )
    return f"""أنت كاتب تقرير عربي مهني لأداة Peche TN، ولست محرك قرار.

قواعد إلزامية:
- Evidence Packet المصغرة أدناه هي المصدر الوحيد للسرد. لا تستخدم معرفة خارجية ولا تخمّن.
- الأرقام والساعات الخام محذوفة عمداً من حزمة الكاتب لأنها تُطبع حتمياً في الخادم؛ لا تعامل هذا الاستبعاد كفجوة بيانات ولا تحاول تعويضه.
- أعد كائن JSON واحداً فقط، بلا Markdown أو سياج code أو نص قبل الكائن أو بعده.
- استخدم المفاتيح الستة المطلوبة حرفياً؛ الملخص فقرة واحدة، وكل قائمة فيها من عنصر واحد إلى أربعة عناصر موجزة.
- لا تغيّر القرار ولا تستخدم أي أمر أو توصية على مستوى الذهاب أو الخروج أو التأجيل أو الإلغاء. القالب الحتمي وحده سيعرض القرار.
- لا تكتب أي رقم أو رمز رقمي في النص، حتى لو ورد في الحزمة. القالب الحتمي وحده يعرض الأرقام.
- لا تدّع وجود صوفة أو عكارة أو تيار ساحبي. قل «احتمال» أو «Unknown» وفق الحزمة، واذكر ضرورة الفحص الميداني.
- عدادات الصوفة والعكارة هي عائلات قرائن تشغيلية مختلفة وليست أرصاداً أو مصادر مستقلة؛ لا تسمّها أدلة مستقلة.
- حتى التصنيف المرتفع للصوفة أو العكارة هو تنبيه نموذج نقل غير معاير وفحص ميداني، ولا يلغي وحده نافذة اجتازت السلامة.
- لا تخترع NTU أو نسبة نجاح أو نوع سمك أو طعماً أو عتاداً أو مدّاً فلكياً أو قياساً داخل البقعة.
- فرّق بين التوقع النموذجي ورصد محطة المطار واستعادة Sentinel-2، ولا تنقل أيّاً منها إلى الشاطئ كقياس ميداني.
- TUR وSPM وCHL سياق أقمار صناعية متقطع لا يثبت الصوفة أو ازدهاراً ضاراً أو نشاط السمك ولا يغير القرار أو السلامة أو التنفيذ أو الفرصة أو الثقة، ولا تحوّل FNU إلى NTU.
- اكتب تفسيراً موجزاً ومفيداً فقط داخل مفاتيح JSON المطلوبة.
- في unknowns_ar اذكر أهم فجوات البيانات الفعلية، ولا تحول Unknown إلى غياب.
{retry_instruction}
Evidence Packet:
{packet_json}
"""


def _narrative_list_schema(description: str) -> dict[str, object]:
    return {
        "type": "array",
        "description": description,
        "minItems": 1,
        "maxItems": _MAX_ITEMS_PER_SECTION,
        "items": {
            "type": "string",
            "description": "جملة عربية موجزة بلا أرقام ولا إعادة لأمر القرار.",
        },
    }


def _response_schema() -> dict[str, object]:
    required = [
        "executive_summary_ar",
        "timing_and_water_ar",
        "temporal_analysis_ar",
        "factor_interactions_ar",
        "field_tactics_ar",
        "unknowns_ar",
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "propertyOrdering": required,
        "properties": {
            "executive_summary_ar": {
                "type": "string",
                "description": "ملخص عربي مهني موجز بلا أرقام ولا إعادة لأمر القرار.",
            },
            "timing_and_water_ar": _narrative_list_schema("تفسير التوقيت والماء."),
            "temporal_analysis_ar": _narrative_list_schema("تفسير زمني موجز."),
            "factor_interactions_ar": _narrative_list_schema("تفاعل العوامل دون اختراع."),
            "field_tactics_ar": _narrative_list_schema("فحوص ميدانية غير رقمية."),
            "unknowns_ar": _narrative_list_schema("أهم الفجوات الفعلية وUnknown."),
        },
    }


def _extract_text(payload: object) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise GeminiServiceError("gemini_invalid_response", "أعاد Gemini استجابة غير مفهومة.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiServiceError(
            "gemini_empty_response",
            "لم يُرجع Gemini نصاً صالحاً. بقي التقرير الحتمي متاحاً.",
        )
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise GeminiServiceError("gemini_invalid_response", "أعاد Gemini مرشحاً غير صالح.")
    finish_reason_value = candidate.get("finishReason")
    finish_reason = finish_reason_value if isinstance(finish_reason_value, str) else None
    if finish_reason in _BLOCKED_FINISH_REASONS:
        raise GeminiServiceError(
            "gemini_generation_blocked",
            "أوقف Gemini التوليد قبل اكتمال السرد؛ بقي التقرير الحتمي كاملاً.",
            422,
        )
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        if finish_reason == "MAX_TOKENS":
            return "", finish_reason
        raise GeminiServiceError("gemini_invalid_response", "تعذر قراءة أجزاء رد Gemini.")
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("thought") is True:
            continue
        part_text = part.get("text")
        if isinstance(part_text, str):
            text_parts.append(part_text)
    text = "".join(text_parts).strip()
    if not text and finish_reason != "MAX_TOKENS":
        raise GeminiServiceError("gemini_empty_response", "لم يُرجع Gemini نصاً صالحاً.")
    return text, finish_reason


def _parse_narrative(raw_text: str, finish_reason: str | None) -> GeminiNarrative:
    document = raw_text.lstrip("\ufeff").strip()
    fence = _JSON_FENCE_PATTERN.fullmatch(document)
    if fence is not None:
        document = fence.group(1).strip()
    try:
        raw_payload: Any = json.loads(document)
        if isinstance(raw_payload, str):
            raw_payload = json.loads(raw_payload.strip())
    except (json.JSONDecodeError, TypeError) as exc:
        reason = "max_tokens" if finish_reason == "MAX_TOKENS" else "invalid_json"
        raise _StructuredOutputValidationError(reason) from exc
    try:
        return GeminiNarrative.model_validate(raw_payload)
    except (ValidationError, TypeError) as exc:
        raise _StructuredOutputValidationError("schema_mismatch") from exc


def _validate_narrative_semantics(narrative: GeminiNarrative) -> None:
    text = "\n".join(
        [
            narrative.executive_summary_ar,
            *narrative.timing_and_water_ar,
            *narrative.temporal_analysis_ar,
            *narrative.factor_interactions_ar,
            *narrative.field_tactics_ar,
            *narrative.unknowns_ar,
        ]
    )
    if _DIGIT_PATTERN.search(text):
        raise GeminiServiceError(
            "gemini_added_numbers",
            "رفض الخادم تقرير Gemini لأنه أضاف أرقاماً؛ التقرير الحتمي لم يتغير.",
            422,
        )
    if any(command in text for command in _DECISION_COMMANDS) or _ENGLISH_DECISION_PATTERN.search(
        text
    ):
        raise GeminiServiceError(
            "gemini_repeated_decision",
            "رفض الخادم السرد لأنه حاول إعادة صياغة القرار؛ قرار المحرك لم يتغير.",
            422,
        )


def _report_number(value: float | None, digits: int = 2) -> str:
    return "Unknown" if value is None else f"{value:.{digits}f}"


def render_report_text(
    request: ForecastDecisionRequest,
    decision: DecisionResponse,
    narrative: GeminiNarrative,
    metadata: GeminiReportMetadata,
) -> str:
    best = decision.recommended_windows[0] if decision.recommended_windows else None
    orientation = request.spot.orientation_evidence
    representative = None
    if best is not None:
        representative = next(
            (item for item in decision.hourly if best.start <= item.time < best.end), None
        )

    lines = [
        "PECHE TN — RAPPORT SPOT",
        "========================",
        "",
        "0. VERDICT DÉTERMINISTE / القرار الحتمي",
        f"{decision.decision_label_ar} — {decision.decision_reason_code.value}",
        decision.summary_ar,
        f"مؤشر الفرصة: {decision.opportunity_score}/100 (ليس احتمال نجاح)",
        f"قابلية التنفيذ: {decision.field_feasibility.score}/100 — {decision.field_feasibility.status.value}",
        f"ثقة المدخلات: {decision.confidence.score}/100 — {decision.confidence.band.value}؛ ليست دقة ميدانية متحققة",
        "",
        "1. SPOT ET ORIENTATION / البقعة والاتجاه",
        f"{request.location.name or 'Spot'} — {request.location.latitude:.5f}, {request.location.longitude:.5f}",
        f"اتجاه البحر: {request.spot.seaward_orientation_deg:.1f}° ({request.spot.orientation_source.value})",
    ]
    if orientation is not None:
        lines.extend(
            [
                f"مماس الساحل: {orientation.coastline_tangent_deg:.1f}°",
                f"المسافة إلى الساحل: {orientation.coastline_distance_m:.1f} م",
                f"Overpass: {orientation.server} — نصف القطر {orientation.search_radius_m} م — الثقة {orientation.confidence}",
            ]
        )
    else:
        lines.append("لا توجد provenance آلية للاتجاه؛ المصدر يدوي/خرائطي.")

    lines.extend(["", "2. FENÊTRE ET CONDITIONS / النافذة والظروف"])
    if best is None:
        lines.append("لا توجد نافذة مكتملة موصى بها.")
    else:
        lines.append(
            f"{best.start.isoformat()} → {best.end.isoformat()} — safety={best.safety.value} — field={best.field_feasibility.value}"
        )
    for avoid in decision.avoid_windows:
        lines.append(
            f"تجنب {avoid.start.isoformat()} → {avoid.end.isoformat()} — {'؛ '.join(avoid.key_factors_ar)}"
        )
    if best is not None and decision.avoid_windows:
        lines.append(
            "وجود فترة خطر لا يلغي نافذة منفصلة اجتازت البوابات؛ لا تمدد النافذة إلى فترة التجنب."
        )
    if representative is not None:
        forecast = representative.forecast
        derived = representative.derived
        lines.extend(
            [
                f"ريح: {forecast.wind_speed_kmh} كم/س؛ هبات: {forecast.wind_gust_kmh} كم/س؛ اتجاه: {forecast.wind_direction_deg}°؛ علاقة: {derived.wind_relation.value}",
                f"موج: {forecast.wave_height_m} م؛ فترة: {forecast.wave_period_s} ث؛ اتجاه: {forecast.wave_direction_deg}°؛ ورود: {derived.wave_incidence.value}",
                f"تيار: {forecast.ocean_current_velocity_kmh} كم/س نحو {forecast.ocean_current_direction_deg}°؛ مستوى البحر: {forecast.sea_level_height_msl_m} م MSL",
            ]
        )

    lines.extend(
        [
            "",
            "2B. DIAGNOSTICS HORAIRES / المشتقات الساعية",
            "المحور الموازي الموجب=(اتجاه البحر+90) modulo 360. للريح والموج القادمين: Vcross=V*cos(delta) وValong الموقّع=-V*sin(delta)؛ الحقل القديم هو |V*sin(delta)|. للتيار towards: Ccross=V*cos(delta_c) موجب نحو البحر وCalong=V*sin(delta_c) موجب على المحور المعلن.",
            "L0=gT²/(2π) وHs/L0 تقريبات مياه عميقة. tau_vector=rho_air*Cd*|U10|*U10_vector بوحدة Pa؛ R محصلة دائرية موزونة بالسرعة بعد استبعاد الريح دون 5 كم/س؛ زاوية موج الريح/السويل وحصة H² للنظام الأضعف تشخيصان منفصلان بلا عتبة قرار.",
        ]
    )
    for item in decision.hourly:
        derived = item.derived
        weaker_share = (
            "Unknown"
            if derived.wave_component_secondary_energy_share is None
            else f"{derived.wave_component_secondary_energy_share * 100:.1f}%"
        )
        lines.append(
            f"{item.time.isoformat()} | axis+={derived.alongshore_positive_bearing_deg:.1f}° | "
            f"wind Δ={_report_number(derived.wind_angle_deg)}° V⊥={_report_number(derived.wind_shoreward_component_kmh)} "
            f"V∥signed={_report_number(derived.wind_alongshore_signed_component_kmh)} km/h | "
            f"tau={_report_number(derived.wind_stress_pa, 4)} Pa "
            f"tau⊥={_report_number(derived.wind_stress_shoreward_pa, 4)} "
            f"tau∥={_report_number(derived.wind_stress_alongshore_pa, 4)} "
            f"Cd={_report_number(derived.wind_drag_coefficient, 6)} "
            f"integral(tau⊥+)48={_report_number(derived.onshore_wind_stress_impulse_48h_pa_h, 3)} Pa·h | "
            f"wave Δ={_report_number(derived.wave_angle_deg)}° L0={_report_number(derived.deep_water_wavelength_m, 1)} m "
            f"Hs/L0={_report_number(derived.wave_steepness, 4)} H²T={_report_number(derived.wave_energy_proxy)} "
            f"forcing∥={_report_number(derived.alongshore_wave_signed_proxy)} | "
            f"wind-wave/swell angle={_report_number(derived.wave_component_angle_deg)}° weaker-share={weaker_share} | "
            f"current⊥={_report_number(derived.current_cross_shore_kmh)} current∥={_report_number(derived.current_alongshore_kmh)} km/h | "
            f"R6={_report_number(derived.wind_direction_coherence_6h, 3)} ({derived.wind_direction_data_hours_6h}/6) | "
            f"air-sea={_report_number(derived.air_sea_temperature_difference_c)}°C air-dew={_report_number(derived.dew_point_depression_c)}°C"
        )

    reference = decision.hourly[0].derived
    lines.extend(
        [
            "",
            "3. ANTÉCÉDENTS 48-72 H / نشاط البحر السابق",
            f"تغطية التاريخ: {reference.history_hours_48h}/48 و{reference.history_hours_72h}/72 ساعة؛ ساعات خام مطبعة مرفقة={len(decision.antecedent_hours)}",
            f"طاقة الموج التراكمية 48س Hs²T·h: {reference.wave_energy_integral_48h}",
            f"ساعات الموج القوي 48س: {reference.strong_wave_hours_48h}",
            f"دفع الريح نحو الشاطئ 48س: {reference.onshore_wind_impulse_48h_kmh_h} كم/س·س",
            f"تكامل إجهاد الريح الشاطئي الموجب 48س: {reference.onshore_wind_stress_impulse_48h_pa_h} Pa·h (تشخيص فقط)",
            f"دفع التيار نحو الشاطئ 48س: {reference.shoreward_current_impulse_48h_kmh_h} كم/س·س",
            f"المطر: 24س={reference.rain_24h_mm} مم؛ 48س={reference.rain_48h_mm} مم؛ 72س={reference.rain_72h_mm} مم",
            f"احتمال الصوفة/الحطام: {decision.field_feasibility.fouling_transport_potential.value} من {decision.field_feasibility.fouling_evidence_count} عائلات قرائن تشغيلية مختلفة؛ ليست أرصاداً أو مصادر مستقلة، وتنبيه غير مانع وحده.",
            f"احتمال العكارة: {decision.field_feasibility.turbidity_potential.value} من {decision.field_feasibility.turbidity_evidence_count} عائلات قرائن تشغيلية مختلفة؛ NTU غير مقاس وليست قياسات ماء مستقلة، وتنبيه غير مانع وحده.",
            "",
            "3B. SENTINEL-2 / سياق جودة الماء",
        ]
    )
    water = decision.coastal_water_context
    if water is None or water.availability == "unavailable":
        reason = water.reason_ar if water is not None else "السياق غير مرفق في الاستجابة"
        lines.append(f"Sentinel-2 TUR/SPM/CHL: Unknown — {reason}")
    else:
        lines.extend(
            [
                f"Sentinel-2 remote-sensing context: valid={water.valid_time.isoformat() if water.valid_time else 'Unknown'} age={_report_number(water.age_hours, 1)} h pixel-distance={_report_number(water.pixel_distance_from_spot_m, 1)} m resolution={water.spatial_resolution_m} m",
                f"TUR={_report_number(water.turbidity_fnu, 4)} {water.turbidity_unit}; SPM={_report_number(water.suspended_particulate_matter_g_m3, 4)} {water.suspended_particulate_matter_unit}; CHL-a={_report_number(water.chlorophyll_a_mg_m3, 4)} {water.chlorophyll_a_unit}. سياق فقط؛ ليس قياساً ميدانياً أو توقعاً ولا يغير القرار أو السلامة أو التنفيذ أو الفرصة أو الثقة.",
            ]
        )
    lines.extend(["", "4. MATRICE 63 FACTEURS / سجل العوامل"])
    lines.extend(
        f"[{item.matrix_id}] {item.title_ar} — {item.status.value} — {item.value_ar}"
        for item in decision.factor_assessments
    )
    lines.extend(["", "5. SOURCES ET LIMITES / المصادر والحدود"])
    lines.extend(
        f"{source.provider} | {source.product} | {source.data_kind} | retrieved={source.retrieved_at.isoformat()}"
        for source in decision.sources
    )
    lines.extend(f"- {item}" for item in decision.limitations_ar)
    lines.extend(
        [
            "",
            "6. NARRATION GEMINI CONTRAINTE / السرد المقيد",
            narrative.executive_summary_ar,
            "",
            "التوقيت والماء:",
            *(f"- {item}" for item in narrative.timing_and_water_ar),
            "التحليل الزمني:",
            *(f"- {item}" for item in narrative.temporal_analysis_ar),
            "تفاعل العوامل:",
            *(f"- {item}" for item in narrative.factor_interactions_ar),
            "تكتيكات ميدانية غير رقمية:",
            *(f"- {item}" for item in narrative.field_tactics_ar),
            "Unknown والفجوات:",
            *(f"- {item}" for item in narrative.unknowns_ar),
            "",
            "7. MÉTADONNÉES / البيانات الوصفية",
            f"model={metadata.model}",
            f"prompt={metadata.prompt_version}",
            f"template={metadata.template_version}",
            f"input_sha256={metadata.input_sha256}",
            f"generated_at={metadata.generated_at.isoformat()}",
            "decision_was_modified=false; numbers_are_server_rendered=true",
        ]
    )
    return "\n".join(lines)


class GeminiClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise ValueError("invalid Gemini model name")
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self.model = model

    async def _request_with_backoff(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        json_body: dict[str, object] | None = None,
        max_attempts: int = _MAX_PROVIDER_ATTEMPTS,
        deadline: float | None = None,
    ) -> tuple[httpx.Response, int]:
        """Retry transient failures while reporting how much of the call budget was used."""
        if not 1 <= max_attempts <= _MAX_PROVIDER_ATTEMPTS:
            raise ValueError("max_attempts must remain inside the bounded provider budget")
        for attempt in range(max_attempts):
            request_timeout = timeout
            if deadline is not None:
                remaining_seconds = deadline - monotonic()
                if remaining_seconds <= 0:
                    raise httpx.TimeoutException("bounded Gemini deadline exhausted")
                request_timeout = min(timeout, remaining_seconds)
            try:
                response = await self._http_client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    timeout=request_timeout,
                )
            except httpx.HTTPError as exc:
                if attempt + 1 >= max_attempts:
                    raise
                LOGGER.warning(
                    "gemini transport retry model=%s error=%s attempt=%s/%s",
                    self.model,
                    type(exc).__name__,
                    attempt + 1,
                    max_attempts,
                )
                delay = _retry_delay_seconds(attempt)
                if deadline is not None and delay >= deadline - monotonic():
                    raise httpx.TimeoutException("bounded Gemini deadline exhausted") from exc
                await asyncio.sleep(delay)
                continue

            if not _is_transient_status(response.status_code):
                return response, attempt + 1
            if attempt + 1 >= max_attempts:
                return response, attempt + 1
            LOGGER.warning(
                "gemini status retry model=%s status=%s attempt=%s/%s",
                self.model,
                response.status_code,
                attempt + 1,
                max_attempts,
            )
            delay = _retry_delay_seconds(attempt, response)
            if deadline is not None and delay >= deadline - monotonic():
                raise httpx.TimeoutException("bounded Gemini deadline exhausted")
            await asyncio.sleep(delay)

        raise RuntimeError("Gemini retry loop ended unexpectedly")  # pragma: no cover

    async def verify_key(self, api_key: str) -> GeminiKeyVerificationResponse:
        key = validate_runtime_key(api_key)
        verification_deadline = monotonic() + _VERIFY_TOTAL_TIMEOUT_SECONDS
        try:
            response, _attempts_used = await self._request_with_backoff(
                "GET",
                f"{self._base_url}/models/{self.model}",
                headers={"x-goog-api-key": key, "Accept": "application/json"},
                timeout=12.0,
                deadline=verification_deadline,
            )
        except httpx.HTTPError as exc:
            raise GeminiServiceError(
                "gemini_unreachable",
                "تعذر الوصول إلى Google Gemini بعد إعادة المحاولة. لم يُخزن المفتاح في الخادم.",
                503,
            ) from exc
        if response.status_code in {400, 401, 403}:
            raise GeminiServiceError(
                "gemini_key_rejected",
                "رفض Google المفتاح أو لا يملك صلاحية النموذج. تحقق منه ثم أعد المحاولة.",
                401,
            )
        if response.status_code >= 400:
            raise GeminiServiceError(
                "gemini_provider_error",
                f"تعذر اختبار Gemini بعد إعادة المحاولة (HTTP {response.status_code}).",
                503 if response.status_code >= 500 else 502,
            )
        return GeminiKeyVerificationResponse(
            model=self.model,
            message_ar="المفتاح صالح لهذا النموذج. بقي المفتاح في المتصفح ولم يُخزن في الخادم.",
        )

    async def generate_report(
        self,
        api_key: str,
        request: ForecastDecisionRequest,
        decision: DecisionResponse,
    ) -> GeminiReportResponse:
        key = validate_runtime_key(api_key)
        packet = build_evidence_packet(request, decision)
        packet_json = _canonical_json(packet)
        input_hash = hashlib.sha256(packet_json.encode("utf-8")).hexdigest()
        url = f"{self._base_url}/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        remaining_requests = _MAX_PROVIDER_ATTEMPTS
        generation_deadline = monotonic() + _GENERATION_TOTAL_TIMEOUT_SECONDS

        for generation_attempt in range(_MAX_STRUCTURED_GENERATIONS):
            generation_config: dict[str, object] = {
                "candidateCount": 1,
                "temperature": 0.0 if generation_attempt else 0.1,
                "maxOutputTokens": _MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
                "responseJsonSchema": _response_schema(),
            }
            if self.model.startswith("gemini-3"):
                generation_config["thinkingConfig"] = {"thinkingLevel": "low"}
            body: dict[str, object] = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": _writer_prompt(
                                    packet_json,
                                    structured_retry=generation_attempt > 0,
                                )
                            }
                        ],
                    }
                ],
                "generationConfig": generation_config,
            }
            try:
                response, attempts_used = await self._request_with_backoff(
                    "POST",
                    url,
                    headers=headers,
                    json_body=body,
                    timeout=_GENERATION_REQUEST_TIMEOUT_SECONDS,
                    max_attempts=remaining_requests,
                    deadline=generation_deadline,
                )
            except httpx.TimeoutException as exc:
                raise GeminiServiceError(
                    "gemini_timeout",
                    "تجاوز Gemini مهلة التوليد المحدودة؛ أوقفنا الانتظار وبقي التقرير الحتمي كاملاً.",
                    504,
                ) from exc
            except httpx.HTTPError as exc:
                raise GeminiServiceError(
                    "gemini_unreachable",
                    "تعذر الاتصال بـ Google Gemini بعد محاولة قصيرة؛ التقرير الحتمي ما زال كاملاً.",
                    503,
                ) from exc
            remaining_requests -= attempts_used
            if response.status_code in {400, 401, 403}:
                raise GeminiServiceError(
                    "gemini_request_rejected",
                    "رفض Google المفتاح أو الطلب المنظم؛ لم يتغير قرار المحرك.",
                    401 if response.status_code in {401, 403} else 422,
                )
            if response.status_code == 429:
                raise GeminiServiceError(
                    "gemini_rate_limited",
                    "بلغ Gemini حد الاستخدام؛ جرّب لاحقاً أو استخدم التقرير الحتمي.",
                    429,
                )
            if response.status_code >= 400:
                raise GeminiServiceError(
                    "gemini_provider_error",
                    f"فشل Gemini بعد إعادة المحاولة (HTTP {response.status_code})؛ التقرير الحتمي متاح.",
                    503 if response.status_code >= 500 else 502,
                )

            validation_error = _StructuredOutputValidationError("invalid_provider_json")
            try:
                provider_payload: Any = response.json()
            except ValueError:
                pass
            else:
                raw_text, finish_reason = _extract_text(provider_payload)
                try:
                    narrative = _parse_narrative(raw_text, finish_reason)
                except _StructuredOutputValidationError as exc:
                    validation_error = exc
                else:
                    _validate_narrative_semantics(narrative)
                    generated_at = datetime.now(UTC)
                    metadata = GeminiReportMetadata(
                        model=self.model,
                        prompt_version=PROMPT_VERSION,
                        template_version=TEMPLATE_VERSION,
                        generated_at=generated_at,
                        input_sha256=input_hash,
                    )
                    report_text = render_report_text(request, decision, narrative, metadata)
                    return GeminiReportResponse(
                        narrative=narrative,
                        report_text=report_text,
                        metadata=metadata,
                    )

            can_regenerate = (
                generation_attempt + 1 < _MAX_STRUCTURED_GENERATIONS and remaining_requests > 0
            )
            if can_regenerate:
                LOGGER.warning(
                    "gemini structured output regeneration model=%s reason=%s generation=%s/%s remaining_requests=%s",
                    self.model,
                    validation_error.reason,
                    generation_attempt + 1,
                    _MAX_STRUCTURED_GENERATIONS,
                    remaining_requests,
                )
                continue
            if validation_error.reason == "max_tokens":
                raise GeminiServiceError(
                    "gemini_output_truncated",
                    "بلغ Gemini حد الخرج قبل إكمال JSON حتى بعد إعادة محدودة؛ لم يتغير القرار والتقرير الحتمي ما زال كاملاً.",
                    502,
                ) from validation_error
            raise GeminiServiceError(
                "gemini_schema_validation_failed",
                "لم يكتمل JSON المنظم من Gemini بعد إعادة محدودة؛ لم يتغير القرار والتقرير الحتمي ما زال كاملاً.",
                422,
            ) from validation_error

        raise RuntimeError(
            "Gemini structured generation loop ended unexpectedly"
        )  # pragma: no cover
