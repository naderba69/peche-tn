import type { DecisionResponse, PotentialLevel, TripRuinFactor } from "@/lib/types";

export type BlockerTone = "block" | "caution" | "clear" | "unknown";

export interface TripBlockerRow {
  id: string;
  group: "سلامة" | "تنفيذ" | "ميدان غير مرئي";
  label: string;
  tone: BlockerTone;
  blocksGo: boolean;
  detail: string;
  hourTime?: string | null;
}

function ruin(result: DecisionResponse, key: TripRuinFactor["factor"]): TripRuinFactor | undefined {
  return result.trip_ruin_factors?.find((item) => item.factor === key);
}

function potentialTone(level: PotentialLevel, highBlocks: boolean): { tone: BlockerTone; blocksGo: boolean } {
  if (level === "high") return { tone: "block", blocksGo: highBlocks };
  if (level === "moderate") return { tone: "caution", blocksGo: false };
  if (level === "low") return { tone: "clear", blocksGo: false };
  return { tone: "unknown", blocksGo: false };
}

function hourHas(result: DecisionResponse, code: string): boolean {
  return result.hourly.some((hour) => hour.factors.some((factor) => factor.code === code));
}

function dayIsGo(result: DecisionResponse): boolean {
  return result.decision === "go";
}

/** A safety code that appears only in blocked hours must not contradict a GO headline. */
function safetyTone(
  result: DecisionResponse,
  noGoCodes: string[],
  cautionCodes: string[],
  missing: boolean,
): { tone: BlockerTone; blocksGo: boolean } {
  const present = noGoCodes.some((code) => hourHas(result, code));
  if (present && dayIsGo(result)) {
    return { tone: "caution", blocksGo: false };
  }
  if (present) return { tone: "block", blocksGo: true };
  if (cautionCodes.some((code) => hourHas(result, code))) return { tone: "caution", blocksGo: false };
  if (missing) return { tone: "unknown", blocksGo: false };
  return { tone: "clear", blocksGo: false };
}

function firstHourWith(result: DecisionResponse, ...codes: string[]): string | null {
  for (const code of codes) {
    const hour = result.hourly.find((item) => item.factors.some((factor) => factor.code === code));
    if (hour) return hour.time;
  }
  return null;
}

function firstHourWhere(
  result: DecisionResponse,
  match: (hour: DecisionResponse["hourly"][number]) => boolean,
): string | null {
  return result.hourly.find(match)?.time ?? null;
}

function maxForecast(result: DecisionResponse, key: "wind_speed_kmh" | "wind_gust_kmh" | "wave_height_m"): number | null {
  const values = result.hourly
    .map((hour) => hour.forecast[key])
    .filter((value): value is number => typeof value === "number");
  return values.length ? Math.max(...values) : null;
}

function minVisibility(result: DecisionResponse): number | null {
  const values = result.hourly
    .map((hour) => hour.forecast.visibility_m)
    .filter((value): value is number => typeof value === "number");
  return values.length ? Math.min(...values) : null;
}

const potentialAr: Record<PotentialLevel, string> = {
  low: "منخفض",
  moderate: "متوسط",
  high: "مرتفع",
  unknown: "غير معروف",
};

/** Complete trip-ruin board from the live decision — not a second scoring engine. */
export function buildTripBlockers(result: DecisionResponse): TripBlockerRow[] {
  const field = result.field_feasibility;
  const holding = potentialTone(field.holding_difficulty, true);
  const turbidity = potentialTone(field.turbidity_potential, true);
  const fouling = potentialTone(field.fouling_transport_potential, false);
  const rip = potentialTone(field.rip_current_potential, field.status === "difficult");
  const foulingRuin = ruin(result, "dense_fouling");
  const turbidityRuin = ruin(result, "turbidity");
  const jelly = ruin(result, "jellyfish");
  const debris = ruin(result, "storm_debris");
  const heat = ruin(result, "marine_heatwave");

  const windKmh = maxForecast(result, "wind_speed_kmh");
  const gustKmh = maxForecast(result, "wind_gust_kmh");
  const waveM = maxForecast(result, "wave_height_m");
  const visM = minVisibility(result);
  const thunder = safetyTone(result, ["thunderstorm", "nearby_metar_thunderstorm"], ["convective_instability"], false);
  const wind = safetyTone(result, ["sustained_wind_no_go"], ["sustained_wind_caution"], windKmh == null);
  const gust = safetyTone(result, ["gust_no_go"], ["gust_caution"], gustKmh == null);
  const wave = safetyTone(
    result,
    ["wave_height_no_go", "steep_wave_no_go"],
    ["wave_height_caution", "steep_wave_caution"],
    waveM == null,
  );
  const vis = safetyTone(result, ["visibility_no_go"], ["visibility_caution"], visM == null);

  function hourGateNote(row: { tone: BlockerTone; blocksGo: boolean }): string {
    return dayIsGo(result) && row.tone === "caution" && !row.blocksGo
      ? " يمنع ساعات محددة لا اليوم كله."
      : "";
  }

  const inmBlocks =
    result.official_warning_check?.status === "warning_active" ||
    result.decision_reason_code === "official_warning" ||
    result.decision_reason_code === "official_warning_unverified";

  const dataBlocks = [
    "critical_data_missing",
    "stale_forecast_data",
    "forecast_horizon_exceeded",
  ].includes(result.decision_reason_code);

  const longshore = field.holding_breakdown?.longshore_current ?? "unknown";

  return [
    {
      id: "thunder",
      group: "سلامة",
      label: "رعد وبرق",
      tone: thunder.tone,
      blocksGo: thunder.blocksGo,
      detail: thunder.tone === "clear" ? "لا رمز رعد في ساعات اليوم." : `عاصفة رعدية في التوقع أو رصد محطة قريبة.${hourGateNote(thunder)}`,
      hourTime: firstHourWith(result, "thunderstorm", "nearby_metar_thunderstorm", "convective_instability"),
    },
    {
      id: "wind",
      group: "سلامة",
      label: "ريح متواصلة",
      tone: wind.tone,
      blocksGo: wind.blocksGo,
      detail: windKmh == null ? "سرعة الريح ناقصة." : `أقصى توقع ${Math.round(windKmh)} كم/س.${hourGateNote(wind)}`,
      hourTime: firstHourWith(result, "sustained_wind_no_go", "sustained_wind_caution"),
    },
    {
      id: "gust",
      group: "سلامة",
      label: "هبّات",
      tone: gust.tone,
      blocksGo: gust.blocksGo,
      detail: gustKmh == null ? "الهبّات ناقصة." : `أقصى هبّة ${Math.round(gustKmh)} كم/س.${hourGateNote(gust)}`,
      hourTime: firstHourWith(result, "gust_no_go", "gust_caution"),
    },
    {
      id: "wave",
      group: "سلامة",
      label: "موج / طاقة كسر",
      tone: wave.tone,
      blocksGo: wave.blocksGo,
      detail:
        waveM == null
          ? "ارتفاع الموج ناقص."
          : `أقصى Hs نموذجي ${waveM.toFixed(2)} م — ليس ارتفاع الكسرة.${hourGateNote(wave)}`,
      hourTime: firstHourWith(result, "wave_height_no_go", "steep_wave_no_go", "wave_height_caution", "steep_wave_caution"),
    },
    {
      id: "visibility",
      group: "سلامة",
      label: "الرؤية الجوية",
      tone: vis.tone,
      blocksGo: vis.blocksGo,
      detail: visM == null ? "الرؤية ناقصة." : `أدنى رؤية ${(visM / 1000).toFixed(1)} كم (جوّية لا شفافية ماء).`,
      hourTime: firstHourWith(result, "visibility_no_go", "visibility_caution"),
    },
    {
      id: "inm",
      group: "سلامة",
      label: "نشرة INM",
      tone: inmBlocks ? "block" : result.official_warning_check?.status === "verified_clear" ? "clear" : "unknown",
      blocksGo: inmBlocks,
      detail: result.official_warning_check?.explanation_ar ?? "فحص النشرة الرسمية شرط للذهاب.",
    },
    {
      id: "data",
      group: "سلامة",
      label: "جودة التوقع",
      tone: dataBlocks || result.cache_fallback_used ? "block" : result.confidence.score < 50 ? "caution" : "clear",
      blocksGo: dataBlocks || Boolean(result.cache_fallback_used),
      detail: result.cache_fallback_used
        ? "توقع قديم من الكاش — لا يُعتمد للتخطيط."
        : `اكتمال ${result.confidence.score}/100 (ليست دقة ميدانية).`,
    },
    {
      id: "holding",
      group: "تنفيذ",
      label: "جرّ الرصاص / تثبيت الخط",
      tone: holding.tone,
      blocksGo: holding.blocksGo,
      detail: `صعوبة ${potentialAr[field.holding_difficulty]} · السبب الغالب: ${
        field.holding_breakdown
          ? { longshore_current: "جرّ جانبي", orbital_motion: "مدار قاعي", return_flow: "رجوع بحري", tidal_current: "مدّي", none: "غير غالب" }[
              field.holding_breakdown.dominant
            ]
          : "غير مفكك"
      }. المرتفع يمنع الخرجة.`,
      hourTime: firstHourWhere(result, (hour) => hour.field_feasibility.holding_difficulty === "high"),
    },
    {
      id: "alongshore",
      group: "تنفيذ",
      label: "تيار/موج جانبي",
      tone: potentialTone(longshore, longshore === "high").tone,
      blocksGo: longshore === "high",
      detail: `قناة الجرّ الجانبي ${potentialAr[longshore]} — يجرف الرصاص خارج المرمى.`,
      hourTime: firstHourWhere(
        result,
        (hour) => hour.field_feasibility.holding_breakdown?.longshore_current === "high",
      ),
    },
    {
      id: "turbidity",
      group: "تنفيذ",
      label: "عكارة الماء",
      tone: turbidity.tone,
      blocksGo: turbidity.blocksGo,
      detail:
        turbidityRuin?.evidence_ar[0] ??
        `مؤشر نموذجي ${potentialAr[field.turbidity_potential]} (${field.turbidity_evidence_count} عائلات/48س) — ليست NTU.`,
      hourTime: firstHourWhere(result, (hour) => hour.field_feasibility.turbidity_potential === "high"),
    },
    {
      id: "fouling",
      group: "تنفيذ",
      label: "صوفة / أعشاب",
      tone: foulingRuin?.is_force_majeure ? "block" : fouling.tone,
      blocksGo: Boolean(foulingRuin?.is_force_majeure),
      detail:
        foulingRuin?.evidence_ar[0] ??
        `قابلية نقل ${potentialAr[field.fouling_transport_potential]} — لا يثبت وجود الأعشاب على الحافة.`,
      hourTime: firstHourWhere(
        result,
        (hour) => hour.field_feasibility.fouling_transport_potential === "high",
      ),
    },
    {
      id: "rip",
      group: "تنفيذ",
      label: "تيار ساحبي",
      tone: rip.tone,
      blocksGo: rip.blocksGo,
      detail: `مؤشر ${potentialAr[field.rip_current_potential]} بلا خريطة قضبان. عاين قناة الرغوة قبل النزول.`,
      hourTime: firstHourWhere(result, (hour) => hour.field_feasibility.rip_current_potential === "high"),
    },
    {
      id: "breaker",
      group: "ميدان غير مرئي",
      label: "كسرة الشاطئ",
      tone: "unknown",
      blocksGo: false,
      detail: "Hs الخلية ليس ارتفاع الكسر. بلا ميل القاع لا قياس — عاين من الشاطئ.",
    },
    {
      id: "jellyfish",
      group: "ميدان غير مرئي",
      label: "قناديل",
      tone: jelly?.level === "high" ? "block" : jelly?.level === "moderate" ? "caution" : "unknown",
      blocksGo: Boolean(jelly?.is_force_majeure),
      detail: jelly?.evidence_ar[0] ?? "لا مصدر آلي للبقعة.",
    },
    {
      id: "debris",
      group: "ميدان غير مرئي",
      label: "حطام الأودية",
      tone: debris?.level === "high" ? "block" : debris?.level === "moderate" ? "caution" : "unknown",
      blocksGo: Boolean(debris?.is_force_majeure),
      detail: debris?.evidence_ar[0] ?? "لا قياس آلي بعد المطر الغزير.",
    },
    {
      id: "heat",
      group: "ميدان غير مرئي",
      label: "شذوذ حرارة البحر",
      tone: heat?.level === "high" ? "caution" : heat?.level === "moderate" ? "caution" : heat ? "clear" : "unknown",
      blocksGo: false,
      detail: heat?.evidence_ar[0] ?? "إعلامي لتوفر السمك — لا يمنع الوقوف.",
    },
    {
      id: "crowd",
      group: "ميدان غير مرئي",
      label: "ناس / شباك في مجال الرمي",
      tone: "unknown",
      blocksGo: false,
      detail: "مانع عملي مباشر لا يظهر في توقع الطقس.",
    },
  ];
}
