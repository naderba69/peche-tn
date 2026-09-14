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

function windowTopSpecies(
  result: DecisionResponse,
  window: { start: string; end: string },
): { label: string; average: number } | null {
  const species = result.species_activity ?? [];
  if (!species.length) return null;
  const rows: { label: string; average: number }[] = [];
  for (const item of species) {
    const hours = item.hourly.filter((hour) => hour.time >= window.start && hour.time < window.end);
    if (!hours.length) continue;
    const average = Math.round(hours.reduce((sum, hour) => sum + hour.score, 0) / hours.length);
    rows.push({ label: item.label_ar, average });
  }
  if (!rows.length) return null;
  rows.sort((first, second) => second.average - first.average);
  return rows[0];
}

/**
 * A primary reason must be a verifiable, measurable reason — not a restatement
 * of the recommendation (audit 2026-09-14). For a safe window we compose it from
 * data already present in the response: the most active species in the lead
 * window, its edge over the runner-up window, twilight contact and tide phase.
 */
export function buildPrimaryReason(result: DecisionResponse, cautions: string[] = []): string {
  switch (result.decision_reason_code) {
    case "safe_window": {
      const lead = result.recommended_windows[0];
      if (!lead) {
        return (
          "توجد نافذة اجتازت حدود السلامة والتنفيذ الآلية وقابلة للتنفيذ مبدئياً؛ "
          + "ليست شهادة سلامة ميدانية."
        );
      }
      const parts: string[] = [];
      const top = windowTopSpecies(result, lead);
      if (top) {
        parts.push(`الأنشط فيها ${top.label} (متوسط ${top.average}/100 مؤشر غير معاير)`);
      }
      const alt = result.recommended_windows[1];
      if (alt && top) {
        const altTop = windowTopSpecies(result, alt);
        if (altTop) {
          const gap = top.average - altTop.average;
          parts.push(
            gap > 0
              ? `والنافذة التالية ${formatWindowRange(alt.start, alt.end)} أدنى منها بفارق ${gap} نقطة (${altTop.average}/100) على المؤشر نفسه غير المعاير`
              : `والنافذة التالية ${formatWindowRange(alt.start, alt.end)} عند ${altTop.average}/100 على المؤشر نفسه غير المعاير`,
          );
        }
      }
      const twilight = result.hourly.some(
        (hour) => hour.time >= lead.start && hour.time < lead.end && hour.derived.is_twilight,
      );
      if (twilight) parts.push("تلامس الغسق");
      const tide = result.hourly.find((hour) => hour.time === lead.start)?.derived.tide_state;
      if (tide === "rising") parts.push("مد صاعد (ماء يتحرك)");
      if (tide === "falling") parts.push("مد هابط (ماء يتحرك)");
      const base = parts.length
        ? `النافذة ${formatWindowRange(lead.start, lead.end)}: ${parts.join(" · ")}.`
        : "توجد نافذة اجتازت حدود السلامة والتنفيذ الآلية وقابلة للتنفيذ مبدئياً؛ ليست شهادة سلامة ميدانية.";
      if (!cautions.length) return base;
      const cleanCautions = cautions
        .slice(0, 3)
        .map((text) => text.replace(/[.؛\s]+$/u, ""));
      return `${base} نقاط الحذر داخلها: ${cleanCautions.join(" · ")}.`;
    }
    case "safety_hazard":
      return "خطر سلامة أو عتبة حذر محافظة داخل أفضل نافذة متاحة.";
    case "field_infeasible":
      return "صعوبة تثبيت الخط مرتفعة داخل أفضل نافذة؛ مؤشرا الصوفة والعكارة تنبيهان غير مانعين بلا رصد.";
    case "critical_data_missing":
      return "بيانات حرجة ناقصة؛ لا يحوّل المحرك Unknown إلى بحر هادئ.";
    case "conservative_uncertainty":
      return "مستوى عدم اليقين المؤثر تجاوز ما تسمح به السياسة المحافظة.";
    case "fouling_confirmed":
      return "صوفة/عوالق مؤكدة ببلاغ ميداني حديث أو رمية اختبار؛ لا نافذة قابلة للتنفيذ رغم سلامة التوقع.";
    case "official_warning":
      return "تحذير رسمي ساري (نشرة INM أو سلطة مختصة) يلغي الرحلة تلقائياً فوق كل العتبات المحلية.";
    case "trip_ruin_confirmed":
      return "عامل مُفسِد مؤكد (قناديل/حطام/تعكر كثيف) يجعل الخرجة غير مجدية.";
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
  if (result.decision === "go" && lead) {
    paragraphs.push(
      `نزيدو ضمن نافذة ${formatWindowRange(lead.start, lead.end)} — الريح والموج داخل حدود السلامة، والتنفيذ الميداني ${fieldFeasibilityLabels[result.field_feasibility.status]}. هذا تحليل من النموذج، موش شهادة ميدانية: العين على البحر قبل العتاد.`,
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

  // 5) السمك والوقت (مؤشر نسبي صادق)
  const species = result.species_axes?.species_matches;
  const top = species
    ?.filter((match) => match.availability !== "unavailable" && match.availability !== "unknown")
    .sort((first, second) => (first.availability === "strong" ? 0 : 1) - (second.availability === "strong" ? 0 : 1))[0];
  const hasTwilight = hours.some((hour) => hour.derived.is_twilight);
  if (top) {
    paragraphs.push(
      `من الأنواع: ${top.label_ar} (توفر ${speciesAvailabilityLabel(top.availability)})${hasTwilight ? "، وفي النافذة شفق معروف عند الصيادين" : ""}. مؤشر نسبي للمقارنة، موش ضمان مصيد.`,
    );
  } else if (hasTwilight) {
    paragraphs.push("النافذة تلامس الشفق — وقت تغذية معروف عند الصيادين، قرينة موش قاعدة مضمونة.");
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
    paragraphs.push("الخلاصة: النموذج يقترح، والعين تحكم. التزم بالنافذة ولا تمدّدها إذا تغيّر البحر على الأرض.");
  } else {
    paragraphs.push("الخلاصة: الساعة اللي ما تجي على مزاج البحر، ما تجي على مزاج الصياد. تأجّل أحسن من مجازفة.");
  }

  return paragraphs;
}
