// جلب Open-Meteo مباشرة من متصفح المستخدم (بعنوان IP جهازه لا من سيرفر Peche TN).
// Open-Meteo يفتح CORS بالكامل، وبذلك تتوزع الحصة اليومية على IP كل مستخدم بدل
// IP الخادم المشترك. الخادم يعيد التحقق من البنية والتواريخ كأنه جلبها بنفسه،
// ويعود للجلب الخادمي احتياطاً إذا فشل هذا المسار.

const MARINE_URL = "https://marine-api.open-meteo.com/v1/marine";
const WEATHER_URL = "https://api.open-meteo.com/v1/forecast";
const OPEN_METEO_TIMEOUT_MS = 12_000;

// نفس متغيرات الخادم حرفياً حتى تبقى بنية الحزمة متطابقة.
const MARINE_HOURLY = [
  "wave_height",
  "wave_period",
  "wave_direction",
  "wind_wave_height",
  "wind_wave_period",
  "wind_wave_direction",
  "swell_wave_height",
  "swell_wave_period",
  "swell_wave_direction",
  "sea_surface_temperature",
  "ocean_current_velocity",
  "ocean_current_direction",
  "sea_level_height_msl",
];

const WEATHER_HOURLY = [
  "temperature_2m",
  "apparent_temperature",
  "relative_humidity_2m",
  "dew_point_2m",
  "cloud_cover",
  "shortwave_radiation",
  "uv_index",
  "lightning_potential",
  "precipitation",
  "precipitation_probability",
  "weather_code",
  "pressure_msl",
  "visibility",
  "wind_speed_10m",
  "wind_direction_10m",
  "wind_gusts_10m",
  "cape",
];

export interface OpenMeteoBundle {
  marine: unknown;
  weather: unknown;
}

function addDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

async function fetchJson(url: string, params: URLSearchParams, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`${url}?${params.toString()}`, { signal, cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Open-Meteo ${response.status}`);
  }
  const body: unknown = await response.json();
  if (!body || typeof body !== "object") {
    throw new Error("Open-Meteo أعاد استجابة غير كائن.");
  }
  return body;
}

export async function fetchOpenMeteoBundle(
  latitude: number,
  longitude: number,
  targetDate: string,
  signal?: AbortSignal,
): Promise<OpenMeteoBundle> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(() => controller.abort(), OPEN_METEO_TIMEOUT_MS);
  try {
    const common = {
      latitude: String(latitude),
      longitude: String(longitude),
      timezone: "Africa/Tunis",
      start_date: addDays(targetDate, -3),
      end_date: addDays(targetDate, 1),
    };
    const marineParams = new URLSearchParams({
      ...common,
      hourly: MARINE_HOURLY.join(","),
      cell_selection: "sea",
    });
    const weatherParams = new URLSearchParams({
      ...common,
      hourly: WEATHER_HOURLY.join(","),
      daily: "sunrise,sunset,moonrise,moonset",
      wind_speed_unit: "kmh",
      cell_selection: "nearest",
    });
    const [marine, weather] = await Promise.all([
      fetchJson(MARINE_URL, marineParams, controller.signal),
      fetchJson(WEATHER_URL, weatherParams, controller.signal),
    ]);
    return { marine, weather };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export function clientOpenMeteoDisabled(): boolean {
  return process.env.NEXT_PUBLIC_DISABLE_CLIENT_OPEN_METEO === "1";
}
