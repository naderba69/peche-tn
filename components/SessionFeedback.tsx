"use client";

import { useState } from "react";
import { Check, ClipboardList, Download, Trash2, X } from "lucide-react";

const STORAGE_KEY = "peche-tn:session-feedback:v1";

interface SessionFeedbackEntry {
  saved_at: string;
  did_lead_hold: "yes" | "no" | "partial";
  setup_ar: string;
  drift: "yes" | "no";
  fouling_seen: "yes" | "no";
  turbidity_seen: "yes" | "no";
  rip_seen: "yes" | "no";
  catch_ar: string;
  blank_casts: number;
  actual_hours: number;
  note_ar: string;
}

const EMPTY: SessionFeedbackEntry = {
  saved_at: "",
  did_lead_hold: "partial",
  setup_ar: "",
  drift: "no",
  fouling_seen: "no",
  turbidity_seen: "no",
  rip_seen: "no",
  catch_ar: "",
  blank_casts: 0,
  actual_hours: 0,
  note_ar: "",
};

function loadEntries(): SessionFeedbackEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SessionFeedbackEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function SessionFeedback() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<SessionFeedbackEntry[]>([]);
  const [draft, setDraft] = useState<SessionFeedbackEntry>(EMPTY);
  const [saved, setSaved] = useState(false);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) setEntries(loadEntries());
  };

  const persist = (next: SessionFeedbackEntry[]) => {
    setEntries(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Non-fatal: storage can be disabled.
    }
  };

  const submit = () => {
    const entry: SessionFeedbackEntry = {
      ...draft,
      saved_at: new Date().toISOString(),
      blank_casts: Math.max(0, Math.round(draft.blank_casts || 0)),
      actual_hours: Math.max(0, draft.actual_hours || 0),
    };
    persist([entry, ...entries]);
    setDraft(EMPTY);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(entries, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `peche-tn-sessions-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const clearAll = () => {
    persist([]);
  };

  const patch = (partial: Partial<SessionFeedbackEntry>) => {
    setDraft((current) => ({ ...current, ...partial }));
  };

  const yesNo = (value: "yes" | "no", label: string, field: "drift" | "fouling_seen" | "turbidity_seen" | "rip_seen") => (
    <label>
      <span>{label}</span>
      <select value={draft[field]} onChange={(event) => patch({ [field]: event.target.value as "yes" | "no" })}>
        <option value="no">لا</option>
        <option value="yes">نعم</option>
      </select>
    </label>
  );

  return (
    <div className="session-feedback">
      <button
        type="button"
        className="feedback-trigger"
        aria-expanded={open}
        aria-controls="session-feedback-form"
        onClick={toggle}
      >
        <ClipboardList size={17} />
        سجّل حصتك{entries.length ? ` (${entries.length})` : ""}
      </button>

      {open && (
        <div className="feedback-panel" id="session-feedback-form">
          <div className="feedback-head">
            <strong>كيفاش مشات الحصة؟</strong>
            <span>تُخزن محلياً في متصفحك فقط، وللمعايرة فقط — لا تدخل أي قرار الآن.</span>
          </div>
          <div className="feedback-grid">
            <label>
              <span>ثبت الرصاص؟</span>
              <select value={draft.did_lead_hold} onChange={(event) => patch({ did_lead_hold: event.target.value as SessionFeedbackEntry["did_lead_hold"] })}>
                <option value="yes">ثبت</option>
                <option value="partial">انجرّ قليلاً</option>
                <option value="no">ما ثبتش</option>
              </select>
            </label>
            <label>
              <span>الإعداد المستعمل (شكل/وزن/مونتاج)</span>
              <input value={draft.setup_ar} onChange={(event) => patch({ setup_ar: event.target.value })} placeholder="مثال: هرمي 120غ، paternoster" />
            </label>
            {yesNo(draft.drift, "انجراف الخط؟", "drift")}
            {yesNo(draft.fouling_seen, "صوفة/أعشاب على الخيط؟", "fouling_seen")}
            {yesNo(draft.turbidity_seen, "عكارة الماء؟", "turbidity_seen")}
            {yesNo(draft.rip_seen, "تيار ساحبي؟", "rip_seen")}
            <label>
              <span>النوع / العدد / الحجم التقريبي</span>
              <input value={draft.catch_ar} onChange={(event) => patch({ catch_ar: event.target.value })} placeholder="مثال: 2 قاروص ~40سم" />
            </label>
            <label>
              <span>رميات بلا نتيجة</span>
              <input type="number" min={0} value={draft.blank_casts} onChange={(event) => patch({ blank_casts: Number(event.target.value) })} />
            </label>
            <label>
              <span>المدة الفعلية (ساعات)</span>
              <input type="number" min={0} step={0.5} value={draft.actual_hours} onChange={(event) => patch({ actual_hours: Number(event.target.value) })} />
            </label>
            <label>
              <span>ملاحظات</span>
              <input value={draft.note_ar} onChange={(event) => patch({ note_ar: event.target.value })} placeholder="أي ملاحظة ميدانية" />
            </label>
          </div>
          <div className="feedback-actions">
            <button type="button" className="primary-action" onClick={submit}>
              {saved ? <Check size={18} /> : <ClipboardList size={18} />}
              <span>{saved ? "تم الحفظ" : "احفظ الحصة"}</span>
            </button>
            <button type="button" onClick={exportJson} disabled={!entries.length}><Download size={16} />تصدير JSON</button>
            <button type="button" onClick={clearAll} disabled={!entries.length}><Trash2 size={16} />امسح الكل</button>
          </div>
          {entries.length > 0 && (
            <ul className="feedback-history">
              {entries.slice(0, 5).map((entry, index) => (
                <li key={`${entry.saved_at}-${index}`}>
                  <strong>{new Date(entry.saved_at).toLocaleString("ar-TN")}</strong>
                  <span>ثبات {entry.did_lead_hold === "yes" ? "تام" : entry.did_lead_hold === "partial" ? "جزئي" : "منعدم"} · رمية {entry.catch_ar || "بلا مصيد"} · {entry.actual_hours} س</span>
                </li>
              ))}
            </ul>
          )}
          <p className="feedback-note">
            <X size={13} /> هذه البيانات ستُستعمل لاحقاً لمعايرة مؤشرات المحرك (مثل استجابة كل نوع للحيّة/المات) بعد تراكم عيّنات كافية — ولن تُرفع إلا برضاك.
          </p>
        </div>
      )}
    </div>
  );
}
