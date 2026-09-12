"use client";

import { useState } from "react";
import Link from "next/link";
import { Info, Waves } from "lucide-react";
import {
  CALENDAR_MONTHS,
  CALENDAR_SPECIES,
  CALENDAR_ZONES,
  PRESENCE_META,
  presenceLevel,
} from "@/lib/seasonalCalendar";

export default function CalendarPage() {
  const [speciesKey, setSpeciesKey] = useState(CALENDAR_SPECIES[0].key);
  const species = CALENDAR_SPECIES.find((item) => item.key === speciesKey) ?? CALENDAR_SPECIES[0];

  return (
    <main>
      <section className="calendar-hero" id="top">
        <div className="eyebrow"><Waves size={15} /> التقويم الموسمي (D15)</div>
        <h1>شنوّة يتصيّد وين،<br /><em>في أي شهر.</em></h1>
        <p>
          جدول شهر × جهة تونسية لكل نوع: حضور <strong>قوي / متوسط / ضعيف / غير متوفر</strong> —
          مبني على تدقيق المصادر (بيولوجيا التكاثر والهجرة والحرارة)، بلا أحكام قانونية،
          وليس سجل مصيد تونسي.
        </p>
      </section>

      <section className="calendar-tools" id="calendar">
        <span className="field-caption">النوع</span>
        <div className="wilaya-chips">
          {CALENDAR_SPECIES.map((item) => (
            <button
              key={item.key}
              type="button"
              className={speciesKey === item.key ? "active" : ""}
              aria-pressed={speciesKey === item.key}
              onClick={() => setSpeciesKey(item.key)}
            >
              {item.labelAr}
            </button>
          ))}
        </div>
      </section>

      <section className="calendar-table-wrap" aria-label="جدول التقويم الموسمي">
        <div className="calendar-heading">
          <div>
            <strong>{species.labelAr}</strong>
            <small><bdi>{species.scientific}</bdi></small>
          </div>
          <p>{species.noteAr}</p>
        </div>

        <div className="calendar-sea-state">
          <small>حالة البحر المفضلة (نمط متوسطي منشور)</small>
          <strong>{species.seaState.labelAr}</strong>
          <p>{species.seaState.basisAr}</p>
        </div>

        <table className="calendar-table">
          <thead>
            <tr>
              <th scope="col">المنطقة</th>
              {CALENDAR_MONTHS.map((month) => <th key={month} scope="col">{month}</th>)}
            </tr>
          </thead>
          <tbody>
            {CALENDAR_ZONES.map((zone) => {
              const matrix = species.matrix[zone.key] ?? "111111111111";
              return (
                <tr key={zone.key}>
                  <th scope="row">
                    {zone.labelAr}
                    <small>{zone.governorates.join(" · ")}</small>
                  </th>
                  {CALENDAR_MONTHS.map((month, index) => {
                    const level = presenceLevel(matrix, index);
                    const meta = PRESENCE_META[level];
                    return (
                      <td key={month} className={meta.className} title={`${month} — ${meta.labelAr}`}>
                        <span aria-hidden="true" />
                        <bdi>{meta.labelAr}</bdi>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="calendar-legend">
          {([3, 2, 1, 0] as const).map((level) => (
            <span key={level}>
              <i className={PRESENCE_META[level].className} />
              {PRESENCE_META[level].labelAr}
            </span>
          ))}
        </div>

        <p className="calendar-note">
          <Info size={15} />
          <span>
            مصفوفات الحضور مشتقة من دراسات علمية منشورة لتونس والمتوسط (مصادر كل نوع معروضة أدناه)،
            وليست وعداً بالمصيد ولا تشمل أي قواعد قانونية (لا أحجام دنيا ولا فترات منع).
            تبقى قابلة للمراجعة وتُعاير مع سجل المصيد التونسي في الحلقة ما بعد الحصة.
          </span>
        </p>

        {species.sources.length > 0 && (
          <div className="calendar-sources">
            <small>المصادر العلمية لهذا النوع</small>
            <ul>
              {species.sources.map((source) => (
                <li key={source}><span>{source}</span></li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <footer className="site-footer">
        <Link className="brand footer-brand" href="/"><span className="brand-mark"><Waves size={20} /></span><strong>Peche TN</strong></Link>
        <p>أداة تونسية مجانية لدعم قرار سيرفكاست أكثر أماناً ووضوحاً.</p>
        <div className="footer-meta">
          <span>الإصدار 1.10.0 · المعطيات البحرية تقريبية وقد تختلف محلياً.</span>
          <Link href="/">الرئيسية</Link>
        </div>
      </footer>
    </main>
  );
}
