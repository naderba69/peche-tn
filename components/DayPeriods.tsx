"use client";

import { Clock3, Droplets, Waves, Wind } from "lucide-react";
import { decisionShortLabels } from "@/lib/format";
import type { PeriodSummary } from "@/lib/periods";

export function DayPeriods({ periods }: { periods: PeriodSummary[] }) {
  return (
    <div className="report-period-grid">
      {periods.map((period) => (
        <article className={!period.hours.length ? "unavailable" : ""} key={period.id}>
          <header><span><Clock3 size={16} /><strong>{period.label}</strong><small>{period.range}</small></span>{period.safety && <b className={`report-safety-${period.safety}`}>سلامة: {decisionShortLabels[period.safety]}</b>}</header>
          {period.hours.length ? <>
            <div className="period-scores"><span>أدنى تنفيذ <strong>{period.field}/100</strong></span><span>متوسط الفرصة <strong>{period.opportunity}/100</strong></span><span>أضعف ثقة <strong>{period.confidence}/100</strong></span></div>
            <p><Wind size={15} /><span>{period.wind}</span></p>
            <p><Waves size={15} /><span>{period.waves}</span></p>
            <p><Droplets size={15} /><span>{period.water}</span></p>
            {period.warnings.length > 0 && <ul>{period.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
          </> : <p className="period-unavailable">لا توجد ساعات مستقبلية قابلة للتقييم في هذه الفترة.</p>}
        </article>
      ))}
    </div>
  );
}
