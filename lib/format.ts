import type { DecisionLevel, FactorBasis, FieldFeasibilityLevel, PotentialLevel, RuleNature } from "@/lib/types";

const TUNIS_TZ = "Africa/Tunis";

export const decisionLabels: Record<DecisionLevel, string> = {
  go: "انطلق في النافذة المختارة",
  caution: "انطلق بحذر",
  no_go: "لا تنطلق",
  unknown: "المعطيات غير كافية",
};

export const decisionShortLabels: Record<DecisionLevel, string> = {
  go: "مناسب",
  caution: "حذر",
  no_go: "ممنوع",
  unknown: "ناقص",
};

export const fieldFeasibilityLabels: Record<FieldFeasibilityLevel, string> = {
  favorable: "مريحة ميدانياً",
  workable: "قابلة مع ضبط العتاد",
  difficult: "صعبة ميدانياً",
  unknown: "غير محسومة",
};

export const potentialLabels: Record<PotentialLevel, string> = {
  low: "منخفض*",
  moderate: "متوسط*",
  high: "مرتفع*",
  unknown: "غير معروف",
};

export const factorBasisLabels: Record<FactorBasis, string> = {
  model_forecast: "توقع نموذجي",
  direct_observation: "رصد فعلي لمحطة",
  remote_sensing_estimate: "استعادة أقمار صناعية",
  derived_forecast: "مشتق من التوقع",
  spot_profile: "ملف البقعة",
  expert_prior: "فرضية أولية",
};

export const ruleNatureLabels: Record<RuleNature, string> = {
  physical_derivation: "اشتقاق فيزيائي",
  safety_policy: "سياسة سلامة",
  operational_proxy: "مؤشر تشغيلي",
  expert_prior: "غير معاير محلياً",
  data_quality: "جودة بيانات",
};

export function formatHour(value: string): string {
  return new Intl.DateTimeFormat("ar-TN", {
    timeZone: TUNIS_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function tunisDateKey(value: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TUNIS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

export function formatWindowRange(start: string, end: string): string {
  const nextDay = tunisDateKey(start) !== tunisDateKey(end) ? " (اليوم التالي)" : "";
  return `${formatHour(start)}–${formatHour(end)}${nextDay}`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ar-TN", {
    timeZone: TUNIS_TZ,
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(`${value}T12:00:00+01:00`));
}

export function formatDateChip(value: string): { weekday: string; day: string } {
  const date = new Date(`${value}T12:00:00+01:00`);
  return {
    weekday: new Intl.DateTimeFormat("ar-TN", {
      timeZone: TUNIS_TZ,
      weekday: "short",
    }).format(date),
    day: new Intl.DateTimeFormat("ar-TN", {
      timeZone: TUNIS_TZ,
      day: "numeric",
      month: "short",
    }).format(date),
  };
}

export function formatGeneratedAt(value: string): string {
  return new Intl.DateTimeFormat("ar-TN", {
    timeZone: TUNIS_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

export function numberOrDash(value: number | null, digits = 0): string {
  return value === null || Number.isNaN(value) ? "—" : value.toFixed(digits);
}

export function compassLabel(value: number): string {
  const directions = ["ش", "ش ش ق", "ش ق", "ق ش ق", "ق", "ق ج ق", "ج ق", "ج ج ق", "ج", "ج ج غ", "ج غ", "غ ج غ", "غ", "غ ش غ", "ش غ", "ش ش غ"];
  return directions[Math.round(value / 22.5) % 16];
}

export function tunisTodayIso(offsetDays = 0): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TUNIS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value);
  const utc = new Date(Date.UTC(read("year"), read("month") - 1, read("day") + offsetDays));
  return utc.toISOString().slice(0, 10);
}

export function tideLabel(value: string): string {
  return { rising: "مستوى البحر صاعد", falling: "مستوى البحر هابط", slack: "حركة ضعيفة", unknown: "غير متوفر" }[value] ?? value;
}

export function springNeapLabel(value: string): string {
  return { spring: "حيّة", neap: "مات", intermediate: "وسط", unknown: "غير معروف" }[value] ?? value;
}

export function speciesAxisStatusLabel(value: string): string {
  return {
    favorable: "مناسب",
    neutral: "محايد",
    unfavorable: "غير مناسب",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function speciesAxisKeyLabel(value: string): string {
  return {
    seasonal: "التوفر الموسمي",
    habitat: "توافق الموطن",
    surf_approach: "قابلية الاقتراب من السيرف",
    feeding_window: "نافذة التغذية",
    prey_evidence: "دليل الفرائس",
  }[value] ?? value;
}

export function speciesAvailabilityLabel(value: string): string {
  return {
    strong: "قوي",
    medium: "متوسط",
    weak: "ضعيف",
    unavailable: "غير متوفر",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function speciesThermalLabel(value: string): string {
  return {
    preferred: "ضمن المفضّل",
    tolerated: "ضمن التحمل",
    outside: "خارج المجال",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function seaStateFitLabel(value: string): string {
  return {
    favorable: "نمط مناسب",
    neutral: "خارج التفضيل (محايد)",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function tripRuinLevelLabel(value: string): string {
  return {
    unknown: "غير معروف",
    low: "منخفض",
    moderate: "متوسط",
    high: "مرتفع",
  }[value] ?? value;
}

export function tripRuinBasisLabel(value: string): string {
  return {
    satellite: "دليل ساتلي",
    forecast_proxy: "تنبؤ نموذجي",
    field_report: "بلاغ ميداني",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function windRelationLabel(value: string): string {
  return {
    onshore: "بحرية مباشرة",
    offshore: "برّية مباشرة",
    cross_onshore: "جانبية من البحر",
    alongshore: "موازية للشاطئ",
    cross_offshore: "جانبية من البر",
    unknown: "غير معروف",
  }[value] ?? value;
}

export function waveIncidenceLabel(value: string): string {
  return {
    direct: "داخل مباشرة نحو الشاطئ",
    oblique: "داخل بزاوية",
    alongshore: "موازٍ تقريباً للشاطئ",
    inconsistent: "قادِم من جهة غير بحرية",
    unknown: "غير معروف",
  }[value] ?? value;
}
