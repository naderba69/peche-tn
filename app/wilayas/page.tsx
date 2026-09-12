"use client";

import { useMemo, useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  Info,
  MapPinned,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { requestRankSpots } from "@/lib/api";
import {
  fieldFeasibilityLabels,
  formatDate,
  formatWindowRange,
  potentialLabels,
  springNeapLabel,
  tunisTodayIso,
} from "@/lib/format";
import { SPOT_PRESETS } from "@/lib/spots";
import type { RankSpotsResponse, TargetSpecies } from "@/lib/types";

const GOVERNORATES = Array.from(new Set(SPOT_PRESETS.map((spot) => spot.governorate)));

const reasonLabels: Record<string, string> = {
  safe_window: "نافذة آمنة",
  safety_hazard: "خطر سلامة",
  field_infeasible: "تثبيت العتاد صعب",
  critical_data_missing: "بيانات ناقصة",
  conservative_uncertainty: "تحفظ محافظ",
  fouling_confirmed: "صوفة مؤكدة",
  official_warning: "تحذير رسمي",
  trip_ruin_confirmed: "عامل مُفسِد مؤكد",
};

export default function WilayasPage() {
  const forecastDates = useMemo(
    () => Array.from({ length: 7 }, (_, index) => tunisTodayIso(index)),
    [],
  );
  const [selected, setSelected] = useState<string[]>([...GOVERNORATES]);
  const [targetDate, setTargetDate] = useState(tunisTodayIso());
  const [species, setSpecies] = useState<TargetSpecies>("general");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RankSpotsResponse | null>(null);

  const spots = SPOT_PRESETS.filter((spot) => selected.includes(spot.governorate));

  const toggleGovernorate = (governorate: string) => {
    setSelected((current) =>
      current.includes(governorate)
        ? current.filter((item) => item !== governorate)
        : [...current, governorate],
    );
  };

  const run = async () => {
    if (!spots.length) return;
    setLoading(true);
    setError(null);
    setResult(null);
    const controller = new AbortController();
    try {
      const payload = {
        target_date: targetDate,
        angler: {
          experience: "intermediate" as const,
          target_species: species,
          session_hours: 3,
        },
        spots: spots.map((spot) => ({
          spot_id: spot.id,
          name_ar: spot.name,
          location: { latitude: spot.latitude, longitude: spot.longitude, name: spot.name },
          spot: {
            seaward_orientation_deg: spot.orientation,
            orientation_source: "estimated" as const,
            shore_type: spot.shoreType,
            exposure: "open" as const,
          },
        })),
      };
      setResult(await requestRankSpots(payload, controller.signal));
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : "تعذر ترتيب البقع.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <section className="wilaya-hero" id="top">
        <div className="eyebrow"><MapPinned size={15} /> وين نخرج اليوم؟</div>
        <h1>اختر ولاياتك،<br /><em>ورتبلك أحسن البقع.</em></h1>
        <p>
          المحرك يحلل البقع المعروفة في الولايات المختارة لنفس اليوم ويرتبها من الأحسن للأضعف:
          كل بقعة بنتيجتها (اذهب / لا تذهب) وأحسن ساعة ومؤشر وجود السمك — ترتيب نسبي، موش احتمال مصيد.
        </p>
      </section>

      <section className="wilaya-tools" id="wilaya-tools" aria-label="أدوات الترتيب">
        <div className="wilaya-governorates">
          <span className="field-caption">الولايات</span>
          <div className="wilaya-chips">
            {GOVERNORATES.map((governorate) => (
              <button
                key={governorate}
                type="button"
                className={selected.includes(governorate) ? "active" : ""}
                aria-pressed={selected.includes(governorate)}
                onClick={() => toggleGovernorate(governorate)}
              >
                {governorate}
                <small>{SPOT_PRESETS.filter((spot) => spot.governorate === governorate).length}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="wilaya-controls">
          <label>
            <span>اليوم</span>
            <select value={targetDate} onChange={(event) => setTargetDate(event.target.value)}>
              {forecastDates.map((date) => (
                <option key={date} value={date}>{formatDate(date)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>الهدف</span>
            <select value={species} onChange={(event) => setSpecies(event.target.value as TargetSpecies)}>
              <option value="general">صيد عام</option>
              <option value="european_seabass">القاروص</option>
              <option value="gilthead_seabream">الوراطة</option>
              <option value="white_seabream">السار</option>
              <option value="striped_seabream">المرمار</option>
            </select>
          </label>
          <button className="primary-action" type="button" disabled={loading || !spots.length} onClick={run}>
            {loading ? <RefreshCw className="spin" size={20} /> : <Sparkles size={20} />}
            <span>{loading ? "يحلل البقع…" : `حلّل ${spots.length} بقعة`}</span>
            {!loading && <ArrowLeft size={19} />}
          </button>
        </div>

        {!spots.length && (
          <p className="wilaya-empty" role="status">اختر ولاية واحدة على الأقل.</p>
        )}
      </section>

      {error && (
        <div className="planner-error" role="alert">
          <strong>ما قدرناش نكملوا الترتيب</strong>
          <span>{error}</span>
        </div>
      )}

      {result && (
        <section className="wilaya-results" aria-label="نتائج الترتيب">
          <div className="wilaya-results-head">
            <span>الترتيب من الأحسن إلى الأضعف</span>
            <small><CalendarDays size={14} /> {formatDate(result.target_date)} · {result.ranked.length} بقعة</small>
          </div>
          <ol className="wilaya-ranking">
            {result.ranked.map((spot, index) => (
              <RankCard key={spot.spot_id} spot={spot} rank={index + 1} />
            ))}
          </ol>
          {result.notes_ar.length > 0 && (
            <div className="wilaya-notes"><Info size={15} /><span>{result.notes_ar.join(" ")}</span></div>
          )}
        </section>
      )}
    </main>
  );
}

function RankCard({ spot, rank }: { spot: RankSpotsResponse["ranked"][number]; rank: number }) {
  const isGo = spot.decision === "go";
  const windowText =
    spot.best_window_start && spot.best_window_end
      ? formatWindowRange(spot.best_window_start, spot.best_window_end)
      : null;
  return (
    <li className={`wilaya-card ${isGo ? "card-go" : "card-nogo"}`}>
      <span className="wilaya-rank">{rank}</span>
      <div className="wilaya-card-main">
        <header>
          <strong>{spot.name_ar}</strong>
          <span className={`wilaya-badge ${isGo ? "badge-go" : "badge-nogo"}`}>
            {isGo ? "✅ اذهب" : "⛔ لا تذهب"}
          </span>
        </header>
        <p className="wilaya-reason">
          {reasonLabels[spot.decision_reason_code] ?? spot.decision_reason_code}
          {spot.error_ar ? ` · ${spot.error_ar}` : ""}
        </p>
        <div className="wilaya-metrics">
          {windowText ? (
            <span><small>أحسن ساعة</small><strong><bdi>{windowText}</bdi></strong></span>
          ) : (
            <span><small>أحسن ساعة</small><strong>—</strong></span>
          )}
          <span><small>تنفيذ ميداني</small><strong>{fieldFeasibilityLabels[spot.field_status]}</strong></span>
          <span><small>مؤشر الفرصة النسبي</small><strong><bdi>{spot.opportunity_score}/100</bdi></strong></span>
          {spot.spring_folk_label ? (
            <span><small>المدّ</small><strong>{springNeapLabel(spot.spring_classification ?? "")} ({spot.spring_folk_label}){spot.spring_gabes_zone ? " · قابس" : ""}</strong></span>
          ) : null}
        </div>
        {spot.species_label_ar && (
          <p className="wilaya-species">
            <small>الأنواع ({spot.species_label_ar}):</small>{" "}
            {spot.species_axes_summary.length ? spot.species_axes_summary.join(" · ") : "محاور أولية غير معايرة"}
            {spot.holding_difficulty !== "low" ? ` · تثبيت الخط ${potentialLabels[spot.holding_difficulty]}` : ""}
          </p>
        )}
        {spot.fouling_force_majeure && (
          <p className="wilaya-fouling">🪸 صوفة/عوالق مؤكدة ميدانياً (مستوى {spot.fouling_level}).</p>
        )}
      </div>
    </li>
  );
}
