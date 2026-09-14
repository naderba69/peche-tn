// التفكيك الزمني لليوم (تحليل كل فترة): تعريف فترات اليوم وحساب ملخصاتها.
// مصدر واحد مشترك بين الصفحة الرئيسية (قرب النوافذ) والتقرير الكامل.

import type { DecisionLevel, Factor, HourDecision } from "@/lib/types";
import { tideLabel, waveIncidenceLabel, windRelationLabel } from "@/lib/format";

const TUNIS_TZ = "Africa/Tunis";

export interface PeriodSummary {
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

export const PERIODS = [
  { id: "late-night", label: "آخر الليل", range: "00:00–03:59", from: 0, to: 3 },
  { id: "morning", label: "الفجر والصباح", range: "04:00–11:59", from: 4, to: 11 },
  { id: "afternoon", label: "الظهيرة والعشية", range: "12:00–17:59", from: 12, to: 17 },
  { id: "evening", label: "المساء والليل", range: "18:00–23:59", from: 18, to: 23 },
] as const;

const safetyPriority: Record<DecisionLevel, number> = {
  go: 0,
  caution: 1,
  unknown: 2,
  no_go: 3,
};

function localHour(value: string): number {
  return Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: TUNIS_TZ,
      hour: "2-digit",
      hourCycle: "h23",
    }).format(new Date(value)),
  );
}

export function numericValues(
  hours: HourDecision[],
  read: (hour: HourDecision) => number | null,
): number[] {
  return hours.map(read).filter((value): value is number => value !== null && Number.isFinite(value));
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

export function maximum(values: number[]): number | null {
  return values.length ? Math.max(...values) : null;
}

export function minimum(values: number[]): number | null {
  return values.length ? Math.min(...values) : null;
}

export function metricRange(values: number[], digits = 1, suffix = ""): string {
  if (!values.length) return "غير متوفر";
  const low = Math.min(...values).toFixed(digits);
  const high = Math.max(...values).toFixed(digits);
  return `${low === high ? low : `${low}–${high}`}${suffix}`;
}

export function dominant(values: string[]): string | null {
  if (!values.length) return null;
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts].sort((first, second) => second[1] - first[1])[0]?.[0] ?? null;
}

export function uniqueFactors(hours: HourDecision[]): Factor[] {
  const factors = new Map<string, Factor>();
  for (const hour of hours) {
    for (const factor of hour.factors) {
      const key = `${factor.code}:${factor.explanation_ar}`;
      if (!factors.has(key)) factors.set(key, factor);
    }
  }
  return [...factors.values()];
}

export function factorPriority(factor: Factor): number {
  const severity = { critical: 30, caution: 20, info: 10 }[factor.severity];
  const impact = { safety: 6, data_gap: 5, negative: 4, neutral: 2, positive: 1 }[factor.impact];
  return severity + impact + Math.min(Math.abs(factor.score_delta), 9) / 10;
}

function worstSafety(hours: HourDecision[]): DecisionLevel | null {
  if (!hours.length) return null;
  return hours.reduce(
    (worst, hour) => (safetyPriority[hour.safety] > safetyPriority[worst] ? hour.safety : worst),
    hours[0].safety,
  );
}

export function buildPeriodSummary(
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
