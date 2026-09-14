"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import SpotMap from "@/components/SpotMap";
import {
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronDown,
  Compass,
  Crosshair,
  Info,
  LocateFixed,
  MapPinned,
  RefreshCw,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Waves,
} from "lucide-react";
import { requestAutoOrientation } from "@/lib/api";
import { formatDate, formatDateChip, tunisTodayIso } from "@/lib/format";
import { SPOT_PRESETS } from "@/lib/spots";
import type {
  ExperienceLevel,
  Coordinates as LocationInput,
  FieldReport,
  ForecastDecisionRequest,
  OfficialWarning,
  ShoreType,
  TargetSpecies,
} from "@/lib/types";

const ORIENTATION_PRESETS = [
  { label: "شمال", short: "ش", value: 0 },
  { label: "شرق", short: "ق", value: 90 },
  { label: "جنوب", short: "ج", value: 180 },
  { label: "غرب", short: "غ", value: 270 },
];

const shoreOptions: Array<{ value: ShoreType; label: string; hint: string }> = [
  { value: "sandy", label: "رملي", hint: "شاطئ مفتوح" },
  { value: "rocky", label: "صخري", hint: "صخور وحواف" },
  { value: "jetty", label: "رصيف", hint: "لسان بحري" },
  { value: "cliff", label: "جرف", hint: "وقوف مرتفع" },
];

const exposureOptions: Array<{ value: ForecastDecisionRequest["spot"]["exposure"]; label: string }> = [
  { value: "open", label: "مفتوحة" },
  { value: "partly_sheltered", label: "شبه محمية" },
  { value: "sheltered", label: "محمية" },
];

function addIsoDays(value: string, amount: number): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + amount));
  return date.toISOString().slice(0, 10);
}

function directionName(degrees: number): string {
  const names = ["شمال", "شمال شرقي", "شرق", "جنوب شرقي", "جنوب", "جنوب غربي", "غرب", "شمال غربي"];
  return names[Math.round(((degrees % 360) / 45)) % 8];
}

function reportKindLabel(kind: FieldReport["kind"]): string {
  switch (kind) {
    case "fouling": return "أعشاب / عوالق";
    case "turbidity": return "عكارة";
    case "rip_current": return "تيار ساحب";
    case "visibility": return "رؤية / غبار";
  }
}

function reportSeverityLabel(severity: FieldReport["severity"]): string {
  return severity === "dense" ? "كثيف" : "موجود";
}

function reportSourceLabel(source: FieldReport["source"]): string {
  switch (source) {
    case "user": return "بلاغي";
    case "community": return "صيّادون";
    case "official": return "رسمي";
  }
}

interface PlannerProps {
  value: ForecastDecisionRequest;
  loading: boolean;
  error: string | null;
  hasResult: boolean;
  isDirty: boolean;
  onChange: (value: ForecastDecisionRequest) => void;
  onSubmit: () => void;
}

export function Planner({ value, loading, error, hasResult, isDirty, onChange, onSubmit }: PlannerProps) {
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(true);
  const [mapMode, setMapMode] = useState<"spot" | "seaward">("spot");
  const [orientationLoading, setOrientationLoading] = useState(false);
  const [orientationError, setOrientationError] = useState<string | null>(null);
  const orientationAbort = useRef<AbortController | null>(null);
  const valueRef = useRef(value);
  const today = tunisTodayIso();
  const forecastDates = useMemo(() => Array.from({ length: 7 }, (_, index) => addIsoDays(today, index)), [today]);

  const patch = (partial: Partial<ForecastDecisionRequest>) => {
    const nextValue = { ...valueRef.current, ...partial };
    valueRef.current = nextValue;
    onChange(nextValue);
  };
  const patchSpot = (partial: Partial<ForecastDecisionRequest["spot"]>) => {
    const current = valueRef.current;
    patch({ spot: { ...current.spot, ...partial } });
  };
  const patchAngler = (partial: Partial<ForecastDecisionRequest["angler"]>) => {
    const current = valueRef.current;
    patch({ angler: { ...current.angler, ...partial } });
  };

  const [draftKind, setDraftKind] = useState<FieldReport["kind"]>("fouling");
  const [draftSeverity, setDraftSeverity] = useState<FieldReport["severity"]>("present");
  const [draftSource, setDraftSource] = useState<FieldReport["source"]>("user");

  const addReport = () => {
    const reports = valueRef.current.field_reports ?? [];
    if (reports.length >= 10) return;
    const report: FieldReport = {
      kind: draftKind,
      severity: draftSeverity,
      source: draftSource,
      reported_at: new Date().toISOString(),
    };
    patch({ field_reports: [...reports, report] });
  };
  const removeReport = (index: number) => {
    const reports = valueRef.current.field_reports ?? [];
    patch({ field_reports: reports.filter((_, i) => i !== index) });
  };
  const setTestCast = (hooked: boolean | null) => {
    patch({
      test_cast: hooked === null ? null : { cast_at: new Date().toISOString(), hooked },
    });
  };
  const patchOfficialWarning = (kind: string) => {
    if (kind === "none") {
      patch({ official_warning: null });
      return;
    }
    const warning: OfficialWarning = {
      source: "inm",
      kind: kind as OfficialWarning["kind"],
      level: "warning",
      issued_at: new Date().toISOString(),
    };
    patch({ official_warning: warning });
  };

  useEffect(() => {
    valueRef.current = value;
  }, [value]);
  useEffect(() => () => orientationAbort.current?.abort(), []);

  const calculateOrientation = async (location: LocationInput) => {
    orientationAbort.current?.abort();
    const controller = new AbortController();
    orientationAbort.current = controller;
    setOrientationLoading(true);
    setOrientationError(null);
    try {
      const result = await requestAutoOrientation(
        location.latitude,
        location.longitude,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      const current = valueRef.current;
      const stillSelected =
        current.location.latitude === location.latitude &&
        current.location.longitude === location.longitude;
      if (!stillSelected) return;
      if (result.status === "resolved" && result.orientation_deg !== null && result.evidence) {
        const nextValue: ForecastDecisionRequest = {
          ...current,
          spot: {
            ...current.spot,
            seaward_orientation_deg: result.orientation_deg,
            orientation_source: "overpass",
            orientation_evidence: result.evidence,
          },
        };
        valueRef.current = nextValue;
        onChange(nextValue);
      } else {
        setOrientationError(result.reasons_ar.join(" "));
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      setOrientationError(
        caught instanceof Error
          ? caught.message
          : "تعذر حساب الاتجاه آلياً؛ الاتجاه اليدوي بقي كما هو.",
      );
    } finally {
      if (!controller.signal.aborted) setOrientationLoading(false);
    }
  };

  const chooseLocation = (location: LocationInput) => {
    const current = valueRef.current;
    const nextValue = {
      ...current,
      location,
      spot: {
        ...current.spot,
        orientation_source: "manual" as const,
        orientation_evidence: null,
      },
    };
    valueRef.current = nextValue;
    onChange(nextValue);
    setGeoError(null);
    void calculateOrientation(location);
  };

  const setManualOrientation = (
    degrees: number,
    source: "manual" | "map" = "manual",
  ) => {
    orientationAbort.current?.abort();
    setOrientationLoading(false);
    setOrientationError(null);
    patchSpot({
      seaward_orientation_deg: Number(degrees.toFixed(1)),
      orientation_source: source,
      orientation_evidence: null,
    });
  };

  const chooseSeawardBearing = (degrees: number) => {
    setManualOrientation(degrees, "map");
  };

  const choosePreset = (id: string) => {
    const preset = SPOT_PRESETS.find((spot) => spot.id === id);
    if (!preset) return;
    const location = { name: preset.name, latitude: preset.latitude, longitude: preset.longitude };
    const nextValue: ForecastDecisionRequest = {
      ...valueRef.current,
      location,
      spot: {
        ...valueRef.current.spot,
        seaward_orientation_deg: preset.orientation,
        orientation_source: "estimated",
        orientation_evidence: null,
        shore_type: preset.shoreType,
      },
    };
    valueRef.current = nextValue;
    onChange(nextValue);
    setGeoError(null);
    void calculateOrientation(location);
  };

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setGeoError("المتصفح لا يدعم تحديد الموقع. اختار بقعة أو حدّدها على الخريطة.");
      return;
    }
    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const latitude = Number(position.coords.latitude.toFixed(5));
        const longitude = Number(position.coords.longitude.toFixed(5));
        if (latitude < 30 || latitude > 38.5 || longitude < 7 || longitude > 12.5) {
          setGeoError("الموقع خارج النطاق التونسي المدعوم حالياً.");
          setLocating(false);
          return;
        }
        chooseLocation({ name: "موقعي الحالي", latitude, longitude });
        setLocating(false);
      },
      () => {
        setGeoError("ما قدرناش نوصلوا لموقعك. اسمح بالموقع أو اختار نقطة من الخريطة.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const orientationEvidence =
    value.spot.orientation_source === "overpass" ? value.spot.orientation_evidence : null;
  const orientationConfidenceLabel = orientationEvidence
    ? { high: "مرتفعة", medium: "متوسطة", low: "منخفضة" }[orientationEvidence.confidence]
    : null;

  const submitLabel = loading
    ? "نجمع المعطيات ونبني التقرير…"
    : isDirty
      ? "حدّث التقرير والقرار"
      : hasResult
        ? "أعد توليد التقرير"
        : "ولّد التقرير البحري";

  return (
    <section className="planner-shell" id="planner" aria-labelledby="planner-title" aria-busy={loading}>
      <div className="section-kicker"><Sparkles size={15} /> تقرير بقعة</div>
      <div className="planner-heading">
        <div>
          <h2 id="planner-title">إعداد تقرير السيرفكاست</h2>
          <p>حدّد نقطة الوقوف، اليوم واتجاه عرض البحر؛ التقرير والقرار يخرجان معاً.</p>
        </div>
        <div className="privacy-note"><Check size={15} /> موقعك يبقى في متصفحك</div>
      </div>

      <div className="planner-flow">
        <section className="planner-step" aria-labelledby="location-step-title">
          <div className="step-heading">
            <span className="step-index">1</span>
            <div>
              <h3 id="location-step-title">وين باش تصطاد؟</h3>
              <p>استعمل موقعك أو اختار بقعة قريبة.</p>
            </div>
          </div>

          <button className="gps-primary" type="button" onClick={useMyLocation} disabled={locating}>
            <span className="gps-icon">{locating ? <RefreshCw className="spin" size={23} /> : <LocateFixed size={23} />}</span>
            <span>
              <strong>{locating ? "جاري تحديد موقعك…" : "استعمل موقعي الحالي"}</strong>
              <small>أسرع طريقة لاختيار نقطة الساحل</small>
            </span>
            <ArrowLeft size={19} className="gps-arrow" />
          </button>

          {geoError && <div className="field-message warning"><Info size={16} /> {geoError}</div>}

          <div className="selected-location" aria-live="polite">
            <span className="selected-location-icon"><MapPinned size={19} /></span>
            <span>
              <small>البقعة المختارة</small>
              <strong>{value.location.name ?? "نقطة على الساحل"}</strong>
            </span>
            <bdi>{value.location.latitude.toFixed(3)}°، {value.location.longitude.toFixed(3)}°</bdi>
          </div>

          <div className="quick-spots-block">
            <div className="field-caption">بقع شائعة</div>
            <div className="quick-spots" aria-label="بقع ساحلية شائعة">
              {SPOT_PRESETS.map((spot) => {
                const selected = spot.name === value.location.name;
                return (
                  <button
                    type="button"
                    className={selected ? "spot-chip selected" : "spot-chip"}
                    key={spot.id}
                    aria-pressed={selected}
                    onClick={() => choosePreset(spot.id)}
                  >
                    {selected && <Check size={14} />}{spot.name}
                  </button>
                );
              })}
            </div>
          </div>

          <button
            className="map-toggle"
            type="button"
            aria-expanded={showMap}
            aria-controls="spot-map-panel"
            onClick={() => setShowMap((visible) => !visible)}
          >
            <span><Crosshair size={18} /> {showMap ? "اخفِ الخريطة" : "حدّد نقطة بدقة على الخريطة"}</span>
            <ChevronDown size={18} />
          </button>
          {showMap && (
            <div className="map-reveal" id="spot-map-panel">
              <div className="map-mode-switch" role="group" aria-label="ماذا تريد تحديده على الخريطة؟">
                <button
                  type="button"
                  className={mapMode === "spot" ? "active" : ""}
                  aria-pressed={mapMode === "spot"}
                  onClick={() => setMapMode("spot")}
                >
                  <MapPinned size={15} /> نقطة الوقوف
                </button>
                <button
                  type="button"
                  className={mapMode === "seaward" ? "active" : ""}
                  aria-pressed={mapMode === "seaward"}
                  onClick={() => setMapMode("seaward")}
                >
                  <Compass size={15} /> اتجاه عرض البحر
                </button>
              </div>
              <SpotMap
                location={value.location}
                orientationDeg={value.spot.seaward_orientation_deg}
                mode={mapMode}
                onLocationChange={chooseLocation}
                onOrientationChange={chooseSeawardBearing}
              />
              <p>
                <Info size={14} />
                {mapMode === "spot"
                  ? "اضغط على موضع الوقوف فوق الساحل؛ بعده اختر «اتجاه عرض البحر»."
                  : "اضغط نقطة واضحة داخل عرض البحر. يبقى موضع الوقوف ثابتاً ويُحسب bearing بين النقطتين."}
              </p>
            </div>
          )}
        </section>

        <section className="planner-step" aria-labelledby="date-step-title">
          <div className="step-heading">
            <span className="step-index">2</span>
            <div>
              <h3 id="date-step-title">وقتاش الحصة؟</h3>
              <p>التوقعات متاحة للسبعة أيام الجاية.</p>
            </div>
          </div>

          <div className="date-strip" role="radiogroup" aria-label="اختيار يوم الحصة">
            {forecastDates.map((date, index) => {
              const parts = formatDateChip(date);
              const selected = value.target_date === date;
              return (
                <button
                  type="button"
                  role="radio"
                  key={date}
                  className={selected ? "date-chip selected" : "date-chip"}
                  aria-checked={selected}
                  onClick={() => patch({ target_date: date })}
                >
                  <span>{index === 0 ? "اليوم" : parts.weekday}</span>
                  <strong>{parts.day}</strong>
                  {selected && <Check size={14} />}
                </button>
              );
            })}
          </div>
          <label className="calendar-field">
            <CalendarDays size={18} />
            <span><small>تاريخ آخر</small><strong>{formatDate(value.target_date)}</strong></span>
            <input
              type="date"
              min={today}
              max={addIsoDays(today, 6)}
              value={value.target_date}
              aria-label="اختيار التاريخ من التقويم"
              onChange={(event) => event.target.value && patch({ target_date: event.target.value })}
            />
          </label>
        </section>

        <section className="planner-step" aria-labelledby="orientation-step-title">
          <div className="step-heading">
            <span className="step-index">3</span>
            <div>
              <h3 id="orientation-step-title">لوين يواجه البحر؟</h3>
              <p>الاتجاه يساعدنا نحسب الريح والموج على الشاطئ.</p>
            </div>
          </div>

          <div className="orientation-card">
            <div className="compass-visual" aria-hidden="true">
              <span className="compass-north">ش</span>
              <span className="compass-east">ق</span>
              <span className="compass-south">ج</span>
              <span className="compass-west">غ</span>
              <svg
                className="seaward-bearing-arrow"
                viewBox="0 0 64 64"
                style={{ transform: `rotate(${value.spot.seaward_orientation_deg}deg)` }}
              >
                <circle cx="32" cy="32" r="28" />
                <path d="M32 50V15" />
                <path className="arrow-head" d="M32 9 23 24h18Z" />
              </svg>
            </div>
            <div className="orientation-control">
              <div className="orientation-value">
                <span>الاتجاه نحو البحر</span>
                <strong>{directionName(value.spot.seaward_orientation_deg)} <bdi>{value.spot.seaward_orientation_deg}°</bdi></strong>
              </div>
              <input
                className="orientation-range"
                type="range"
                min="0"
                max="359"
                step="1"
                dir="ltr"
                aria-label="اتجاه البحر بالدرجات"
                value={value.spot.seaward_orientation_deg}
                onChange={(event) => setManualOrientation(Number(event.target.value))}
              />
              <div className="orientation-presets" aria-label="اتجاهات سريعة">
                {ORIENTATION_PRESETS.map((preset) => (
                  <button
                    type="button"
                    key={preset.value}
                    title={preset.label}
                    aria-label={preset.label}
                    className={value.spot.seaward_orientation_deg === preset.value ? "active" : ""}
                    onClick={() => setManualOrientation(preset.value)}
                  >
                    {preset.short}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="orientation-auto-panel" aria-live="polite">
            <div>
              <strong>حساب الساحل الآلي</strong>
              <span>OpenStreetMap Overpass — العمود المصحح على أقرب مقطع ساحلي</span>
            </div>
            <button
              type="button"
              className="orientation-recalculate"
              data-testid="orientation-recalculate"
              disabled={orientationLoading}
              onClick={() => void calculateOrientation(value.location)}
            >
              <RefreshCw className={orientationLoading ? "spin" : ""} size={16} />
              {orientationLoading ? "نحسب الاتجاه…" : "أعد حساب الاتجاه"}
            </button>
          </div>

          {orientationEvidence && (
            <div className="orientation-provenance" data-testid="orientation-provenance">
              <span><bdi>{orientationEvidence.orientation_deg.toFixed(1)}°</bdi><small>اتجاه البحر</small></span>
              <span><bdi>{orientationEvidence.coastline_tangent_deg.toFixed(1)}°</bdi><small>مماس الساحل</small></span>
              <span><bdi>{orientationEvidence.coastline_distance_m.toFixed(0)} م</bdi><small>مسافة الساحل</small></span>
              <span><bdi>{orientationEvidence.search_radius_m} م</bdi><small>نصف البحث</small></span>
              <span><bdi>{orientationEvidence.segments_used}</bdi><small>المقاطع</small></span>
              <span><bdi>{orientationConfidenceLabel}</bdi><small>الثقة</small></span>
              <p>
                <strong>{orientationEvidence.provider}</strong>
                <bdi>{orientationEvidence.server}</bdi>
              </p>
              {orientationEvidence.limitations_ar.map((item) => <p key={item}><Info size={14} /> {item}</p>)}
            </div>
          )}
          {orientationError && (
            <div className="field-message warning" data-testid="orientation-error">
              <Info size={16} />
              <span>{orientationError} لم نخترع اتجاهاً بديلاً؛ عدّل السهم يدوياً إن لزم.</span>
            </div>
          )}

          <p className="orientation-help">
            <Compass size={16} />
            <span><strong>التعريف الهندسي:</strong> وجّه السهم من نقطة وقوفك على الساحل إلى عرض البحر. لا تُدخل جهة سير الموج ولا جهة هبوب الريح؛ المحرك يقارن جهتي قدومهما بهذا السهم تلقائياً.</span>
          </p>
          {value.spot.orientation_source === "estimated" && (
            <div className="orientation-confirm">
              <span><Info size={16} /> الاتجاه الحالي أولي وقد لا يطابق انحناء الجزء الذي ستقف فيه.</span>
              <button type="button" onClick={() => setManualOrientation(value.spot.seaward_orientation_deg)}>
                <Check size={15} /> راجعته وهو صحيح
              </button>
            </div>
          )}

          <div className="field-group">
            <div className="field-caption">نوع الشاطئ</div>
            <div className="setting-options shore-options">
              {shoreOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={value.spot.shore_type === option.value ? "active" : ""}
                  aria-pressed={value.spot.shore_type === option.value}
                  onClick={() => patchSpot({ shore_type: option.value })}
                >
                  <Waves size={17} />
                  <span><strong>{option.label}</strong><small>{option.hint}</small></span>
                </button>
              ))}
            </div>
          </div>

          <details className="advanced-settings">
            <summary>
              <span><Settings2 size={18} /><strong>إعدادات متقدمة</strong></span>
              <span className="advanced-summary">خبرة، مدة، تعرض الشاطئ</span>
              <ChevronDown size={18} className="details-chevron" />
            </summary>
            <div className="advanced-content">
              <div className="field-group">
                <div className="field-caption">تعرض الشاطئ</div>
                <div className="segmented-control">
                  {exposureOptions.map((option) => (
                    <button
                      type="button"
                      key={option.value}
                      className={value.spot.exposure === option.value ? "active" : ""}
                      aria-pressed={value.spot.exposure === option.value}
                      onClick={() => patchSpot({ exposure: option.value })}
                    >{option.label}</button>
                  ))}
                </div>
              </div>
              <div className="advanced-grid">
                <label>
                  <span>الخبرة</span>
                  <select
                    value={value.angler.experience}
                    onChange={(event) => patchAngler({ experience: event.target.value as ExperienceLevel })}
                  >
                    <option value="beginner">مبتدئ — حدود أكثر تحفظاً</option>
                    <option value="intermediate">متوسط</option>
                    <option value="advanced">متقدم</option>
                  </select>
                </label>
                <label>
                  <span>مدة الحصة</span>
                  <select
                    value={value.angler.session_hours}
                    onChange={(event) => patchAngler({ session_hours: Number(event.target.value) })}
                  >
                    <option value={2}>ساعتان</option>
                    <option value={3}>3 ساعات</option>
                    <option value={4}>4 ساعات</option>
                  </select>
                </label>
                <label>
                  <span>الهدف</span>
                  <select
                    value={value.angler.target_species}
                    onChange={(event) => patchAngler({ target_species: event.target.value as TargetSpecies })}
                  >
                    <option value="general">صيد عام</option>
                    <option value="european_seabass">القاروص</option>
                    <option value="gilthead_seabream">الوراطة</option>
                    <option value="white_seabream">السار</option>
                    <option value="striped_seabream">المرمار</option>
                  </select>
                </label>
                <label>
                  <span>تحذير رسمي ساري (INM)</span>
                  <select
                    value={value.official_warning?.kind ?? "none"}
                    onChange={(event) => patchOfficialWarning(event.target.value)}
                  >
                    <option value="none">لا يوجد</option>
                    <option value="strong_wind">رياح قوية</option>
                    <option value="rough_sea">بحر هائج</option>
                    <option value="heavy_rain">أمطار غزيرة</option>
                    <option value="other">تحذير آخر</option>
                  </select>
                </label>
              </div>
            </div>
          </details>
        </section>

        <section className="planner-step" aria-labelledby="evidence-step-title">
          <div className="step-heading">
            <span className="step-index">4</span>
            <div>
              <h3 id="evidence-step-title">أدلة ميدانية (اختياري)</h3>
              <p>بلاغ حديث أو رمية اختبار تثبت عوالق/أعشاب البحر وترفع التحذير إلى إلغاء مؤكد.</p>
            </div>
          </div>

          <div className="field-group">
            <div className="field-caption">بلاغ ميداني حديث</div>
            <div className="advanced-grid evidence-controls">
              <label>
                <span>النوع</span>
                <select value={draftKind} onChange={(event) => setDraftKind(event.target.value as FieldReport["kind"])}>
                  <option value="fouling">أعشاب / عوالق (صوفة)</option>
                  <option value="turbidity">عكارة</option>
                  <option value="rip_current">تيار ساحب</option>
                  <option value="visibility">رؤية / غبار</option>
                </select>
              </label>
              <label>
                <span>الشدّة</span>
                <select value={draftSeverity} onChange={(event) => setDraftSeverity(event.target.value as FieldReport["severity"])}>
                  <option value="present">موجود</option>
                  <option value="dense">كثيف</option>
                </select>
              </label>
              <label>
                <span>المصدر</span>
                <select value={draftSource} onChange={(event) => setDraftSource(event.target.value as FieldReport["source"])}>
                  <option value="user">بلاغي الشخصي</option>
                  <option value="community">بلاغ من صيّادين آخرين</option>
                  <option value="official">بلاغ رسمي</option>
                </select>
              </label>
              <button type="button" className="secondary-action" onClick={addReport} disabled={(value.field_reports ?? []).length >= 10}>
                <Info size={17} />
                <span>أضف البلاغ</span>
              </button>
            </div>
            {(value.field_reports ?? []).length > 0 && (
              <ul className="report-chips" aria-label="البلاغات المضافة">
                {(value.field_reports ?? []).map((report, index) => (
                  <li key={`${report.kind}-${index}`}>
                    <span>
                      <strong>{reportKindLabel(report.kind)}</strong>
                      <small>{reportSeverityLabel(report.severity)} · {reportSourceLabel(report.source)}</small>
                    </span>
                    <button type="button" aria-label={`احذف البلاغ ${index + 1}`} onClick={() => removeReport(index)}>✕</button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="field-group">
            <div className="field-caption">رمية اختبار (من نفس الموقع الآن)</div>
            <div className="setting-options shore-options">
              <button
                type="button"
                className={(value.test_cast == null) ? "active" : ""}
                aria-pressed={value.test_cast == null}
                onClick={() => setTestCast(null)}
              >
                <span><strong>بدون رمية</strong><small>لا بلاغ اختبار</small></span>
              </button>
              <button
                type="button"
                className={value.test_cast?.hooked === true ? "active" : ""}
                aria-pressed={value.test_cast?.hooked === true}
                onClick={() => setTestCast(true)}
              >
                <span><strong>صادت أعشاب/عوالق</strong><small>تثبت الصوفة في الماء</small></span>
              </button>
              <button
                type="button"
                className={value.test_cast?.hooked === false ? "active" : ""}
                aria-pressed={value.test_cast?.hooked === false}
                onClick={() => setTestCast(false)}
              >
                <span><strong>رمية نظيفة</strong><small>ما صادتش شي</small></span>
              </button>
            </div>
          </div>
        </section>
      </div>

      {isDirty && (
        <div className="dirty-note" role="status">
          <SlidersHorizontal size={17} />
          <span><strong>عدّلت تفاصيل الحصة.</strong> حدّث القرار باش يعكس الاختيارات الجديدة.</span>
        </div>
      )}

      {error && (
        <div className="planner-error" id="planner-error" role="alert">
          <strong>ما قدرناش نكمّلوا التحليل</strong>
          <span>{error}</span>
          <small>ثبّت اتصالك وعاود المحاولة. القرار السابق يبقى ظاهر إذا كان موجود.</small>
        </div>
      )}

      <div className="planner-action-bar">
        <div className="action-context">
          <span>{value.location.name ?? "بقعة مختارة"}</span>
          <strong>{formatDate(value.target_date)}</strong>
        </div>
        <button className="primary-action" type="button" disabled={loading} onClick={onSubmit}>
          {loading ? <RefreshCw className="spin" size={20} /> : <Sparkles size={20} />}
          <span>{submitLabel}</span>
          {!loading && <ArrowLeft size={19} />}
        </button>
      </div>
      <p className="post-analysis-hint">
        <Sparkles size={16} /> بعد نجاح الجلب يفتح التقرير الحتمي تلقائياً: القرار، النوافذ، نشاط 48–72 ساعة، الصوفة والعكارة، الأرقام والمصادر.
        <strong> Gemini يبقى كاتباً اختيارياً فقط.</strong>
      </p>
    </section>
  );
}
