"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { requestAutoOrientation } from "@/lib/api";
import { formatDate, formatDateChip, tunisTodayIso } from "@/lib/format";
import { SPOT_PRESETS } from "@/lib/spots";
import type {
  AutomatedShoreProfile,
  Coordinates as LocationInput,
  ForecastDecisionRequest,
} from "@/lib/types";

function addIsoDays(value: string, amount: number): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + amount));
  return date.toISOString().slice(0, 10);
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
  const [orientationLoading, setOrientationLoading] = useState(false);
  const [orientationError, setOrientationError] = useState<string | null>(null);
  const [shoreProfile, setShoreProfile] = useState<AutomatedShoreProfile | null>(null);
  const orientationAbort = useRef<AbortController | null>(null);
  const valueRef = useRef(value);
  const today = tunisTodayIso();
  const forecastDates = useMemo(() => Array.from({ length: 7 }, (_, index) => addIsoDays(today, index)), [today]);

  const patch = (partial: Partial<ForecastDecisionRequest>) => {
    const nextValue = { ...valueRef.current, ...partial };
    valueRef.current = nextValue;
    onChange(nextValue);
  };
  const patchTargetDate = (targetDate: string) => {
    patch({ target_date: targetDate });
  };
  useEffect(() => {
    valueRef.current = value;
  }, [value]);
  useEffect(() => () => orientationAbort.current?.abort(), []);

  const calculateOrientation = useCallback(async (location: LocationInput) => {
    orientationAbort.current?.abort();
    const controller = new AbortController();
    orientationAbort.current = controller;
    setOrientationLoading(true);
    setOrientationError(null);
    setShoreProfile(null);
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
      setShoreProfile(result.shore_profile ?? null);
      if (result.status === "resolved" && result.orientation_deg !== null && result.evidence) {
        const manualShore = current.spot.shore_type_source === "user" ? current.spot.shore_type : null;
        const osmShore = result.shore_profile?.status === "resolved" ? result.shore_profile.shore_type : null;
        const selectedShore = manualShore ?? osmShore ?? null;
        const selectedShoreSource = manualShore ? "user" : osmShore ? "overpass" : "unknown";
        const nextValue: ForecastDecisionRequest = {
          ...current,
          spot: {
            ...current.spot,
            seaward_orientation_deg: result.orientation_deg,
            orientation_source: "overpass",
            orientation_evidence: result.evidence,
            shore_type: selectedShore,
            shore_type_source: selectedShoreSource,
            exposure: null,
          },
        };
        valueRef.current = nextValue;
        onChange(nextValue);
      } else {
        setOrientationError(result.reasons_ar.join(" "));
        const unknownValue: ForecastDecisionRequest = {
          ...current,
          spot: {
            ...current.spot,
            seaward_orientation_deg: null,
            orientation_source: "estimated",
            orientation_evidence: null,
            shore_type: current.spot.shore_type_source === "user" ? current.spot.shore_type : null,
            shore_type_source: current.spot.shore_type_source === "user" ? "user" : "unknown",
            exposure: null,
          },
        };
        valueRef.current = unknownValue;
        onChange(unknownValue);
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      const current = valueRef.current;
      const stillSelected =
        current.location.latitude === location.latitude
        && current.location.longitude === location.longitude;
      if (stillSelected) {
        const unknownValue: ForecastDecisionRequest = {
          ...current,
          spot: {
            ...current.spot,
            seaward_orientation_deg: null,
            orientation_source: "estimated",
            orientation_evidence: null,
            shore_type: current.spot.shore_type_source === "user" ? current.spot.shore_type : null,
            shore_type_source: current.spot.shore_type_source === "user" ? "user" : "unknown",
            exposure: null,
          },
        };
        valueRef.current = unknownValue;
        onChange(unknownValue);
      }
      setOrientationError(
        caught instanceof Error
          ? caught.message
          : "تعذر حساب اتجاه الساحل آلياً؛ لن نستبدله بتخمين.",
      );
    } finally {
      if (!controller.signal.aborted) setOrientationLoading(false);
    }
  }, [onChange]);

  const selectedLatitude = value.location.latitude;
  const selectedLongitude = value.location.longitude;
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const location = valueRef.current.location;
      if (location.latitude === selectedLatitude && location.longitude === selectedLongitude) {
        void calculateOrientation(location);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [calculateOrientation, selectedLatitude, selectedLongitude]);

  const chooseLocation = (location: LocationInput) => {
    const current = valueRef.current;
    const nextValue = {
      ...current,
      location,
      spot: {
        ...current.spot,
        seaward_orientation_deg: null,
        orientation_source: "estimated" as const,
        orientation_evidence: null,
        shore_type: null,
        shore_type_source: "unknown" as const,
        exposure: null,
      },
    };
    valueRef.current = nextValue;
    onChange(nextValue);
    setGeoError(null);
    setShoreProfile(null);
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
        seaward_orientation_deg: null,
        orientation_source: "estimated",
        orientation_evidence: null,
        shore_type: null,
        shore_type_source: "unknown" as const,
        exposure: null,
      },
    };
    valueRef.current = nextValue;
    onChange(nextValue);
    setGeoError(null);
    setShoreProfile(null);
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
  const orientationVerified = Boolean(
    orientationEvidence
      && orientationEvidence.confidence === "high"
      && orientationEvidence.coastline_distance_m <= 500
      && orientationEvidence.segments_used >= 3,
  );
  // A usable substrate label requires explicit nearby OSM tags and feature provenance.
  // Exposure is intentionally Unknown and no longer contributes to engine scores.
  const resolvedShoreProfile =
    shoreProfile?.status === "resolved"
      && shoreProfile.shore_type
      && shoreProfile.evidence_feature_id
      && shoreProfile.evidence_feature_version
      && shoreProfile.evidence_feature_timestamp
      && shoreProfile.feature_distance_m !== null
      && Object.keys(shoreProfile.raw_tags).length > 0
      ? shoreProfile
      : null;
  const shoreProfileVerified = Boolean(resolvedShoreProfile);
  // اختيار البقعة وجلب اتجاه ساحل موثق يكفي لبدء التحليل. نوع الساحل اليدوي
  // مدخل يقدمه المستخدم بوضوح، وليس رصداً أو وسم OSM.
  const decisionContextVerified = orientationVerified;

  const submitLabel = loading
    ? "نجمع المعطيات ونبني التقرير…"
    : !orientationVerified
      ? orientationLoading
        ? "نجلب اتجاه الساحل الموثق…"
        : "محجوب: اتجاه الساحل غير موثق"
      : isDirty
        ? "حدّث التقرير والقرار"
        : hasResult
          ? "أعد توليد التقرير"
          : "حلّل 24 ساعة";

  return (
    <section className="planner-shell" id="planner" aria-labelledby="planner-title" aria-busy={loading}>
      <div className="section-kicker"><Sparkles size={15} /> تقرير بقعة</div>
      <div className="planner-heading">
        <div>
          <h2 id="planner-title">إعداد تقرير السيرفكاست</h2>
          <p>اختَر البقعة واليوم؛ نجيب اتجاه البحر آلياً ثم نحلّل 24 ساعة.</p>
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
              <SpotMap location={value.location} onLocationChange={chooseLocation} />
              <p>
                <Info size={14} /> اضغط على موضع الوقوف على الساحل؛ اتجاه عرض البحر يُجلب آلياً من بيانات الساحل ولا يُطلب إدخاله يدوياً.
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
                  onClick={() => patchTargetDate(date)}
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
              onChange={(event) => event.target.value && patchTargetDate(event.target.value)}
            />
          </label>
        </section>

        <section className="planner-step" aria-labelledby="orientation-step-title">
          <div className="step-heading">
            <span className="step-index">3</span>
            <div>
              <h3 id="orientation-step-title">تحليل اتجاه الساحل</h3>
              <p>نجلب اتجاه الساحل آلياً ونُظهر مصدره؛ لا حاجة لإدخال اتجاه يدوي.</p>
            </div>
          </div>

          <div className="orientation-card">
            <div className="compass-visual" aria-hidden="true">
              <span className="compass-north">ش</span>
              <span className="compass-east">ق</span>
              <span className="compass-south">ج</span>
              <span className="compass-west">غ</span>
              {orientationEvidence && (
                <svg
                  className="seaward-bearing-arrow"
                  viewBox="0 0 64 64"
                  style={{ transform: `rotate(${orientationEvidence.orientation_deg}deg)` }}
                >
                  <circle cx="32" cy="32" r="28" />
                  <path d="M32 50V15" />
                  <path className="arrow-head" d="M32 9 23 24h18Z" />
                </svg>
              )}
            </div>
            <div className="orientation-control">
              <div className="orientation-value">
                <span>اتجاه البحر من مصدر الخريطة</span>
                <strong>{orientationEvidence ? <bdi>{orientationEvidence.orientation_deg.toFixed(1)}°</bdi> : "غير متاح"}</strong>
              </div>
              <small>لا يمكن إدخال الاتجاه يدوياً؛ عند تعذر المصدر تبقى القيمة Unknown.</small>
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
              <span><bdi>{orientationConfidenceLabel}</bdi><small>ثقة اتجاه الهندسة</small></span>
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
              <span>{orientationError} لم نخترع اتجاهاً بديلاً؛ لا يمكن إصدار قرار إيجابي حتى تتوفر هندسة ساحل موثقة.</span>
            </div>
          )}

          <p className="orientation-help">
            <Compass size={16} />
            <span><strong>الاشتقاق الآلي:</strong> نستخدم عمود الساحل المستخرج من الخريطة للمقارنة مع اتجاه قدوم الريح والموج. لا تُدخل اتجاهاً يدوياً؛ الدليل الهندسي ومصدره ودرجة ثقته معروضة أعلاه.</span>
          </p>

          <div className={shoreProfileVerified ? "field-message success" : "field-message warning"} data-testid="automatic-spot-profile-status">
            <Info size={16} />
            <span>
              {resolvedShoreProfile
                ? <>نوع الساحل من وسم OSM صريح: {resolvedShoreProfile.shore_type} — way/{resolvedShoreProfile.evidence_feature_id} v{resolvedShoreProfile.evidence_feature_version}، آخر تعديل {resolvedShoreProfile.evidence_feature_timestamp}، على {resolvedShoreProfile.feature_distance_m} م؛ التعرض Unknown وغير مستخدم.</>
                : <><strong>OSM لم يوثّق نوع الساحل.</strong> إذا اخترته أنت أدناه، سنستخدمه كإدخال يدوي منفصل عن بيانات الخريطة.</>}
            </span>
          </div>
          <label className="shore-type-field" data-testid="manual-shore-type-field">
            <span>نوع الشاطئ — اختيارك</span>
            <select
              aria-label="نوع الشاطئ الذي اخترته"
              value={value.spot.shore_type_source === "user" ? value.spot.shore_type ?? "" : ""}
              onChange={(event) => {
                const selected = event.target.value as ForecastDecisionRequest["spot"]["shore_type"] | "";
                const automatic = resolvedShoreProfile?.shore_type ?? null;
                const shoreType = selected || automatic;
                const shoreTypeSource = selected ? "user" : automatic ? "overpass" : "unknown";
                patch({ spot: { ...valueRef.current.spot, shore_type: shoreType, shore_type_source: shoreTypeSource, exposure: null } });
              }}
            >
              <option value="">استخدم OSM إن وُجد، وإلا غير محدد</option>
              <option value="sandy">رملي</option>
              <option value="rocky">صخري</option>
              <option value="cliff">جرف أو حافة</option>
              <option value="jetty">رصيف أو حاجز بحري</option>
            </select>
            <small>اختيارك يُستخدم في الحساب ويظهر كإدخال يدوي؛ لا يُسجَّل كرصد ميداني أو وسم OSM. لا يضمن القرار «اذهب».</small>
          </label>
          <p className="orientation-help">
            <Info size={16} /> يفحص التطبيق نشرة INM آلياً قبل السماح بقرار «اذهب».
          </p>
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

      {!decisionContextVerified && (
        <div className="field-message warning" role="status" data-testid="decision-preflight-no-go">
          <Info size={16} />
          <span>
            <strong>انتظر جلب اتجاه الشاطئ الموثق.</strong>{" "}
            لا يبدأ التحليل قبل التحقق الآلي من اتجاه البحر.
          </span>
        </div>
      )}
      {orientationVerified && !value.spot.shore_type && (
        <div className="field-message warning" role="status" data-testid="shore-type-caution">
          <Info size={16} />
          <span>
            نوع الساحل غير محدد. اختره يدوياً إذا كنت تعرفه؛ وإلا سيبقى القرار النهائي «لا تذهب» بسبب هذه المعلومة الناقصة.
          </span>
        </div>
      )}

      <div className="planner-action-bar">
        <div className="action-context">
          <span>{value.location.name ?? "بقعة مختارة"}</span>
          <strong>{formatDate(value.target_date)}</strong>
        </div>
        <button className="primary-action" type="button" disabled={loading || !decisionContextVerified} onClick={onSubmit}>
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
