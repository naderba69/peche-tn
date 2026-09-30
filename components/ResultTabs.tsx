"use client";

import { useId, useRef, useState } from "react";

export interface ResultTab {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
  content: React.ReactNode;
}

/**
 * تبويبات نتيجة القرار.
 *
 * الهدف تقليل التكدس: بدل 13 قسماً مفتوحاً دفعة واحدة (‎22.7 شاشة على الهاتف)
 * يرى الصيّاد القرار فوراً ثم يفتح ما يحتاجه فقط.
 * تتبع نمط ARIA Tabs: أسهم للتنقل، Home/End للطرفين، وتفعيل يدوي.
 */
export function ResultTabs({ tabs, ariaLabel }: { tabs: ResultTab[]; ariaLabel: string }) {
  const [active, setActive] = useState(tabs[0]?.id ?? "");
  const baseId = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const focusTab = (id: string) => {
    setActive(id);
    window.setTimeout(() => refs.current[id]?.focus(), 0);
  };

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    // الواجهة عربية (RTL): السهم الأيسر يعني "التالي" بصرياً.
    const last = tabs.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowLeft") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowRight") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    if (next === null) return;
    event.preventDefault();
    focusTab(tabs[next].id);
  };

  return (
    <div className="result-tabs" data-testid="result-tabs">
      <div className="result-tablist" role="tablist" aria-label={ariaLabel}>
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(node) => {
              refs.current[tab.id] = node;
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${tab.id}`}
            aria-selected={active === tab.id}
            aria-controls={`${baseId}-panel-${tab.id}`}
            tabIndex={active === tab.id ? 0 : -1}
            className={active === tab.id ? "active" : ""}
            onClick={() => setActive(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && <em>{tab.badge}</em>}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          hidden={active !== tab.id}
          tabIndex={0}
          className="result-tabpanel"
        >
          {active === tab.id && tab.content}
        </div>
      ))}
    </div>
  );
}
