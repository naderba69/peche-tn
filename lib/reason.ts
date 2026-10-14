import {
  fieldFeasibilityLabels,
  formatWindowRange,
  potentialLabels,
  speciesAvailabilityLabel,
  springNeapLabel,
  tideLabel,
  windRelationLabel,
  windSectorName,
} from "./format";
import type { DecisionResponse, ForecastDecisionRequest, HourDecision } from "./types";

/**
 * Explain the binary decision from the safety/execution gates, not from the
 * uncalibrated fish-activity ranking. Fish opportunity is a separate axis.
 */
export function buildPrimaryReason(result: DecisionResponse): string {
  switch (result.decision_reason_code) {
    case "safe_window": {
      const lead = result.recommended_windows[0];
      if (!lead) {
        return "قرار الذهاب يتطلب نافذة اجتازت بوابتي السلامة والتنفيذ؛ لا توجد نافذة مرفقة لتفسير القرار.";
      }
      const hours = windowHours(result, lead);
      const formatRange = (values: (number | null)[]): string | null => {
        const present = numeric(values);
        if (!present.length) return null;
        const min = Math.min(...present);
        const max = Math.max(...present);
        return min === max ? max.toFixed(0) : `${min.toFixed(0)}–${max.toFixed(0)}`;
      };
      const windRange = formatRange(hours.map((hour) => hour.forecast.wind_speed_kmh));
      const gustValues = numeric(hours.map((hour) => hour.forecast.wind_gust_kmh));
      const waveRange = formatRange(hours.map((hour) => hour.forecast.wave_height_m));
      const conditions = [
        windRange ? `الريح ${windRange} كم/س` : null,
        gustValues.length ? `الهبات حتى ${Math.max(...gustValues).toFixed(0)} كم/س` : null,
        waveRange ? `الموج ${waveRange} م` : null,
      ].filter((item): item is string => item !== null);
      const caveats = [...new Set(
        hours.flatMap((hour) => hour.factors)
          .filter((factor) => factor.severity === "caution" || factor.severity === "critical")
          .map((factor) => factor.label_ar),
      )].slice(0, 2);
      const confidenceNote = result.confidence.score < 55
        ? "دعم بيانات هذه النافذة محدود."
        : result.confidence.score < 75
          ? "دعم بيانات هذه النافذة متوسط."
          : "درجة دعم البيانات لا تعني دقة ميدانية أو احتمال سلامة.";
      return [
        `قرار «اذهب» لساعات ${formatWindowRange(lead.start, lead.end)} لأنه لا مانع محسوب فيها. خارجها لا تخرج. هذا اجتياز آلي لا إثبات لراحة المكان.`,
        conditions.length ? `توقع النافذة: ${conditions.join(" · ")}.` : "",
        caveats.length ? `تحفظات داخل النافذة: ${caveats.join(" · ")}.` : "",
        confidenceNote,
        "مؤشر نشاط السمك لا يقرر السماح بالذهاب.",
      ].filter(Boolean).join(" ");
    }
    case "caution_only_windows": {
      const cautious = result.recommended_windows.find((w) => w.safety === "caution") ?? result.recommended_windows[0];
      if (!cautious) {
        return "لا توجد ساعات مفتوحة بتحذير في هذا الحكم.";
      }
      return `حذر: ساعات ${formatWindowRange(cautious.start, cautious.end)} مفتوحة بتحذيرات احترازية، ولا توجد ساعة اجتازت الحدود بلا تحذير. هذا ليس اذهب نظيفاً.`;
    }
    case "safety_hazard":
      return "خطر سلامة في الساعات المتاحة؛ لا توجد ساعات كافية بلا مانع محسوب.";
    case "field_infeasible":
      return "جرّ الرصاص أو العكارة مرتفعان في الساعات المتاحة؛ لا توجد ساعات كافية بلا مانع تنفيذ.";
    case "critical_data_missing":
      if (result.spot_profile?.shore_type == null) {
        return [
          "لا تذهب: نوع الشاطئ لم يوثّقه OSM ولم تحدده يدوياً. هذا نقص معلومات، وليس حكماً بأن البحر هادئ أو خطر.",
          ...(result.decision_context_ar ?? []),
        ].join(" ");
      }
      return "بيانات حرجة أخرى ناقصة؛ لا يحوّل المحرك Unknown إلى بحر هادئ.";
    case "conservative_uncertainty":
      return "لا توجد ساعتان متتاليتان بلا مانع محسوب، أو أن اكتمال البيانات لا يكفي.";
    case "fouling_confirmed":
      return "رمز قديم غير مستخدم؛ البلاغات الميدانية ورمية الاختبار لا تدخل في القرار الحالي.";
    case "fouling_proxy_risk":
      return "إشارة CHL حديثة مع بروكسي نقل نموذجي مرتفع؛ خطر صوفة محتمل احترازياً، لا تأكيد ميداني.";
    case "forecast_horizon_exceeded":
      return "الفترة المطلوبة خارج أفق التوقع التشغيلي البالغ 72 ساعة؛ لا يصدر النظام GO خارج هذا النطاق.";
    case "stale_forecast_data":
      return "تعذر جلب بيانات حديثة، وعاد النظام إلى cache قديم؛ لا تستخدم هذه البيانات لتبرير الخروج.";
    case "trip_ruin_confirmed":
      return "عامل مفسد محتمل للخرجة وفق إشارات النظام؛ لا يعني ذلك تحققاً ميدانياً.";
  }
}

function windowHours(result: DecisionResponse, window: { start: string; end: string } | undefined): HourDecision[] {
  if (!window) return result.hourly;
  return result.hourly.filter((hour) => hour.time >= window.start && hour.time < window.end);
}

function numeric(values: (number | null)[]): number[] {
  return values.filter((value): value is number => value !== null && Number.isFinite(value));
}

function mostFrequent<T>(items: T[]): T | null {
  if (!items.length) return null;
  const counts = new Map<string, { value: T; count: number }>();
  for (const item of items) {
    const key = String(item);
    const entry = counts.get(key) ?? { value: item, count: 0 };
    entry.count += 1;
    counts.set(key, entry);
  }
  return [...counts.values()].sort((first, second) => second.count - first.count)[0].value;
}

function span(values: number[]): { min: number; max: number } | null {
  if (!values.length) return null;
  return { min: Math.min(...values), max: Math.max(...values) };
}

const mechanismNames: Record<string, string> = {
  longshore_current: "الجرّ الجانبي",
  orbital_motion: "حركة القاع المدارية",
  return_flow: "الرجوع للبحر",
  tidal_current: "تيار المدّ",
  none: "لا سبب غالب",
};

const targetNames: Record<string, string> = {
  general: "صيد عام",
  european_seabass: "القاروص",
  gilthead_seabream: "الدوراد (الورقة)",
  white_seabream: "المرجان الأبيض",
  striped_seabream: "المرجان المخطط",
};

const relationMeaning: Record<string, string> = {
  onshore: "تجّي من البحر وترمي الموج على الكسرة — راقب الكسرة والرغوة عن قرب",
  cross_onshore: "مائلة من البحر — تدفع الخط نحو الشاطئ وتزيد لمسة الموج",
  alongshore: "موازية للساحل — تدفع الخط جانبياً وتزيد الجرّ",
  cross_offshore: "مائلة من البر — تسهّل الرمي وترقّد البحر شوية",
  offshore: "برّية — البحر يرقّد قدامك، لكن المسافة البعيدة موش بالضرورة فيها سمك",
};

function waveStory(maximum: number): string {
  if (maximum < 0.5) return "هادئ — مريح للتثبيت وقريب من الكسرة";
  if (maximum < 1.0) return "متوسط — يتعامل معه الرصاص العادي";
  if (maximum < 1.6) return "قوي شوية — يحتاج وزناً أثقل قليلاً وحذراً قرب الحافة";
  return "هائج — راقب سلامة الوقوف قبل ما تفكّر في الصيد";
}

/**
 * سرد حتمي بصيغة صيّاد: يشرح «علاش نزيدو أو لا نزيدوش» بلغة ميدانية، من نفس
 * البيانات التي حسم بها المحرك القرار. لا يخترع أرقاماً ولا يحوّل المؤشر
 * النسبي إلى وعد مصيد. (يبقى تقرير Gemini اختيارياً منفصلاً في آخر الصفحة.)
 */
export function buildFishermanNarrative(
  result: DecisionResponse,
  request: ForecastDecisionRequest,
): string[] {
  const lead = result.recommended_windows[0];
  const hours = windowHours(result, lead);
  const paragraphs: string[] = [];

  // 1) الحكم
  if (result.decision === "caution" && lead) {
    paragraphs.push(
      `حذر: ساعات ${formatWindowRange(lead.start, lead.end)} مفتوحة بتحذيرات محددة وليست نظيفة. راقب البحر قبل الخروج. التنفيذ ${fieldFeasibilityLabels[result.field_feasibility.status]}.`
    );
  } else if (result.decision === "go" && lead) {
    paragraphs.push(
      `نزيدو في الساعات بلا موانع ${formatWindowRange(lead.start, lead.end)} فقط. خارجها لا تخرج. التنفيذ ${fieldFeasibilityLabels[result.field_feasibility.status]}. العين على البحر قبل العتاد.`,
    );
  } else {
    paragraphs.push(`الحكم: ${result.summary_ar || result.decision_label_ar} النموذج المحافظ ما يشجعش على الخروج اليوم ضمن الإعدادات الحالية.`);
  }

  // 2) الريح
  const windSpeeds = numeric(hours.map((hour) => hour.forecast.wind_speed_kmh));
  const gusts = numeric(hours.map((hour) => hour.forecast.wind_gust_kmh));
  const windSpan = span(windSpeeds);
  const gustMax = gusts.length ? Math.max(...gusts) : null;
  const relation = mostFrequent(
    hours.map((hour) => hour.derived.wind_relation).filter((value) => value && value !== "unknown"),
  );
  const sector = mostFrequent(
    hours.map((hour) => windSectorName(hour.forecast.wind_direction_deg)).filter((name) => name !== "غير معروف"),
  );
  if (windSpan) {
    const bits = [`الريح ${windSpan.min.toFixed(0)}–${windSpan.max.toFixed(0)} كم/س`];
    if (gustMax !== null && gustMax > windSpan.max + 2) bits.push(`هبات حتى ${gustMax.toFixed(0)} كم/س`);
    if (sector) bits.push(`غالبها ${sector}`);
    if (relation && relation !== "unknown") bits.push(windRelationLabel(relation));
    paragraphs.push(
      `${bits.join("، ")}.${relation && relationMeaning[relation] ? ` ${relationMeaning[relation]}.` : ""}`,
    );
  }

  // 3) الموج
  const waveHeights = numeric(hours.map((hour) => hour.forecast.wave_height_m));
  const wavePeriods = numeric(hours.map((hour) => hour.forecast.wave_period_s));
  const waveSpan = span(waveHeights);
  const periodSpan = span(wavePeriods);
  if (waveSpan) {
    paragraphs.push(
      `الموج ${waveSpan.min.toFixed(1)}–${waveSpan.max.toFixed(1)} م${periodSpan ? ` بفترة ${periodSpan.min.toFixed(0)}–${periodSpan.max.toFixed(0)} ثانية` : ""} — ${waveStory(waveSpan.max)}.`,
    );
  }

  // 4) الما والمد
  const ssts = numeric(hours.map((hour) => hour.forecast.sea_surface_temperature_c));
  const sstSpan = span(ssts);
  const tideAtStart = hours[0]?.derived.tide_state;
  const springNeap = result.spring_neap;
  if (sstSpan || tideAtStart || springNeap) {
    const parts: string[] = [];
    if (sstSpan) parts.push(`حرارة الماء ${sstSpan.min.toFixed(0)}–${sstSpan.max.toFixed(0)}°`);
    if (tideAtStart && tideAtStart !== "unknown") parts.push(`${tideLabel(tideAtStart)}`);
    if (springNeap && springNeap.classification !== "unknown") {
      parts.push(
        `المدّ ${springNeap.folk_label_ar} (${springNeapLabel(springNeap.classification)}) بمدى ${springNeap.range_target_day_m?.toFixed(2)} م`,
      );
    }
    if (parts.length) paragraphs.push(`${parts.join(" · ")}.`);
  }

  if (result.decision !== "go") {
    paragraphs.push("الخلاصة: لا تذهب. لا عتاد ولا نوع سمك يفتح ساعات فيها مانع محسوب.");
    return paragraphs;
  }

  // 5) السمك والوقت (مؤشر نسبي صادق)
  const species = result.species_axes?.species_matches;
  const top = species
    ?.filter((match) => match.availability !== "unavailable" && match.availability !== "unknown")
    .sort((first, second) => (first.availability === "strong" ? 0 : 1) - (second.availability === "strong" ? 0 : 1))[0];
  const hasTwilight = hours.some((hour) => hour.derived.is_twilight);
  if (top) {
    paragraphs.push(
      `من الأنواع (ترتيب لا قرار): ${top.label_ar} (توفر ${speciesAvailabilityLabel(top.availability)})${hasTwilight ? "؛ الساعات المفتوحة تلامس الشفق" : ""}. ليس ضمان مصيد.`,
    );
  } else if (hasTwilight) {
    paragraphs.push("الساعات المفتوحة تلامس الشفق — قرينة ضوء فقط، لا تفتح ساعة ممنوعة.");
  } else {
    const target = targetNames[request.angler.target_species] ?? request.angler.target_species;
    paragraphs.push(`الهدف مضبوط على ${target} — من غير سجل مصيد محلي، المؤشر ترتيب نسبي موش وعد صيد.`);
  }

  // 6) التثبيت والعتاد
  const field = result.field_feasibility;
  const dominant = field.holding_breakdown?.dominant;
  const gearLead = result.gear_recommendation?.scenarios?.[0];
  const holdingBits: string[] = [`تثبيت الخط ${potentialLabels[field.holding_difficulty]}`];
  if (dominant && dominant !== "none") holdingBits.push(`الغالب ${mechanismNames[dominant] ?? dominant}`);
  paragraphs.push(`${holdingBits.join("، ")}.`);
  if (gearLead) {
    paragraphs.push(
      `العتاد المقترح: ${gearLead.shape_ar} ${gearLead.weight_band_ar} على ${gearLead.montage_ar}${result.gear_recommendation?.casting_advice_ar ? ` — ${result.gear_recommendation.casting_advice_ar}` : ""}.`,
    );
  }
  if (field.fouling_transport_potential === "moderate" || field.fouling_transport_potential === "high") {
    paragraphs.push("الصوفة محتملة (مؤشر نموذجي موش رصد مؤكد) — رمية اختبارية قبل نصب العتاد الكامل.");
  }

  // 7) الخلاصة
  if (result.decision === "go") {
    paragraphs.push("الخلاصة: اخرج فقط في الساعات بلا موانع. إن تغيّر البحر على الأرض، أعد المعاينة.");
  } else if (result.decision === "caution") {
    paragraphs.push("الخلاصة: حذر. اخرج فقط في الساعات المعروضة مع مراعاة التحذيرات المذكورة، وأعد المعاينة إن تغيّر البحر.");
  } else {
    paragraphs.push("الخلاصة: لا تذهب. لا عتاد ولا نوع سمك يفتح ساعات فيها مانع محسوب.");
  }

  return paragraphs;
}
