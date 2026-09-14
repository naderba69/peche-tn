"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  AlertTriangle,
  Check,
  Eye,
  EyeOff,
  Info,
  KeyRound,
  RefreshCw,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import { requestGeminiReport, verifyGeminiKey } from "@/lib/api";
import { formatGeneratedAt } from "@/lib/format";
import type { DecisionResponse, ForecastDecisionRequest, GeminiReportResponse } from "@/lib/types";

interface GeminiReportProps {
  result: DecisionResponse;
  request: ForecastDecisionRequest;
}

const GEMINI_KEY_STORAGE = "peche-tn:gemini-api-key";
const GEMINI_KEY_EVENT = "peche-tn:gemini-key-change";
const GEMINI_VERIFY_TIMEOUT_MS = 26_000;
const GEMINI_GENERATE_TIMEOUT_MS = 42_000;

function subscribeGeminiKey(onStoreChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === GEMINI_KEY_STORAGE) onStoreChange();
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(GEMINI_KEY_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(GEMINI_KEY_EVENT, onStoreChange);
  };
}

function geminiKeySnapshot(): string {
  try {
    return window.localStorage.getItem(GEMINI_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

const emptyGeminiKeySnapshot = () => "";

/**
 * تقرير Gemini الاختياري — يوضع في آخر الصفحة دائماً.
 * Gemini يكتب السرد فقط؛ محرك Peche TN وحده يحسم القرار والأرقام.
 */
export function GeminiReport({ result, request }: GeminiReportProps) {
  const persistedGeminiKey = useSyncExternalStore(
    subscribeGeminiKey,
    geminiKeySnapshot,
    emptyGeminiKeySnapshot,
  );
  const [geminiKeyDraft, setGeminiKeyDraft] = useState<string | null>(null);
  const [storageRiskChoice, setStorageRiskChoice] = useState<boolean | null>(null);
  const geminiKey = geminiKeyDraft ?? persistedGeminiKey;
  const geminiKeySaved = Boolean(persistedGeminiKey && persistedGeminiKey === geminiKey);
  const storageRiskAccepted = storageRiskChoice ?? Boolean(persistedGeminiKey);
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [geminiBusy, setGeminiBusy] = useState<"idle" | "verify" | "generate">("idle");
  const [geminiStatus, setGeminiStatus] = useState<{
    kind: "success" | "error" | "info";
    text: string;
  } | null>(null);
  const [geminiReport, setGeminiReport] = useState<GeminiReportResponse | null>(null);
  const geminiAbort = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      const activeRequest = geminiAbort.current;
      geminiAbort.current = null;
      activeRequest?.abort();
    },
    [],
  );

  const saveGeminiKey = () => {
    if (!storageRiskAccepted || !geminiKey.trim()) return;
    try {
      window.localStorage.setItem(GEMINI_KEY_STORAGE, geminiKey.trim());
      setGeminiKeyDraft(null);
      setStorageRiskChoice(true);
      window.dispatchEvent(new Event(GEMINI_KEY_EVENT));
      setGeminiStatus({
        kind: "info",
        text: "حُفظ المفتاح في localStorage على هذا المتصفح فقط. لم يُرسل بعد إلى Google.",
      });
    } catch {
      setGeminiStatus({ kind: "error", text: "تعذر الحفظ المحلي؛ إعدادات المتصفح قد تمنع التخزين." });
    }
  };

  const deleteGeminiKey = () => {
    const activeRequest = geminiAbort.current;
    geminiAbort.current = null;
    activeRequest?.abort();
    try {
      window.localStorage.removeItem(GEMINI_KEY_STORAGE);
    } catch {
      // State is still cleared when browser storage is unavailable.
    }
    window.dispatchEvent(new Event(GEMINI_KEY_EVENT));
    setGeminiKeyDraft("");
    setShowGeminiKey(false);
    setStorageRiskChoice(false);
    setGeminiReport(null);
    setGeminiBusy("idle");
    setGeminiStatus({ kind: "success", text: "حُذف المفتاح من هذا المتصفح." });
  };

  const testGeminiKey = async () => {
    if (!geminiKey.trim()) return;
    geminiAbort.current?.abort();
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, GEMINI_VERIFY_TIMEOUT_MS);
    geminiAbort.current = controller;
    setGeminiBusy("verify");
    setGeminiStatus(null);
    try {
      const verification = await verifyGeminiKey(geminiKey.trim(), controller.signal);
      setGeminiStatus({ kind: "success", text: verification.message_ar });
    } catch (cause) {
      if (controller.signal.aborted && !timedOut) return;
      setGeminiStatus({
        kind: "error",
        text: timedOut
          ? "انتهت مهلة اختبار Gemini؛ لم يُخزن المفتاح في الخادم."
          : cause instanceof Error
            ? cause.message
            : "تعذر اختبار المفتاح.",
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (geminiAbort.current === controller) {
        geminiAbort.current = null;
        setGeminiBusy("idle");
      }
    }
  };

  const generateWithGemini = async () => {
    if (!geminiKey.trim()) return;
    geminiAbort.current?.abort();
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, GEMINI_GENERATE_TIMEOUT_MS);
    geminiAbort.current = controller;
    setGeminiBusy("generate");
    setGeminiStatus({
      kind: "info",
      text: "أرسلنا إلى Gemini حزمة سرد مصغرة بلا الإحداثيات أو السلاسل الرقمية الخام؛ يمكنك إيقاف الانتظار.",
    });
    try {
      const generated = await requestGeminiReport(
        geminiKey.trim(),
        request,
        result,
        controller.signal,
      );
      setGeminiReport(generated);
      setGeminiStatus({
        kind: "success",
        text: "تم التحقق من JSON وبناء التقرير. القرار والأرقام بقيت من المحرك الحتمي.",
      });
    } catch (cause) {
      if (controller.signal.aborted && !timedOut) return;
      setGeminiReport(null);
      setGeminiStatus({
        kind: "error",
        text: timedOut
          ? "أوقفنا انتظار Gemini عند المهلة المحددة؛ التقرير الحتمي بقي كاملاً."
          : cause instanceof Error
            ? `${cause.message} التقرير الحتمي بقي كاملاً.`
            : "تعذر توليد السرد؛ التقرير الحتمي بقي كاملاً.",
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (geminiAbort.current === controller) {
        geminiAbort.current = null;
        setGeminiBusy("idle");
      }
    }
  };

  const cancelGeminiGeneration = () => {
    const activeRequest = geminiAbort.current;
    geminiAbort.current = null;
    activeRequest?.abort();
    setGeminiBusy("idle");
    setGeminiStatus({
      kind: "info",
      text: "ألغيت انتظار Gemini؛ التقرير الحتمي بقي كاملاً وجاهزاً للنسخ أو التنزيل.",
    });
  };

  return (
    <section className="report-gemini" aria-labelledby="gemini-report-title">
      <div className="report-gemini-heading">
        <span><WandSparkles size={20} /></span>
        <div>
          <h3 id="gemini-report-title">تقرير Gemini الاختياري</h3>
          <p>Gemini يكتب الشرح فقط؛ محرك Peche TN وحده يحسم القرار والأرقام.</p>
        </div>
        {geminiReport && <b><Check size={14} /> JSON متحقق</b>}
      </div>
      <div className="gemini-risk" role="note">
        <AlertTriangle size={18} />
        <p>
          <strong>تنبيه أمني قبل الحفظ:</strong> localStorage موش خزنة أسرار؛ أي سكربت يعمل في نفس الموقع، إضافة متصفح ذات صلاحية، أو شخص يستعمل نفس الجهاز قد يصل للمفتاح. عند الاختبار أو التوليد يُرسل المفتاح مؤقتاً عبر HTTPS إلى API ثم Google، ولا يخزنه أو يسجله خادم Peche TN. Google يستقبل Evidence Packet وفق شروط خدمته.
        </p>
      </div>
      <div className="gemini-key-row">
        <label>
          <span><KeyRound size={15} /> مفتاح Google AI Studio</span>
          <span className="gemini-key-input">
            <input
              data-testid="gemini-key-input"
              type={showGeminiKey ? "text" : "password"}
              value={geminiKey}
              autoComplete="off"
              spellCheck={false}
              placeholder="ألصق المفتاح هنا"
              aria-label="مفتاح Google Gemini"
              onChange={(event) => {
                setGeminiKeyDraft(event.target.value);
                setGeminiStatus(null);
              }}
            />
            <button
              type="button"
              aria-label={showGeminiKey ? "أخفِ المفتاح" : "أظهر المفتاح"}
              onClick={() => setShowGeminiKey((visible) => !visible)}
            >
              {showGeminiKey ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </span>
        </label>
        <label className="gemini-consent">
          <input
            type="checkbox"
            checked={storageRiskAccepted}
            onChange={(event) => setStorageRiskChoice(event.target.checked)}
          />
          <span>فهمت مخاطر التخزين المحلي وأريد حفظ المفتاح دائماً على هذا المتصفح.</span>
        </label>
        <div className="gemini-key-actions">
          <button
            type="button"
            data-testid="gemini-save-key"
            disabled={!geminiKey.trim() || !storageRiskAccepted}
            onClick={saveGeminiKey}
          >
            <KeyRound size={15} /> {geminiKeySaved ? "محفوظ محلياً" : "احفظ محلياً"}
          </button>
          <button
            type="button"
            data-testid="gemini-test-key"
            disabled={!geminiKey.trim() || geminiBusy !== "idle"}
            onClick={() => void testGeminiKey()}
          >
            <RefreshCw className={geminiBusy === "verify" ? "spin" : ""} size={15} />
            {geminiBusy === "verify" ? "نختبر…" : "اختبر المفتاح"}
          </button>
          <button
            type="button"
            className="gemini-delete"
            disabled={!geminiKey && !geminiKeySaved}
            onClick={deleteGeminiKey}
          >
            <Trash2 size={15} /> احذف
          </button>
        </div>
      </div>
      <button
        type="button"
        className="gemini-generate"
        data-testid="gemini-generate"
        disabled={!geminiKey.trim() || geminiBusy === "verify"}
        onClick={() => {
          if (geminiBusy === "generate") cancelGeminiGeneration();
          else void generateWithGemini();
        }}
      >
        {geminiBusy === "generate" ? <X size={18} /> : <Sparkles size={18} />}
        {geminiBusy === "generate" ? "أوقف انتظار Gemini" : "ولّد التقرير المنظم عند الطلب"}
      </button>
      {geminiStatus && (
        <div className={`gemini-status ${geminiStatus.kind}`} role="status" data-testid="gemini-status">
          {geminiStatus.kind === "success" ? <Check size={16} /> : <Info size={16} />}
          <span>{geminiStatus.text}</span>
        </div>
      )}
      {geminiReport && (
        <div className="gemini-narrative" data-testid="gemini-narrative">
          <h4>السرد المقيد</h4>
          <p>{geminiReport.narrative.executive_summary_ar}</p>
          <div>
            <article><strong>التوقيت والماء</strong><ul>{geminiReport.narrative.timing_and_water_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <article><strong>التحليل السابق</strong><ul>{geminiReport.narrative.temporal_analysis_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <article><strong>تفاعل العوامل</strong><ul>{geminiReport.narrative.factor_interactions_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <article><strong>التكتيك الميداني</strong><ul>{geminiReport.narrative.field_tactics_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <article><strong>Unknown</strong><ul>{geminiReport.narrative.unknowns_ar.map((item) => <li key={item}>{item}</li>)}</ul></article>
          </div>
          <footer>
            <span>model: {geminiReport.metadata.model}</span>
            <span>prompt: {geminiReport.metadata.prompt_version}</span>
            <span>hash: <bdi>{geminiReport.metadata.input_sha256}</bdi></span>
            <span>{formatGeneratedAt(geminiReport.metadata.generated_at)}</span>
          </footer>
        </div>
      )}
    </section>
  );
}
