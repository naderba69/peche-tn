import type {
  AutoOrientationResponse,
  DecisionResponse,
  ForecastDecisionRequest,
  GeminiKeyVerificationResponse,
  GeminiReportResponse,
  RankSpotsRequest,
  RankSpotsResponse,
} from "@/lib/types";

const CACHE_TTL_MS = 10 * 60 * 1000;

interface CachedDecision {
  savedAt: number;
  response: DecisionResponse;
}

interface ApiErrorBody {
  detail?: { message_ar?: string; code?: string } | string;
}

export interface ApiHealthResponse {
  status: string;
  version: string;
  engine_version: string;
  schema_version: string;
  time: string;
  upstream_cache: {
    entries: number;
    hits: number;
    misses: number;
    scope: string;
  };
}

function cacheKey(payload: ForecastDecisionRequest): string {
  return `peche-tn:v9:${JSON.stringify(payload)}`;
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as ApiErrorBody).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && typeof detail.message_ar === "string") {
    return detail.message_ar;
  }
  return fallback;
}

async function parseResponse<T>(response: Response, fallback: string): Promise<T> {
  const raw = await response.text();
  let body: unknown = null;
  if (raw) {
    try {
      body = JSON.parse(raw) as unknown;
    } catch {
      if (!response.ok) {
        throw new Error(
          response.status >= 500
            ? "بوابة Peche TN أعادت خطأ خادماً غير صالح بدل JSON. الخدمة غير متصلة حالياً؛ أعد المحاولة بعد إصلاح النشر."
            : fallback,
        );
      }
      throw new Error("استجابة خدمة Peche TN غير صالحة؛ لم نستعمل بيانات ناقصة لإصدار قرار.");
    }
  }
  if (!response.ok) throw new Error(errorMessage(body, fallback));
  if (body === null) throw new Error("خدمة Peche TN أعادت استجابة فارغة.");
  return body as T;
}

export async function requestRankSpots(
  payload: RankSpotsRequest,
  signal?: AbortSignal,
): Promise<RankSpotsResponse> {
  const response = await fetch("/api/v1/decisions/rank-spots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  return parseResponse<RankSpotsResponse>(
    response,
    "تعذر ترتيب البقع الآن. حاول من جديد.",
  );
}

export async function requestApiHealth(signal?: AbortSignal): Promise<ApiHealthResponse> {
  const response = await fetch("/api/health", { signal, cache: "no-store" });
  return parseResponse<ApiHealthResponse>(
    response,
    "تعذر الاتصال بمحرك Peche TN.",
  );
}

export async function requestDecision(
  payload: ForecastDecisionRequest,
  signal?: AbortSignal,
): Promise<DecisionResponse> {
  const key = cacheKey(payload);
  try {
    const cached = window.sessionStorage.getItem(key);
    if (cached) {
      const value = JSON.parse(cached) as CachedDecision;
      if (Date.now() - value.savedAt < CACHE_TTL_MS) return value.response;
      window.sessionStorage.removeItem(key);
    }
  } catch {
    // Storage can be disabled; network remains functional.
  }

  const response = await fetch("/api/v1/decisions/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const decision = await parseResponse<DecisionResponse>(
    response,
    "تعذر إصدار القرار الآن. حاول من جديد.",
  );
  try {
    window.sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), response: decision }));
  } catch {
    // Non-fatal.
  }
  return decision;
}

export async function requestAutoOrientation(
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
): Promise<AutoOrientationResponse> {
  const response = await fetch("/api/v1/spots/orientation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude, longitude }),
    signal,
  });
  return parseResponse<AutoOrientationResponse>(
    response,
    "تعذر حساب اتجاه البحر آلياً؛ ثبّت السهم يدوياً.",
  );
}

export async function verifyGeminiKey(
  apiKey: string,
  signal?: AbortSignal,
): Promise<GeminiKeyVerificationResponse> {
  const response = await fetch("/api/v1/gemini/verify", {
    method: "POST",
    headers: { "X-Gemini-API-Key": apiKey },
    signal,
    cache: "no-store",
  });
  return parseResponse<GeminiKeyVerificationResponse>(
    response,
    "تعذر اختبار المفتاح. لم يُحفظ شيء في الخادم.",
  );
}

export async function requestGeminiReport(
  apiKey: string,
  request: ForecastDecisionRequest,
  decision: DecisionResponse,
  signal?: AbortSignal,
): Promise<GeminiReportResponse> {
  const response = await fetch("/api/v1/reports/gemini", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Gemini-API-Key": apiKey,
    },
    body: JSON.stringify({ request, decision }),
    signal,
    cache: "no-store",
  });
  return parseResponse<GeminiReportResponse>(
    response,
    "تعذر توليد تقرير Gemini؛ التقرير الحتمي بقي متاحاً.",
  );
}
