"use client";

import { Info } from "lucide-react";
import { potentialLabels } from "@/lib/format";
import type { GearRecommendation } from "@/lib/types";

export function GearPanel({ gear, heading = true }: { gear: GearRecommendation; heading?: boolean }) {
  return (
    <div className="report-gear-recommendation">
      {heading && (
        <div className="report-gear-head">
          <span>🎣 العتاد المقترح</span>
          <small>ثقة {gear.confidence}/30 · <strong>{gear.required_rod_rating_note_ar}</strong></small>
        </div>
      )}
      {!heading && (
        <div className="report-gear-head">
          <small>ثقة {gear.confidence}/30 · <strong>{gear.required_rod_rating_note_ar}</strong></small>
        </div>
      )}
      <div className="report-gear-grid">
        {gear.scenarios.map((scenario, index) => (
          <article key={scenario.shape} className={index === 0 ? "primary" : ""}>
            <header>
              <span className="report-gear-rank">{index === 0 ? "الخيار الأنسب" : `بديل ${index}`}</span>
              <strong>{scenario.shape_ar}</strong>
              <bdi>{scenario.weight_band_ar}</bdi>
            </header>
            <p>{scenario.rationale_ar}</p>
            <ul>
              <li>القاع المناسب: {scenario.bottom_ar}</li>
              <li>{scenario.montage_ar}</li>
              <li>ثبات جانبي: {potentialLabels[scenario.lateral_hold]} · خطر تعليق: {potentialLabels[scenario.snag_risk]}</li>
            </ul>
          </article>
        ))}
      </div>
      {gear.casting_advice_ar ? (
        <div className="report-gear-advice"><Info size={14} /><span>{gear.casting_advice_ar}</span></div>
      ) : null}
      <div className="report-gear-note"><Info size={14} /><span>مجالات تقريبية من كتالوج عام، لا رقم دقيق بلا بيانات قصبتك وخيطك وقاعك؛ القاع تحت الطعم غير معروف فالنتيجة سيناريوهات. أكّد الرمل ميدانياً قبل grapnel ثابت. للتثبيت زد الوزن؛ لتقليل التشابك خففه مع إمبيلة أقصر — حسب الهدف، وليس حكماً واحداً.</span></div>
    </div>
  );
}
