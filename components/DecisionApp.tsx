"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Check, CircleAlert, Database, RefreshCw, Server } from "lucide-react";
import { DecisionResult } from "@/components/DecisionResult";
import { LoadingPreview } from "@/components/LoadingPreview";
import { Planner } from "@/components/Planner";
import { requestApiHealth, requestDecision } from "@/lib/api";
import { tunisTodayIso } from "@/lib/format";
import type { DecisionResponse, ForecastDecisionRequest } from "@/lib/types";

const initialRequest = (): ForecastDecisionRequest => ({
  location: {
    latitude: 36.4561,
    longitude: 10.7389,
    name: "نابل",
  },
  target_date: tunisTodayIso(),
  spot: {
    seaward_orientation_deg: 90,
    orientation_source: "estimated",
    shore_type: "sandy",
    exposure: "open",
  },
  angler: {
    experience: "intermediate",
    target_species: "general",
    session_hours: 3,
  },
});

const REQUEST_TIMEOUT_MS = 30_000;
const subscribeToHydration = () => () => undefined;

type ApiState =
  | { status: "checking"; version?: undefined; engineVersion?: undefined; message?: undefined }
  | { status: "online"; version: string; engineVersion: string; message?: undefined }
  | { status: "offline"; version?: undefined; engineVersion?: undefined; message: string };

function fingerprint(value: ForecastDecisionRequest): string {
  return JSON.stringify(value);
}

export function DecisionApp() {
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false);
  const [request, setRequest] = useState<ForecastDecisionRequest>(initialRequest);
  const [evaluatedRequest, setEvaluatedRequest] = useState<ForecastDecisionRequest | null>(null);
  const [result, setResult] = useState<DecisionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiState, setApiState] = useState<ApiState>({ status: "checking" });
  const controllerRef = useRef<AbortController | null>(null);
  const healthControllerRef = useRef<AbortController | null>(null);

  const checkApi = useCallback(async () => {
    healthControllerRef.current?.abort();
    const controller = new AbortController();
    healthControllerRef.current = controller;
    try {
      const health = await requestApiHealth(controller.signal);
      if (!controller.signal.aborted) {
        setApiState({
          status: "online",
          version: health.version,
          engineVersion: health.engine_version,
        });
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setApiState({
          status: "offline",
          message: cause instanceof Error ? cause.message : "تعذر الاتصال بمحرك Peche TN.",
        });
      }
    } finally {
      if (healthControllerRef.current === controller) healthControllerRef.current = null;
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void checkApi(), 0);
    return () => {
      window.clearTimeout(timer);
      healthControllerRef.current?.abort();
    };
  }, [checkApi]);

  const changeRequest = (next: ForecastDecisionRequest) => {
    setRequest(next);
    setError(null);
  };

  const submit = async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    const submittedRequest = structuredClone(request);
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    window.setTimeout(
      () => document.getElementById("analysis-progress")?.scrollIntoView({ behavior: "smooth", block: "center" }),
      80,
    );
    try {
      const decision = await requestDecision(submittedRequest, controller.signal);
      setResult(decision);
      setEvaluatedRequest(submittedRequest);
      setApiState((current) => {
        if (current.status === "offline") {
          window.setTimeout(() => void checkApi(), 0);
          return { status: "checking" };
        }
        return current;
      });
      window.setTimeout(
        () => document.getElementById("decision")?.scrollIntoView({ behavior: "smooth", block: "start" }),
        100,
      );
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError" && !timedOut) return;
      setError(
        timedOut
          ? "التحليل استغرق أكثر من 30 ثانية. ثبّت اتصالك وعاود المحاولة."
          : cause instanceof Error
            ? cause.message
            : "تعذر إصدار القرار.",
      );
      window.setTimeout(
        () => document.getElementById("planner-error")?.scrollIntoView({ behavior: "smooth", block: "center" }),
        60,
      );
    } finally {
      window.clearTimeout(timeoutId);
      if (controllerRef.current === controller) {
        setLoading(false);
        controllerRef.current = null;
      }
    }
  };

  const isDirty = Boolean(
    result && evaluatedRequest && fingerprint(request) !== fingerprint(evaluatedRequest),
  );

  if (!hydrated) {
    return (
      <section className="planner-shell planner-boot" id="planner" aria-label="جاري تجهيز مخطط الحصة">
        <div className="boot-line boot-kicker" />
        <div className="boot-line boot-title" />
        <div className="boot-grid" aria-hidden="true"><span /><span /><span /></div>
      </section>
    );
  }

  return (
    <>
      <section className={`api-console api-${apiState.status}`} aria-live="polite" data-testid="api-console">
        <div className="api-console-state">
          <span className="api-state-icon">
            {apiState.status === "checking" ? <RefreshCw className="spin" size={18} /> : apiState.status === "online" ? <Check size={18} /> : <CircleAlert size={18} />}
          </span>
          <span>
            <small>حالة الخدمة العامة</small>
            <strong>{apiState.status === "checking" ? "نتثبتوا من المحرك…" : apiState.status === "online" ? "المحرك متصل" : "المحرك غير متصل"}</strong>
          </span>
          {apiState.status === "online" && <bdi>API {apiState.version} · Engine {apiState.engineVersion}</bdi>}
          {apiState.status === "offline" && <button type="button" onClick={() => { setApiState({ status: "checking" }); void checkApi(); }}><RefreshCw size={14} /> أعد الفحص</button>}
        </div>
        {apiState.status === "offline" && <p><CircleAlert size={14} />{apiState.message} لن نصدر قراراً وهمياً عند انقطاع الخادم.</p>}
        <div className="api-provider-strip" aria-label="مصادر البيانات المستخدمة">
          <span><Database size={14} /> Open-Meteo طقس وبحر</span>
          <span><Database size={14} /> METAR رصد محطات</span>
          <span><Server size={14} /> Overpass للاتجاه عند الطلب</span>
          <span><Server size={14} /> Gemini اختياري بمفتاحك</span>
        </div>
      </section>
      <Planner
        value={request}
        loading={loading}
        error={error}
        hasResult={Boolean(result)}
        isDirty={isDirty}
        onChange={changeRequest}
        onSubmit={submit}
      />
      {loading && <LoadingPreview />}
      {result && evaluatedRequest && (
        <DecisionResult
          key={result.generated_at}
          result={result}
          request={evaluatedRequest}
          stale={isDirty}
        />
      )}
    </>
  );
}
