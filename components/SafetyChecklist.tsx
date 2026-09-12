"use client";

import { useSyncExternalStore } from "react";
import { Check, ClipboardCheck, RotateCcw, ShieldCheck, WifiOff } from "lucide-react";

const STORAGE_KEY = "peche-tn:safety-checklist:v4";
const CHANGE_EVENT = "peche-tn:safety-checklist-change";
const MAX_AGE_MS = 6 * 60 * 60 * 1000;

const ITEMS = [
  "راجعت تنبيهاً رسمياً حديثاً: ما ثماش رعد مسموع أو برق ظاهر؛ إذا ظهر نلغي الحصة وننتظر 30 دقيقة بعد آخر رعد.",
  "عاينت الكسرة عشر دقائق من مكان آمن وما شفتش قناة رغوة أو حطام تتحرك نحو عرض البحر.",
  "الماء ما فيهش لون أو رائحة أو رغوة دائمة أو نفوق سمك غير طبيعي؛ عند الشك ما نصطادش وما ناكلش المصيد.",
  "ما ثماش تجمع قناديل أو كائن مجهول خطر؛ ما نستعملش وصفة إسعاف عامة بلا تعرف النوع أو توجيه طبي.",
  "منطقة الرمي خالية من سبّاحين وقوارب وشباك وعوامات، وعندي مجال آمن خلفي وأمامي.",
  "عملت رمية اختبارية: الرصاص ما يجرّش والخيط والسنارة ما جمعوش صوفة أو حطام.",
  "الوصول مسموح واللافتات محترمة ومسار الدخول والخروج واضح ولن يقطعه ارتفاع الماء.",
  "تجنبت الصخور الزلقة والحواف وحددت نقطة رجوع أعلى وآمنة.",
  "الطعم محفوظ بارداً وحالته طبيعية؛ الطعم الفاسد أو المشكوك فيه يُرمى.",
  "القصبة والخيط والرصاص ضمن مواصفات العتاد، وما نخمنش وزناً أو مسافة من التطبيق وحده.",
  "الهاتف مشحون وشخص آخر يعرف البقعة ووقت الرجوع، ومعي ماء ولباس مناسب وحماية شمس.",
  "مستعد نلغي الحصة فوراً إذا الواقع خالف التوقع أو ساورني الشك.",
] as const;

const EMPTY_SNAPSHOT = "0".repeat(ITEMS.length);
let memorySnapshot = EMPTY_SNAPSHOT;
let memorySavedAt = 0;
let storageWritable = true;

function normalizeSnapshot(value: unknown): string {
  return typeof value === "string" && value.length === ITEMS.length && /^[01]+$/.test(value)
    ? value
    : EMPTY_SNAPSHOT;
}

function activeMemorySnapshot(): string {
  const age = Date.now() - memorySavedAt;
  if (memorySavedAt > 0 && age >= -60_000 && age <= MAX_AGE_MS) return memorySnapshot;
  memorySnapshot = EMPTY_SNAPSHOT;
  memorySavedAt = 0;
  return EMPTY_SNAPSHOT;
}

function getSnapshot(): string {
  if (typeof window === "undefined") return EMPTY_SNAPSHOT;
  if (!storageWritable) return activeMemorySnapshot();
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      if (storageWritable) {
        memorySnapshot = EMPTY_SNAPSHOT;
        memorySavedAt = 0;
      }
      return activeMemorySnapshot();
    }

    let parsed: { value?: unknown; savedAt?: unknown };
    try {
      const decoded: unknown = JSON.parse(stored);
      if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
        throw new Error("Invalid checklist record");
      }
      parsed = decoded as { value?: unknown; savedAt?: unknown };
    } catch {
      memorySnapshot = EMPTY_SNAPSHOT;
      memorySavedAt = 0;
      return EMPTY_SNAPSHOT;
    }

    const savedAt = typeof parsed.savedAt === "number" && Number.isFinite(parsed.savedAt)
      ? parsed.savedAt
      : 0;
    const age = Date.now() - savedAt;
    if (savedAt <= 0 || age < -60_000 || age > MAX_AGE_MS) {
      memorySnapshot = EMPTY_SNAPSHOT;
      memorySavedAt = 0;
      return EMPTY_SNAPSHOT;
    }
    memorySnapshot = normalizeSnapshot(parsed.value);
    memorySavedAt = savedAt;
  } catch {
    storageWritable = false;
    // Private browsing can disable storage; the in-memory checklist still works.
    return activeMemorySnapshot();
  }
  return memorySnapshot;
}

function getServerSnapshot(): string {
  return EMPTY_SNAPSHOT;
}

function subscribe(onStoreChange: () => void): () => void {
  let expiryTimer: number | undefined;

  const scheduleExpiry = () => {
    if (expiryTimer !== undefined) {
      window.clearTimeout(expiryTimer);
      expiryTimer = undefined;
    }
    const snapshot = getSnapshot();
    if (snapshot === EMPTY_SNAPSHOT || memorySavedAt <= 0) return;
    const remaining = MAX_AGE_MS - (Date.now() - memorySavedAt);
    expiryTimer = window.setTimeout(() => {
      expiryTimer = undefined;
      memorySnapshot = EMPTY_SNAPSHOT;
      memorySavedAt = 0;
      onStoreChange();
    }, Math.max(remaining, 0) + 25);
  };
  const notify = () => {
    scheduleExpiry();
    onStoreChange();
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === STORAGE_KEY) notify();
  };

  window.addEventListener("storage", onStorage);
  window.addEventListener("pageshow", notify);
  window.addEventListener(CHANGE_EVENT, notify);
  scheduleExpiry();
  return () => {
    if (expiryTimer !== undefined) window.clearTimeout(expiryTimer);
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("pageshow", notify);
    window.removeEventListener(CHANGE_EVENT, notify);
  };
}

function saveSnapshot(value: string): void {
  memorySnapshot = value;
  memorySavedAt = value === EMPTY_SNAPSHOT ? 0 : Date.now();
  try {
    if (value === EMPTY_SNAPSHOT) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ value, savedAt: memorySavedAt }));
    }
    storageWritable = true;
  } catch {
    storageWritable = false;
    // Keep the memory fallback when storage is unavailable.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function SafetyChecklist() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const completed = [...snapshot].filter((value) => value === "1").length;
  const allDone = completed === ITEMS.length;

  const toggle = (index: number) => {
    const next = [...snapshot];
    next[index] = next[index] === "1" ? "0" : "1";
    saveSnapshot(next.join(""));
  };

  return (
    <section className={allDone ? "safety-checklist checklist-complete" : "safety-checklist"} id="field-checklist" aria-labelledby="checklist-title">
      <header className="checklist-head">
        <span className="checklist-icon"><ClipboardCheck size={23} /></span>
        <div>
          <div className="checklist-kicker"><ShieldCheck size={14} /> قبل ما توقف على البحر</div>
          <h2 id="checklist-title">قائمة السلامة الميدانية</h2>
          <p>التوقع يساعدك تخطط، أما القرار الأخير يتاخذ قدّام البحر.</p>
        </div>
        <span className="offline-badge"><WifiOff size={14} /> متاحة دون اتصال</span>
      </header>

      <div className="checklist-progress-wrap">
        <div className="checklist-progress-copy">
          <strong>{allDone ? "راجعت النقاط الكل" : `${completed} من ${ITEMS.length} مكتملة`}</strong>
          <span>{allDone ? "ابقَ مستعداً لإلغاء الحصة إذا تبدل الواقع." : "راجع كل نقطة في المكان، موش من الدار فقط."}</span>
        </div>
        <div
          className="checklist-progress"
          role="progressbar"
          aria-label="تقدم قائمة السلامة"
          aria-valuemin={0}
          aria-valuemax={ITEMS.length}
          aria-valuenow={completed}
        >
          <i style={{ width: `${(completed / ITEMS.length) * 100}%` }} />
        </div>
      </div>

      <div className="checklist-items">
        {ITEMS.map((item, index) => {
          const checked = snapshot[index] === "1";
          return (
            <label className={checked ? "check-item checked" : "check-item"} key={item}>
              <input type="checkbox" checked={checked} onChange={() => toggle(index)} />
              <span className="custom-check" aria-hidden="true">{checked && <Check size={15} />}</span>
              <span>{item}</span>
            </label>
          );
        })}
      </div>

      <div className="checklist-footer">
        <p><strong>مهم:</strong> اكتمال القائمة ما يضمنش السلامة وما يعوضش تحذيرات السلطات. تتصفّر تلقائياً بعد 6 ساعات.</p>
        {completed > 0 && <button type="button" onClick={() => saveSnapshot(EMPTY_SNAPSHOT)}><RotateCcw size={15} /> صفّر القائمة</button>}
      </div>
    </section>
  );
}
