"use client";

import { AlertOctagon, CircleHelp, Clock3, ShieldCheck, TriangleAlert } from "lucide-react";
import { formatHour } from "@/lib/format";
import { buildTripBlockers, type BlockerTone, type TripBlockerRow } from "@/lib/tripBlockers";
import type { DecisionResponse } from "@/lib/types";

const TONE_LABEL: Record<BlockerTone, string> = {
  block: "يمنع",
  caution: "حذر",
  clear: "لا مانع ظاهر",
  unknown: "غير معروف",
};

function ToneIcon({ tone }: { tone: BlockerTone }) {
  if (tone === "block") return <AlertOctagon size={16} />;
  if (tone === "caution") return <TriangleAlert size={16} />;
  if (tone === "clear") return <ShieldCheck size={16} />;
  return <CircleHelp size={16} />;
}

function Group({
  title,
  rows,
  onOpenHour,
}: {
  title: string;
  rows: TripBlockerRow[];
  onOpenHour?: (time: string) => void;
}) {
  return (
    <section className="trip-blocker-group">
      <h4>{title}</h4>
      <ul>
        {rows.map((row) => (
          <li key={row.id} className={`trip-blocker tone-${row.tone}`} data-blocks={row.blocksGo ? "true" : "false"}>
            <span className="trip-blocker-icon" aria-hidden>
              <ToneIcon tone={row.tone} />
            </span>
            <div>
              <strong>{row.label}</strong>
              <small>{TONE_LABEL[row.tone]}{row.blocksGo ? " · يوقف اذهب" : ""}</small>
              <p>{row.detail}</p>
              {row.hourTime && onOpenHour ? (
                <button
                  type="button"
                  className="trip-blocker-hour"
                  onClick={() => onOpenHour(row.hourTime!)}
                >
                  <Clock3 size={13} />
                  أول ساعة: {formatHour(row.hourTime)}
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TripBlockers({
  result,
  onOpenHour,
}: {
  result: DecisionResponse;
  onOpenHour?: (time: string) => void;
}) {
  const rows = buildTripBlockers(result);
  const blocking = rows.filter((row) => row.blocksGo).length;
  const unknown = rows.filter((row) => row.tone === "unknown").length;
  const groups = ["سلامة", "تنفيذ", "ميدان غير مرئي"] as const;

  return (
    <section className="trip-blockers" id="trip-blockers" data-testid="trip-blockers" aria-labelledby="trip-blockers-title">
      <div className="result-section-head">
        <div>
          <span className="section-icon"><AlertOctagon size={18} /></span>
          <span>
            <h3 id="trip-blockers-title">مفسدات الخرجة</h3>
            <p>
              {blocking > 0
                ? `${blocking} عامل يوقف الذهاب لليوم.`
                : result.decision === "go"
                  ? "اذهب في الساعات بلا موانع. ما يظهر حذراً هنا قد يمنع ساعات أخرى لا اليوم كله."
                  : "لا مانع آلي ظاهر في السلامة/التنفيذ."}{" "}
              {unknown} بند يبقى غير مرئي من النموذج — عاين الكسرة قبل أول رمية.
            </p>
          </span>
        </div>
      </div>
      <div className="trip-blocker-grid">
        {groups.map((group) => (
          <Group
            key={group}
            title={group}
            rows={rows.filter((row) => row.group === group)}
            onOpenHour={onOpenHour}
          />
        ))}
      </div>
    </section>
  );
}
