"use client";

import { Fish } from "lucide-react";
import type { SpeciesForecast } from "@/lib/types";

const ORDER = ["european_seabass", "gilthead_seabream", "white_seabream", "striped_seabream"];

export function SpeciesActivityBoard({
  rows,
  compact = false,
}: {
  rows: SpeciesForecast[];
  compact?: boolean;
}) {
  const ordered = [...rows].sort((a, b) => ORDER.indexOf(a.species) - ORDER.indexOf(b.species));
  if (!ordered.length) return null;
  return (
    <div className={compact ? "species-board compact" : "species-board"} data-testid="species-activity-board">
      {!compact ? (
        <p className="species-board-lead">
          <Fish size={15} /> توقع نشاط كل نوع من العوامل المقيسة في الساعات المفتوحة — نسبة ترتيب 0–100، ليست احتمال مصيد.
        </p>
      ) : null}
      <ul>
        {ordered.map((row) => {
          const pct = row.score;
          return (
            <li key={row.species}>
              <div className="species-board-row">
                <strong>{row.label_ar}</strong>
                <bdi>{pct === null || pct === undefined ? "لا رقم" : `${pct}%`}</bdi>
              </div>
              <div className="species-board-bar" aria-hidden>
                <span style={{ width: `${pct == null ? 0 : pct}%` }} />
              </div>
              {!compact ? (
                <>
                  <small>{row.mode_ar}</small>
                  {row.drivers_ar.length ? <small>{row.drivers_ar.join(" · ")}</small> : null}
                </>
              ) : (
                <small>{row.mode_ar}</small>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
