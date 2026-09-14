"use client";

import {
  AlertTriangle,
  Anchor,
  Check,
  Clock3,
  Compass,
  Droplets,
  Fish,
  Gauge,
  Moon,
  Navigation,
  Shield,
  Sparkles,
  Sunrise,
  Sunset,
  Target,
  Thermometer,
  Waves,
  Wind,
} from "lucide-react";

import type { FishermanReport, ReportPeriod } from "@/lib/types";

function FormatValue({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) return <span className="fr-na">غير متوفر</span>;
  return (
    <bdi>
      {value}
      {suffix}
    </bdi>
  );
}

function PeriodCard({ period }: { period: ReportPeriod }) {
  const hasData = period.wind_speed_kmh !== null || period.wave_height_m !== null;

  // فترة بلا بيانات (خارج أفق التوقّع أو الحصة) تُطوى في سطر واحد:
  // بطاقة كاملة فارغة كانت تُغرق التقرير بصناديق بلا محتوى.
  if (!hasData) {
    return (
      <article className={`fr-period fr-period-empty fr-period-${period.key}`}>
        <strong>{period.label_ar}</strong>
        <span>{period.range_ar}</span>
        <small>لا بيانات في هذه الفترة</small>
      </article>
    );
  }

  return (
    <article className={`fr-period fr-period-${period.key}`}>
      <header>
        <strong>{period.label_ar}</strong>
        <span>{period.range_ar}</span>
      </header>
      {hasData ? (
        <div className="fr-period-grid">
          <div className="fr-period-state">
            <Waves size={15} />
            <span>{period.state_ar}</span>
            {period.confidence_pct !== null && <small>ثقة المدخلات {period.confidence_pct}%</small>}
          </div>
          <div className="fr-metric">
            <span><Wind size={14} /> الرياح</span>
            <strong>
              <FormatValue value={period.wind_speed_kmh} suffix=" كم/س" />
              {period.wind_gust_kmh !== null && <small>هبات حتى {period.wind_gust_kmh} كم/س</small>}
            </strong>
            <small>{period.wind_relation_ar}{period.wind_dir_deg !== null ? ` · ${period.wind_dir_deg}°` : ""}</small>
          </div>
          <div className="fr-metric">
            <span><Droplets size={14} /> الموج</span>
            <strong>
              <FormatValue value={period.wave_height_m} suffix=" م" />
              {period.wave_period_s !== null && <small>فترة {period.wave_period_s} ث</small>}
            </strong>
            <small>{period.wind_cast_effect_m > 0 ? `الريح تنقص الرمي ≈ ${period.wind_cast_effect_m} م` : "لا أثر ملحوظ للريح على الرمي"}</small>
          </div>
          <div className="fr-metric">
            <span><Navigation size={14} /> الرمي</span>
            <strong><FormatValue value={period.cast_distance_m} suffix=" م" /></strong>
            <small>تقدير موثق · راحة {period.comfort_index}/100</small>
          </div>
        </div>
      ) : (
        <p className="fr-empty">{period.state_ar}</p>
      )}
      <div className="fr-period-extra">
        <span><Thermometer size={13} /> العكارة: {period.turbidity_ar}</span>
        <span><Anchor size={13} /> {period.montage_ar}</span>
      </div>
      {period.warnings_ar.length > 0 && (
        <ul className="fr-warnings">
          {period.warnings_ar.map((warning) => (
            <li key={warning}><AlertTriangle size={13} /> {warning}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function FishermanReportView({ report }: { report: FishermanReport }) {
  const moonTimes = report.astronomical_times.filter((item) => item.kind.startsWith("moon") || item.kind.includes("transit"));
  return (
    <section className="fisherman-report" aria-labelledby="fisherman-report-title" data-testid="fisherman-report">
      <div className="result-section-head">
        <div>
          <span className="section-icon"><Fish size={18} /></span>
          <span>
            <h3 id="fisherman-report-title">التقرير الميداني المنظّم</h3>
            <p>كل الأرقام من المحرك أو مشتقة فلكياً/فيزيائياً بطريقة موثقة — لا شيء مكتوب بالذكاء الاصطناعي.</p>
          </span>
        </div>
      </div>

      {/* 0. الملخص التنفيذي */}
      <div className="fr-exec">
        <div className="fr-exec-row">
          <div className="fr-exec-item">
            <span><Target size={15} /> القرار</span>
            <strong className={report.decision_label_ar === "اذهب" ? "fr-go" : "fr-nogo"}>{report.decision_label_ar}</strong>
            <small>{report.decision_reason_ar}</small>
          </div>
          <div className="fr-exec-item">
            <span><Gauge size={15} /> مؤشر الفرصة</span>
            <strong><bdi>{report.opportunity_score}/100</bdi></strong>
            <small>{report.opportunity_note_ar}</small>
          </div>
          <div className="fr-exec-item">
            <span><Compass size={15} /> اتجاه الشاطئ</span>
            <strong>
              {report.beach_direction_deg !== null ? <bdi>{report.beach_direction_deg}°</bdi> : "غير معروف"}
            </strong>
            <small>{report.beach_direction_ar}</small>
          </div>
        </div>
        <div className="fr-exec-bait">
          <span><Fish size={15} /> الطعم المستهدف</span>
          <strong>{report.target_bait_ar}</strong>
          <small>{report.bait_note_ar}</small>
        </div>
      </div>

      {/* 1. التوقيت وحركة المياه */}
      <div className="fr-block">
        <h4><Clock3 size={16} /> 1. التوقيت وحركة المياه</h4>
        <div className="fr-timing-grid">
          {report.moon_upper_transit_ar && (
            <div className="fr-timing"><Moon size={15} /><span>العبور القمري العلوي (تقديري)</span><strong><bdi>{report.moon_upper_transit_ar}</bdi></strong></div>
          )}
          {report.moon_lower_transit_ar && (
            <div className="fr-timing"><Moon size={15} /><span>العبور القمري السفلي (تقديري)</span><strong><bdi>{report.moon_lower_transit_ar}</bdi></strong></div>
          )}
          {report.moonrise_ar && (
            <div className="fr-timing"><Moon size={15} /><span>طلوع القمر</span><strong><bdi>{report.moonrise_ar}</bdi></strong></div>
          )}
          {report.moonset_ar && (
            <div className="fr-timing"><Moon size={15} /><span>غروب القمر</span><strong><bdi>{report.moonset_ar}</bdi></strong></div>
          )}
          {report.sunrise_ar && (
            <div className="fr-timing"><Sunrise size={15} /><span>الشروق</span><strong><bdi>{report.sunrise_ar}</bdi></strong></div>
          )}
          {report.sunset_ar && (
            <div className="fr-timing"><Sunset size={15} /><span>الغروب</span><strong><bdi>{report.sunset_ar}</bdi></strong></div>
          )}
        </div>
        <div className="fr-tide-line">
          {report.tide_high_ar.length > 0 && <span><Droplets size={14} /> قمم مدّ نموذجية: <strong>{report.tide_high_ar.join(" · ")}</strong></span>}
          {report.tide_low_ar.length > 0 && <span><Droplets size={14} /> قيعان جزر نموذجية: <strong>{report.tide_low_ar.join(" · ")}</strong></span>}
          <small>{report.tide_note_ar}</small>
        </div>
        <div className="fr-pressure">
          <span><Gauge size={14} /> الضغط الجوي: <strong><FormatValue value={report.pressure_hpa} suffix=" hPa" /></strong> · {report.pressure_trend_ar}</span>
          <span><Waves size={14} /> مؤشر الشاطئ: <strong>{report.beach_summary_ar}</strong></span>
          {report.moon_illumination_pct !== null && (
            <span><Moon size={14} /> إضاءة القمر: <strong><bdi>{report.moon_illumination_pct}%</bdi></strong></span>
          )}
        </div>
      </div>

      {/* 2. الأوقات الفلكية المرجعية */}
      {moonTimes.length > 0 && (
        <div className="fr-block">
          <h4><Moon size={16} /> 2. الأوقات الفلكية المرجعية</h4>
          <ul className="fr-astro-list">
            {moonTimes.map((item) => (
              <li key={`${item.kind}-${item.time_ar}`}>
                <span>{item.label_ar}</span>
                <strong><bdi>{item.time_ar}</bdi></strong>
                <small>{item.note_ar}</small>
              </li>
            ))}
          </ul>
          <p className="fr-note">{report.astronomy_note_ar}</p>
        </div>
      )}

      {/* 3. التفكيك الزمني */}
      <div className="fr-block">
        <h4><Waves size={16} /> 3. التفكيك الزمني للفترات</h4>
        <div className="fr-periods">
          {report.periods
            .filter((period) => period.wind_speed_kmh !== null || period.wave_height_m !== null)
            .map((period) => <PeriodCard key={period.key} period={period} />)}
        </div>
        {report.periods.some((period) => period.wind_speed_kmh === null && period.wave_height_m === null) && (
          <div className="fr-periods-empty">
            {report.periods
              .filter((period) => period.wind_speed_kmh === null && period.wave_height_m === null)
              .map((period) => <PeriodCard key={period.key} period={period} />)}
          </div>
        )}
      </div>

      {/* 4. ميزان العوامل */}
      <div className="fr-block">
        <h4><Sparkles size={16} /> 4. ميزان العوامل</h4>
        <div className="fr-balance">
          <div className="fr-red">
            <strong><AlertTriangle size={15} /> العوامل المعوقة</strong>
            {report.red_factors_ar.length > 0 ? (
              <ul>{report.red_factors_ar.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : (
              <p>لا عوامل معوقة حرجة ضمن حدود المحرك اليوم.</p>
            )}
          </div>
          <div className="fr-green">
            <strong><Check size={15} /> العوامل الإيجابية</strong>
            {report.green_factors_ar.length > 0 ? (
              <ul>{report.green_factors_ar.map((item) => <li key={item}>{item}</li>)}</ul>
            ) : (
              <p>لا مؤشرات إيجابية قوية اليوم.</p>
            )}
          </div>
        </div>
      </div>

      {/* 5. التكتيك الميداني والسلامة */}
      <div className="fr-block">
        <h4><Anchor size={16} /> 5. التكتيك الميداني والسلامة</h4>
        <ul className="fr-tactics">
          <li><Anchor size={14} /><span><strong>الرصاص:</strong> {report.lead_advice_ar}</span></li>
          <li><Clock3 size={14} /><span><strong>التوقيت:</strong> {report.timing_advice_ar}</span></li>
          <li><Navigation size={14} /><span><strong>المسافة:</strong> {report.distance_advice_ar}</span></li>
          <li><Shield size={14} /><span><strong>السلامة:</strong> {report.safety_advice_ar}</span></li>
        </ul>
      </div>

      {/* 6. الأرقام المرجعية */}
      <div className="fr-block fr-refs">
        <h4><Thermometer size={16} /> 6. الأرقام المرجعية (للتحقق)</h4>
        <div className="fr-refs-grid">
          <span>حرارة الماء: <strong><FormatValue value={report.water_temp_c} suffix="°م" /></strong></span>
          <span>حرارة الهواء: <strong><FormatValue value={report.air_temp_c} suffix="°م" /></strong></span>
          <span>أقصى هبات: <strong><FormatValue value={report.max_gust_kmh} suffix=" كم/س" /></strong></span>
          <span>الضغط: <strong><FormatValue value={report.pressure_hpa} suffix=" hPa" /></strong></span>
        </div>
        <p className="fr-note">{report.reference_note_ar}</p>
      </div>
    </section>
  );
}
