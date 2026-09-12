"use client";

import { useMemo, useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Anchor,
  ArrowDownLeft,
  ArrowUp,
  ArrowUpRight,
  CalendarClock,
  Check,
  ChevronLeft,
  CircleGauge,
  Clock3,
  CloudRain,
  Compass,
  Database,
  Droplets,
  FileText,
  Gauge,
  Info,
  Link2,
  MapPin,
  Navigation,
  Printer,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sparkles,
  Thermometer,
  TriangleAlert,
  Waves,
  Wind,
} from "lucide-react";
import { ScoreRing } from "@/components/ScoreRing";
import { SpotReport } from "@/components/SpotReport";
import { TideChart } from "@/components/TideChart";
import { MiniReport } from "@/components/MiniReport";
import { SessionFeedback } from "@/components/SessionFeedback";
import {
  decisionLabels,
  decisionShortLabels,
  factorBasisLabels,
  fieldFeasibilityLabels,
  formatDate,
  formatGeneratedAt,
  formatHour,
  formatWindowRange,
  numberOrDash,
  potentialLabels,
  ruleNatureLabels,
  tideLabel,
  waveIncidenceLabel,
  windRelationLabel,
} from "@/lib/format";
import type {
  DecisionLevel,
  DecisionResponse,
  Factor,
  ForecastDecisionRequest,
  HourDecision,
} from "@/lib/types";

interface DecisionResultProps {
  result: DecisionResponse;
  request: ForecastDecisionRequest;
  stale?: boolean;
}

type Tone = "mint" | "amber" | "red" | "muted";

const toneByDecision: Record<DecisionLevel, Tone> = {
  go: "mint",
  caution: "amber",
  no_go: "red",
  unknown: "muted",
};

const fieldTone = {
  favorable: "good",
  workable: "watch",
  difficult: "hard",
  unknown: "unknown",
} as const;

const observationStatusCopy = {
  unavailable: { label: "الرصد غير متاح", tone: "muted" },
  not_applicable: { label: "الرصد الحالي لا ينطبق على الموعد", tone: "muted" },
  stale: { label: "الرصد قديم", tone: "amber" },
  distant: { label: "المحطة بعيدة", tone: "amber" },
  limited: { label: "مقارنة محدودة بالمسافة", tone: "amber" },
  consistent: { label: "لا اختلاف كبير مع النموذج", tone: "mint" },
  divergent: { label: "اختلاف مهم عن النموذج", tone: "red" },
} as const;

const decisionCopy: Record<DecisionLevel, { eyebrow: string; title: string; text: string }> = {
  go: {
    eyebrow: "النافذة اجتازت الحدود الآلية المتاحة",
    title: "اذهب",
    text: "فحوصات المحرك والتنفيذ عدّت؛ هذا ليس شهادة سلامة ميدانية، وضعف فرصة الصيد وحده لا يلغي نافذة قابلة للتنفيذ.",
  },
  caution: {
    eyebrow: "يلزم انتباه",
    title: "امشِ بحذر",
    text: "فما عوامل تستحق الحذر. راقب البحر ميدانياً والتزم بالنافذة الأقل خطراً.",
  },
  no_go: {
    eyebrow: "الأولوية للسلامة واليقين التنفيذي",
    title: "لا تذهب",
    text: "المحرك المحافظ وجد مانعاً في السلامة أو البيانات الحرجة أو قابلية التنفيذ.",
  },
  unknown: {
    eyebrow: "التقييم غير مكتمل",
    title: "المعطيات ناقصة",
    text: "المصادر المتاحة ما تكفيش لقرار مسؤول. عاود لاحقاً أو استعمل مصادر محلية إضافية.",
  },
};

const primaryReasonCopy = {
  safe_window: "توجد نافذة اجتازت الحدود الآلية وقابلة للتنفيذ مبدئياً؛ ليست شهادة سلامة ميدانية، ومؤشر الفرصة النسبي ليس احتمال نجاح.",
  safety_hazard: "سبب لا تذهب: خطر سلامة أو عتبة حذر محافظة داخل أفضل نافذة متاحة.",
  field_infeasible: "سبب لا تذهب: صعوبة تثبيت الخط مرتفعة داخل أفضل نافذة؛ مؤشرا الصوفة والعكارة تنبيهان غير مانعين بلا رصد.",
  critical_data_missing: "سبب لا تذهب: بيانات حرجة ناقصة؛ لا يحوّل المحرك Unknown إلى بحر هادئ.",
  conservative_uncertainty: "سبب لا تذهب: مستوى عدم اليقين المؤثر تجاوز ما تسمح به السياسة المحافظة.",
  fouling_confirmed: "سبب لا تذهب: صوفة/عوالق مؤكدة ببلاغ ميداني حديث أو رمية اختبار؛ لا نافذة قابلة للتنفيذ رغم سلامة التوقع.",
  official_warning: "سبب لا تذهب: تحذير رسمي ساري (نشرة INM أو سلطة مختصة) يلغي الرحلة تلقائياً فوق كل العتبات المحلية.",
  trip_ruin_confirmed: "سبب لا تذهب: عامل مُفسِد مؤكد (قناديل/حطام/تعكر كثيف) يجعل الخرجة غير مجدية.",
} as const;

function uniqueFactors(hours: HourDecision[], predicate: (factor: Factor) => boolean): Factor[] {
  const factors = new Map<string, Factor>();
  for (const hour of hours) {
    for (const factor of hour.factors) {
      if (predicate(factor) && !factors.has(`${factor.code}:${factor.explanation_ar}`)) {
        factors.set(`${factor.code}:${factor.explanation_ar}`, factor);
      }
    }
  }
  return [...factors.values()];
}

function HourCard({ hour, selected, onSelect }: { hour: HourDecision; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`hour-card hour-${hour.safety} ${selected ? "selected" : ""}`}
      onClick={onSelect}
    >
      <div className="hour-card-top">
        <strong>{formatHour(hour.time)}</strong>
        {hour.derived.is_twilight ? <span className="best-tag"><Sparkles size={12} /> شفق</span> : hour.safety === "no_go" ? <ShieldAlert size={15} /> : null}
      </div>
      <div className="hour-score"><bdi>{hour.opportunity_score}</bdi><small>/100</small></div>
      <div className="hour-mini-metrics">
        <span><Wind size={14} /><bdi>{numberOrDash(hour.forecast.wind_speed_kmh)} كم/س</bdi></span>
        <span><Waves size={14} /><bdi>{numberOrDash(hour.forecast.wave_height_m, 1)} م</bdi></span>
      </div>
      <div className={`hour-verdict verdict-${hour.safety}`}>{decisionShortLabels[hour.safety]}</div>
    </button>
  );
}

function Metric({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note?: string }) {
  return (
    <article className="condition-card">
      <span className="condition-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </article>
  );
}

function formatObservationTime(value: string): string {
  return new Intl.DateTimeFormat("ar-TN", {
    timeZone: "Africa/Tunis",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function FactorItem({ factor }: { factor: Factor }) {
  const Icon = factor.severity === "critical" ? AlertOctagon : factor.impact === "positive" ? Check : Info;
  return (
    <li className={`factor-row factor-${factor.impact} severity-${factor.severity}`}>
      <span className="factor-row-icon"><Icon size={16} /></span>
      <div>
        <div className="factor-row-head">
          <strong>{factor.label_ar}</strong>
          {factor.value && <span>{factor.value}</span>}
          {factor.score_delta !== 0 && <b className={factor.score_delta > 0 ? "delta-positive" : "delta-negative"}>{factor.score_delta > 0 ? "+" : ""}{factor.score_delta}</b>}
        </div>
        <p>{factor.explanation_ar}</p>
        <div className="factor-provenance"><span>{factorBasisLabels[factor.basis]}</span><span>{ruleNatureLabels[factor.rule_nature]}</span>{factor.is_direct_observation ? null : <span>ليس رصداً مباشراً</span>}</div>
      </div>
    </li>
  );
}

export function DecisionResult({ result, request, stale = false }: DecisionResultProps) {
  const { location, target_date: targetDate } = request;
  const leadWindow = result.recommended_windows[0];
  const initialTime = leadWindow?.start ?? result.hourly[0]?.time ?? "";
  const [selectedTime, setSelectedTime] = useState(initialTime);
  const [shareState, setShareState] = useState<"idle" | "done" | "error">("idle");
  const [realityMismatch, setRealityMismatch] = useState(false);
  const [reportVisible, setReportVisible] = useState(true);
  const selected = useMemo(
    () => result.hourly.find((hour) => hour.time === selectedTime) ?? result.hourly[0],
    [result.hourly, selectedTime],
  );
  const criticalFactors = useMemo(
    () => uniqueFactors(result.hourly, (factor) => factor.severity === "critical").slice(0, 5),
    [result.hourly],
  );
  const cautionFactors = useMemo(
    () => uniqueFactors(result.hourly, (factor) => factor.severity === "caution").slice(0, 5),
    [result.hourly],
  );
  const positiveFactors = useMemo(
    () => uniqueFactors(result.hourly, (factor) => factor.impact === "positive").slice(0, 5),
    [result.hourly],
  );
  const tone = toneByDecision[result.decision];
  const copy = {
    ...decisionCopy[result.decision],
    text: primaryReasonCopy[result.decision_reason_code],
  };
  const field = result.field_feasibility;
  const safetyAxis = leadWindow?.safety ?? result.decision;
  const fieldContext = result.hourly.find((hour) => hour.time === leadWindow?.start) ?? result.hourly[0];
  const observation = result.current_weather_observation;
  const waterContext = result.coastal_water_context;
  const observationStatus = observationStatusCopy[result.observation_comparison.status];

  const share = async () => {
    const text = [
      `Peche TN — ${location.name ?? "بقعة مختارة"}`,
      decisionLabels[result.decision],
      result.summary_ar,
      leadWindow ? `أفضل نافذة: ${formatWindowRange(leadWindow.start, leadWindow.end)}` : "",
      `سبب القرار: ${primaryReasonCopy[result.decision_reason_code]}`,
      `بوابة المحرك: ${decisionShortLabels[safetyAxis]} · قابلية التنفيذ: ${field.score}/100 (${fieldFeasibilityLabels[field.status]})`,
      `مؤشر الفرصة النسبي: ${result.opportunity_score}/100 · ثقة المدخلات: ${result.confidence.score}/100 (ليست دقة ميدانية)`,
      `احتمال الصوفة ${potentialLabels[field.fouling_transport_potential]} (${field.fouling_evidence_count} عائلات قرائن) · احتمال العكارة ${potentialLabels[field.turbidity_potential]} (${field.turbidity_evidence_count} عائلات قرائن)؛ ليست أرصاداً أو مصادر مستقلة ولا قياس NTU. دعم قرار فقط.`,
    ].filter(Boolean).join("\n");
    try {
      if (navigator.share) {
        await navigator.share({ title: "قرار Peche TN", text });
      } else {
        await navigator.clipboard.writeText(text);
      }
      setShareState("done");
      window.setTimeout(() => setShareState("idle"), 2500);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setShareState("error");
      window.setTimeout(() => setShareState("idle"), 2500);
    }
  };

  const closeReport = () => {
    setReportVisible(false);
    window.setTimeout(() => document.getElementById("spot-report-trigger")?.focus(), 0);
  };

  const toggleReport = () => {
    if (reportVisible) return closeReport();
    setReportVisible(true);
    window.setTimeout(() => {
      document.getElementById("spot-report")?.scrollIntoView({ behavior: "smooth", block: "start" });
      document.getElementById("spot-report-title")?.focus({ preventScroll: true });
    }, 80);
  };

  return (
    <section className={`results-shell result-${tone}`} id="decision" aria-labelledby="decision-title" aria-live="polite">
      {stale && (
        <div className="stale-banner" role="status">
          <RefreshCw size={17} />
          <span><strong>هذه النتيجة تخص الاختيارات السابقة.</strong> عندك تغييرات مازالت ما تحلّلتش.</span>
          <a href="#planner">حدّث القرار <ArrowUp size={15} /></a>
        </div>
      )}

      <div className="result-context-bar">
        <div><MapPin size={16} /><strong>{location.name ?? "بقعة مختارة"}</strong><span>{formatDate(targetDate)}</span></div>
        <span className="generated-label"><Database size={14} /> حُدّث {formatGeneratedAt(result.generated_at)}</span>
      </div>

      <header className={`decision-hero decision-${result.decision}`}>
        <div className="decision-copy">
          <div className={`decision-status status-${tone}`}><span />{copy.eyebrow}</div>
          <h2 id="decision-title">{copy.title}</h2>
          <p>{result.summary_ar || copy.text}</p>
          {leadWindow ? (
            <div className="lead-window">
              <span className="lead-window-icon"><CalendarClock size={22} /></span>
              <span><small>أفضل نافذة مقترحة</small><strong><bdi>{formatWindowRange(leadWindow.start, leadWindow.end)}</bdi></strong></span>
              <span className={`window-safety safety-${leadWindow.safety}`}>{decisionShortLabels[leadWindow.safety]}</span>
            </div>
          ) : (
            <div className="no-window"><TriangleAlert size={19} /><span><strong>ما فماش نافذة اجتازت حدود المحرك.</strong> راجع أسباب القرار قبل التخطيط.</span></div>
          )}
        </div>

        <div className="decision-scores" aria-label="ملخص النقاط">
          <ScoreRing value={result.opportunity_score} label="مؤشر الفرصة النسبي" tone={tone} />
          <div className="confidence-card">
            <span><Shield size={19} /> ثقة المدخلات</span>
            <strong><bdi>{result.confidence.score}%</bdi></strong>
            <div className="confidence-track"><i style={{ width: `${result.confidence.score}%` }} /></div>
            <small>{result.confidence.band === "high" ? "اكتمال مرتفع" : result.confidence.band === "medium" ? "اكتمال متوسط" : "اكتمال منخفض"} · ليست دقة ميدانية</small>
          </div>
        </div>
        <div className="not-probability"><Info size={15} /> مؤشر الفرصة النسبي ترتيب مقارن، وليس احتمال مصيد.</div>
      </header>

      <MiniReport result={result} />

      <div className="result-actions" aria-live="polite">
        <button id="spot-report-trigger" className="report-trigger" type="button" aria-expanded={reportVisible} aria-controls="spot-report" onClick={toggleReport}><FileText size={17} />{reportVisible ? "أخفِ التقرير" : "التقرير الكامل + Gemini"}</button>
        <button type="button" onClick={share}><Link2 size={17} />{shareState === "done" ? "تم النسخ" : shareState === "error" ? "تعذّر النسخ" : "شارك القرار"}</button>
        <button type="button" onClick={() => window.print()}><Printer size={17} />اطبع</button>
        <button
          className={realityMismatch ? "reality-trigger active" : "reality-trigger"}
          type="button"
          aria-expanded={realityMismatch}
          aria-controls="reality-warning"
          onClick={() => setRealityMismatch((visible) => !visible)}
        >
          <AlertTriangle size={17} />الواقع مختلف؟
        </button>
        <a href="#planner"><RefreshCw size={17} />غيّر التفاصيل</a>
      </div>

      <SessionFeedback />

      {realityMismatch && (
        <div className="reality-warning" id="reality-warning" role="alert">
          <span className="reality-warning-icon"><ShieldAlert size={23} /></span>
          <div>
            <strong>اعتمد الواقع ووقّف الحصة وقت الشك.</strong>
            <p>إذا الموج أو الريح أقوى، الوصول أخطر، أو فما برق وتحذير رسمي: ما تعتمدش نتيجة التطبيق. وقرار «ما تمشيش» ما يتخففش بمجرد أن البحر يبدو أهدأ للحظة.</p>
          </div>
          <a href="#field-checklist">راجع قائمة السلامة <ChevronLeft size={16} /></a>
        </div>
      )}

      {reportVisible && <SpotReport result={result} request={request} stale={stale} onClose={closeReport} />}

      <section className={`observation-panel observation-${observationStatus.tone}`} data-testid="actual-observation" aria-labelledby="actual-observation-title">
        <div className="observation-heading">
          <div>
            <span className="observation-icon"><Database size={21} /></span>
            <span>
              <small>طبقة الرصد الحقيقي المنفصلة</small>
              <h3 id="actual-observation-title">رصد جوي فعلي الآن</h3>
            </span>
          </div>
          <span className={`observation-status status-${observationStatus.tone}`}>{observationStatus.label}</span>
        </div>
        {observation ? (
          <>
            <div className="observation-identity">
              <div>
                <strong>{observation.station_name}</strong>
                <span><bdi>{observation.station_id}</bdi> · {observation.distance_to_spot_km.toFixed(1)} كم عن البقعة</span>
              </div>
              <div>
                <strong>{formatObservationTime(observation.observed_at)}</strong>
                <span>عمر القياس {result.observation_comparison.observation_age_minutes === null ? "—" : `${Math.round(result.observation_comparison.observation_age_minutes)} دقيقة`}</span>
              </div>
            </div>
            <div className="observation-metrics">
              <span><Wind size={16} /><small>الريح في المحطة</small><strong>{numberOrDash(observation.wind_speed_kmh)} كم/س</strong></span>
              <span><Wind size={16} /><small>الهبة في المحطة</small><strong>{numberOrDash(observation.wind_gust_kmh)} كم/س</strong></span>
              <span><Compass size={16} /><small>اتجاه الريح</small><strong>{observation.wind_direction_deg === null ? "—" : `${observation.wind_direction_deg.toFixed(0)}°`}</strong></span>
              <span><Thermometer size={16} /><small>حرارة الهواء</small><strong>{observation.air_temperature_c === null ? "—" : `${observation.air_temperature_c.toFixed(1)}°`}</strong></span>
              <span><Gauge size={16} /><small>{observation.pressure_kind === "sea_level_pressure" ? "ضغط سطح البحر" : "QNH المحطة"}</small><strong>{observation.pressure_hpa === null ? "—" : `${observation.pressure_hpa.toFixed(0)} hPa`}</strong></span>
              <span><Navigation size={16} /><small>الرؤية الجوية</small><strong>{observation.visibility_m === null ? "—" : `${observation.visibility_is_lower_bound ? "≥ " : ""}${(observation.visibility_m / 1000).toFixed(1)} كم`}</strong></span>
            </div>
            <div className="observation-comparison">
              <div>
                <strong>مقارنة المحطة بالنموذج عند نفس الوقت</strong>
                <span>فرق الريح {numberOrDash(result.observation_comparison.wind_speed_difference_kmh, 1)} كم/س · الاتجاه {numberOrDash(result.observation_comparison.wind_direction_difference_deg)}° · الحرارة {numberOrDash(result.observation_comparison.temperature_difference_c, 1)}°</span>
              </div>
              <p>{result.observation_comparison.reasons_ar.join(" ")}</p>
            </div>
            <details className="raw-observation">
              <summary>السطر الخام METAR <ChevronLeft size={15} /></summary>
              <code dir="ltr">{observation.raw_report}</code>
            </details>
            <div className="observation-boundary" role="note"><Info size={16} /><span><strong>قياس حقيقي، لكن ليس داخل الـSpot:</strong> هذه محطة مطار والمسافة ظاهرة؛ لا يقيس هذا الرصد الموج أو التيار أو حرارة البحر أو الصوفة.</span></div>
          </>
        ) : (
          <div className="observation-empty">
            <Info size={19} />
            <div><strong>لم يصل رصد محطة صالح لهذا الموعد.</strong><p>{result.observation_comparison.reasons_ar.join(" ")}</p></div>
          </div>
        )}
      </section>

      {waterContext && (
        <section className={`observation-panel satellite-panel satellite-${waterContext.availability}`} data-testid="coastal-water-context" aria-labelledby="coastal-water-title">
          <div className="observation-heading">
            <div>
              <span className="observation-icon"><Droplets size={21} /></span>
              <span>
                <small>سياق استشعار عن بعد منفصل</small>
                <h3 id="coastal-water-title">Sentinel-2 لجودة الماء الساحلي</h3>
              </span>
            </div>
            <span className={`observation-status status-${waterContext.availability === "available" ? "mint" : "muted"}`}>
              {waterContext.availability === "available" ? "بكسل صالح" : "Unknown"}
            </span>
          </div>
          {waterContext.availability === "available" ? (
            <>
              <div className="observation-identity satellite-identity">
                <div>
                  <strong>Copernicus Marine · Sentinel-2</strong>
                  <span>دقة المنتج {waterContext.spatial_resolution_m} م · بكسل على بعد {waterContext.pixel_distance_from_spot_m === null ? "Unknown" : `${Math.round(waterContext.pixel_distance_from_spot_m)} م`} من البقعة</span>
                </div>
                <div>
                  <strong>{waterContext.valid_time ? new Intl.DateTimeFormat("ar-TN", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(waterContext.valid_time)) : "Unknown"}</strong>
                  <span>عمر طبقة المنتج {waterContext.age_hours === null ? "Unknown" : `${Math.round(waterContext.age_hours)} ساعة`}</span>
                </div>
              </div>
              <div className="observation-metrics satellite-metrics">
                <span><Droplets size={16} /><small>العكارة TUR</small><strong>{waterContext.turbidity_fnu === null ? "Unknown" : `${waterContext.turbidity_fnu.toFixed(2)} ${waterContext.turbidity_unit}`}</strong></span>
                <span><Waves size={16} /><small>المادة العالقة SPM</small><strong>{waterContext.suspended_particulate_matter_g_m3 === null ? "Unknown" : `${waterContext.suspended_particulate_matter_g_m3.toFixed(2)} ${waterContext.suspended_particulate_matter_unit}`}</strong></span>
                <span><Sparkles size={16} /><small>كلوروفيل-a</small><strong>{waterContext.chlorophyll_a_mg_m3 === null ? "Unknown" : `${waterContext.chlorophyll_a_mg_m3.toFixed(2)} ${waterContext.chlorophyll_a_unit}`}</strong></span>
                <span><Thermometer size={16} /><small>حرارة السطح SST</small><strong>{waterContext.sea_surface_temperature_c === null ? "Unknown" : `${waterContext.sea_surface_temperature_c.toFixed(1)} °م`}</strong></span>
                <span><Navigation size={16} /><small>بعد مركز البكسل عن العينة</small><strong>{waterContext.pixel_distance_from_sample_m === null ? "Unknown" : `${Math.round(waterContext.pixel_distance_from_sample_m)} م`}</strong></span>
              </div>
              <p className="satellite-reason">{waterContext.reason_ar}</p>
            </>
          ) : (
            <div className="observation-empty">
              <Info size={19} />
              <div><strong>القيمة Unknown وليست صفراً.</strong><p>{waterContext.reason_ar}</p></div>
            </div>
          )}
          <div className="observation-boundary satellite-boundary" role="note"><Info size={16} /><span><strong>سياق فقط:</strong> العينة ثابتة على بعد 1 كم باتجاه البحر؛ ليست قياساً ميدانياً ولا توقعاً للموعد. FNU لا تتحول إلى NTU، ولا تغيّر TUR/SPM/CHL/SST القرار أو السلامة أو التنفيذ أو الفرصة أو الثقة؛ CHL لا تشخّص ازدهاراً ضاراً أو نشاط السمك. ازدهار عضوي كثيف (CHL ≥ 10) مع نقل بحري مرتفع يرفع سلم أدلة الصوفة إلى الإثبات القاهر.</span></div>
        </section>
      )}

      <section className="decision-axes-panel" aria-labelledby="decision-axes-title">
        <div className="axes-heading">
          <div>
            <span>تفكيك التوصية</span>
            <h3 id="decision-axes-title">أربعة محاور مستقلة، قرار واحد</h3>
          </div>
          <small>السلامة لا يعوّضها ارتفاع مؤشر الفرصة النسبي</small>
        </div>
        <div className="decision-axes-grid">
          <article className={`axis-card axis-${safetyAxis}`}>
            <span><Shield size={18} /> 01 · السلامة</span>
            <strong>{decisionShortLabels[safetyAxis]}</strong>
            <small>بوابة الريح والموج والرعد والرؤية</small>
          </article>
          <article className={`axis-card field-${fieldTone[field.status]}`}>
            <span><Anchor size={18} /> 02 · قابلية التنفيذ</span>
            <strong><bdi>{field.score}/100</bdi></strong>
            <small>{fieldFeasibilityLabels[field.status]}</small>
          </article>
          <article className="axis-card axis-opportunity">
            <span><Sparkles size={18} /> 03 · الفرصة النسبية</span>
            <strong><bdi>{result.opportunity_score}/100</bdi></strong>
            <small>ترتيب نسبي، وليس نسبة نجاح</small>
          </article>
          <article className="axis-card axis-confidence">
            <span><Database size={18} /> 04 · ثقة المدخلات</span>
            <strong><bdi>{result.confidence.score}/100</bdi></strong>
            <small>اكتمال واتساق وأفق؛ ليست دقة ميدانية</small>
          </article>
        </div>
      </section>

      <section className={`field-feasibility-panel field-${fieldTone[field.status]}`} id="field-feasibility" data-testid="field-feasibility" aria-labelledby="field-feasibility-title">
        <div className="field-panel-head">
          <div className="field-panel-title">
            <span className="field-panel-icon"><Anchor size={22} /></span>
            <span>
              <small>فحص عملي قبل حمل العتاد</small>
              <h3 id="field-feasibility-title">هل يمكن تنفيذ الحصة ميدانياً؟</h3>
            </span>
          </div>
          <div className="field-panel-score">
            <strong><bdi>{field.score}</bdi><small>/100</small></strong>
            <span>{fieldFeasibilityLabels[field.status]}</span>
          </div>
        </div>

        <div className="field-signal-grid">
          <article>
            <span><Anchor size={17} /> صعوبة تثبيت الخط</span>
            <strong className={`potential-${field.holding_difficulty}`}>{potentialLabels[field.holding_difficulty]}</strong>
            <small>تجميع محافظ للموج الجانبي والتيار النموذجي والريح؛ لا يختار وزن الرصاص بدلاً منك.</small>
          </article>
          <article>
            <span><Wind size={17} /> احتمال نقل الصوفة أو الحطام</span>
            <strong className={`potential-${field.fouling_transport_potential}`}>{potentialLabels[field.fouling_transport_potential]}</strong>
            <small>{field.fouling_evidence_count} عائلات قرائن تشغيلية مختلفة خلال 48 ساعة؛ ليست أرصاداً أو مصادر مستقلة ولا تثبت وجود المادة.</small>
          </article>
          <article>
            <span><Droplets size={17} /> احتمال العكارة</span>
            <strong className={`potential-${field.turbidity_potential}`}>{potentialLabels[field.turbidity_potential]}</strong>
            <small>{field.turbidity_evidence_count} عائلات قرائن تشغيلية مختلفة؛ ليست قياسات ماء مستقلة ولا توجد قيمة NTU.</small>
          </article>
          <article>
            <span><Waves size={17} /> تيار ساحبي محتمل</span>
            <strong className={`potential-${field.rip_current_potential}`}>{potentialLabels[field.rip_current_potential]}</strong>
            <small>فحص موج واتجاه وتعرّض البقعة؛ لا يرى الحواجز الرملية أو قناة الكسرة.</small>
          </article>
        </div>

        {fieldContext && (
          <div className="field-context-strip" aria-label="سياق ما قبل الحصة">
            <span className="field-context-label">نشاط سابق لبداية النافذة · {formatHour(fieldContext.time)}</span>
            <span><CloudRain size={15} /> مطر 48س <strong>{numberOrDash(fieldContext.derived.rain_48h_mm, 1)} مم</strong><small>تغطية {fieldContext.derived.rain_data_hours_48h}/48</small></span>
            <span><Wind size={15} /> دفع ريح شاطئي <strong>{numberOrDash(fieldContext.derived.onshore_wind_impulse_48h_kmh_h, 1)}</strong><small>كم/س·س · {fieldContext.derived.wind_data_hours_48h}/48</small></span>
            <span><Waves size={15} /> طاقة موج تراكمية <strong>{numberOrDash(fieldContext.derived.wave_energy_integral_48h, 1)}</strong><small>Hs²T·h · {fieldContext.derived.wave_energy_data_hours_48h}/48</small></span>
            <span><Compass size={15} /> تاريخ متاح <strong>{fieldContext.derived.history_hours_48h}/48 س</strong><small>{fieldContext.derived.history_hours_72h}/72 س</small></span>
          </div>
        )}

        <div className="field-evidence-row">
          <div className="field-confidence">
            <span><Database size={16} /> ثقة هذا الفحص <bdi>{field.confidence}/100</bdi></span>
            <div><i style={{ width: `${field.confidence}%` }} /></div>
            <small>السقف 50/100 لغياب رصد مباشر داخل منطقة الكسرة.</small>
          </div>
          <div className="proxy-warning" role="note">
            <Info size={18} />
            <p><strong>مؤشرات آلية منخفضة الثقة، موش رصد.</strong> العلامة «منخفض*» لا تنفي الخطر. الواقع يعلو على النموذج دائماً.</p>
          </div>
        </div>

        <div className="field-panel-foot">
          <ul>{field.reasons_ar.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
          <div className="field-hard-stop">
            <AlertTriangle size={18} />
            <span><strong>اختبار حاسم في المكان:</strong> إذا جرّ الرصاص، علقت الصوفة في الرمية الاختبارية، أو رأيت ممراً من رغوة/حطام يتحرك إلى عرض البحر—غيّر الموضع أو أجّل الحصة.</span>
          </div>
        </div>
      </section>

      {(criticalFactors.length > 0 || cautionFactors.length > 0 || positiveFactors.length > 0) && (
        <section className="explanation-grid" aria-labelledby="explanation-title">
          <div className="result-section-head full-width">
            <div><span className="section-icon"><Info size={18} /></span><span><h3 id="explanation-title">علاش هذا القرار؟</h3><p>الأسباب مرتبة باش تبدأ بالأهم للسلامة.</p></span></div>
          </div>
          {criticalFactors.length > 0 && (
            <article className="reason-panel danger-panel">
              <div className="reason-panel-title"><ShieldAlert size={20} /><strong>تنبيهات السلامة</strong><span>{criticalFactors.length}</span></div>
              <ul>{criticalFactors.map((factor) => <li key={`${factor.code}-${factor.explanation_ar}`}><AlertTriangle size={16} /><span>{factor.explanation_ar}</span></li>)}</ul>
            </article>
          )}
          {cautionFactors.length > 0 && (
            <article className="reason-panel risk-panel">
              <div className="reason-panel-title"><TriangleAlert size={20} /><strong>نقاط تستحق الحذر</strong><span>{cautionFactors.length}</span></div>
              <ul>{cautionFactors.map((factor) => <li key={`${factor.code}-${factor.explanation_ar}`}><span className="severity-dot severity-caution" /><span><strong>{factor.label_ar}</strong>{factor.explanation_ar}</span></li>)}</ul>
            </article>
          )}
          {positiveFactors.length > 0 && (
            <article className="reason-panel reason-positive">
              <div className="reason-panel-title"><CircleGauge size={20} /><strong>مؤشرات إيجابية</strong><span>{positiveFactors.length}</span></div>
              <ul>{positiveFactors.map((factor) => <li key={`${factor.code}-${factor.explanation_ar}`}><Check size={16} /><span>{factor.explanation_ar}</span></li>)}</ul>
            </article>
          )}
        </section>
      )}

      <section className="timeline-section" aria-labelledby="timeline-title">
        <div className="result-section-head">
          <div><span className="section-icon"><Clock3 size={18} /></span><span><h3 id="timeline-title">القرار ساعة بساعة</h3><p>اختار أي ساعة باش تشوف قيم التوقع ومشتقاته وأسبابه.</p></span></div>
          <div className="timeline-legend"><span className="safe">مناسب</span><span className="caution">حذر</span><span className="blocked">ممنوع</span></div>
        </div>
        <div className="hour-strip" aria-label="توقعات الساعات">
          {result.hourly.map((hour) => <HourCard key={hour.time} hour={hour} selected={selected?.time === hour.time} onSelect={() => setSelectedTime(hour.time)} />)}
        </div>
      </section>

      <section className="windows-section" aria-labelledby="windows-title">
        <div className="result-section-head">
          <div><span className="section-icon"><CalendarClock size={18} /></span><span><h3 id="windows-title">نوافذ الحصة</h3><p>فترات متواصلة اجتازت فحص المحرك.</p></span></div>
        </div>
        {result.recommended_windows.length ? (
          <div className="windows-grid">
            {result.recommended_windows.map((window, index) => (
              <article className={index === 0 ? "window-card lead" : "window-card"} key={`${window.start}-${window.end}`}>
                <div className="window-rank">{index === 0 ? <><Sparkles size={14} /> الأنسب</> : `خيار ${index + 1}`}</div>
                <strong><bdi>{formatWindowRange(window.start, window.end)}</bdi></strong>
                <div><span><Anchor size={14} /> تنفيذ {window.field_score}/100</span><span><CircleGauge size={14} /> فرصة نسبية {window.opportunity_score}/100</span><span><Shield size={14} /> ثقة مدخلات {window.confidence_score}/100</span></div>
                <p>{window.headline_ar}</p>
                <div className="window-factors">{window.key_factors_ar.slice(0, 3).map((factor) => <span key={factor}>{factor}</span>)}</div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-result"><ShieldAlert size={25} /><span><strong>لا توجد نافذة موصى بها.</strong> ما لقيناش مدة متواصلة اجتازت حدود المحرك حسب الإعدادات الحالية.</span><a href="#planner">جرّب يوماً أو بقعة أخرى <ChevronLeft size={16} /></a></div>
        )}
        {result.avoid_windows.length > 0 && (
          <details className="avoid-details">
            <summary><span><ShieldAlert size={17} /> فترات لازم تتجنبها ({result.avoid_windows.length})</span><ChevronLeft size={17} /></summary>
            <div className="avoid-list">{result.avoid_windows.map((window) => <div key={window.start}><AlertOctagon size={16} /><span><strong>{formatWindowRange(window.start, window.end)}</strong>{window.key_factors_ar.join(" · ")}</span></div>)}</div>
          </details>
        )}
      </section>

      {selected && (
        <section className="conditions-section" aria-labelledby="conditions-title">
          <div className="result-section-head">
            <div><span className="section-icon"><Compass size={18} /></span><span><h3 id="conditions-title">صورة التوقع النموذجي · {formatHour(selected.time)}</h3><p>قيم API المتوقعة ومشتقاتها—وليست محطة رصد داخل البقعة.</p></span></div>
            <span className={`selected-verdict verdict-${selected.safety}`}>{decisionShortLabels[selected.safety]} · فرصة نسبية {selected.opportunity_score}/100 · تنفيذ {selected.field_feasibility.score}/100</span>
          </div>
          <div className="conditions-grid">
            <Metric icon={<Wind size={21} />} label="الريح" value={`${numberOrDash(selected.forecast.wind_speed_kmh)} كم/س`} note={`هبات ${numberOrDash(selected.forecast.wind_gust_kmh)} كم/س`} />
            <Metric icon={<Waves size={21} />} label="الموج الكلي" value={`${numberOrDash(selected.forecast.wave_height_m, 2)} م`} note={`فترة ${numberOrDash(selected.forecast.wave_period_s, 1)} ث`} />
            <Metric icon={<Wind size={21} />} label="موج الريح" value={`${numberOrDash(selected.forecast.wind_wave_height_m, 2)} م`} note={`فترة ${numberOrDash(selected.forecast.wind_wave_period_s, 1)} ث${selected.forecast.wind_wave_direction_deg === null ? "" : ` · ${selected.forecast.wind_wave_direction_deg.toFixed(0)}°`}`} />
            <Metric icon={<Waves size={21} />} label="السويل" value={`${numberOrDash(selected.forecast.swell_height_m, 2)} م`} note={`فترة ${numberOrDash(selected.forecast.swell_period_s, 1)} ث${selected.forecast.swell_direction_deg === null ? "" : ` · ${selected.forecast.swell_direction_deg.toFixed(0)}°`}`} />
            <Metric
              icon={<Compass size={21} />}
              label="الريح مقابل واجهة البحر"
              value={windRelationLabel(selected.derived.wind_relation)}
              note={selected.forecast.wind_direction_deg === null
                ? "اتجاه القدوم ناقص"
                : `قادمة من ${selected.forecast.wind_direction_deg.toFixed(0)}° · فرق ${numberOrDash(selected.derived.wind_angle_deg)}° · ${selected.derived.wind_shoreward_component_kmh === null ? "المركبة ناقصة" : selected.derived.wind_shoreward_component_kmh >= 0 ? `نحو الشاطئ ${selected.derived.wind_shoreward_component_kmh.toFixed(1)} كم/س` : `نحو البحر ${Math.abs(selected.derived.wind_shoreward_component_kmh).toFixed(1)} كم/س`}`}
            />
            <Metric
              icon={<Waves size={21} />}
              label="الموج مقابل واجهة البحر"
              value={waveIncidenceLabel(selected.derived.wave_incidence)}
              note={selected.forecast.wave_direction_deg === null
                ? "اتجاه القدوم ناقص"
                : `قادم من ${selected.forecast.wave_direction_deg.toFixed(0)}° · فرق ${numberOrDash(selected.derived.wave_angle_deg)}° · محاذاة عمودية ${selected.derived.wave_shoreward_alignment === null ? "—" : `${Math.round(selected.derived.wave_shoreward_alignment * 100)}%`}`}
            />
            <Metric icon={<Navigation size={21} />} label="التيار النموذجي" value={`${numberOrDash(selected.forecast.ocean_current_velocity_kmh, 2)} كم/س`} note="موش تيار الكسرة" />
            <Metric icon={<Droplets size={21} />} label="مستوى البحر" value={tideLabel(selected.derived.tide_state)} note={selected.derived.sea_level_rate_m_per_h === null ? "الحركة غير متوفرة" : `${selected.derived.sea_level_rate_m_per_h > 0 ? "+" : ""}${selected.derived.sea_level_rate_m_per_h.toFixed(3)} م/ساعة`} />
            <Metric icon={<Thermometer size={21} />} label="حرارة الماء" value={`${numberOrDash(selected.forecast.sea_surface_temperature_c, 1)}°`} note={selected.derived.sea_surface_temperature_change_24h_c === null ? `الهواء ${numberOrDash(selected.forecast.air_temperature_c, 1)}°` : `تغير 24س ${selected.derived.sea_surface_temperature_change_24h_c > 0 ? "+" : ""}${selected.derived.sea_surface_temperature_change_24h_c.toFixed(1)}°`} />
            <Metric icon={<Thermometer size={21} />} label="الهواء والرطوبة" value={`${numberOrDash(selected.forecast.air_temperature_c, 1)}° · ${numberOrDash(selected.forecast.relative_humidity_pct)}%`} note={`محسوسة ${numberOrDash(selected.forecast.apparent_temperature_c, 1)}° · ندى ${numberOrDash(selected.forecast.dew_point_c, 1)}°`} />
            <Metric icon={<Gauge size={21} />} label="الضغط" value={`${numberOrDash(selected.forecast.pressure_msl_hpa)} hPa`} note={selected.derived.pressure_change_3h_hpa === null ? "التغير غير متوفر" : `${selected.derived.pressure_change_3h_hpa > 0 ? "+" : ""}${selected.derived.pressure_change_3h_hpa.toFixed(1)} hPa / 3س`} />
            <Metric icon={<Sparkles size={21} />} label="الضوء وUV" value={`${numberOrDash(selected.forecast.shortwave_radiation_wm2)} W/m²`} note={`سحب ${numberOrDash(selected.forecast.cloud_cover_pct)}% · UV ${numberOrDash(selected.forecast.uv_index, 1)}`} />
            <Metric icon={<Compass size={21} />} label="تغيّر الريح" value={selected.derived.gust_factor === null ? "Unknown" : `${selected.derived.gust_factor.toFixed(2)}× هبّات`} note={selected.derived.max_wind_direction_shift_6h_deg === null ? "أقصى تحول ساعي Unknown" : `أقصى تحول ساعي ${selected.derived.max_wind_direction_shift_6h_deg.toFixed(0)}°`} />
            <Metric icon={<Compass size={21} />} label="تماسك اتجاه الريح / 6س" value={selected.derived.wind_direction_coherence_6h === null ? "Unknown" : `R = ${selected.derived.wind_direction_coherence_6h.toFixed(2)}`} note={`تغطية ${selected.derived.wind_direction_data_hours_6h}/6؛ استُبعدت الريح دون 5 كم/س`} />
            <Metric icon={<Wind size={21} />} label="إجهاد الريح التشخيصي" value={selected.derived.wind_stress_pa === null ? "Unknown" : `${selected.derived.wind_stress_pa.toFixed(4)} Pa`} note={selected.derived.wind_stress_shoreward_pa === null || selected.derived.wind_stress_alongshore_pa === null ? "الإسقاط Unknown" : `نحو الشاطئ ${selected.derived.wind_stress_shoreward_pa.toFixed(4)} · موازٍ ${selected.derived.wind_stress_alongshore_pa.toFixed(4)} Pa`} />
            <Metric icon={<Navigation size={21} />} label="المحور الموازي الموقّع" value={selected.derived.wind_alongshore_signed_component_kmh === null ? "Unknown" : `${selected.derived.wind_alongshore_signed_component_kmh > 0 ? "+" : ""}${selected.derived.wind_alongshore_signed_component_kmh.toFixed(2)} كم/س`} note={`الموجب نحو bearing ${selected.derived.alongshore_positive_bearing_deg.toFixed(0)}°؛ القديم |V∥|=${numberOrDash(selected.derived.wind_alongshore_component_kmh, 2)}`} />
            <Metric icon={<Waves size={21} />} label="تقاطع موج الريح والسويل" value={selected.derived.wave_component_angle_deg === null ? "Unknown" : `${selected.derived.wave_component_angle_deg.toFixed(0)}°`} note={selected.derived.wave_component_secondary_energy_share === null ? "حصة النظام الأضعف Unknown" : `حصة H² للنظام الأضعف ${(selected.derived.wave_component_secondary_energy_share * 100).toFixed(0)}% · بلا عتبة خطر`} />
            <Metric icon={<Waves size={21} />} label="دفع الموج الموازي النسبي" value={selected.derived.alongshore_wave_signed_proxy === null ? "Unknown" : `${selected.derived.alongshore_wave_signed_proxy > 0 ? "+" : ""}${selected.derived.alongshore_wave_signed_proxy.toFixed(2)} Hs²T`} note={`الموجب نحو ${selected.derived.alongshore_positive_bearing_deg.toFixed(0)}°؛ ليس سرعة تيار أو نقل رسوبي`} />
            <Metric icon={<Thermometer size={21} />} label="فروق حرارية صريحة" value={selected.derived.air_sea_temperature_difference_c === null ? "Unknown" : `هواء−بحر ${selected.derived.air_sea_temperature_difference_c > 0 ? "+" : ""}${selected.derived.air_sea_temperature_difference_c.toFixed(1)}°`} note={selected.derived.dew_point_depression_c === null ? "هواء−ندى Unknown" : `هواء−ندى ${selected.derived.dew_point_depression_c.toFixed(1)}°؛ لا يُحوّل تلقائياً إلى توقع ضباب`} />
            <Metric icon={<Waves size={21} />} label="طول موج مياه عميقة" value={selected.derived.deep_water_wavelength_m === null ? "Unknown" : `${selected.derived.deep_water_wavelength_m.toFixed(0)} م`} note="تقريب فيزيائي، لا طول الكسرة قرب الشاطئ" />
            <Metric icon={<CloudRain size={21} />} label="الأمطار" value={`${numberOrDash(selected.forecast.precipitation_mm, 1)} مم`} note={`رؤية جوية ${selected.forecast.visibility_m === null ? "—" : `${(selected.forecast.visibility_m / 1000).toFixed(1)} كم`}`} />
          </div>
          <div className="hour-field-summary" aria-label="قابلية التنفيذ في الساعة المختارة">
            <span><Anchor size={15} /> تثبيت الخط <strong>{potentialLabels[selected.field_feasibility.holding_difficulty]}</strong></span>
            <span><Wind size={15} /> احتمال الصوفة <strong>{potentialLabels[selected.field_feasibility.fouling_transport_potential]}</strong></span>
            <span><Droplets size={15} /> احتمال العكارة <strong>{potentialLabels[selected.field_feasibility.turbidity_potential]}</strong></span>
            <span><Waves size={15} /> تيار ساحبي محتمل <strong>{potentialLabels[selected.field_feasibility.rip_current_potential]}</strong></span>
            <small>فحص احتمالي بثقة {selected.field_feasibility.confidence}/100، وليس مشاهدة ميدانية.</small>
          </div>
          <details className="hour-reasons" open>
            <summary><span><Gauge size={17} /> كيف وصل المحرك لقرار هذه الساعة؟</span><ChevronLeft size={17} /></summary>
            <ul className="factor-list">{[...selected.factors].sort((a, b) => {
              const priority = { critical: 3, caution: 2, info: 1 };
              return priority[b.severity] - priority[a.severity] || Math.abs(b.score_delta) - Math.abs(a.score_delta);
            }).map((factor) => <FactorItem factor={factor} key={`${factor.code}-${factor.value}`} />)}</ul>
          </details>
        </section>
      )}

      <section className="tide-section" aria-labelledby="tide-title">
        <div className="result-section-head">
          <div><span className="section-icon"><Droplets size={18} /></span><span><h3 id="tide-title">حركة مستوى البحر</h3><p>اتجاه تقريبي من النموذج البحري، وليس جدول مدّ ملاحي.</p></span></div>
        </div>
        <TideChart hours={result.hourly} events={result.tide_events} />
        {result.tide_events.length > 0 && <div className="tide-events">{result.tide_events.map((event) => <div key={event.time}>{event.kind === "high" ? <ArrowUpRight size={16} /> : <ArrowDownLeft size={16} />}<span>{event.kind === "high" ? "قمة نموذجية" : "قاع نموذجي"}</span><strong>{formatHour(event.time)}</strong><small>{event.level_msl_m.toFixed(2)} م بالنسبة إلى مرجع MSL في النموذج؛ ليس قياس مد محلي</small></div>)}</div>}
      </section>

      <div className="transparency-grid">
        <details className="details-panel">
          <summary><span><Database size={19} /><strong>المصادر وحدودها</strong></span><span>{result.sources.length} مصادر</span><ChevronLeft size={18} /></summary>
          <div className="details-content">
            {result.sources.map((source) => <div className="source-item" key={source.product}><strong>{source.product}</strong><span>{source.provider}</span><small>{source.data_kind === "direct_observation" ? "رصد فعلي نقطي في محطة، موش في البقعة" : source.data_kind === "remote_sensing_estimate" ? `استعادة أقمار صناعية سياقية · دقة المنتج ${source.horizontal_resolution_km ?? "Unknown"} كم` : source.horizontal_resolution_km ? `توقع نموذجي · دقة تقريبية ${source.horizontal_resolution_km} كم` : "توقع نموذجي · الدقة حسب أفضل نموذج متاح"}</small></div>)}
            <ul>{result.limitations_ar.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </details>
        <details className="details-panel">
          <summary><span><Shield size={19} /><strong>علاش ثقة المدخلات {result.confidence.score}/100؟</strong></span><span>{result.confidence.reasons_ar.length} أسباب</span><ChevronLeft size={18} /></summary>
          <div className="details-content"><ul>{result.confidence.reasons_ar.map((item) => <li key={item}>{item}</li>)}</ul></div>
        </details>
        <details className="details-panel field-method-details">
          <summary><span><Anchor size={19} /><strong>حدود فحص قابلية التنفيذ</strong></span><span>ثقة {field.confidence}/100</span><ChevronLeft size={18} /></summary>
          <div className="details-content"><ul>{field.limitations_ar.map((item) => <li key={item}>{item}</li>)}</ul></div>
        </details>
        <details className="details-panel factor-coverage-details">
          <summary><span><Database size={19} /><strong>تدقيق مصفوفة العوامل</strong></span><span>{result.factor_coverage.audited_total} عاملاً</span><ChevronLeft size={18} /></summary>
          <div className="details-content">
            <p>{result.factor_coverage.note_ar}</p>
            <ul>
              <li>{result.factor_coverage.automated_decision} عوامل آلية تدخل القرار أو السلامة.</li>
              <li>{result.factor_coverage.automated_context} عوامل آلية للسياق فقط بلا وزن تلقائي.</li>
              <li>{result.factor_coverage.proxy_requires_field_check} مؤشرات تقريبية تحتاج تحققاً ميدانياً.</li>
              <li>{result.factor_coverage.field_or_external_required} عوامل تبقى Unknown حتى يتوفر قياس/بلاغ/تحقق.</li>
              <li>{result.factor_coverage.excluded_unsupported} علاقات مستبعدة لضعف الدليل أو خطر التكرار.</li>
            </ul>
            <a href="/api/methodology/factors" target="_blank" rel="noreferrer">افتح سجل التدقيق الكامل</a>
          </div>
        </details>
      </div>
    </section>
  );
}
