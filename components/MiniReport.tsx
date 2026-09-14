"use client";

import { useMemo } from "react";
import {
  Anchor,
  CalendarClock,
  CircleAlert,
  Fish,
  Info,
  TriangleAlert,
  Waves,
  Wind,
} from "lucide-react";
import { formatWindowRange, potentialLabels, speciesAvailabilityLabel, speciesAxisStatusLabel, springNeapLabel } from "@/lib/format";
import type { DecisionResponse, HourDecision } from "@/lib/types";

interface MiniReportProps {
  result: DecisionResponse;
}

/** وسوم وصفية إرشادية فقط — حدود القرار الفعلية تبقى في التقرير الكامل. */
function windBucket(kmh: number | null): { label: string; level: "ok" | "watch" | "bad" } | null {
  if (kmh === null) return null;
  if (kmh < 20) return { label: "هادئة", level: "ok" };
  if (kmh < 30) return { label: "معتدلة", level: "ok" };
  if (kmh < 40) return { label: "قوية", level: "watch" };
  return { label: "عاصفة", level: "bad" };
}

function waveBucket(m: number | null): { label: string; level: "ok" | "watch" | "bad" } | null {
  if (m === null) return null;
  if (m < 0.5) return { label: "هادئ", level: "ok" };
  if (m < 1.0) return { label: "متوسط", level: "ok" };
  if (m < 2.0) return { label: "قوي", level: "watch" };
  return { label: "هائج", level: "bad" };
}

function potentialLevel(p: "low" | "moderate" | "high" | "unknown"): "ok" | "watch" | "bad" {
  if (p === "low") return "ok";
  if (p === "moderate") return "watch";
  if (p === "high") return "bad";
  return "watch";
}

const reasonShort: Record<string, string> = {
  safe_window: "نافذة اجتازت حدود المحرك",
  safety_hazard: "خطر سلامة",
  field_infeasible: "استحالة تثبيت العتاد",
  critical_data_missing: "نقص بيانات حرجة",
  conservative_uncertainty: "تحفظ محافظ",
  fouling_confirmed: "صوفة/عوالق مؤكدة",
  official_warning: "تحذير رسمي ساري",
  trip_ruin_confirmed: "عامل مُفسِد مؤكد",
};

const mechanismLabel: Record<string, string> = {
  longshore_current: "الجرّ الجانبي",
  orbital_motion: "حركة القاع المدارية",
  return_flow: "الرجوع للبحر",
  tidal_current: "تيار المدّ",
  none: "لا سبب غالب",
};

const mechanismHint: Record<string, string> = {
  longshore_current: "موج مائل يجرّ الخط جانبياً: رصاص هرمي/بأذرع وارمِ بزاوية عكس الجرّ.",
  orbital_motion: "الموج يحرّك الماء فوق الرصاص: فضّل وزناً أثقل قليلاً ضمن قدرة قصبتك.",
  return_flow: "رجوع الماء نحو البحر يسحب الطعم: مونتاج قليل المقاومة وارمِ أقصر.",
  tidal_current: "تيار المدّ يجرّ الخيط (قوي في خليج قابس): استنى قرب ساعة السكون.",
  none: "",
};

const forceMajeureLabels: Record<string, string> = {
  safety: "خطر سلامة",
  holding: "استحالة تثبيت العتاد",
  fouling: "صوفة/حطام كثيف مؤكد",
  access_legal: "منع قانوني/تحذير رسمي",
  trip_ruin: "عامل مُفسِد مؤكد (قناديل/حطام/تعكر)",
  data: "نقص بيانات حرجة",
};

export function MiniReport({ result }: MiniReportProps) {
  const { decision, field_feasibility: field } = result;
  const isGo = decision === "go";
  const leadWindow = result.recommended_windows[0] ?? null;

  const scopeHours: HourDecision[] = useMemo(() => {
    if (!leadWindow) return result.hourly;
    return result.hourly.filter(
      (h) => h.time >= leadWindow.start && h.time < leadWindow.end,
    );
  }, [result.hourly, leadWindow]);

  const windMax = useMemo(() => {
    const values = scopeHours
      .map((h) => h.forecast.wind_speed_kmh)
      .filter((v): v is number => v !== null);
    return values.length ? Math.max(...values) : null;
  }, [scopeHours]);

  const gustMax = useMemo(() => {
    const values = scopeHours
      .map((h) => h.forecast.wind_gust_kmh)
      .filter((v): v is number => v !== null);
    return values.length ? Math.max(...values) : null;
  }, [scopeHours]);

  const waveMax = useMemo(() => {
    const values = scopeHours
      .map((h) => h.forecast.wave_height_m)
      .filter((v): v is number => v !== null);
    return values.length ? Math.max(...values) : null;
  }, [scopeHours]);

  const wind = windBucket(windMax);
  const wave = waveBucket(waveMax);
  const holding = field.holding_difficulty;
  const fouling = field.fouling_transport_potential;
  const turbidity = field.turbidity_potential;
  const rip = field.rip_current_potential;

  const breakdown = field.holding_breakdown;
  const dominant = breakdown?.dominant ?? "none";
  const dominantHint = mechanismHint[dominant];
  const gear = result.gear_recommendation;
  const gearLead = gear?.scenarios?.[0] ?? null;
  const foulingEvidence = result.fouling_evidence;
  const springNeap = result.spring_neap;
  const speciesAxes = result.species_axes;
  const speciesSummary = speciesAxes
    ? speciesAxes.axes
        .filter((axis) => axis.status !== "unknown")
        .slice(0, 2)
        .map((axis) => `${axis.label_ar}: ${speciesAxisStatusLabel(axis.status)}`)
        .join(" · ")
    : null;
  const speciesMatchesSummary =
    speciesAxes?.species_matches && speciesAxes.species_matches.length > 0
      ? speciesAxes.species_matches
          .filter((match) => match.status !== "unknown" && match.availability !== "unavailable")
          .slice(0, 3)
          .map((match) => `${match.label_ar} (${speciesAvailabilityLabel(match.availability)})`)
          .join(" · ")
      : null;
  const gearHint =
    holding === "high" || holding === "moderate"
      ? dominantHint ||
        (holding === "high"
          ? "تثبيت الخط صعب جداً: جهّز أثقل وزن ضمن قدرة قصبتك ومونتاجاً قليل المقاومة، وافحص القاع قبل النصب."
          : "تثبيت الخط يحتاج اهتماماً: فضّل وزناً أثقل قليلاً من المعتاد ومونتاجاً منخفض المقاومة.")
      : null;
  const causeLabel =
    result.force_majeure_kind && result.force_majeure_kind !== "none"
      ? forceMajeureLabels[result.force_majeure_kind]
      : reasonShort[result.decision_reason_code];

  const avoidRange =
    result.avoid_windows.length > 0
      ? result.avoid_windows
          .slice(0, 3)
          .map((w) => formatWindowRange(w.start, w.end))
          .join(" · ")
      : null;

  return (
    <section className="mini-report" aria-label="الخلاصة السريعة">
      <div className="mini-report-head">
        <span className="mini-report-title">📋 الخلاصة السريعة</span>
        <span className={`mini-badge mini-${isGo ? "go" : "nogo"}`}>
          {isGo ? "✅ اذهب" : "⛔ لا تذهب"}
        </span>
      </div>

      <div className="mini-report-body">
        {isGo && leadWindow ? (
          <div className="mini-line mini-line-lead">
            <CalendarClock size={16} />
            <span>
              <strong>أحسن وقت:</strong> <bdi>{formatWindowRange(leadWindow.start, leadWindow.end)}</bdi>
            </span>
          </div>
        ) : (
          <div className="mini-line mini-line-lead mini-line-block">
            <CircleAlert size={16} />
            <span>
              <strong>السبب القاهر:</strong> {causeLabel ?? "عامل غير قابل للتكيّف"}
            </span>
          </div>
        )}

        <ul className="mini-factors">
          <li className={`mini-factor level-${wind?.level ?? "na"}`}>
            <Wind size={15} />
            <span className="mini-factor-name">الريح</span>
            <span className="mini-factor-value">
              {windMax !== null ? (
                <>
                  <bdi>{Math.round(windMax)} كم/س</bdi>
                  {gustMax !== null && gustMax > windMax ? (
                    <small> هبات {Math.round(gustMax)}</small>
                  ) : null}
                  <em className={`chip chip-${wind?.level}`}>{wind?.label}</em>
                </>
              ) : (
                "غير متوفرة"
              )}
            </span>
          </li>
          <li className={`mini-factor level-${wave?.level ?? "na"}`}>
            <Waves size={15} />
            <span className="mini-factor-name">الموج</span>
            <span className="mini-factor-value">
              {waveMax !== null ? (
                <>
                  <bdi>{waveMax.toFixed(1)} م</bdi>
                  <em className={`chip chip-${wave?.level}`}>{wave?.label}</em>
                </>
              ) : (
                "غير متوفرة"
              )}
            </span>
          </li>
          <li className={`mini-factor level-${potentialLevel(holding)}`}>
            <Anchor size={15} />
            <span className="mini-factor-name">تثبيت الخط</span>
            <span className="mini-factor-value">
              <em className={`chip chip-${potentialLevel(holding)}`}>{potentialLabels[holding]}</em>
              {dominant !== "none" && holding !== "low" ? (
                <small>الغالب: {mechanismLabel[dominant]}</small>
              ) : null}
            </span>
          </li>
          <li className={`mini-factor level-${potentialLevel(fouling)}`}>
            <span className="mini-factor-name">الصوفة</span>
            <span className="mini-factor-value">
              <em className={`chip chip-${potentialLevel(fouling)}`}>{potentialLabels[fouling]}</em>
              {foulingEvidence && foulingEvidence.level >= 3 ? (
                <small className={foulingEvidence.is_force_majeure ? "evidence-confirmed" : ""}>
                  دليل ميداني: مستوى {foulingEvidence.level}
                </small>
              ) : (
                <small> محتملة — ما تثبتش إلا بالعين</small>
              )}
            </span>
          </li>
          <li className={`mini-factor level-${potentialLevel(turbidity)}`}>
            <span className="mini-factor-name">العكارة</span>
            <span className="mini-factor-value">
              <em className={`chip chip-${potentialLevel(turbidity)}`}>{potentialLabels[turbidity]}</em>
            </span>
          </li>
          <li className={`mini-factor level-${potentialLevel(rip)}`}>
            <span className="mini-factor-name">تيار ساحبي</span>
            <span className="mini-factor-value">
              <em className={`chip chip-${potentialLevel(rip)}`}>{potentialLabels[rip]}</em>
            </span>
          </li>
        </ul>

        {gearLead ? (
          <div className="mini-line mini-line-gear">
            <Anchor size={16} />
            <span>
              <strong>العتاد المقترح:</strong> {gearLead.shape_ar}{" "}
              <bdi>{gearLead.weight_band_ar}</bdi> · {gearLead.montage_ar}
              {gear?.casting_advice_ar ? <small> — {gear.casting_advice_ar}</small> : null}
              <small> ({gear?.required_rod_rating_note_ar})</small>
            </span>
          </div>
        ) : gearHint ? (
          <div className="mini-line mini-line-gear">
            <Anchor size={16} />
            <span>{gearHint}</span>
          </div>
        ) : null}

        {springNeap && springNeap.classification !== "unknown" ? (
          <div className="mini-line mini-line-tide">
            <Waves size={16} />
            <span>
              <strong>المدّ والجزر:</strong> {springNeap.folk_label_ar} (
              {springNeapLabel(springNeap.classification)}) · المدى{" "}
              {springNeap.range_target_day_m != null ? (
                <bdi>{springNeap.range_target_day_m.toFixed(2)} م</bdi>
              ) : (
                "غير متاح"
              )}
              {springNeap.gabes_zone ? <small> — منطقة خليج قابس</small> : null}
            </span>
          </div>
        ) : null}

        {speciesAxes ? (
          <div className="mini-line mini-line-species">
            <Fish size={16} />
            <span>
              <strong>الأنواع:</strong> {speciesAxes.label_ar}
              {speciesMatchesSummary ? <small> — الأفضل توفراً: {speciesMatchesSummary}</small> : null}
              {speciesSummary ? <small> — {speciesSummary}</small> : <small> — محاور أولية غير معايرة</small>}
              {springNeap ? <small> · المدّ {springNeap.folk_label_ar}</small> : null}
              {speciesAxes.sea_state_ar ? <small> · {speciesAxes.sea_state_ar}</small> : null}
            </span>
          </div>
        ) : null}

        {!isGo && avoidRange ? (
          <div className="mini-line mini-line-avoid">
            <TriangleAlert size={16} />
            <span>
              <strong>فترات ممنوعة:</strong> <bdi>{avoidRange}</bdi>
            </span>
          </div>
        ) : null}

        {result.trip_ruin_factors && result.trip_ruin_factors.length > 0 ? (
          <div className="mini-line mini-line-trip-ruin">
            <TriangleAlert size={16} />
            <span>
              <strong>مفسدات الخرجة:</strong>{" "}
              {result.trip_ruin_factors
                .filter((f) => f.level === "high" || f.is_force_majeure)
                .map((f) => f.label_ar)
                .join(" · ") || "لا عامل مؤكد"}
            </span>
          </div>
        ) : null}

        <div className="mini-line mini-line-note">
          <Info size={15} />
          <span>
            هذا ملخص إرشادي. التفاصيل الكاملة والتقسيمات وكل العوامل في التقرير الكامل تحت.
          </span>
        </div>
      </div>
    </section>
  );
}
