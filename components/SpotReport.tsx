"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  AlertTriangle,
  Anchor,
  Check,
  Clipboard,
  Clock3,
  Copy,
  Database,
  Download,
  Droplets,
  Eye,
  EyeOff,
  FileText,
  Fish,
  Info,
  KeyRound,
  MessageCircle,
  Printer,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Sunrise,
  Sunset,
  Trash2,
  WandSparkles,
  Waves,
  Wind,
  X,
} from "lucide-react";
import { requestGeminiReport, verifyGeminiKey } from "@/lib/api";
import {
  compassLabel,
  fieldFeasibilityLabels,
  formatDate,
  formatGeneratedAt,
  formatHour,
  formatWindowRange,
  potentialLabels,
  seaStateFitLabel,
  speciesAvailabilityLabel,
  speciesAxisKeyLabel,
  speciesAxisStatusLabel,
  speciesThermalLabel,
  springNeapLabel,
  tideLabel,
  tripRuinBasisLabel,
  tripRuinLevelLabel,
  waveIncidenceLabel,
  windRelationLabel,
} from "@/lib/format";
import type {
  DecisionLevel,
  DecisionResponse,
  Factor,
  ForecastDecisionRequest,
  GeminiReportResponse,
  HourDecision,
} from "@/lib/types";

interface SpotReportProps {
  result: DecisionResponse;
  request: ForecastDecisionRequest;
  stale?: boolean;
  onClose: () => void;
}

interface PeriodSummary {
  id: string;
  label: string;
  range: string;
  hours: HourDecision[];
  safety: DecisionLevel | null;
  opportunity: number | null;
  field: number | null;
  confidence: number | null;
  wind: string;
  waves: string;
  water: string;
  warnings: string[];
}

const TUNIS_TZ = "Africa/Tunis";
const GEMINI_KEY_STORAGE = "peche-tn:gemini-api-key";
const GEMINI_KEY_EVENT = "peche-tn:gemini-key-change";
const GEMINI_VERIFY_TIMEOUT_MS = 26_000;
const GEMINI_GENERATE_TIMEOUT_MS = 42_000;

function subscribeGeminiKey(onStoreChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === GEMINI_KEY_STORAGE) onStoreChange();
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(GEMINI_KEY_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(GEMINI_KEY_EVENT, onStoreChange);
  };
}

function geminiKeySnapshot(): string {
  try {
    return window.localStorage.getItem(GEMINI_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

const emptyGeminiKeySnapshot = () => "";

const factorAssessmentLabels = {
  decision: "مستخدم في القرار",
  context: "سياق",
  proxy: "مؤشر غير مباشر يحتاج تحقق",
  unknown: "غير معروف (Unknown)",
  excluded: "مستبعد",
} as const;
const holdingMechanismLabels: Record<string, string> = {
  longshore_current: "الجرّ الجانبي",
  orbital_motion: "حركة القاع المدارية",
  return_flow: "الرجوع للبحر",
  tidal_current: "تيار المدّ",
  none: "لا سبب غالب",
};

const decisionReasonLabels = {
  safe_window: "نافذة اجتازت الحدود الآلية وقابلة للتنفيذ مبدئياً؛ ليست شهادة سلامة ميدانية",
  safety_hazard: "خطر سلامة",
  field_infeasible: "صعوبة مرتفعة متوقعة في تثبيت الخط",
  critical_data_missing: "نقص بيانات حرجة",
  conservative_uncertainty: "تحفظ محافظ",
  fouling_confirmed: "صوفة/عوالق مؤكدة ميدانياً",
  official_warning: "تحذير رسمي ساري",
  trip_ruin_confirmed: "عامل مُفسِد مؤكد (قناديل/حطام/تعكر كثيف)",
} as const;
const PERIODS = [
  { id: "late-night", label: "آخر الليل", range: "00:00–03:59", from: 0, to: 3 },
  { id: "morning", label: "الفجر والصباح", range: "04:00–11:59", from: 4, to: 11 },
  { id: "afternoon", label: "الظهيرة والعشية", range: "12:00–17:59", from: 12, to: 17 },
  { id: "evening", label: "المساء والليل", range: "18:00–23:59", from: 18, to: 23 },
] as const;

const decisionReportLabels: Record<DecisionLevel, string> = {
  go: "اذهب",
  caution: "فرصة مع تحفظات",
  no_go: "لا تذهب",
  unknown: "بيانات غير كافية لقرار مسؤول",
};

const shortDecisionLabels: Record<DecisionLevel, string> = {
  go: "مناسب",
  caution: "حذر",
  no_go: "ممنوع",
  unknown: "ناقص",
};

const targetLabels: Record<ForecastDecisionRequest["angler"]["target_species"], string> = {
  general: "صيد عام",
  european_seabass: "القاروص",
  gilthead_seabream: "الوراطة",
  white_seabream: "السار",
  striped_seabream: "المرمار",
};

const shoreLabels: Record<ForecastDecisionRequest["spot"]["shore_type"], string> = {
  sandy: "شاطئ رملي",
  rocky: "وقوف صخري",
  cliff: "حافة أو جرف",
  jetty: "رصيف أو حاجز بحري",
};

const exposureLabels: Record<ForecastDecisionRequest["spot"]["exposure"], string> = {
  open: "مكشوف",
  partly_sheltered: "محمي جزئياً",
  sheltered: "محمي",
};

const experienceLabels: Record<ForecastDecisionRequest["angler"]["experience"], string> = {
  beginner: "مبتدئ",
  intermediate: "متوسط",
  advanced: "متقدم",
};

const orientationSourceLabels: Record<ForecastDecisionRequest["spot"]["orientation_source"], string> = {
  surveyed: "مقاس ميدانياً",
  manual: "مدخل يدوياً",
  map: "مستخرج من الخريطة",
  overpass: "محسوب من OpenStreetMap Overpass",
  estimated: "تقدير أولي",
};

const orientationConfidenceLabels = {
  high: "مرتفعة",
  medium: "متوسطة",
  low: "منخفضة",
} as const;

const observationStatusLabels: Record<DecisionResponse["observation_comparison"]["status"], string> = {
  consistent: "متسقة ضمن الحدود",
  divergent: "مختلفة عن النموذج",
  limited: "محدودة الصلاحية",
  distant: "بعيدة عن البقعة",
  stale: "قديمة زمنياً",
  unavailable: "غير متاحة",
  not_applicable: "غير قابلة للمطابقة",
};

const safetyPriority: Record<DecisionLevel, number> = {
  go: 0,
  caution: 1,
  unknown: 2,
  no_go: 3,
};

type ReportTab = "summary" | "windows" | "fish" | "feasibility" | "references";

const REPORT_TABS: { key: ReportTab; label: string }[] = [
  { key: "summary", label: "الملخص" },
  { key: "windows", label: "التوقيت والنوافذ" },
  { key: "fish", label: "الأسماك" },
  { key: "feasibility", label: "التنفيذ والعوامل" },
  { key: "references", label: "المراجع والمصادر" },
];

const TAB_ICONS: Record<ReportTab, typeof Clipboard> = {
  summary: Clipboard,
  windows: Clock3,
  fish: Fish,
  feasibility: Anchor,
  references: Database,
};

function localHour(value: string): number {
  return Number(new Intl.DateTimeFormat("en-GB", {
    timeZone: TUNIS_TZ,
    hour: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value)));
}

function numericValues(
  hours: HourDecision[],
  read: (hour: HourDecision) => number | null,
): number[] {
  return hours.map(read).filter((value): value is number => value !== null && Number.isFinite(value));
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function maximum(values: number[]): number | null {
  return values.length ? Math.max(...values) : null;
}

function minimum(values: number[]): number | null {
  return values.length ? Math.min(...values) : null;
}

function metricRange(values: number[], digits = 1, suffix = ""): string {
  if (!values.length) return "غير متوفر";
  const low = Math.min(...values).toFixed(digits);
  const high = Math.max(...values).toFixed(digits);
  return `${low === high ? low : `${low}–${high}`}${suffix}`;
}

function metricValue(
  value: number | null | undefined,
  digits = 1,
  suffix = "",
): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "غير متوفر"
    : `${value.toFixed(digits)}${suffix}`;
}

function signedMetricRange(values: number[], digits = 1, suffix = ""): string {
  if (!values.length) return "غير متوفر";
  const signed = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
  const low = Math.min(...values);
  const high = Math.max(...values);
  return `${low === high ? signed(low) : `${signed(low)} إلى ${signed(high)}`}${suffix}`;
}

function diagnosticRange(values: number[], digits = 1, suffix = ""): string {
  return values.length ? metricRange(values, digits, suffix) : "Unknown";
}

function signedDiagnosticRange(values: number[], digits = 1, suffix = ""): string {
  return values.length ? signedMetricRange(values, digits, suffix) : "Unknown";
}

function diagnosticValue(value: number | null, digits = 2, suffix = ""): string {
  return value === null || !Number.isFinite(value) ? "Unknown" : `${value.toFixed(digits)}${suffix}`;
}

function signedDiagnosticValue(value: number | null, digits = 2, suffix = ""): string {
  return value === null || !Number.isFinite(value)
    ? "Unknown"
    : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}${suffix}`;
}

function coverageText(values: number[], total: number): string {
  return `${values.length}/${total} ساعة`;
}

function maximumAbsolute(values: number[]): number | null {
  return values.length ? Math.max(...values.map((value) => Math.abs(value))) : null;
}

function dominant(values: string[]): string | null {
  if (!values.length) return null;
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts].sort((first, second) => second[1] - first[1])[0]?.[0] ?? null;
}

function uniqueFactors(hours: HourDecision[]): Factor[] {
  const factors = new Map<string, Factor>();
  for (const hour of hours) {
    for (const factor of hour.factors) {
      const key = `${factor.code}:${factor.explanation_ar}`;
      if (!factors.has(key)) factors.set(key, factor);
    }
  }
  return [...factors.values()];
}

function factorPriority(factor: Factor): number {
  const severity = { critical: 30, caution: 20, info: 10 }[factor.severity];
  const impact = { safety: 6, data_gap: 5, negative: 4, neutral: 2, positive: 1 }[factor.impact];
  return severity + impact + Math.min(Math.abs(factor.score_delta), 9) / 10;
}

function worstSafety(hours: HourDecision[]): DecisionLevel | null {
  if (!hours.length) return null;
  return hours.reduce((worst, hour) =>
    safetyPriority[hour.safety] > safetyPriority[worst] ? hour.safety : worst, hours[0].safety);
}

function buildPeriodSummary(
  definition: (typeof PERIODS)[number],
  allHours: HourDecision[],
): PeriodSummary {
  const hours = allHours.filter((hour) => {
    const value = localHour(hour.time);
    return value >= definition.from && value <= definition.to;
  });
  if (!hours.length) {
    return {
      id: definition.id,
      label: definition.label,
      range: definition.range,
      hours,
      safety: null,
      opportunity: null,
      field: null,
      confidence: null,
      wind: "لا توجد ساعات قابلة للتقييم",
      waves: "لا توجد ساعات قابلة للتقييم",
      water: "لا توجد ساعات قابلة للتقييم",
      warnings: [],
    };
  }

  const windSpeeds = numericValues(hours, (hour) => hour.forecast.wind_speed_kmh);
  const gusts = numericValues(hours, (hour) => hour.forecast.wind_gust_kmh);
  const waveHeights = numericValues(hours, (hour) => hour.forecast.wave_height_m);
  const wavePeriods = numericValues(hours, (hour) => hour.forecast.wave_period_s);
  const currents = numericValues(hours, (hour) => hour.forecast.ocean_current_velocity_kmh);
  const relation = dominant(hours.map((hour) => hour.derived.wind_relation).filter((value) => value !== "unknown"));
  const incidence = dominant(hours.map((hour) => hour.derived.wave_incidence).filter((value) => value !== "unknown"));
  const waterState = dominant(hours.map((hour) => hour.derived.tide_state).filter((value) => value !== "unknown"));
  const warnings = uniqueFactors(hours)
    .filter((factor) => factor.severity !== "info" || factor.impact === "data_gap")
    .sort((first, second) => factorPriority(second) - factorPriority(first))
    .slice(0, 3)
    .map((factor) => factor.explanation_ar);

  const windAverage = average(windSpeeds);
  const gustMaximum = maximum(gusts);
  const periodAverage = average(wavePeriods);
  const currentMaximum = maximum(currents);
  return {
    id: definition.id,
    label: definition.label,
    range: definition.range,
    hours,
    safety: worstSafety(hours),
    opportunity: Math.round(average(hours.map((hour) => hour.opportunity_score)) ?? 0),
    field: minimum(hours.map((hour) => hour.field_feasibility.score)),
    confidence: minimum(hours.map((hour) => hour.confidence.score)),
    wind: windAverage === null
      ? "الريح غير متوفرة"
      : `${windAverage.toFixed(1)} كم/س كمعدل${gustMaximum === null ? "" : ` · أقصى هبة ${gustMaximum.toFixed(1)}`} · ${relation ? windRelationLabel(relation) : "العلاقة بالشاطئ ناقصة"}`,
    waves: waveHeights.length
      ? `${metricRange(waveHeights, 2, " م")} · فترة ${periodAverage === null ? "—" : periodAverage.toFixed(1)} ث · ${incidence ? waveIncidenceLabel(incidence) : "العلاقة بالشاطئ ناقصة"}`
      : "بيانات الموج غير متوفرة",
    water: `${waterState ? tideLabel(waterState) : "حركة مستوى البحر ناقصة"}${currentMaximum === null ? "" : ` · تيار نموذجي حتى ${currentMaximum.toFixed(2)} كم/س`}`,
    warnings,
  };
}

function confidenceLabel(score: number): string {
  if (score >= 75) return "مرتفعة";
  if (score >= 55) return "متوسطة";
  return "منخفضة";
}

function activityBand(score: number): "strong" | "medium" | "weak" | "low" {
  if (score >= 66) return "strong";
  if (score >= 50) return "medium";
  if (score >= 36) return "weak";
  return "low";
}

function buildFieldGuidance(
  result: DecisionResponse,
  request: ForecastDecisionRequest,
  periods: PeriodSummary[],
): string[] {
  const guidance: string[] = [
    "هذا التقرير لقطة وقتية، موش متابعة مباشرة للبحر؛ أعد التحليل قريباً من وقت الانطلاق وتثبت من اتصالك ووقت آخر تحديث.",
  ];
  const leadWindow = result.recommended_windows[0];
  if (leadWindow) {
    guidance.push(`إذا قررت الانطلاق، التزم أساساً بنافذة ${formatWindowRange(leadWindow.start, leadWindow.end)} ولا تمددها تلقائياً بعد تغيّر الظروف.`);
  } else {
    guidance.push("لا توجد نافذة متواصلة اجتازت فحص المحرك؛ تغيير البقعة أو اليوم أفضل من تركيب خطة على ساعة منفردة.");
  }

  const field = result.field_feasibility;
  if (field.holding_difficulty === "high") {
    guidance.push("فحص تثبيت الخط مرتفع الصعوبة: لا تعتبر الرصاص الأثقل حلاً تلقائياً؛ ابدأ برمية قصيرة اختبارية، وإذا استمر الجر غيّر الموضع أو أجّل الحصة.");
  } else if (field.holding_difficulty === "moderate") {
    guidance.push("فحص تثبيت الخط متوسط الصعوبة: اختبر جرّ الرصاص وحساسية الخيط قبل نشر بقية العتاد.");
  }
  if (["moderate", "high"].includes(field.fouling_transport_potential)) {
    guidance.push("توجد قابلية لنقل مادة موجودة، لا إثبات لوجود الصوفة: افحص السنارة والخيط بعد رمية اختبارية، وأجّل الحصة إذا تكرر التعلق.");
  }
  if (["moderate", "high"].includes(field.turbidity_potential)) {
    guidance.push("احتمال العكارة مدعوم بعدة عائلات قرائن تشغيلية وليس قياس NTU: افحص لون الماء وخط التصريف ميدانياً ولا تفترض أن التوقع رأى الماء داخل البقعة.");
  }
  if (["moderate", "high"].includes(field.rip_current_potential)) {
    guidance.push("فحص التيار الساحبي ليس رصداً: راقب من مكان آمن ممراً داكناً أو خط رغوة/حطام يتحرك إلى عرض البحر، وابتعد عنه عند الشك.");
  }

  const gustMaximum = maximum(numericValues(result.hourly, (hour) => hour.forecast.wind_gust_kmh));
  if (gustMaximum !== null && gustMaximum >= 40) {
    guidance.push(`الهبات تصل نموذجياً إلى ${gustMaximum.toFixed(0)} كم/س؛ لا تحاول تعويض خطر الوقوف أو فقدان التوازن برصاص أثقل.`);
  } else if (gustMaximum !== null && gustMaximum >= 25) {
    guidance.push(`الهبات تصل إلى ${gustMaximum.toFixed(0)} كم/س؛ راقب الفرق بين الريح المتوسطة والهبة قبل اختيار موضع الوقوف والمعدات.`);
  }

  const dominantRelation = dominant(result.hourly.map((hour) => hour.derived.wind_relation).filter((value) => value !== "unknown"));
  if (dominantRelation === "onshore" || dominantRelation === "cross_onshore") {
    guidance.push("الريح الغالبة من جهة البحر أو مائلة منه؛ راقب رجوع الخيط والمعدات، ولا نستنتج من النموذج مسافة رمي مضمونة.");
  } else if (dominantRelation === "offshore" || dominantRelation === "cross_offshore") {
    guidance.push("الريح الغالبة من جهة البر أو مائلة منه وقد تسهّل الرمي، لكنها لا تثبت وجود السمك في المسافة البعيدة.");
  }

  if (request.spot.shore_type === "rocky" || request.spot.shore_type === "cliff" || request.spot.shore_type === "jetty") {
    guidance.push("نوع الوقوف يحتاج مسار رجوع جافاً وواضحاً؛ افحص الصخور والحواف وارتفاع الماء ميدانياً قبل إنزال العتاد.");
  } else {
    guidance.push("على الشاطئ الرملي، راقب الكسرة والقنوات والتيار الساحبي عشر دقائق على الأقل من مكان آمن قبل اختيار موضعك.");
  }

  const target = targetLabels[request.angler.target_species];
  guidance.push(request.angler.target_species === "general"
    ? "الهدف مضبوط على صيد عام؛ لا يحوّل التقرير ذلك إلى توصية طعم أو نوع سمك غير مدعومة ببيانات محلية."
    : `النوع المستهدف هو ${target}. تأثير ملف النوع في المؤشر محدود ومعلن؛ اختيار الطعم يحتاج معاينة محلية للفرائس والمصيد.`);
  guidance.push("لا نحسب مسافة الرمي أو وزن الرصاص: ذلك يتطلب بيانات القصبة والخيط والرصاص والقاع وقدرة الرامي، وهي غير موجودة في التوقع.");

  if (periods.some((period) => period.confidence !== null && period.confidence < 55)) {
    guidance.push("توجد فترة بثقة منخفضة؛ اعتبر أرقامها سياقاً ناقصاً لا أساساً لمجازفة ميدانية.");
  }
  return guidance;
}

function reportDate(value: string): string {
  return new Intl.DateTimeFormat("ar-TN", {
    timeZone: TUNIS_TZ,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(`${value}T12:00:00+01:00`));
}

function buildReportText(
  result: DecisionResponse,
  request: ForecastDecisionRequest,
  periods: PeriodSummary[],
  obstacles: Factor[],
  positives: Factor[],
  guidance: string[],
  stale: boolean,
): string {
  const hours = result.hourly;
  const leadWindow = result.recommended_windows[0];
  const fieldContext = hours.find((hour) => hour.time === leadWindow?.start) ?? hours[0];
  const lines = [
    `تقرير Peche TN الميداني — ${request.location.name ?? "بقعة مختارة"}`,
    `التاريخ: ${reportDate(request.target_date)}`,
    ...(stale ? ["تحذير: هذا التقرير يخص آخر تحليل، لا تعديلات المخطط التي لم تُحلل بعد."] : []),
    "",
    "0. الملخص التنفيذي",
    `• القرار النهائي: ${decisionReportLabels[result.decision]}`,
    `• سبب القرار: ${decisionReasonLabels[result.decision_reason_code]}`,
    `• قابلية التنفيذ الميداني: ${result.field_feasibility.score}/100 — ${fieldFeasibilityLabels[result.field_feasibility.status]}`,
    `• فحص التنفيذ: صعوبة تثبيت الخط ${potentialLabels[result.field_feasibility.holding_difficulty]} · احتمال الصوفة/الحطام ${potentialLabels[result.field_feasibility.fouling_transport_potential]} (${result.field_feasibility.fouling_evidence_count} عائلات قرائن) · احتمال العكارة ${potentialLabels[result.field_feasibility.turbidity_potential]} (${result.field_feasibility.turbidity_evidence_count} عائلات قرائن) · تيار ساحبي محتمل ${potentialLabels[result.field_feasibility.rip_current_potential]}`,
    "• سلطة مؤشري الصوفة والعكارة: تنبيه وفحص ميداني فقط؛ لا يمنعان وحدهما نافذة اجتازت السلامة بلا رصد فعلي.",
    `• ثقة فحص التنفيذ: ${result.field_feasibility.confidence}/100 (سقف آلي 50؛ ليس رصداً ميدانياً)`,
    `• مؤشر الفرصة النسبي: ${result.opportunity_score}/100 — مؤشر ترتيب وليس نسبة نجاح أو ضمان مصيد`,
    `• ثقة مدخلات الإرشاد: ${result.confidence.score}/100 (${confidenceLabel(result.confidence.score)}) — اكتمال واتساق وأفق، وليست دقة ميدانية متحققة`,
    `• السبب الرئيسي: ${result.summary_ar}`,
    `• الهدف: ${targetLabels[request.angler.target_species]}`,
    "• الطعم والمونتاج: غير محسومين من التوقع وحده؛ يلزمهما رصد محلي للفرائس والقاع ومدخلات العتاد.",
    `• اتجاه البحر: ${request.spot.seaward_orientation_deg.toFixed(0)}° (${compassLabel(request.spot.seaward_orientation_deg)}) — ${orientationSourceLabels[request.spot.orientation_source]}`,
    ...(request.spot.orientation_evidence ? [
      `• دليل الاتجاه: مماس ${request.spot.orientation_evidence.coastline_tangent_deg.toFixed(1)}° · مسافة ساحل ${request.spot.orientation_evidence.coastline_distance_m.toFixed(1)} م · خادم ${request.spot.orientation_evidence.server} · نصف بحث ${request.spot.orientation_evidence.search_radius_m} م · ثقة ${orientationConfidenceLabels[request.spot.orientation_evidence.confidence]}.`,
    ] : []),
    "• تعريف الاتجاه: bearing من نقطة الوقوف إلى عرض البحر؛ اتجاه الريح والموج المعروض هو جهة القدوم، ويحسب المحرك الفرق والمركبات تلقائياً.",
    `• الموقع: ${request.location.latitude.toFixed(4)}, ${request.location.longitude.toFixed(4)} · ${shoreLabels[request.spot.shore_type]} ${exposureLabels[request.spot.exposure]}`,
    ...(result.current_weather_observation ? [
      `• رصد جوي فعلي: ${result.current_weather_observation.station_id} على بعد ${result.current_weather_observation.distance_to_spot_km.toFixed(1)} كم · ${formatGeneratedAt(result.current_weather_observation.observed_at)} · ${result.current_weather_observation.wind_speed_kmh === null ? "الريح غير مسجلة" : `ريح ${result.current_weather_observation.wind_speed_kmh.toFixed(1)} كم/س`} · ${result.current_weather_observation.wind_gust_kmh === null ? "الهبة غير مسجلة" : `هبة ${result.current_weather_observation.wind_gust_kmh.toFixed(1)} كم/س`} · ${result.current_weather_observation.air_temperature_c === null ? "الحرارة غير مسجلة" : `حرارة ${result.current_weather_observation.air_temperature_c.toFixed(1)}°م`}.`,
      `• حدود الرصد: محطة مطار وليست قياساً داخل البقعة؛ حالة المقارنة ${observationStatusLabels[result.observation_comparison.status]}.`,
      `• METAR خام: ${result.current_weather_observation.raw_report}`,
    ] : [`• رصد جوي فعلي: غير متاح؛ ${result.observation_comparison.reasons_ar.join(" ")}`]),
    ...(result.coastal_water_context ? result.coastal_water_context.availability === "available" ? [
      `• Sentinel-2 سياقي: ${result.coastal_water_context.valid_time?.slice(0, 10) ?? "Unknown"} · عمر ${result.coastal_water_context.age_hours === null ? "Unknown" : `${Math.round(result.coastal_water_context.age_hours)} ساعة`} · بعد البكسل ${result.coastal_water_context.pixel_distance_from_spot_m === null ? "Unknown" : `${Math.round(result.coastal_water_context.pixel_distance_from_spot_m)} م`} · دقة ${result.coastal_water_context.spatial_resolution_m} م.`,
      `• TUR ${diagnosticValue(result.coastal_water_context.turbidity_fnu, 2, ` ${result.coastal_water_context.turbidity_unit}`)} · SPM ${diagnosticValue(result.coastal_water_context.suspended_particulate_matter_g_m3, 2, ` ${result.coastal_water_context.suspended_particulate_matter_unit}`)} · CHL-a ${diagnosticValue(result.coastal_water_context.chlorophyll_a_mg_m3, 2, ` ${result.coastal_water_context.chlorophyll_a_unit}`)}. استعادة أقمار صناعية وليست قياساً أو توقعاً ولا تغيّر القرار أو السلامة أو التنفيذ أو الفرصة أو الثقة.`,
    ] : [`• Sentinel-2 سياقي: Unknown — ${result.coastal_water_context.reason_ar}`] : []),
    "",
    "1. التوقيت وحركة المياه",
    `• الشروق: ${result.sunrise ? formatHour(result.sunrise) : "غير متوفر"} · الغروب: ${result.sunset ? formatHour(result.sunset) : "غير متوفر"}`,
    ...result.tide_events.map((event) => `• ${event.kind === "high" ? "قمة" : "قاع"} مستوى بحر نموذجي: ${formatHour(event.time)} · ${event.level_msl_m.toFixed(2)} م`),
    "• لا نعرض عبوراً قمرياً أو فترات سولونار كأنها مدّ مؤكد؛ حركة المياه هنا من نموذج مستوى البحر والتيار.",
    "",
    "2. نوافذ الحصة",
    ...(result.recommended_windows.length
      ? result.recommended_windows.map((window, index) => `• ${index + 1}. ${formatWindowRange(window.start, window.end)} · ${shortDecisionLabels[window.safety]} · تنفيذ ${window.field_score}/100 · فرصة نسبية ${window.opportunity_score}/100 · ثقة مدخلات ${window.confidence_score}/100 — ${window.headline_ar}`)
      : ["• لا توجد نافذة موصى بها."]),
    ...result.avoid_windows.map((window) => `• تجنب ${formatWindowRange(window.start, window.end)} — ${window.key_factors_ar.join(" · ")}`),
    ...(result.recommended_windows.length && result.avoid_windows.length
      ? ["• الفصل الزمني: وجود فترة رعد/خطر لا يلغي نافذة منفصلة اجتازت البوابات؛ لا تمدد النافذة إلى فترة التجنب."]
      : []),
    ...(result.species_activity && result.species_activity.length > 0
      ? [
          "",
          "2أ. نشاط الأنواع خلال فترات اليوم (مؤشر نسبي 0-100)",
          ...result.species_activity.map((species) => {
            const ranked = species.periods
              .filter((period) => period.score !== null)
              .sort((first, second) => (second.score ?? 0) - (first.score ?? 0));
            if (!ranked.length) return `• ${species.label_ar}: لا ساعات مقيمة في هذا اليوم.`;
            const best = ranked[0];
            return `• ${species.label_ar}: الذروة ${best.label_ar} (${best.range_ar}) بمتوسط ${best.score}/100${best.peak_hour_ar ? ` · أفضل ساعة ${best.peak_hour_ar}` : ""}${best.top_factor_ar ? ` · العامل الأبرز: ${best.top_factor_ar}` : ""}`;
          }),
          "• هذا مؤشر نسبي غير معاير وليس احتمالاً إحصائياً لوجود السمك؛ أوزانه أولية من دراسات منشورة وتحتاج سجل مصيد تونسي معايراً.",
        ]
      : []),
    "",
    "3. قابلية التنفيذ الميداني",
    `• الحالة: ${fieldFeasibilityLabels[result.field_feasibility.status]} · ${result.field_feasibility.score}/100`,
    `• صعوبة تثبيت الخط: ${potentialLabels[result.field_feasibility.holding_difficulty]}`,
    ...(result.field_feasibility.holding_breakdown
      ? [
          `• تفكيك أسباب تثبيت الخط: جرّ جانبي ${potentialLabels[result.field_feasibility.holding_breakdown.longshore_current]} · حركة قاع مدارية ${potentialLabels[result.field_feasibility.holding_breakdown.orbital_motion]} (${result.field_feasibility.holding_breakdown.orbital_velocity_band_ms ?? "غير متوفرة"} م/ث، عمق مفترض ${result.field_feasibility.holding_breakdown.depth_band_m} م) · رجوع للبحر ${potentialLabels[result.field_feasibility.holding_breakdown.return_flow]} · تيار مدّ ${potentialLabels[result.field_feasibility.holding_breakdown.tidal_current]} · السبب الغالب: ${holdingMechanismLabels[result.field_feasibility.holding_breakdown.dominant]}.`,
        ]
      : []),
    `• احتمال نقل الصوفة/الحطام: ${potentialLabels[result.field_feasibility.fouling_transport_potential]} من ${result.field_feasibility.fouling_evidence_count} عائلات قرائن تشغيلية مختلفة؛ ليست أرصاداً أو مصادر مستقلة، ولا تثبت وجود المادة ولا تمنع وحدها.`,
    `• احتمال العكارة: ${potentialLabels[result.field_feasibility.turbidity_potential]} من ${result.field_feasibility.turbidity_evidence_count} عائلات قرائن تشغيلية مختلفة؛ ليست قياسات مستقلة للماء ولا توجد قراءة NTU ولا تمنع وحدها.`,
    `• تيار ساحبي محتمل: ${potentialLabels[result.field_feasibility.rip_current_potential]}`,
    `• ثقة هذا الفحص: ${result.field_feasibility.confidence}/100؛ المؤشرات احتمالية وليست رصداً للبقعة.`,
    ...(fieldContext ? [
      `• سياق سابق عند ${formatHour(fieldContext.time)}: مطر 48س ${metricValue(fieldContext.derived.rain_48h_mm, 1, " مم")} (تغطية ${fieldContext.derived.rain_data_hours_48h}/48) · ريح بحرية 48س ${fieldContext.derived.onshore_wind_fraction_48h === null ? "غير متوفر" : `${Math.round(fieldContext.derived.onshore_wind_fraction_48h * 100)}%`} ودفع ${metricValue(fieldContext.derived.onshore_wind_impulse_48h_kmh_h, 1, " كم/س·س")} (تغطية ${fieldContext.derived.wind_data_hours_48h}/48) · طاقة موج تراكمية ${metricValue(fieldContext.derived.wave_energy_integral_48h, 1, " Hs²T·h")} وساعات قوية ${fieldContext.derived.strong_wave_hours_48h} (تغطية ${fieldContext.derived.wave_energy_data_hours_48h}/48) · تاريخ ${fieldContext.derived.history_hours_72h}/72 ساعة.`,
    ] : []),
    ...result.field_feasibility.reasons_ar.map((reason) => `• تفسير: ${reason}`),
    ...result.field_feasibility.limitations_ar.map((limitation) => `• حد: ${limitation}`),
    "",
    "4. التفكيك الزمني",
    ...periods.flatMap((period) => period.hours.length ? [
      `• ${period.label} (${period.range}): سلامة آلية ${period.safety ? shortDecisionLabels[period.safety] : "—"} · أدنى تنفيذ ${period.field}/100 · متوسط الفرصة النسبية ${period.opportunity}/100 · أضعف ثقة مدخلات ${period.confidence}/100`,
      `  الريح: ${period.wind}`,
      `  الموج: ${period.waves}`,
      `  المياه: ${period.water}`,
      ...period.warnings.map((warning) => `  تحذير: ${warning}`),
    ] : [`• ${period.label} (${period.range}): لا توجد ساعات متبقية قابلة للتقييم في هذا الجزء من اليوم.`]),
    "",
    "5. ميزان العوامل",
    "• ملاحظة زمنية: العوامل أدناه مجمعة من اليوم كله؛ ظهور الرعد هنا لا يعني كل الساعات، وفترات التجنب في القسم السابق هي المرجع الزمني.",
    ...(obstacles.length ? obstacles.map((factor) => `• تحفظ/خطر: ${factor.explanation_ar}`) : ["• لا توجد معوقات بارزة في الساعات المقيمة، مع بقاء المعاينة الميدانية واجبة."]),
    ...(positives.length ? positives.map((factor) => `• إيجابي: ${factor.explanation_ar}`) : ["• لا توجد أفضلية إيجابية قوية مثبتة."]),
    "",
    "6. التكتيك الميداني والسلامة",
    ...guidance.map((item) => `• ${item}`),
    "",
    "7. الأرقام المرجعية",
    `• الريح: ${metricRange(numericValues(hours, (hour) => hour.forecast.wind_speed_kmh), 1, " كم/س")} · أقصى هبة ${metricValue(maximum(numericValues(hours, (hour) => hour.forecast.wind_gust_kmh)), 1, " كم/س")}`,
    `• الموج الكلي: ${metricRange(numericValues(hours, (hour) => hour.forecast.wave_height_m), 2, " م")} · الفترة ${metricRange(numericValues(hours, (hour) => hour.forecast.wave_period_s), 1, " ث")}`,
    `• موج الريح: ${metricRange(numericValues(hours, (hour) => hour.forecast.wind_wave_height_m), 2, " م")} · الفترة ${metricRange(numericValues(hours, (hour) => hour.forecast.wind_wave_period_s), 1, " ث")}`,
    `• السويل: ${metricRange(numericValues(hours, (hour) => hour.forecast.swell_height_m), 2, " م")} · الفترة ${metricRange(numericValues(hours, (hour) => hour.forecast.swell_period_s), 1, " ث")}`,
    `• حرارة الماء: ${metricRange(numericValues(hours, (hour) => hour.forecast.sea_surface_temperature_c), 1, "°م")} · الهواء ${metricRange(numericValues(hours, (hour) => hour.forecast.air_temperature_c), 1, "°م")}`,
    `• الضغط: ${metricRange(numericValues(hours, (hour) => hour.forecast.pressure_msl_hpa), 1, " hPa")} · تغير 3س ${signedMetricRange(numericValues(hours, (hour) => hour.derived.pressure_change_3h_hpa), 1, " hPa")}`,
    `• التيار البحري النموذجي: ${metricRange(numericValues(hours, (hour) => hour.forecast.ocean_current_velocity_kmh), 2, " كم/س")}`,
    `• مستوى البحر النموذجي: ${metricRange(numericValues(hours, (hour) => hour.forecast.sea_level_height_msl_m), 2, " م")}`,
    ...(hours.length ? [
      `• محور alongshore الموجب: bearing ${(hours[0].derived.alongshore_positive_bearing_deg).toFixed(0)}° = (S+90) mod 360. الحقل القديم |V∥| قيمة مطلقة؛ الحقل الموقّع يبيّن الجهة.`,
      `• تغطية المشتقات: ريح موقّعة ${coverageText(numericValues(hours, (hour) => hour.derived.wind_alongshore_signed_component_kmh), hours.length)} · إجهاد ريح ${coverageText(numericValues(hours, (hour) => hour.derived.wind_stress_pa), hours.length)} · تقاطع موج ${coverageText(numericValues(hours, (hour) => hour.derived.wave_component_angle_deg), hours.length)} · تماسك اتجاه ${coverageText(numericValues(hours, (hour) => hour.derived.wind_direction_coherence_6h), hours.length)}.`,
      `• النطاقات: V∥ الموقّع ${signedMetricRange(numericValues(hours, (hour) => hour.derived.wind_alongshore_signed_component_kmh), 2, " كم/س")} · τ ${metricRange(numericValues(hours, (hour) => hour.derived.wind_stress_pa), 4, " Pa")} · دفع موج موقّع ${signedMetricRange(numericValues(hours, (hour) => hour.derived.alongshore_wave_signed_proxy), 2, " Hs²T")} · زاوية التقاطع ${metricRange(numericValues(hours, (hour) => hour.derived.wave_component_angle_deg), 0, "°")}.`,
      "• المعادلات: Δ=wrap(Dfrom−S)، نحو الشاطئ V⊥=VcosΔ، alongshore الموقّع V∥=−VsinΔ، والحقل القديم |V∥|. للتيار towards: C⊥=VcosΔc موجب نحو البحر وC∥=VsinΔc موجب على المحور الموازي المعلن. L₀=gT²/(2π)، والانحدار=Hs/L₀. τ⃗=ρair Cd |U10|U⃗10 بوحدة Pa. R=|ΣUi e^{iθi}|/ΣUi مع استبعاد U<5 كم/س. حصة النظام الأضعف=min(Hww²,Hsw²)/(Hww²+Hsw²). لا عتبة قرار لهذه التشخيصات.",
      ...hours.map((hour) =>
        `• ${formatHour(hour.time)} | ريح Δ ${diagnosticValue(hour.derived.wind_angle_deg, 1, "°")}, V⊥ ${signedDiagnosticValue(hour.derived.wind_shoreward_component_kmh, 2)}, V∥ ${signedDiagnosticValue(hour.derived.wind_alongshore_signed_component_kmh, 2)} كم/س | τ ${diagnosticValue(hour.derived.wind_stress_pa, 4)}, τ⊥ ${signedDiagnosticValue(hour.derived.wind_stress_shoreward_pa, 4)}, τ∥ ${signedDiagnosticValue(hour.derived.wind_stress_alongshore_pa, 4)} Pa | موج Δ ${diagnosticValue(hour.derived.wave_angle_deg, 1, "°")}, L₀ ${diagnosticValue(hour.derived.deep_water_wavelength_m, 1, " م")}, Hs/L₀ ${diagnosticValue(hour.derived.wave_steepness, 4)}, H²T ${diagnosticValue(hour.derived.wave_energy_proxy, 2)}, دفع∥ ${signedDiagnosticValue(hour.derived.alongshore_wave_signed_proxy, 2)} | موج ريح/سويل ${diagnosticValue(hour.derived.wave_component_angle_deg, 0, "°")} + حصة أضعف ${hour.derived.wave_component_secondary_energy_share === null ? "Unknown" : `${(hour.derived.wave_component_secondary_energy_share * 100).toFixed(0)}%`} | تيار ⊥ ${signedDiagnosticValue(hour.derived.current_cross_shore_kmh, 2)}, ∥ ${signedDiagnosticValue(hour.derived.current_alongshore_kmh, 2)} كم/س | R6 ${diagnosticValue(hour.derived.wind_direction_coherence_6h, 2)} (${hour.derived.wind_direction_data_hours_6h}/6).`,
      ),
    ] : []),
    "",
    "8. المصادر وحدود المطابقة",
    ...(result.sources.length ? result.sources.map((source) => `• ${source.provider} / ${source.product} · ${source.data_kind === "model_forecast" ? "توقع نموذجي وليس رصداً" : source.data_kind === "direct_observation" ? "رصد فعلي في محطة، وليس داخل البقعة" : source.data_kind === "remote_sensing_estimate" ? "استعادة أقمار صناعية سياقية، وليست قياساً أو توقعاً" : source.data_kind}${source.horizontal_resolution_km ? ` · دقة أفقية تقريبية ${source.horizontal_resolution_km} كم` : ""}`) : ["• المصدر: غير متوفر"]),
    "",
    "9. تدقيق مصفوفة العوامل",
    `• الإصدار: ${result.factor_coverage.catalog_version} · العدد التشغيلي المصحح ${result.factor_coverage.audited_total} عاملاً؛ ذِكر ${result.factor_coverage.source_claimed_total} في المصدر الأصلي محفوظ للتتبع فقط.`,

    `• قرار آلي ${result.factor_coverage.automated_decision} · سياق آلي ${result.factor_coverage.automated_context} · proxy مع تحقق ${result.factor_coverage.proxy_requires_field_check} · ميداني/خارجي ${result.factor_coverage.field_or_external_required} · مستبعد ${result.factor_coverage.excluded_unsupported}.`,
    `• ${result.factor_coverage.note_ar}`,
    ...result.factor_assessments.map((factor) =>
      `• [${factor.matrix_id}] ${factor.title_ar} — ${factorAssessmentLabels[factor.status]} — ${factor.value_ar}${factor.affects_final_decision ? result.decision === "go" ? " — دخل بوابة الحسم النهائي" : " — مؤثر في سبب قرار لا تذهب" : ""}`,
    ),
    ...result.confidence.reasons_ar.map((reason) => `• سبب ثقة: ${reason}`),
    ...result.limitations_ar.map((limitation) => `• حد: ${limitation}`),
    `حُدّث التقرير: ${formatGeneratedAt(result.generated_at)} · schema ${result.schema_version} · engine ${result.engine_version}`,
    "Peche TN أداة دعم قرار وليست نشرة ملاحة أو ضمان سلامة أو مصيد.",
  ];
  return lines.join("\n");
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back for embedded browsers that expose Clipboard but deny its permission.
    }
  }
  const textArea = document.createElement("textarea");
  textArea.value = value;
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.append(textArea);
  textArea.select();
  const copied = document.execCommand("copy");
  textArea.remove();
  if (!copied) throw new Error("Copy failed");
}

export function SpotReport({ result, request, stale = false, onClose }: SpotReportProps) {
  const [copyState, setCopyState] = useState<"idle" | "done" | "error">("idle");
  const [reportTab, setReportTab] = useState<ReportTab>("summary");
  const persistedGeminiKey = useSyncExternalStore(
    subscribeGeminiKey,
    geminiKeySnapshot,
    emptyGeminiKeySnapshot,
  );
  const [geminiKeyDraft, setGeminiKeyDraft] = useState<string | null>(null);
  const [storageRiskChoice, setStorageRiskChoice] = useState<boolean | null>(null);
  const geminiKey = geminiKeyDraft ?? persistedGeminiKey;
  const geminiKeySaved = Boolean(persistedGeminiKey && persistedGeminiKey === geminiKey);
  const storageRiskAccepted = storageRiskChoice ?? Boolean(persistedGeminiKey);
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [geminiBusy, setGeminiBusy] = useState<"idle" | "verify" | "generate">("idle");
  const [geminiStatus, setGeminiStatus] = useState<{
    kind: "success" | "error" | "info";
    text: string;
  } | null>(null);
  const [geminiReport, setGeminiReport] = useState<GeminiReportResponse | null>(null);
  const geminiAbort = useRef<AbortController | null>(null);

  useEffect(() => () => {
    const activeRequest = geminiAbort.current;
    geminiAbort.current = null;
    activeRequest?.abort();
  }, []);

  const factors = useMemo(() => uniqueFactors(result.hourly), [result.hourly]);
  const obstacles = useMemo(() => factors
    .filter((factor) => factor.severity !== "info" || ["negative", "safety", "data_gap"].includes(factor.impact))
    .sort((first, second) => factorPriority(second) - factorPriority(first))
    .slice(0, 8), [factors]);
  const positives = useMemo(() => factors
    .filter((factor) => factor.impact === "positive" && factor.score_delta > 0)
    .sort((first, second) => second.score_delta - first.score_delta)
    .slice(0, 6), [factors]);
  const periods = useMemo(() => PERIODS.map((period) => buildPeriodSummary(period, result.hourly)), [result.hourly]);
  const guidance = useMemo(() => buildFieldGuidance(result, request, periods), [periods, request, result]);
  const reportText = useMemo(
    () => buildReportText(result, request, periods, obstacles, positives, guidance, stale),
    [guidance, obstacles, periods, positives, request, result, stale],
  );
  const activeReportText = geminiReport?.report_text ?? reportText;
  const primaryReason = result.summary_ar;
  const leadWindow = result.recommended_windows[0];
  const fieldContext = result.hourly.find((hour) => hour.time === leadWindow?.start) ?? result.hourly[0];
  const windValues = numericValues(result.hourly, (hour) => hour.forecast.wind_speed_kmh);
  const gustValues = numericValues(result.hourly, (hour) => hour.forecast.wind_gust_kmh);
  const waveValues = numericValues(result.hourly, (hour) => hour.forecast.wave_height_m);
  const wavePeriodValues = numericValues(result.hourly, (hour) => hour.forecast.wave_period_s);
  const windWaveValues = numericValues(result.hourly, (hour) => hour.forecast.wind_wave_height_m);
  const windWavePeriodValues = numericValues(result.hourly, (hour) => hour.forecast.wind_wave_period_s);
  const swellValues = numericValues(result.hourly, (hour) => hour.forecast.swell_height_m);
  const swellPeriodValues = numericValues(result.hourly, (hour) => hour.forecast.swell_period_s);
  const waterTemperatures = numericValues(result.hourly, (hour) => hour.forecast.sea_surface_temperature_c);
  const airTemperatures = numericValues(result.hourly, (hour) => hour.forecast.air_temperature_c);
  const pressures = numericValues(result.hourly, (hour) => hour.forecast.pressure_msl_hpa);
  const pressureChanges = numericValues(result.hourly, (hour) => hour.derived.pressure_change_3h_hpa);
  const currents = numericValues(result.hourly, (hour) => hour.forecast.ocean_current_velocity_kmh);
  const seaLevels = numericValues(result.hourly, (hour) => hour.forecast.sea_level_height_msl_m);
  const precipitation = numericValues(result.hourly, (hour) => hour.forecast.precipitation_mm);
  const visibility = numericValues(result.hourly, (hour) => hour.forecast.visibility_m);
  const signedWindAlongshore = numericValues(result.hourly, (hour) => hour.derived.wind_alongshore_signed_component_kmh);
  const windStress = numericValues(result.hourly, (hour) => hour.derived.wind_stress_pa);
  const windStressShoreward = numericValues(result.hourly, (hour) => hour.derived.wind_stress_shoreward_pa);
  const windStressAlongshore = numericValues(result.hourly, (hour) => hour.derived.wind_stress_alongshore_pa);
  const signedWaveForcing = numericValues(result.hourly, (hour) => hour.derived.alongshore_wave_signed_proxy);
  const componentAngles = numericValues(result.hourly, (hour) => hour.derived.wave_component_angle_deg);
  const secondaryShares = numericValues(result.hourly, (hour) => hour.derived.wave_component_secondary_energy_share);
  const directionCoherence = numericValues(result.hourly, (hour) => hour.derived.wind_direction_coherence_6h);
  const currentAlongshore = numericValues(result.hourly, (hour) => hour.derived.current_alongshore_kmh);
  const currentCrossShore = numericValues(result.hourly, (hour) => hour.derived.current_cross_shore_kmh);
  const airSeaDifferences = numericValues(result.hourly, (hour) => hour.derived.air_sea_temperature_difference_c);
  const dewPointDepressions = numericValues(result.hourly, (hour) => hour.derived.dew_point_depression_c);

  const saveGeminiKey = () => {
    if (!storageRiskAccepted || !geminiKey.trim()) return;
    try {
      window.localStorage.setItem(GEMINI_KEY_STORAGE, geminiKey.trim());
      setGeminiKeyDraft(null);
      setStorageRiskChoice(true);
      window.dispatchEvent(new Event(GEMINI_KEY_EVENT));
      setGeminiStatus({
        kind: "info",
        text: "حُفظ المفتاح في localStorage على هذا المتصفح فقط. لم يُرسل بعد إلى Google.",
      });
    } catch {
      setGeminiStatus({ kind: "error", text: "تعذر الحفظ المحلي؛ إعدادات المتصفح قد تمنع التخزين." });
    }
  };

  const deleteGeminiKey = () => {
    const activeRequest = geminiAbort.current;
    geminiAbort.current = null;
    activeRequest?.abort();
    try {
      window.localStorage.removeItem(GEMINI_KEY_STORAGE);
    } catch {
      // State is still cleared when browser storage is unavailable.
    }
    window.dispatchEvent(new Event(GEMINI_KEY_EVENT));
    setGeminiKeyDraft("");
    setShowGeminiKey(false);
    setStorageRiskChoice(false);
    setGeminiReport(null);
    setGeminiBusy("idle");
    setGeminiStatus({ kind: "success", text: "حُذف المفتاح من هذا المتصفح." });
  };

  const testGeminiKey = async () => {
    if (!geminiKey.trim()) return;
    geminiAbort.current?.abort();
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, GEMINI_VERIFY_TIMEOUT_MS);
    geminiAbort.current = controller;
    setGeminiBusy("verify");
    setGeminiStatus(null);
    try {
      const verification = await verifyGeminiKey(geminiKey.trim(), controller.signal);
      setGeminiStatus({ kind: "success", text: verification.message_ar });
    } catch (cause) {
      if (controller.signal.aborted && !timedOut) return;
      setGeminiStatus({
        kind: "error",
        text: timedOut
          ? "انتهت مهلة اختبار Gemini؛ لم يُخزن المفتاح في الخادم."
          : cause instanceof Error
            ? cause.message
            : "تعذر اختبار المفتاح.",
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (geminiAbort.current === controller) {
        geminiAbort.current = null;
        setGeminiBusy("idle");
      }
    }
  };

  const generateWithGemini = async () => {
    if (!geminiKey.trim()) return;
    geminiAbort.current?.abort();
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, GEMINI_GENERATE_TIMEOUT_MS);
    geminiAbort.current = controller;
    setGeminiBusy("generate");
    setGeminiStatus({
      kind: "info",
      text: "أرسلنا إلى Gemini حزمة سرد مصغرة بلا الإحداثيات أو السلاسل الرقمية الخام؛ يمكنك إيقاف الانتظار.",
    });
    try {
      const generated = await requestGeminiReport(
        geminiKey.trim(),
        request,
        result,
        controller.signal,
      );
      setGeminiReport(generated);
      setGeminiStatus({
        kind: "success",
        text: "تم التحقق من JSON وبناء التقرير. القرار والأرقام بقيت من المحرك الحتمي.",
      });
    } catch (cause) {
      if (controller.signal.aborted && !timedOut) return;
      setGeminiReport(null);
      setGeminiStatus({
        kind: "error",
        text: timedOut
          ? "أوقفنا انتظار Gemini عند المهلة المحددة؛ يمكنك نسخ أو تنزيل التقرير الحتمي كاملاً."
          : cause instanceof Error
            ? `${cause.message} يمكنك نسخ أو تنزيل التقرير الحتمي كاملاً.`
            : "تعذر توليد السرد؛ التقرير الحتمي بقي كاملاً.",
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (geminiAbort.current === controller) {
        geminiAbort.current = null;
        setGeminiBusy("idle");
      }
    }
  };

  const cancelGeminiGeneration = () => {
    const activeRequest = geminiAbort.current;
    geminiAbort.current = null;
    activeRequest?.abort();
    setGeminiBusy("idle");
    setGeminiStatus({
      kind: "info",
      text: "ألغيت انتظار Gemini؛ التقرير الحتمي بقي كاملاً وجاهزاً للنسخ أو التنزيل.",
    });
  };

  const handleCopy = async () => {
    try {
      await copyText(activeReportText);
      setCopyState("done");
    } catch {
      setCopyState("error");
    }
    window.setTimeout(() => setCopyState("idle"), 2500);
  };

  const handleWhatsAppShare = () => {
    const maxCharacters = 3500;
    const shareText = activeReportText.length > maxCharacters
      ? `${activeReportText.slice(0, maxCharacters)}\n\n… التقرير مختصر بسبب حد المشاركة؛ نزّل TXT من Peche TN للتقرير الكامل.`
      : activeReportText;
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, "_blank", "noopener,noreferrer");
  };

  const handleDownload = () => {
    const blob = new Blob([activeReportText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `peche-tn-${request.target_date}-report.txt`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handlePrint = () => {
    const root = document.documentElement;
    const cleanup = () => root.classList.remove("print-spot-report");
    root.classList.add("print-spot-report");
    window.addEventListener("afterprint", cleanup, { once: true });
    window.print();
  };

  return (
    <section className="spot-report" id="spot-report" aria-labelledby="spot-report-title" aria-live="off">
      <header className="report-header">
        <div className="report-title-wrap">
          <span className="report-title-icon"><FileText size={24} /></span>
          <div>
            <span className="report-kicker"><ShieldCheck size={14} /> تقرير ميداني قابل للتحقق</span>
            <h2 id="spot-report-title" tabIndex={-1}>تقرير {request.location.name ?? "البقعة المختارة"}</h2>
            <p>{reportDate(request.target_date)} · حُدّث {formatGeneratedAt(result.generated_at)}</p>
          </div>
        </div>
        <div className="report-actions" aria-live="polite">
          <button type="button" onClick={handleCopy}><Copy size={16} />{copyState === "done" ? "تم النسخ" : copyState === "error" ? "تعذّر النسخ" : "انسخ التقرير"}</button>
          <button type="button" onClick={handleDownload}><Download size={16} />نزّل TXT</button>
          <button type="button" onClick={handleWhatsAppShare}><MessageCircle size={16} />واتساب</button>
          <button type="button" onClick={() => document.getElementById("gemini-report-title")?.scrollIntoView({ behavior: "smooth", block: "start" })}><WandSparkles size={16} />Gemini اختياري</button>
          <button type="button" onClick={handlePrint}><Printer size={16} />اطبع / PDF</button>
          <button className="report-close" type="button" onClick={onClose}><X size={18} />أغلق</button>
        </div>
      </header>

      {stale && <div className="report-stale" role="alert"><AlertTriangle size={18} /><span><strong>التقرير يخص آخر تحليل.</strong> التعديلات الحالية في المخطط مازالت ما تحلّلتش؛ حدّث القرار قبل اعتمادها.</span></div>}

      <div className="report-integrity" role="note">
        <Info size={19} />
        <p><strong>نسخة علمية، موش تنجيم.</strong> الرقم هو مؤشر فرصة نسبي وليس «نسبة نجاح». لا نختلق سولونار أو مدّاً قمرياً أو مسافة رمي؛ ومؤشرات الصوفة والتيار الساحبي احتمالية منخفضة الثقة وليست رصداً فعلياً.</p>
      </div>

      <div className="report-tabs" role="tablist" aria-label="أقسام التقرير">
        {REPORT_TABS.map((tab) => {
          const Icon = TAB_ICONS[tab.key];
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={reportTab === tab.key}
              className={reportTab === tab.key ? "active" : ""}
              onClick={() => setReportTab(tab.key)}
            >
              <Icon size={15} />{tab.label}
            </button>
          );
        })}
      </div>

      <section className="report-section" aria-labelledby="report-summary-title" hidden={reportTab !== "summary"}>
        <div className="report-section-title"><span>0</span><div><h3 id="report-summary-title">الملخص التنفيذي</h3><p>القرار والسياق الذي بُني عليه.</p></div></div>
        <div className="report-summary-grid">
          <article className={`report-verdict report-verdict-${result.decision}`}><small>القرار النهائي · {decisionReasonLabels[result.decision_reason_code]}</small><strong>{decisionReportLabels[result.decision]}</strong><p>{result.summary_ar}</p></article>
          <article className="report-field-summary"><small>قابلية التنفيذ الميداني</small><strong><bdi>{result.field_feasibility.score}/100</bdi></strong><p>{fieldFeasibilityLabels[result.field_feasibility.status]} · ثقة الفحص {result.field_feasibility.confidence}/100.</p></article>
          <article><small>مؤشر الفرصة النسبي</small><strong><bdi>{result.opportunity_score}/100</bdi></strong><p>ترتيب نسبي، موش احتمال مصيد.</p></article>
          <article><small>ثقة مدخلات الإرشاد</small><strong><bdi>{result.confidence.score}/100</bdi></strong><p>{confidenceLabel(result.confidence.score)} · اكتمال واتساق وأفق، لا دقة ميدانية. {result.recommended_windows.length ? "أضعف قيمة داخل النافذة الأفضل." : "أضعف قيمة خلال الساعات المقيمة."}</p></article>
          <article><small>الهدف والإعداد</small><strong>{targetLabels[request.angler.target_species]}</strong><p>{experienceLabels[request.angler.experience]} · {request.angler.session_hours} س · {shoreLabels[request.spot.shore_type]} {exposureLabels[request.spot.exposure]}<br />الطعم والمونتاج يحتاجان معطيات ميدانية إضافية.</p></article>
          <article><small>اتجاه البحر من موضع الوقوف</small><strong><bdi>{request.spot.seaward_orientation_deg.toFixed(0)}° · {compassLabel(request.spot.seaward_orientation_deg)}</bdi></strong><p>{orientationSourceLabels[request.spot.orientation_source]}</p></article>
          {request.spot.orientation_evidence && <article><small>مصدر اتجاه الساحل</small><strong><bdi>مماس {request.spot.orientation_evidence.coastline_tangent_deg.toFixed(1)}° · بعد {request.spot.orientation_evidence.coastline_distance_m.toFixed(0)} م</bdi></strong><p>Overpass · نصف بحث {request.spot.orientation_evidence.search_radius_m} م · ثقة {orientationConfidenceLabels[request.spot.orientation_evidence.confidence]}<br /><bdi>{request.spot.orientation_evidence.server}</bdi></p></article>}
          <article><small>الإحداثيات</small><strong><bdi>{request.location.latitude.toFixed(4)}, {request.location.longitude.toFixed(4)}</bdi></strong><p>ثبّت نقطة الوقوف واتجاه الجزء الفعلي من الشاطئ.</p></article>
          {result.current_weather_observation ? <article className="report-observation-summary"><small>الرصد الجوي الفعلي الأقرب</small><strong><bdi>{result.current_weather_observation.station_id} · {result.current_weather_observation.distance_to_spot_km.toFixed(1)} كم</bdi></strong><p>{result.current_weather_observation.wind_speed_kmh === null ? "الريح غير مسجلة" : `ريح ${result.current_weather_observation.wind_speed_kmh.toFixed(1)} كم/س`} · {result.current_weather_observation.wind_gust_kmh === null ? "الهبة غير مسجلة" : `هبة ${result.current_weather_observation.wind_gust_kmh.toFixed(1)} كم/س`} · {formatGeneratedAt(result.current_weather_observation.observed_at)}.<br />محطة مطار، موش قياس داخل البقعة.</p></article> : <article className="report-observation-summary"><small>الرصد الجوي الفعلي الأقرب</small><strong>غير متاح</strong><p>{result.observation_comparison.reasons_ar.join(" ")}</p></article>}
        </div>
        <div className="report-primary-reason"><AlertTriangle size={18} /><span><strong>السبب الأهم:</strong> {primaryReason}</span></div>
      </section>

      <section className="report-section" aria-labelledby="report-water-title" hidden={reportTab !== "windows"}>
        <div className="report-section-title"><span>1</span><div><h3 id="report-water-title">التوقيت وحركة المياه</h3><p>توقيت شمسي وحركة نموذجية، لا مواقيت قمرية مصطنعة.</p></div></div>
        <div className="sun-times">
          <div><Sunrise size={20} /><span>الشروق<strong>{result.sunrise ? formatHour(result.sunrise) : "غير متوفر"}</strong></span></div>
          <div><Sunset size={20} /><span>الغروب<strong>{result.sunset ? formatHour(result.sunset) : "غير متوفر"}</strong></span></div>
        </div>
        {result.tide_events.length ? (
          <div className="report-water-events">
            {result.tide_events.map((event) => <article key={`${event.kind}-${event.time}`}><Droplets size={18} /><span><small>{event.kind === "high" ? "قمة مستوى نموذجية" : "قاع مستوى نموذجي"}</small><strong>{formatHour(event.time)}</strong></span><bdi>{event.level_msl_m.toFixed(2)} م</bdi></article>)}
          </div>
        ) : <p className="report-empty">ما توفرش تغير كافٍ لاستخراج قمم أو قيعان نموذجية مسؤولة.</p>}
        <p className="report-method-note"><Info size={15} />هذه الأحداث مستخرجة من مستوى البحر النموذجي وليست جدول مدّ ملاحي. تيار الكسرة والسحب قرب الشاطئ غير مرئي للنموذج.</p>
      </section>

      <section className="report-section" aria-labelledby="report-windows-title" hidden={reportTab !== "windows"}>
        <div className="report-section-title"><span>2</span><div><h3 id="report-windows-title">نوافذ الحصة</h3><p>فترات متواصلة، وليست ساعة خضراء معزولة.</p></div></div>
        {result.recommended_windows.length ? <div className="report-window-list">{result.recommended_windows.map((window, index) => (
          <article key={`${window.start}-${window.end}`} className={index === 0 ? "lead" : ""}>
            <span className="report-window-rank">{index === 0 ? <><Sparkles size={13} /> الأنسب</> : `خيار ${index + 1}`}</span>
            <strong><bdi>{formatWindowRange(window.start, window.end)}</bdi></strong>
            <div><span>تنفيذ {window.field_score}/100</span><span>فرصة {window.opportunity_score}/100</span><span>ثقة مدخلات {window.confidence_score}/100</span><span className={`report-safety-${window.safety}`}>{shortDecisionLabels[window.safety]}</span></div>
            <p>{window.headline_ar}</p>
          </article>
        ))}</div> : <p className="report-empty">لا توجد نافذة متواصلة اجتازت حدود المحرك.</p>}
        {result.avoid_windows.length > 0 && <div className="report-avoid"><strong>فترات تتجنبها</strong>{result.avoid_windows.map((window) => <p key={`${window.start}-${window.end}`}><AlertTriangle size={15} /><bdi>{formatWindowRange(window.start, window.end)}</bdi><span>{window.key_factors_ar.join(" · ")}</span></p>)}</div>}
        {result.recommended_windows.length > 0 && result.avoid_windows.length > 0 && <p className="report-method-note"><Info size={15} /><span><strong>الخطر مربوط بوقته.</strong> فترة الرعد أو التجنب لا تلغي نافذة أخرى اجتازت البوابات؛ التزم بحدود النافذة ولا تمددها إلى وقت الخطر.</span></p>}
      </section>

      <section className="report-section report-species-section" aria-labelledby="report-species-title" hidden={reportTab !== "fish"}>
        <div className="report-section-title"><span>3</span><div><h3 id="report-species-title">الأسماك</h3><p>توفر الأنواع الأربعة ونشاطها خلال فترات اليوم والمنحنى الساعي.</p></div></div>
        {result.species_axes && (
          <div className="report-species-axes">
            <div className="report-gear-head">
              <span>🐟 محور الأنواع ({result.species_axes.label_ar})</span>
              <small>ثقة {result.species_axes.confidence}/30 · تقريري لا يغيّر القرار</small>
            </div>
            <div className="report-species-grid">
              {result.species_axes.axes.map((axis) => (
                <article key={axis.axis} className={`species-${axis.status}`}>
                  <header>
                    <strong>{axis.label_ar}</strong>
                    <em className={`chip chip-species-${axis.status}`}>{speciesAxisStatusLabel(axis.status)}</em>
                  </header>
                  {axis.evidence_ar.length > 0 ? (
                    <ul>{axis.evidence_ar.map((line) => <li key={line}>{line}</li>)}</ul>
                  ) : (
                    <p>غير معروف — ينتظر تدقيق المصادر أو سجل المصيد.</p>
                  )}
                </article>
              ))}
            </div>
            {result.species_axes.species_matches && result.species_axes.species_matches.length > 0 && (
              <div className="report-species-matches">
                <div className="report-species-matches-head">
                  <span>🐟 توفر الأسماك اليوم وملاءمتها للعوامل الحالية</span>
                  <small>ترتيب من الأنسب إلى الأضعف · تقريري لا يغيّر القرار</small>
                </div>
                {result.species_axes.sea_state_ar && (
                  <p className="report-sea-state-line">🌊 {result.species_axes.sea_state_ar}</p>
                )}
                {result.species_axes.species_matches.map((match) => (
                  <article key={match.species} className={`species-match species-match-${match.status}`}>
                    <header>
                      <strong>{match.label_ar}</strong>
                      <span className="species-match-chips">
                        <em className={`chip chip-availability-${match.availability}`}>توفر {speciesAvailabilityLabel(match.availability)}</em>
                        <em className={`chip chip-species-${match.status}`}>{speciesAxisStatusLabel(match.status)}</em>
                      </span>
                    </header>
                    <p>
                      <span>حرارة الماء: {speciesThermalLabel(match.thermal)}</span>
                      {match.habitat_match !== null && (
                        <span> · القاع: {match.habitat_match ? "ملائم" : "خارج التفضيل"}</span>
                      )}
                    </p>
                    <ul>{match.reasons_ar.map((line) => <li key={line}>{line}</li>)}</ul>
                    {match.sea_state_fit && match.sea_state_ar && (
                      <p className="species-match-sea-state">
                        🌊 {match.sea_state_ar} — <span className={`ss-fit-${match.sea_state_fit}`}>{seaStateFitLabel(match.sea_state_fit)}</span>
                        {match.sea_state_preference_ar ? <> · يفضّل: {match.sea_state_preference_ar}</> : null}
                      </p>
                    )}
                    {match.sources_ar && match.sources_ar.length > 0 && (
                      <p className="species-match-sources">📚 {match.sources_ar[0]}</p>
                    )}
                  </article>
                ))}
                <p className="report-method-note"><Info size={15} /><span>التوفر مشتق من دراسات علمية منشورة لتونس والمتوسط (انظر المصادر أعلاه)، وليس سجل مصيد تونسي ولا احتمال صيد؛ المعاينة الميدانية تبقى الحكم.</span></p>
              </div>
            )}
            {result.species_activity && result.species_activity.length > 0 && (
              <div className="report-species-activity">
                <div className="report-species-matches-head">
                  <span>🕐 نشاط الأسماك خلال فترات اليوم</span>
                  <small>مؤشر نسبي 0–100 · ليس احتمالاً ولا وعداً بالمصيد</small>
                </div>
                <div className="species-activity-table-wrap" tabIndex={0} aria-label="جدول نشاط الأنواع حسب فترات اليوم">
                  <table className="species-activity-table">
                    <thead>
                      <tr>
                        <th scope="col">النوع</th>
                        {result.species_activity[0].periods.map((period) => (
                          <th key={period.key} scope="col"><span>{period.label_ar}</span><small>{period.range_ar}</small></th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.species_activity.map((species) => (
                        <tr key={species.species}>
                          <th scope="row">{species.label_ar}</th>
                          {species.periods.map((period) => (
                            <td
                              key={period.key}
                              className={period.score === null ? "act-none" : `act-${activityBand(period.score)}`}
                              title={period.score === null ? "لا ساعات مقيمة في هذه الفترة" : `${period.label_ar} · متوسط ${period.score}/100${period.top_factor_ar ? ` · ${period.top_factor_ar}` : ""}${period.peak_hour_ar ? ` · الذروة ${period.peak_hour_ar}` : ""}`}
                            >
                              <strong>{period.score === null ? "—" : period.score}</strong>
                              {period.peak_hour_ar ? <small>{period.peak_hour_ar}</small> : null}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="species-activity-cards">
                  {result.species_activity.map((species) => (
                    <article className="species-activity-card" key={`card-${species.species}`}>
                      <header>{species.label_ar}</header>
                      <div className="species-activity-card-periods">
                        {species.periods.map((period) => (
                          <div
                            key={period.key}
                            className={period.score === null ? "act-none" : `act-${activityBand(period.score)}`}
                            title={period.score === null ? "لا ساعات مقيمة في هذه الفترة" : `${period.peak_hour_ar ? `الذروة ${period.peak_hour_ar} · ` : ""}${period.top_factor_ar ?? ""}`}
                          >
                            <span>{period.label_ar}</span>
                            <strong>{period.score === null ? "—" : period.score}</strong>
                            {period.peak_hour_ar ? <small>{period.peak_hour_ar}</small> : null}
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
                {result.species_activity.map((species) => (
                  <div className="species-activity-hourly" key={`hourly-${species.species}`}>
                    <span className="species-activity-name">{species.label_ar}</span>
                    <div className="species-activity-bars">
                      {species.hourly.map((hour) => (
                        <div
                          key={hour.time}
                          className={`species-activity-bar${hour.is_twilight ? " is-twilight" : ""}${hour.is_night ? " is-night" : ""}`}
                          style={{ height: `${Math.max(5, hour.score)}%` }}
                          title={`${formatHour(hour.time)} · ${hour.score}/100${hour.is_twilight ? " · غسق" : hour.is_night ? " · ليل" : ""}`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
                <p className="report-method-note">
                  <Info size={15} />
                  <span>{result.species_activity[0].basis_ar.join(" ")}</span>
                </p>
              </div>
            )}
            {result.species_axes.unknown_axes.length > 0 && (
              <div className="report-species-unknown">
                <small>محاور غير معروفة بعد:</small>
                {result.species_axes.unknown_axes.map((key) => (
                  <span key={key}>{speciesAxisKeyLabel(key)}</span>
                ))}
              </div>
            )}
            {result.species_axes.notes_ar.length > 0 && (
              <div className="report-gear-note"><Info size={14} /><span>{result.species_axes.notes_ar.join(" ")}</span></div>
            )}
          </div>
        )}
      </section>

      <section className="report-section report-field-feasibility" aria-labelledby="report-feasibility-title" hidden={reportTab !== "feasibility"}>
        <div className="report-section-title"><span>4</span><div><h3 id="report-feasibility-title">قابلية التنفيذ ونشاط 48–72 ساعة</h3><p>جرّ الخط واحتمالا الصوفة والعكارة والتيار الساحبي—كمؤشرات، لا كمشاهدات.</p></div></div>
        <div className="report-field-headline">
          <span><Anchor size={19} /></span>
          <div><small>الحالة المجمعة</small><strong>{fieldFeasibilityLabels[result.field_feasibility.status]} · <bdi>{result.field_feasibility.score}/100</bdi></strong></div>
          <p>ثقة الفحص <bdi>{result.field_feasibility.confidence}/100</bdi><small>السقف 50/100 لغياب شكل القاع والرصد المباشر.</small></p>
        </div>
        <div className="report-field-signals">
          <article><small>صعوبة تثبيت الخط</small><strong className={`potential-${result.field_feasibility.holding_difficulty}`}>{potentialLabels[result.field_feasibility.holding_difficulty]}</strong><p>الموج الجانبي والتيار النموذجي والريح.</p></article>
          <article><small>احتمال الصوفة/الحطام</small><strong className={`potential-${result.field_feasibility.fouling_transport_potential}`}>{potentialLabels[result.field_feasibility.fouling_transport_potential]}</strong><p>{result.field_feasibility.fouling_evidence_count} عائلات قرائن / 48س؛ ليست أرصاداً مستقلة ولا تثبت وجودها أو تمنع وحدها.</p></article>
          <article><small>احتمال العكارة</small><strong className={`potential-${result.field_feasibility.turbidity_potential}`}>{potentialLabels[result.field_feasibility.turbidity_potential]}</strong><p>{result.field_feasibility.turbidity_evidence_count} عائلات قرائن / 48س؛ ليست قياسات ماء ولا توجد NTU ولا تمنع وحدها.</p></article>
          <article><small>تيار ساحبي محتمل</small><strong className={`potential-${result.field_feasibility.rip_current_potential}`}>{potentialLabels[result.field_feasibility.rip_current_potential]}</strong><p>لا يرى الحواجز الرملية أو قناة الكسرة.</p></article>
        </div>
        {result.field_feasibility.holding_breakdown && (
          <div className="report-holding-breakdown">
            <div className="report-holding-breakdown-head">
              <span>تفكيك أسباب تثبيت الخط</span>
              <small>
                السبب الغالب: <strong>{holdingMechanismLabels[result.field_feasibility.holding_breakdown.dominant]}</strong> · ثقة {result.field_feasibility.holding_breakdown.confidence}/30
              </small>
            </div>
            <div className="report-holding-grid">
              <article>
                <small>الجرّ الجانبي</small>
                <strong className={`potential-${result.field_feasibility.holding_breakdown.longshore_current}`}>{potentialLabels[result.field_feasibility.holding_breakdown.longshore_current]}</strong>
                <p>موج مائل/موازٍ + تيار موازٍ للشاطئ.</p>
              </article>
              <article>
                <small>حركة القاع المدارية</small>
                <strong className={`potential-${result.field_feasibility.holding_breakdown.orbital_motion}`}>{potentialLabels[result.field_feasibility.holding_breakdown.orbital_motion]}</strong>
                <p>سرعة تقديرية {result.field_feasibility.holding_breakdown.orbital_velocity_band_ms ?? "غير متوفرة"} م/ث داخل عمق مفترض {result.field_feasibility.holding_breakdown.depth_band_m} م.</p>
              </article>
              <article>
                <small>الرجوع للبحر</small>
                <strong className={`potential-${result.field_feasibility.holding_breakdown.return_flow}`}>{potentialLabels[result.field_feasibility.holding_breakdown.return_flow]}</strong>
                <p>دفع الموج نحو الشاطئ يحتاج عودة ماء.</p>
              </article>
              <article>
                <small>تيار المدّ</small>
                <strong className={`potential-${result.field_feasibility.holding_breakdown.tidal_current}`}>{potentialLabels[result.field_feasibility.holding_breakdown.tidal_current]}</strong>
                <p>من حركة مستوى البحر؛ أقوى في خليج قابس.</p>
              </article>
            </div>
            <div className="report-holding-note"><Info size={14} /><span>تفكيك تشخيصي بلا عتبة قرار جديدة؛ بوابة «صعوبة تثبيت الخط» بقيت كما هي. العمق والقاع غير معروفين لذا النطاق واسع والثقة منخفضة.</span></div>
          </div>
        )}
        {result.gear_recommendation && (
          <div className="report-gear-recommendation">
            <div className="report-gear-head">
              <span>🎣 العتاد المقترح</span>
              <small>ثقة {result.gear_recommendation.confidence}/30 · <strong>{result.gear_recommendation.required_rod_rating_note_ar}</strong></small>
            </div>
            <div className="report-gear-grid">
              {result.gear_recommendation.scenarios.map((scenario, index) => (
                <article key={scenario.shape} className={index === 0 ? "primary" : ""}>
                  <header>
                    <span className="report-gear-rank">{index === 0 ? "الخيار الأنسب" : `بديل ${index}`}</span>
                    <strong>{scenario.shape_ar}</strong>
                    <bdi>{scenario.weight_band_ar}</bdi>
                  </header>
                  <p>{scenario.rationale_ar}</p>
                  <ul>
                    <li>القاع المناسب: {scenario.bottom_ar}</li>
                    <li>{scenario.montage_ar}</li>
                    <li>ثبات جانبي: {potentialLabels[scenario.lateral_hold]} · خطر تعليق: {potentialLabels[scenario.snag_risk]}</li>
                  </ul>
                </article>
              ))}
            </div>
            {result.gear_recommendation.casting_advice_ar ? (
              <div className="report-gear-advice"><Info size={14} /><span>{result.gear_recommendation.casting_advice_ar}</span></div>
            ) : null}
            <div className="report-gear-note"><Info size={14} /><span>مجالات تقريبية من كتالوج عام، لا رقم دقيق بلا بيانات قصبتك وخيطك وقاعك؛ القاع تحت الطعم غير معروف فالنتيجة سيناريوهات. أكّد الرمل ميدانياً قبل grapnel ثابت.</span></div>
          </div>
        )}
        {result.fouling_evidence && (
          <div className="report-fouling-evidence">
            <div className="report-gear-head">
              <span>🪸 سلم أدلة الصوفة والعوالق</span>
              <small className={result.fouling_evidence.is_force_majeure ? "evidence-confirmed" : ""}>
                المستوى {result.fouling_evidence.level} / 5{result.fouling_evidence.is_force_majeure ? " — إثبات قاهر" : ""}
              </small>
            </div>
            <ol className="report-evidence-ladder">
              {result.fouling_evidence.basis_ar.map((basis) => (
                <li key={basis}>{basis}</li>
              ))}
            </ol>
            {result.fouling_evidence.notes_ar.length > 0 && (
              <div className="report-gear-note"><Info size={14} /><span>{result.fouling_evidence.notes_ar.join(" ")}</span></div>
            )}
          </div>
        )}
        {result.trip_ruin_factors && result.trip_ruin_factors.length > 0 && (
          <div className="report-trip-ruin">
            <div className="report-gear-head">
              <span>⚠️ ما قد يُفسد الخرجة (داتا حية + دليل مؤكد)</span>
              <small>الدليل المؤكد يمنع · التنبؤ يبقى تنبيهاً</small>
            </div>
            {result.trip_ruin_factors.map((factor) => (
              <article key={factor.factor} className={`trip-ruin trip-ruin-${factor.level}${factor.is_force_majeure ? " trip-ruin-block" : ""}`}>
                <header>
                  <strong>{factor.label_ar}</strong>
                  <span className="trip-ruin-chips">
                    <em className={`chip chip-trip-${factor.level}`}>{tripRuinLevelLabel(factor.level)}</em>
                    <em className={`chip chip-basis-${factor.basis}`}>{tripRuinBasisLabel(factor.basis)}</em>
                    {factor.is_force_majeure && <em className="chip chip-basis-block">يمنع الخرجة</em>}
                  </span>
                </header>
                <ul>{factor.evidence_ar.map((line) => <li key={line}>{line}</li>)}</ul>
                <p className="trip-ruin-meta">
                  <span>{factor.source_ar}</span>
                  {factor.age_ar ? <span> · {factor.age_ar}</span> : null}
                </p>
              </article>
            ))}
            <div className="report-method-note"><Info size={14} /><span>العمر ظاهر بجانب كل معلومة: الدليل الساتلي تاريخه عمر الصورة، والبلاغ الميداني بفارق ساعات، والتنبؤ النموذجي مذكور كتنبؤ لا رصد. ما لا مصدر موثوق له يبقى «غير معروف» ولا يدخل القرار.</span></div>
          </div>
        )}
        {result.spring_neap && (
          <div className="report-spring-neap">
            <div className="report-gear-head">
              <span>🌊 المدّ والجزر (حيّة / مات)</span>
              <small>ثقة {result.spring_neap.confidence}/30{result.spring_neap.gabes_zone ? " · خليج قابس" : ""}</small>
            </div>
            <div className="report-spring-neap-grid">
              <article>
                <small>التصنيف</small>
                <strong>{result.spring_neap.folk_label_ar} ({springNeapLabel(result.spring_neap.classification)})</strong>
              </article>
              <article>
                <small>مدى اليوم المستهدف</small>
                <strong>{result.spring_neap.range_target_day_m != null ? `${result.spring_neap.range_target_day_m.toFixed(2)} م` : "غير متاح"}</strong>
              </article>
              <article>
                <small>المدى المرجعي (وسيط السلسلة)</small>
                <strong>{result.spring_neap.range_reference_m != null ? `${result.spring_neap.range_reference_m.toFixed(2)} م` : "غير متاح"}</strong>
              </article>
              <article>
                <small>نسبة المدى إلى الوسيط</small>
                <strong>{result.spring_neap.range_ratio != null ? `${result.spring_neap.range_ratio.toFixed(2)}` : "—"}</strong>
              </article>
              <article>
                <small>أقصى معدل ارتفاع/ساعة</small>
                <strong>{result.spring_neap.max_level_rate_m_per_h != null ? `${result.spring_neap.max_level_rate_m_per_h.toFixed(2)} م/س` : "—"}</strong>
              </article>
            </div>
            {result.spring_neap.notes_ar.length > 0 && (
              <div className="report-gear-note"><Info size={14} /><span>{result.spring_neap.notes_ar.join(" ")}</span></div>
            )}
            {result.spring_neap.limitations_ar.length > 0 && (
              <div className="report-gear-note"><Info size={14} /><span>{result.spring_neap.limitations_ar.join(" ")}</span></div>
            )}
          </div>
        )}
        {fieldContext && <div className="report-field-context">
          <span><small>مطر 48س</small><strong>{fieldContext.derived.rain_48h_mm === null ? "—" : `${fieldContext.derived.rain_48h_mm.toFixed(1)} مم`}</strong><bdi>تغطية {fieldContext.derived.rain_data_hours_48h}/48</bdi></span>
          <span><small>دفع الريح الشاطئي 48س</small><strong>{fieldContext.derived.onshore_wind_impulse_48h_kmh_h === null ? "—" : `${fieldContext.derived.onshore_wind_impulse_48h_kmh_h.toFixed(1)} كم/س·س`}</strong><bdi>تغطية {fieldContext.derived.wind_data_hours_48h}/48</bdi></span>
          <span><small>طاقة الموج التراكمية 48س</small><strong>{fieldContext.derived.wave_energy_integral_48h === null ? "—" : `${fieldContext.derived.wave_energy_integral_48h.toFixed(1)} Hs²T·h`}</strong><bdi>{fieldContext.derived.strong_wave_hours_48h} ساعات قوية · تغطية {fieldContext.derived.wave_energy_data_hours_48h}/48</bdi></span>
          <span><small>دفع التيار الشاطئي 48س</small><strong>{fieldContext.derived.shoreward_current_impulse_48h_kmh_h === null ? "—" : `${fieldContext.derived.shoreward_current_impulse_48h_kmh_h.toFixed(1)} كم/س·س`}</strong><bdi>تغطية {fieldContext.derived.current_data_hours_48h}/48</bdi></span>
          <span><small>التغطية السابقة</small><strong>{fieldContext.derived.history_hours_48h}/48 س</strong><bdi>{fieldContext.derived.history_hours_72h}/72 س · عند {formatHour(fieldContext.time)}</bdi></span>
        </div>}
        <div className="report-field-evidence"><ul>{result.field_feasibility.reasons_ar.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
        <div className="report-method-note report-proxy-note"><Info size={15} /><span><strong>هذه مؤشرات تنبيه لا موانع آلية.</strong> لا تلغي نافذة آمنة بلا رصد، لكن رمية يجرّها البحر، صوفة على الخيط، عكارة ظاهرة، أو قناة رغوة/حطام إلى عرض البحر تعني تغيير الموضع أو التأجيل مهما كان التوقع.</span></div>
      </section>

      <section className="report-section" aria-labelledby="report-periods-title" hidden={reportTab !== "feasibility"}>
        <div className="report-section-title"><span>5</span><div><h3 id="report-periods-title">التفكيك الزمني</h3><p>متوسطات محافظة لكل جزء من اليوم؛ التفاصيل الساعية تبقى المرجع الأدق.</p></div></div>
        <div className="report-period-grid">{periods.map((period) => (
          <article className={!period.hours.length ? "unavailable" : ""} key={period.id}>
            <header><span><Clock3 size={16} /><strong>{period.label}</strong><small>{period.range}</small></span>{period.safety && <b className={`report-safety-${period.safety}`}>سلامة: {shortDecisionLabels[period.safety]}</b>}</header>
            {period.hours.length ? <>
              <div className="period-scores"><span>أدنى تنفيذ <strong>{period.field}/100</strong></span><span>متوسط الفرصة <strong>{period.opportunity}/100</strong></span><span>أضعف ثقة <strong>{period.confidence}/100</strong></span></div>
              <p><Wind size={15} /><span>{period.wind}</span></p>
              <p><Waves size={15} /><span>{period.waves}</span></p>
              <p><Droplets size={15} /><span>{period.water}</span></p>
              {period.warnings.length > 0 && <ul>{period.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
            </> : <p className="period-unavailable">لا توجد ساعات مستقبلية قابلة للتقييم في هذه الفترة.</p>}
          </article>
        ))}</div>
      </section>

      <section className="report-section" aria-labelledby="report-balance-title" hidden={reportTab !== "feasibility"}>
        <div className="report-section-title"><span>6</span><div><h3 id="report-balance-title">ميزان العوامل</h3><p>السلامة ونقص البيانات يسبقان مؤشرات الصيد.</p></div></div>
        <p className="report-method-note"><Info size={15} /><span>هذه قائمة مجمعة من ساعات اليوم؛ وجود عامل رعد فيها لا يعني أن اليوم كله رعدي. ارجع إلى نوافذ الحصة وفترات التجنب لتحديد ساعته.</span></p>
        <div className="report-factor-columns">
          <article className="report-obstacles"><h4><AlertTriangle size={18} /> تحفظات ومخاطر</h4>{obstacles.length ? <ul>{obstacles.map((factor) => <li key={`${factor.code}-${factor.explanation_ar}`}><span /><p><strong>{factor.label_ar}</strong>{factor.explanation_ar}</p></li>)}</ul> : <p className="report-empty">لا توجد معوقات بارزة، مع بقاء الواقع الميداني هو الحكم.</p>}</article>
          <article className="report-positives"><h4><Check size={18} /> مؤشرات إيجابية</h4>{positives.length ? <ul>{positives.map((factor) => <li key={`${factor.code}-${factor.explanation_ar}`}><span /><p><strong>{factor.label_ar}</strong>{factor.explanation_ar}</p></li>)}</ul> : <p className="report-empty">لا توجد أفضلية إيجابية قوية مثبتة.</p>}</article>
        </div>
      </section>

      <section className="report-section" aria-labelledby="report-field-title" hidden={reportTab !== "references"}>
        <div className="report-section-title"><span>7</span><div><h3 id="report-field-title">التكتيك الميداني والسلامة</h3><p>إرشاد مرتبط بالبيانات، من دون أرقام معدات أو مصيد مخترعة.</p></div></div>
        <ol className="report-guidance">{guidance.map((item, index) => <li key={item}><span>{index + 1}</span><p>{item}</p></li>)}</ol>
      </section>

      <section className="report-gemini" aria-labelledby="gemini-report-title">
        <div className="report-gemini-heading">
          <span><WandSparkles size={20} /></span>
          <div>
            <h3 id="gemini-report-title">تقرير Gemini الاختياري</h3>
            <p>Gemini يكتب الشرح فقط؛ محرك Peche TN وحده يحسم القرار والأرقام.</p>
          </div>
          {geminiReport && <b><Check size={14} /> JSON متحقق</b>}
        </div>
        <div className="gemini-risk" role="note">
          <AlertTriangle size={18} />
          <p>
            <strong>تنبيه أمني قبل الحفظ:</strong> localStorage موش خزنة أسرار؛ أي سكربت يعمل في نفس الموقع، إضافة متصفح ذات صلاحية، أو شخص يستعمل نفس الجهاز قد يصل للمفتاح. عند الاختبار أو التوليد يُرسل المفتاح مؤقتاً عبر HTTPS إلى API ثم Google، ولا يخزنه أو يسجله خادم Peche TN. Google يستقبل Evidence Packet وفق شروط خدمته.
          </p>
        </div>
        <div className="gemini-key-row">
          <label>
            <span><KeyRound size={15} /> مفتاح Google AI Studio</span>
            <span className="gemini-key-input">
              <input
                data-testid="gemini-key-input"
                type={showGeminiKey ? "text" : "password"}
                value={geminiKey}
                autoComplete="off"
                spellCheck={false}
                placeholder="ألصق المفتاح هنا"
                aria-label="مفتاح Google Gemini"
                onChange={(event) => {
                  setGeminiKeyDraft(event.target.value);
                  setGeminiStatus(null);
                }}
              />
              <button
                type="button"
                aria-label={showGeminiKey ? "أخفِ المفتاح" : "أظهر المفتاح"}
                onClick={() => setShowGeminiKey((visible) => !visible)}
              >
                {showGeminiKey ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </span>
          </label>
          <label className="gemini-consent">
            <input
              type="checkbox"
              checked={storageRiskAccepted}
              onChange={(event) => setStorageRiskChoice(event.target.checked)}
            />
            <span>فهمت مخاطر التخزين المحلي وأريد حفظ المفتاح دائماً على هذا المتصفح.</span>
          </label>
          <div className="gemini-key-actions">
            <button
              type="button"
              data-testid="gemini-save-key"
              disabled={!geminiKey.trim() || !storageRiskAccepted}
              onClick={saveGeminiKey}
            >
              <KeyRound size={15} /> {geminiKeySaved ? "محفوظ محلياً" : "احفظ محلياً"}
            </button>
            <button
              type="button"
              data-testid="gemini-test-key"
              disabled={!geminiKey.trim() || geminiBusy !== "idle"}
              onClick={() => void testGeminiKey()}
            >
              <RefreshCw className={geminiBusy === "verify" ? "spin" : ""} size={15} />
              {geminiBusy === "verify" ? "نختبر…" : "اختبر المفتاح"}
            </button>
            <button
              type="button"
              className="gemini-delete"
              disabled={!geminiKey && !geminiKeySaved}
              onClick={deleteGeminiKey}
            >
              <Trash2 size={15} /> احذف
            </button>
          </div>
        </div>
        <button
          type="button"
          className="gemini-generate"
          data-testid="gemini-generate"
          disabled={!geminiKey.trim() || geminiBusy === "verify"}
          onClick={() => {
            if (geminiBusy === "generate") cancelGeminiGeneration();
            else void generateWithGemini();
          }}
        >
          {geminiBusy === "generate" ? <X size={18} /> : <Sparkles size={18} />}
          {geminiBusy === "generate" ? "أوقف انتظار Gemini" : "ولّد التقرير المنظم عند الطلب"}
        </button>
        {geminiStatus && (
          <div className={`gemini-status ${geminiStatus.kind}`} role="status" data-testid="gemini-status">
            {geminiStatus.kind === "success" ? <Check size={16} /> : <Info size={16} />}
            <span>{geminiStatus.text}</span>
          </div>
        )}
        {geminiReport && (
          <div className="gemini-narrative" data-testid="gemini-narrative">
            <h4>السرد المقيد</h4>
            <p>{geminiReport.narrative.executive_summary_ar}</p>
            <div>
              <article><strong>التوقيت والماء</strong><ul>{geminiReport.narrative.timing_and_water_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
              <article><strong>التحليل السابق</strong><ul>{geminiReport.narrative.temporal_analysis_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
              <article><strong>تفاعل العوامل</strong><ul>{geminiReport.narrative.factor_interactions_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
              <article><strong>التكتيك الميداني</strong><ul>{geminiReport.narrative.field_tactics_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
              <article><strong>Unknown</strong><ul>{geminiReport.narrative.unknowns_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
            </div>
            <footer>
              <span>model: {geminiReport.metadata.model}</span>
              <span>prompt: {geminiReport.metadata.prompt_version}</span>
              <span>hash: <bdi>{geminiReport.metadata.input_sha256}</bdi></span>
              <span>{formatGeneratedAt(geminiReport.metadata.generated_at)}</span>
            </footer>
          </div>
        )}
      </section>

      <section className="report-section report-reference-section" aria-labelledby="report-reference-title" hidden={reportTab !== "references"}>
        <div className="report-section-title"><span>8</span><div><h3 id="report-reference-title">الأرقام المرجعية</h3><p>المدى الأدنى–الأعلى في الساعات التي قيّمها المحرك فقط.</p></div></div>
        <dl className="report-reference-grid">
          <div><dt><Wind size={16} /> الريح</dt><dd>{metricRange(windValues, 1, " كم/س")}<small>أقصى هبة {metricValue(maximum(gustValues), 1, " كم/س")}</small></dd></div>
          <div><dt><Waves size={16} /> الموج الكلي</dt><dd>{metricRange(waveValues, 2, " م")}<small>الفترة {metricRange(wavePeriodValues, 1, " ث")}</small></dd></div>
          <div><dt><Wind size={16} /> موج الريح</dt><dd>{metricRange(windWaveValues, 2, " م")}<small>الفترة {metricRange(windWavePeriodValues, 1, " ث")}</small></dd></div>
          <div><dt><Waves size={16} /> السويل</dt><dd>{metricRange(swellValues, 2, " م")}<small>الفترة {metricRange(swellPeriodValues, 1, " ث")}</small></dd></div>
          <div><dt>حرارة الماء</dt><dd>{metricRange(waterTemperatures, 1, "°م")}<small>الهواء {metricRange(airTemperatures, 1, "°م")}</small></dd></div>
          <div><dt>الضغط</dt><dd>{metricRange(pressures, 1, " hPa")}<small>تغير 3س {signedMetricRange(pressureChanges, 1, " hPa")} · موش ضمان نشاط</small></dd></div>
          <div><dt>التيار النموذجي</dt><dd>{metricRange(currents, 2, " كم/س")}<small>لا يمثل تيار الكسرة</small></dd></div>
          <div><dt>مستوى البحر</dt><dd>{metricRange(seaLevels, 2, " م")}<small>بالنسبة إلى متوسط مستوى البحر</small></dd></div>
          <div><dt>الأمطار</dt><dd>{precipitation.length ? `حتى ${metricValue(maximum(precipitation), 1, " مم/س")}` : "غير متوفر"}<small>حسب الساعات المقيمة</small></dd></div>
          <div><dt>أدنى رؤية</dt><dd>{minimum(visibility) === null ? "غير متوفر" : `${((minimum(visibility) ?? 0) / 1000).toFixed(1)} كم`}<small>الرؤية النموذجية العامة</small></dd></div>
        </dl>
        {result.hourly.length > 0 && <div className="report-equations report-hourly-diagnostics" data-testid="report-equations">
          <header><strong>المشتقات الحتمية لكل ساعة مقيمة</strong><small>المفقود يظهر Unknown. القمم والنطاقات لا تدخل composite score.</small></header>
          <div className="diagnostic-summary-grid">
            <article><small>ريح alongshore موقعة</small><p><bdi>{signedDiagnosticRange(signedWindAlongshore, 2, " كم/س")}</bdi></p><p>تغطية {coverageText(signedWindAlongshore, result.hourly.length)}</p></article>
            <article><small>إجهاد الريح |τ|</small><p><bdi>{diagnosticRange(windStress, 4, " Pa")}</bdi></p><p>قمة {diagnosticValue(maximum(windStress), 4, " Pa")} · {coverageText(windStress, result.hourly.length)}</p></article>
            <article><small>دفع موج alongshore موقّع</small><p><bdi>{signedDiagnosticRange(signedWaveForcing, 2, " Hs²T")}</bdi></p><p>أقصى مقدار {diagnosticValue(maximumAbsolute(signedWaveForcing), 2)} · {coverageText(signedWaveForcing, result.hourly.length)}</p></article>
            <article><small>موج الريح × السويل</small><p><bdi>زاوية {diagnosticRange(componentAngles, 0, "°")}</bdi></p><p>حصة الأضعف {secondaryShares.length ? `${(Math.min(...secondaryShares) * 100).toFixed(0)}–${(Math.max(...secondaryShares) * 100).toFixed(0)}%` : "Unknown"} · {coverageText(componentAngles, result.hourly.length)}</p></article>
            <article><small>تماسك اتجاه الريح R / 6س</small><p><bdi>{diagnosticRange(directionCoherence, 2)}</bdi></p><p>تغطية {coverageText(directionCoherence, result.hourly.length)} · السكون مستبعد</p></article>
            <article><small>تيار نموذجي موقّع</small><p><bdi>⊥ {signedDiagnosticRange(currentCrossShore, 2)}</bdi></p><p><bdi>∥ {signedDiagnosticRange(currentAlongshore, 2, " كم/س")}</bdi></p></article>
            <article><small>فروق حرارية صريحة</small><p><bdi>هواء−بحر {signedDiagnosticRange(airSeaDifferences, 1, "°")}</bdi></p><p><bdi>هواء−ندى {signedDiagnosticRange(dewPointDepressions, 1, "°")}</bdi></p></article>
            <article><small>إسقاط إجهاد الريح</small><p><bdi>⊥ {signedDiagnosticRange(windStressShoreward, 4)}</bdi></p><p><bdi>∥ {signedDiagnosticRange(windStressAlongshore, 4, " Pa")}</bdi></p></article>
          </div>
          <div className="report-diagnostic-table-wrap" tabIndex={0} aria-label="جدول المشتقات الساعية، قابل للتمرير أفقياً">
            <table className="report-diagnostic-table">
              <thead><tr><th>الساعة</th><th>الريح والمحور</th><th>إجهاد الريح</th><th>الموج والـforcing</th><th>موج الريح × السويل</th><th>التيار النموذجي</th><th>الاتساق والحرارة</th></tr></thead>
              <tbody>{result.hourly.map((hour) => <tr key={hour.time}>
                <th scope="row"><bdi>{formatHour(hour.time)}</bdi></th>
                <td><bdi>Δ {diagnosticValue(hour.derived.wind_angle_deg, 1, "°")}</bdi><small><bdi>V⊥ {signedDiagnosticValue(hour.derived.wind_shoreward_component_kmh, 2)}</bdi></small><small><bdi>V∥ {signedDiagnosticValue(hour.derived.wind_alongshore_signed_component_kmh, 2)} كم/س</bdi></small></td>
                <td><bdi>|τ| {diagnosticValue(hour.derived.wind_stress_pa, 4)}</bdi><small><bdi>τ⊥ {signedDiagnosticValue(hour.derived.wind_stress_shoreward_pa, 4)}</bdi></small><small><bdi>τ∥ {signedDiagnosticValue(hour.derived.wind_stress_alongshore_pa, 4)} Pa</bdi></small><small><bdi>Cd {diagnosticValue(hour.derived.wind_drag_coefficient, 6)} · ∫τ⊥⁺48 {diagnosticValue(hour.derived.onshore_wind_stress_impulse_48h_pa_h, 3)}</bdi></small></td>
                <td><bdi>Δ {diagnosticValue(hour.derived.wave_angle_deg, 1, "°")}</bdi><small><bdi>align∥ {signedDiagnosticValue(hour.derived.wave_alongshore_signed_alignment, 3)}</bdi></small><small><bdi>L₀ {diagnosticValue(hour.derived.deep_water_wavelength_m, 1, " م")} · Hs/L₀ {diagnosticValue(hour.derived.wave_steepness, 4)}</bdi></small><small><bdi>H²T {diagnosticValue(hour.derived.wave_energy_proxy, 2)}</bdi></small><small><bdi>forcing∥ {signedDiagnosticValue(hour.derived.alongshore_wave_signed_proxy, 2)}</bdi></small></td>
                <td><bdi>{diagnosticValue(hour.derived.wave_component_angle_deg, 0, "°")}</bdi><small>حصة الأضعف {hour.derived.wave_component_secondary_energy_share === null ? "Unknown" : `${(hour.derived.wave_component_secondary_energy_share * 100).toFixed(0)}%`}</small><small>بلا عتبة قرار</small></td>
                <td><bdi>⊥ {signedDiagnosticValue(hour.derived.current_cross_shore_kmh, 2)}</bdi><small><bdi>∥ {signedDiagnosticValue(hour.derived.current_alongshore_kmh, 2)} كم/س</bdi></small><small>نحو bearing لا from</small></td>
                <td><bdi>R6 {diagnosticValue(hour.derived.wind_direction_coherence_6h, 2)}</bdi><small>{hour.derived.wind_direction_data_hours_6h}/6 اتجاهات</small><small><bdi>هواء−بحر {signedDiagnosticValue(hour.derived.air_sea_temperature_difference_c, 1)}°</bdi></small><small><bdi>هواء−ندى {signedDiagnosticValue(hour.derived.dew_point_depression_c, 1)}°</bdi></small></td>
              </tr>)}</tbody>
            </table>
          </div>
          <p><Info size={14} /><span>المحور الموازي الموجب bearing <bdi>{result.hourly[0].derived.alongshore_positive_bearing_deg.toFixed(0)}° = (S+90) mod 360</bdi>. للريح والموج القادمين: <bdi>V⊥=VcosΔ</bdi> نحو الشاطئ و<bdi>V∥=−VsinΔ</bdi>؛ الحقل القديم هو <bdi>|VsinΔ|</bdi>. للتيار المتجه نحو bearing: <bdi>C⊥=VcosΔc</bdi> موجب نحو البحر و<bdi>C∥=VsinΔc</bdi> موجب على المحور نفسه. <bdi>L₀=gT²/(2π)</bdi> و<bdi>Hs/L₀</bdi> تقريب مياه عميقة. <bdi>τ⃗=ρair Cd |U10|U⃗10</bdi> بمعامل Large–Pond محايد. <bdi>R=|ΣUi eᶦᶿⁱ|/ΣUi</bdi>. حصة النظام الأضعف <bdi>min(Hww²,Hsw²)/(Hww²+Hsw²)</bdi>. forcing الموج نسبي، لا سرعة تيار أو نقل رسوبي.</span></p>
        </div>}
        {result.coastal_water_context && <div className={`report-water-context water-${result.coastal_water_context.availability}`} data-testid="report-water-context">
          <header><Droplets size={17} /><span><strong>Sentinel-2 — سياق جودة الماء</strong><small>استعادة يومية متقطعة من Copernicus Marine؛ لا تغيّر محاور القرار أو الفرصة أو الثقة.</small></span><b>{result.coastal_water_context.availability === "available" ? "بكسل صالح" : "Unknown"}</b></header>
          {result.coastal_water_context.availability === "available" ? <>
            <div>
              <span><small>TUR</small><strong>{diagnosticValue(result.coastal_water_context.turbidity_fnu, 2, ` ${result.coastal_water_context.turbidity_unit}`)}</strong></span>
              <span><small>SPM</small><strong>{diagnosticValue(result.coastal_water_context.suspended_particulate_matter_g_m3, 2, ` ${result.coastal_water_context.suspended_particulate_matter_unit}`)}</strong></span>
              <span><small>CHL-a</small><strong>{diagnosticValue(result.coastal_water_context.chlorophyll_a_mg_m3, 2, ` ${result.coastal_water_context.chlorophyll_a_unit}`)}</strong></span>
              <span><small>SST</small><strong>{diagnosticValue(result.coastal_water_context.sea_surface_temperature_c, 1, " °م")}</strong></span>
              <span><small>التاريخ والعمر</small><strong>{result.coastal_water_context.valid_time?.slice(0, 10) ?? "Unknown"}</strong><bdi>{result.coastal_water_context.age_hours === null ? "Unknown" : `${Math.round(result.coastal_water_context.age_hours)} ساعة`}</bdi></span>
              <span><small>البكسل</small><strong>{result.coastal_water_context.pixel_distance_from_spot_m === null ? "Unknown" : `${Math.round(result.coastal_water_context.pixel_distance_from_spot_m)} م من البقعة`}</strong><bdi>دقة المنتج {result.coastal_water_context.spatial_resolution_m} م</bdi></span>
            </div>
          </> : <p>القيمة Unknown وليست صفراً. {result.coastal_water_context.reason_ar}</p>}
          <p><Info size={14} /> أخذت العينة عند نقطة ثابتة على بعد 1 كم باتجاه البحر، بلا بحث جانبي عن بكسل ملائم. TUR بوحدة FNU وليست NTU، والمنتج لا يرصد الصوفة أو التيار الساحبي أو ساعة الرحلة المستقبلية، وCHL لا تشخّص ازدهاراً ضاراً أو نشاط السمك.</p>
        </div>}
      </section>

      <section className="report-section report-sources" aria-labelledby="report-sources-title" hidden={reportTab !== "references"}>
        <div className="report-section-title"><span>9</span><div><h3 id="report-sources-title">المصادر وحدود المطابقة</h3><p>باش تعرف منين جاء الرقم وشنوّة ما ينجمش يشوف.</p></div></div>
        {result.sources.length ? <div className="report-source-list">{result.sources.map((source) => <article key={`${source.provider}-${source.product}`}><Database size={17} /><span><strong>{source.provider} · {source.product}</strong><small>{source.data_kind === "direct_observation" ? "رصد نقطي في محطة، وليس داخل البقعة" : source.data_kind === "remote_sensing_estimate" ? `استعادة أقمار صناعية سياقية · دقة ${source.horizontal_resolution_km ?? "Unknown"} كم` : source.horizontal_resolution_km ? `توقع بدقة أفقية تقريبية ${source.horizontal_resolution_km} كم` : "توقع حسب النموذج المتاح"} · جُلب {formatHour(source.retrieved_at)}</small></span></article>)}</div> : <p className="report-empty">مصدر البيانات غير متوفر في الاستجابة.</p>}
        <div className="report-confidence-reasons"><strong>علاش ثقة المدخلات {result.confidence.score}/100؟</strong><ul>{result.confidence.reasons_ar.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
        <div className="report-confidence-reasons"><strong>حدود فحص التنفيذ منخفض الثقة</strong><ul>{result.field_feasibility.limitations_ar.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></div>
        <div className="report-limitations"><strong>حدود يجب تبقى ظاهرة</strong><ul>{result.limitations_ar.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></div>
      </section>

      <section className="report-section report-matrix-audit" aria-labelledby="report-matrix-title" hidden={reportTab !== "references"}>
        <div className="report-section-title"><span>10</span><div><h3 id="report-matrix-title">تدقيق مصفوفة العوامل</h3><p>التغطية لا تعني أن كل عامل يدخل النقاط.</p></div></div>
        <div className="report-field-signals">
          <article><small>قرار آلي</small><strong>{result.factor_coverage.automated_decision}</strong><p>سلامة أو قرار بمدخل يمكن الدفاع عنه.</p></article>
          <article><small>سياق آلي</small><strong>{result.factor_coverage.automated_context}</strong><p>يظهر بلا وزن تلقائي عندما لا تثبت العلاقة.</p></article>
          <article><small>proxy + تحقق</small><strong>{result.factor_coverage.proxy_requires_field_check}</strong><p>مؤشر منخفض الثقة لا يعوض المعاينة.</p></article>
          <article><small>ميداني/خارجي</small><strong>{result.factor_coverage.field_or_external_required}</strong><p>يبقى Unknown حتى يتوفر قياس أو بلاغ.</p></article>
          <article><small>مستبعد</small><strong>{result.factor_coverage.excluded_unsupported}</strong><p>لا وزن لعلاقة غير مدعومة أو مكررة.</p></article>
        </div>
        <div className="report-method-note"><Info size={15} /><span>{result.factor_coverage.note_ar}</span></div>
        <div className="factor-ledger" data-testid="factor-ledger">
          {result.factor_assessments.map((factor) => (
            <article key={factor.matrix_id} className={`factor-ledger-${factor.status}`}>
              <header>
                <bdi>{factor.matrix_id}</bdi>
                <strong>{factor.title_ar}</strong>
                <span>{factorAssessmentLabels[factor.status]}</span>
              </header>
              <p>{factor.value_ar}</p>
              <dl>
                <div><dt>المحور</dt><dd>{factor.decision_axis}</dd></div>
                <div><dt>الأدلة</dt><dd>{factor.evidence_variables.length ? factor.evidence_variables.join(" · ") : "لا مدخل تشغيلي"}</dd></div>
              </dl>
              <small>{factor.rationale_ar}</small>
              {factor.affects_final_decision && <em><AlertTriangle size={13} /> {result.decision === "go" ? "دخل بوابة الحسم النهائي" : "مؤثر في سبب قرار لا تذهب"}</em>}
            </article>
          ))}
        </div>
      </section>

      <footer className="report-footer">
        <Clipboard size={17} /><span>Peche TN · schema {result.schema_version} · engine {result.engine_version} · {formatDate(request.target_date)}</span>
        <strong>دعم قرار، موش نشرة ملاحة أو ضمان سلامة/صيد.</strong>
      </footer>
    </section>
  );
}
