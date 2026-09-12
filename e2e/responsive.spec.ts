import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { DecisionResponse, ForecastDecisionRequest, HourDecision } from "@/lib/types";

const viewports = [
  { name: "small-phone", width: 320, height: 568 },
  { name: "phone", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "small-desktop", width: 1024, height: 768 },
  { name: "wide-desktop", width: 1440, height: 900 },
];

function isoHour(date: string, hour: number): string {
  return `${date}T${String(hour).padStart(2, "0")}:00:00+01:00`;
}

function nextIsoDate(date: string): string {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + 1);
  return value.toISOString().slice(0, 10);
}

function makeHour(date: string, hour: number): HourDecision {
  const safety = hour === 11 ? "caution" as const : "go" as const;
  const opportunity = hour === 8 ? 82 : Math.max(45, 78 - Math.abs(hour - 8) * 7);
  return {
    time: isoHour(date, hour),
    safety,
    opportunity_score: opportunity,
    confidence: {
      score: 84,
      band: "high",
      reasons_ar: ["توفرت أهم متغيرات الريح والموج للساعة."],
      is_accuracy_probability: false,
    },
    field_feasibility: {
      status: "favorable",
      score: 82,
      confidence: 48,
      holding_difficulty: "low",
      fouling_transport_potential: "moderate",
      turbidity_potential: "low",
      rip_current_potential: "low",
      fouling_evidence_count: 2,
      turbidity_evidence_count: 1,
      antecedent_window_hours: 48,
      reasons_ar: [
        "صعوبة تثبيت الخط منخفضة في الفحص الآلي.",
        "قابلية نقل مادة موجودة متوسطة وتحتاج رمية اختبارية.",
      ],
      limitations_ar: [
        "هذا فحص مؤشرات منخفض الثقة وليس رصداً مباشراً للصوفة أو التيار الساحبي.",
      ],
      is_direct_observation: false,
    },
    factors: [
      {
        code: "wind_speed",
        label_ar: "الريح",
        impact: hour === 11 ? "negative" : "positive",
        severity: hour === 11 ? "caution" : "info",
        basis: "model_forecast",
        rule_nature: "safety_policy",
        value: hour === 11 ? "22 كم/س" : "11 كم/س",
        score_delta: hour === 11 ? -8 : 9,
        explanation_ar: hour === 11
          ? "الريح تقوى قرب منتصف النهار وتستحق الانتباه."
          : "الريح هادئة ومناسبة نسبياً للوقوف على الشاطئ.",
        is_direct_observation: false,
      },
      {
        code: "wave_height",
        label_ar: "الموج",
        impact: "positive",
        severity: "info",
        basis: "derived_forecast",
        rule_nature: "expert_prior",
        value: "0.6 م",
        score_delta: 7,
        explanation_ar: "ارتفاع الموج ضمن المجال التشغيلي الأولي لهذه البقعة.",
        is_direct_observation: false,
      },
    ],
    forecast: {
      wind_speed_kmh: hour === 11 ? 22 : 11,
      wind_gust_kmh: hour === 11 ? 31 : 17,
      wind_direction_deg: 62,
      wave_height_m: 0.6,
      wave_period_s: 7.8,
      wave_direction_deg: 74,
      wind_wave_height_m: 0.35,
      wind_wave_period_s: 4.8,
      wind_wave_direction_deg: 65,
      swell_height_m: 0.4,
      swell_period_s: 8.2,
      swell_direction_deg: 78,
      sea_surface_temperature_c: 25.1,
      ocean_current_velocity_kmh: 0.24,
      ocean_current_direction_deg: 95,
      sea_level_height_msl_m: 0.18 + (hour - 6) * 0.03,
      air_temperature_c: 27,
      apparent_temperature_c: 28,
      relative_humidity_pct: 64,
      dew_point_c: 19.5,
      cloud_cover_pct: 24,
      shortwave_radiation_wm2: hour === 6 ? 90 : 520,
      uv_index: hour === 6 ? 0.7 : 5.2,
      lightning_potential_jkg: null,
      cape_jkg: 50,
      precipitation_mm: 0,
      precipitation_probability_pct: 5,
      weather_code: 1,
      pressure_msl_hpa: 1015,
      visibility_m: 18_000,
    },
    derived: {
      wind_relation: "cross_offshore",
      wind_angle_deg: 118,
      wind_shoreward_component_kmh: -7.1,
      wind_alongshore_component_kmh: 13.2,
      wind_alongshore_signed_component_kmh: -13.2,
      alongshore_positive_bearing_deg: 152,
      wind_drag_coefficient: 0.0012,
      wind_stress_pa: hour === 11 ? 0.0457 : 0.0137,
      wind_stress_shoreward_pa: hour === 11 ? -0.0215 : -0.0064,
      wind_stress_alongshore_pa: hour === 11 ? -0.0403 : -0.0121,
      wave_incidence: "direct",
      wave_angle_deg: 16,
      wave_shoreward_alignment: 0.961,
      wave_alongshore_alignment: 0.276,
      wave_alongshore_signed_alignment: -0.276,
      deep_water_wavelength_m: 95,
      wave_steepness: 0.012,
      wave_energy_proxy: 2.8,
      alongshore_wave_proxy: 0.8,
      alongshore_wave_signed_proxy: -0.8,
      wave_component_angle_deg: 13,
      wave_component_secondary_energy_share: 0.43,
      gust_factor: hour === 11 ? 1.41 : 1.55,
      max_wind_direction_shift_6h_deg: 18,
      wind_direction_coherence_6h: 0.94,
      wind_direction_data_hours_6h: 6,
      current_alongshore_kmh: 0.18,
      current_cross_shore_kmh: 0.1,
      tide_state: hour < 10 ? "rising" : "falling",
      sea_level_rate_m_per_h: hour < 10 ? 0.03 : -0.02,
      tide_movement_index: 0.4,
      pressure_change_3h_hpa: 0.6,
      pressure_change_24h_hpa: -1.2,
      sea_surface_temperature_change_24h_c: 0.2,
      max_wind_speed_24h_kmh: 22,
      max_wave_height_24h_m: 0.7,
      strong_wind_hours_24h: 0,
      sea_level_range_target_day_m: 0.35,
      rain_24h_mm: 0,
      rain_48h_mm: 0,
      rain_72h_mm: 0,
      max_wave_height_48h_m: 0.7,
      max_wave_height_72h_m: 0.8,
      wave_energy_integral_48h: 138.2,
      onshore_wind_impulse_48h_kmh_h: 94.5,
      onshore_wind_stress_impulse_48h_pa_h: 0.642,
      shoreward_current_impulse_48h_kmh_h: 2.4,
      strong_wave_hours_48h: 0,
      history_hours_72h: 72,
      history_hours_48h: 48,
      history_hours_24h: 24,
      history_hours_12h: 12,
      rain_data_hours_48h: 48,
      rain_data_hours_24h: 24,
      wind_data_hours_48h: 48,
      wind_data_hours_12h: 12,
      wave_energy_data_hours_48h: 48,
      wave_energy_data_hours_12h: 12,
      current_data_hours_48h: 48,
      onshore_wind_fraction_48h: 0.25,
      onshore_wind_fraction_12h: 0.25,
      energetic_wave_fraction_48h: 0.25,
      energetic_wave_fraction_12h: 0.25,
      air_sea_temperature_difference_c: 1.9,
      dew_point_depression_c: 7.5,
      is_twilight: hour === 6,
      is_night: false,
    },
  };
}

function mockDecision(payload: ForecastDecisionRequest): DecisionResponse {
  const date = payload.target_date;
  const hourly = Array.from({ length: 8 }, (_, index) => makeHour(date, index + 6));
  const satelliteRetrievedAt = new Date();
  const satelliteValidTime = new Date(satelliteRetrievedAt.getTime() - 72 * 60 * 60 * 1000);
  return {
    schema_version: "3.9",
    engine_version: "1.6.8",
    decision: "go",
    decision_reason_code: "safe_window",
    decision_label_ar: "اذهب",
    summary_ar: "الظروف مناسبة نسبياً في الصباح، مع ريح هادئة وموج قابل للتعامل.",
    opportunity_score: 78,
    score_is_success_probability: false,
    confidence: {
      score: 84,
      band: "high",
      reasons_ar: ["توفرت بيانات الريح والموج والطقس.", "التغطية الزمنية كاملة للساعات المقترحة."],
      is_accuracy_probability: false,
    },
    field_feasibility: {
      status: "favorable",
      score: 82,
      confidence: 48,
      holding_difficulty: "low",
      fouling_transport_potential: "moderate",
      turbidity_potential: "low",
      rip_current_potential: "low",
      fouling_evidence_count: 2,
      turbidity_evidence_count: 1,
      antecedent_window_hours: 48,
      reasons_ar: [
        "اعتمد التجميع أضعف ساعة داخل أفضل نافذة كإجراء محافظ.",
        "صعوبة تثبيت الخط منخفضة في الفحص الآلي.",
        "قابلية نقل مادة موجودة متوسطة؛ لا يتوفر رصد لوجودها.",
      ],
      limitations_ar: [
        "هذا فحص مؤشرات منخفض الثقة وليس رصداً مباشراً للأعشاب أو التيار الساحبي.",
        "الإشارة المنخفضة لا تنفي الخطر؛ عاين الكسرة واعمل رمية اختبارية.",
      ],
      is_direct_observation: false,
    },
    sunrise: isoHour(date, 6),
    sunset: `${date}T18:35:00+01:00`,
    recommended_windows: [
      {
        start: isoHour(date, 6),
        end: isoHour(date, 9),
        safety: "go",
        field_feasibility: "favorable",
        field_score: 82,
        opportunity_score: 78,
        confidence_score: 84,
        headline_ar: "نافذة صباحية متوازنة قبل اشتداد الريح.",
        key_factors_ar: ["ريح هادئة", "موج معتدل", "ضوء صباحي"],
      },
      {
        start: isoHour(date, 9),
        end: isoHour(date, 10),
        safety: "caution",
        field_feasibility: "workable",
        field_score: 68,
        opportunity_score: 66,
        confidence_score: 81,
        headline_ar: "نافذة أقصر مع بداية ارتفاع الريح.",
        key_factors_ar: ["ريح متزايدة", "موج معتدل"],
      },
    ],
    avoid_windows: [
      {
        start: isoHour(date, 11),
        end: isoHour(date, 13),
        safety: "caution",
        field_feasibility: "workable",
        field_score: 60,
        opportunity_score: 48,
        confidence_score: 82,
        headline_ar: "الريح أقوى من الفترة الصباحية.",
        key_factors_ar: ["هبات أقوى", "راحة أقل"],
      },
    ],
    tide_events: [
      { time: isoHour(date, 9), kind: "high", level_msl_m: 0.27, disclaimer_ar: "قيمة نموذجية تقريبية." },
      { time: isoHour(date, 13), kind: "low", level_msl_m: 0.12, disclaimer_ar: "قيمة نموذجية تقريبية." },
    ],
    hourly,
    antecedent_hours: [],
    sources: [
      {
        provider: "Open-Meteo",
        product: "Marine API",
        data_kind: "model_forecast",
        variables: ["wave_height", "sea_level_height_msl"],
        horizontal_resolution_km: 5,
        retrieved_at: new Date().toISOString(),
        limitations_ar: ["الدقة الساحلية محدودة قرب الحواجز والموانئ."],
      },
      {
        provider: "AviationWeather.gov / METAR",
        product: "Latest Tunisian airport observation (DTTA)",
        data_kind: "direct_observation",
        variables: ["wind_speed", "air_temperature", "pressure"],
        horizontal_resolution_km: null,
        retrieved_at: isoHour(date, 7),
        limitations_ar: ["رصد محطة مطار، وليس قياساً داخل البقعة."],
      },
      {
        provider: "Copernicus Marine Service / Sentinel-2",
        product: "Mediterranean daily 100 m ocean-colour TUR/SPM/CHL mosaic",
        data_kind: "remote_sensing_estimate",
        variables: ["turbidity_fnu", "suspended_particulate_matter_g_m3", "chlorophyll_a_mg_m3"],
        horizontal_resolution_km: 0.1,
        retrieved_at: satelliteRetrievedAt.toISOString(),
        limitations_ar: ["استعادة أقمار صناعية سياقية وليست قياساً أو توقعاً."],
      },
    ],
    current_weather_observation: {
      provider: "AviationWeather.gov METAR",
      station_id: "DTTA",
      station_name: "Tunis/Carthage Intl",
      station_latitude: 36.851,
      station_longitude: 10.227,
      station_elevation_m: 7,
      observed_at: `${date}T06:30:00+01:00`,
      retrieved_at: isoHour(date, 7),
      distance_to_spot_km: 24.6,
      wind_speed_kmh: 13,
      wind_gust_kmh: null,
      wind_direction_deg: 70,
      air_temperature_c: 19,
      dew_point_c: 12,
      pressure_hpa: 1018,
      pressure_kind: "altimeter_setting",
      visibility_m: 9656,
      visibility_is_lower_bound: true,
      weather_text: null,
      cloud_cover_code: "FEW",
      raw_report: "DTTA 150530Z 07007KT 9999 FEW020 19/12 Q1018",
      quality_control_flag: 1,
      is_direct_observation: true,
      is_spot_observation: false,
    },
    coastal_water_context: {
      availability: "available",
      provider: "Copernicus Marine Service",
      product_id: "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205",
      dataset_id: "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107",
      data_kind: "remote_sensing_estimate",
      sample_strategy: "fixed_1000m_seaward_axis",
      sample_latitude: 36.81,
      sample_longitude: 10.31,
      sample_distance_from_spot_m: 1000,
      pixel_latitude: 36.8102,
      pixel_longitude: 10.3104,
      pixel_distance_from_spot_m: 1018,
      pixel_distance_from_sample_m: 42,
      spatial_resolution_m: 100,
      valid_time: satelliteValidTime.toISOString(),
      retrieved_at: satelliteRetrievedAt.toISOString(),
      age_hours: 72,
      search_days: 10,
      turbidity_fnu: 0.32,
      turbidity_unit: "FNU",
      suspended_particulate_matter_g_m3: 0.18,
      suspended_particulate_matter_unit: "g/m³",
      chlorophyll_a_mg_m3: 0.54,
      chlorophyll_a_unit: "mg/m³",
      sea_surface_temperature_c: 25.4,
      reason_ar: "أحدث بكسل صالح عند نقطة العينة الثابتة.",
      affects_final_decision: false,
      is_direct_observation: false,
      is_spot_observation: false,
      is_forecast: false,
    },
    observation_comparison: {
      status: "consistent",
      compared_forecast_time: isoHour(date, 7),
      observation_age_minutes: 30,
      station_distance_km: 24.6,
      wind_speed_difference_kmh: 2,
      wind_direction_difference_deg: 8,
      temperature_difference_c: 1,
      pressure_difference_hpa: 2,
      affects_confidence: false,
      reasons_ar: ["لا يوجد اختلاف كبير، مع بقاء محطة المطار خارج البقعة."],
    },
    factor_coverage: {
      catalog_version: "matrix-v3-audit-5",
      matrix_version: "TUN-SURFCAST-MATRICE-v3.0",
      source_claimed_total: 62,
      audited_total: 63,
      automated_decision: 11,
      automated_context: 13,
      proxy_requires_field_check: 5,
      field_or_external_required: 30,
      excluded_unsupported: 4,
      note_ar: "صحح التدقيق العدد من 62 في المصدر الأصلي إلى 63 عاملاً تشغيلياً؛ تُقيّم كلها لكن التسجيل لا يعني التنقيط.",
    },
    factor_assessments: Array.from({ length: 63 }, (_, index) => ({
      matrix_id: `F-${index + 1}`,
      chapter_ar: "فصل اختباري",
      title_ar: `عامل اختباري ${index + 1}`,
      status: index < 11 ? "decision" : index < 24 ? "context" : index < 28 ? "proxy" : index < 59 ? "unknown" : "excluded",
      decision_axis: index < 11 ? "السلامة" : "السياق",
      value_ar: index < 28 ? "قيمة تشغيلية من الحزمة" : "Unknown — يلزم رصد ميداني",
      evidence_variables: index < 28 ? ["wave_height"] : [],
      rationale_ar: "تفسير تدقيقي يوضح لماذا استعمل العامل أو بقي غير معروف.",
      affects_final_decision: false,
    })),
    limitations_ar: ["المعطيات نموذجية ولا تعوض معاينة البحر من الشاطئ."],
    generated_at: new Date().toISOString(),
  };
}

async function mockForecast(page: Page, delayMs = 0) {
  await page.route("**/api/v1/decisions/forecast", async (route) => {
    const payload = route.request().postDataJSON() as ForecastDecisionRequest;
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockDecision(payload)) });
  });
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    root: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.root, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(dimensions.body, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport + 1);
}

for (const viewport of viewports) {
  test(`landing, planner, and result fit ${viewport.name} (${viewport.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockForecast(page);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /تقرير سيرفكاست دقيق/ })).toBeVisible();
    await expect(page.locator(".workspace-tabs a.active")).toContainText("تقرير بقعة");
    await expectNoPageOverflow(page);

    await expect(page.getByRole("heading", { name: "وين باش تصطاد؟" })).toBeVisible();
    await page.locator("#planner").scrollIntoViewIfNeeded();
    await expect(page.getByRole("heading", { name: "وقتاش الحصة؟" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "لوين يواجه البحر؟" })).toBeVisible();
    const submit = page.getByRole("button", { name: "ولّد التقرير البحري" });
    await expect(submit).toBeVisible();
    await expectNoPageOverflow(page);

    await submit.click();
    await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "رصد جوي فعلي الآن" })).toBeVisible();
    await expect(page.getByTestId("actual-observation")).toContainText("DTTA");
    await expect(page.getByTestId("actual-observation")).toContainText("ليس داخل الـSpot");
    await expect(page.getByTestId("coastal-water-context")).toContainText("0.32 FNU");
    await expect(page.getByTestId("coastal-water-context")).toContainText("لا تغيّر");
    await expect(page.getByTestId("coastal-water-context")).toContainText("الثقة");
    await expect(page.getByRole("heading", { name: "هل يمكن تنفيذ الحصة ميدانياً؟" })).toBeVisible();
    await expect(page.getByTestId("field-feasibility")).toContainText("موش رصد");
    await expect(page.getByRole("heading", { name: "القرار ساعة بساعة" })).toBeVisible();
    await expect(page.getByTestId("report-equations")).toContainText("V∥=−VsinΔ");
    await expect(page.locator(".report-diagnostic-table tbody tr")).toHaveCount(8);
    await expect(page.getByTestId("report-water-context")).toContainText("سياق جودة الماء");
    await expectNoPageOverflow(page);
  });
}

test("mobile result stays readable, interactive, and marks stale choices", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await mockForecast(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();

  await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();
  await expect(page.getByText("أفضل نافذة مقترحة")).toBeVisible();
  await expect(page.getByRole("heading", { name: "القرار ساعة بساعة" })).toBeVisible();
  await expectNoPageOverflow(page);

  await page.locator(".hour-card").nth(3).click();
  await expect(page.getByRole("heading", { name: /صورة التوقع النموذجي/ })).toBeVisible();
  await expect(page.locator(".hour-card").nth(3)).toHaveAttribute("aria-pressed", "true");

  await page.locator("#planner").scrollIntoViewIfNeeded();
  await page.locator(".date-chip").nth(1).click();
  await expect(page.getByText("هذه النتيجة تخص الاختيارات السابقة.")).toBeVisible();
  await expect(page.getByRole("button", { name: "حدّث التقرير والقرار" })).toBeVisible();
  await expect(page.locator("#spot-report .report-stale")).toContainText("التقرير يخص آخر تحليل");
  await expectNoPageOverflow(page);
});

test("the full spot report is scientific, complete, downloadable, and mobile-safe", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 320, height: 568 });
  await mockForecast(page);
  await page.goto("/");
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();
  await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();
  const report = page.locator("#spot-report");
  const reportTitle = report.getByRole("heading", { name: "تقرير نابل" });
  await expect(report).toBeVisible();
  await expect(reportTitle).toBeVisible();
  await expect(report).toContainText("نسخة علمية، موش تنجيم");
  await expect(report).toContainText("مؤشر الفرصة");
  await expect(report).toContainText("قابلية التنفيذ الميداني");
  await expect(report).toContainText("الرصد الجوي الفعلي الأقرب");
  await expect(report).toContainText("محطة مطار، موش قياس داخل البقعة");
  await expect(report).toContainText("الهبة غير مسجلة");
  await expect(report).toContainText("لا تثبت وجودها أو تمنع وحدها");
  await expect(report).toContainText("الخطر مربوط بوقته");
  await expect(report).toContainText("سلامة: مناسب");
  await expect(report).toContainText("ثقة الفحص");
  await expect(report).toContainText("تغطية 48/48");
  await expect(report).toContainText("اتجاه البحر من موضع الوقوف");
  await expect(report).toContainText("التفكيك الزمني");
  await expect(report).toContainText("الأرقام المرجعية");
  await expect(report.getByTestId("report-equations")).toContainText("L₀=gT²/(2π)");
  await expect(report.locator(".sun-times")).toContainText("06:00");
  await expect(report.locator(".sun-times")).toContainText("18:35");
  await expectNoPageOverflow(page);

  await report.getByRole("button", { name: "انسخ التقرير" }).click();
  await expect(report.getByRole("button", { name: "تم النسخ" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("تقرير Peche TN الميداني — نابل");

  const downloadPromise = page.waitForEvent("download");
  await report.getByRole("button", { name: "نزّل TXT" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^peche-tn-\d{4}-\d{2}-\d{2}-report\.txt$/);
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const text = await readFile(downloadPath!, "utf8");
  expect(text).toContain("تقرير Peche TN الميداني — نابل");
  expect(text).toContain("مؤشر ترتيب وليس نسبة نجاح أو ضمان مصيد");
  expect(text).toContain("3. قابلية التنفيذ الميداني");
  expect(text).toContain("المؤشرات احتمالية وليست رصداً للبقعة");
  expect(text).toContain("عائلات قرائن تشغيلية مختلفة");
  expect(text).toContain("ليست أرصاداً أو مصادر مستقلة");
  expect(text).toContain("لا يمنعان وحدهما نافذة اجتازت السلامة");
  expect(text).toContain("وجود فترة رعد/خطر لا يلغي نافذة منفصلة");
  expect(text).not.toContain("أدلة مستقلة");
  expect(text).toContain("رصد جوي فعلي: DTTA");
  expect(text).toContain("حالة المقارنة متسقة ضمن الحدود");
  expect(text).toContain("الهبة غير مسجلة");
  expect(text).not.toContain("هبة — كم/س");
  expect(text).toContain("METAR خام");
  expect(text).toContain("موج الريح");
  expect(text).toContain("السويل");
  expect(text).toContain("V⊥=VcosΔ");
  expect(text).toContain("L₀=gT²/(2π)");
  expect(text).toContain("لا نعرض عبوراً قمرياً أو فترات سولونار كأنها مدّ مؤكد");
  expect(text).toContain("العدد التشغيلي المصحح 63 عاملاً");
  expect(text).toContain("ذِكر 62 في المصدر الأصلي محفوظ للتتبع فقط");
  expect(text).not.toContain("الملف يعلن");
  expect(text).toContain("ليست دقة ميدانية متحققة");
  expect(text).not.toMatch(/العبور القمري:\s*\d{2}:\d{2}/);
  expect(text).not.toMatch(/مسافة الرمي:\s*\d+/);

  await page.evaluate(() => document.documentElement.classList.add("print-spot-report"));
  await page.emulateMedia({ media: "print" });
  await expect(report).toBeVisible();
  await expect(report.locator(".report-actions")).toBeHidden();
  await expect(page.locator(".decision-hero")).toBeHidden();
  await page.emulateMedia({ media: "screen" });
  await page.evaluate(() => document.documentElement.classList.remove("print-spot-report"));

  await report.getByRole("button", { name: "أغلق" }).click();
  await expect(report).toHaveCount(0);
  await expect(page.locator("#spot-report-trigger")).toBeFocused();
});

test("a window crossing midnight is marked as ending on the next day", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.route("**/api/v1/decisions/forecast", async (route) => {
    const payload = route.request().postDataJSON() as ForecastDecisionRequest;
    const decision = mockDecision(payload);
    const start = isoHour(payload.target_date, 23);
    const end = isoHour(nextIsoDate(payload.target_date), 0);
    const template = decision.recommended_windows[0];
    if (!template) throw new Error("mock recommendation missing");
    decision.recommended_windows = [{
      ...template,
      start,
      end,
      headline_ar: "نافذة مناسبة من 23:00 إلى 00:00 من اليوم التالي",
    }];
    decision.summary_ar = "التوصية تخص نافذة تنتهي في اليوم التالي، وليست شهادة سلامة ميدانية.";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(decision),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();
  await expect(page.locator(".lead-window")).toContainText("اليوم التالي");
  await expect(page.locator("#spot-report")).toContainText("23:00–00:00 (اليوم التالي)");
});

test("loading feedback appears while the forecast is being prepared", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await mockForecast(page, 700);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();

  await expect(page.getByRole("status").filter({ hasText: "نحضّر قرار الحصة" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();
});

test("the public API probe rejects Vercel HTML failures instead of pretending the engine is online", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/html", body: "<!doctype html><h1>500</h1>" });
  });
  await page.goto("/");

  const console = page.getByTestId("api-console");
  await expect(console).toContainText("المحرك غير متصل");
  await expect(console).toContainText("بوابة Peche TN أعادت خطأ خادماً غير صالح بدل JSON");
  await expect(page.locator("#decision")).toHaveCount(0);
  await expectNoPageOverflow(page);
});

test("network errors are explained without breaking the planner", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.route("**/api/v1/decisions/forecast", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "upstream_unavailable", message_ar: "المصدر البحري غير متاح مؤقتاً." } }),
    });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();

  const error = page.locator("#planner-error");
  await expect(error).toContainText("ما قدرناش نكمّلوا التحليل");
  await expect(error).toContainText("المصدر البحري غير متاح مؤقتاً");
  await expect(page.getByRole("button", { name: "ولّد التقرير البحري" })).toBeEnabled();
  await expectNoPageOverflow(page);
});

test("field safety checklist works locally and survives a reload", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "قائمة السلامة الميدانية" })).toBeVisible();

  const first = page.getByText("عاينت الكسرة عشر دقائق من مكان آمن وما شفتش قناة رغوة أو حطام تتحرك نحو عرض البحر.", { exact: true });
  const second = page.getByText("الوصول مسموح واللافتات محترمة ومسار الدخول والخروج واضح ولن يقطعه ارتفاع الماء.", { exact: true });
  await first.click();
  await second.click();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "2");

  await page.reload();
  await expect(page.getByRole("checkbox", { name: /عاينت الكسرة/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /مسار الدخول والخروج/ })).toBeChecked();
  await page.getByRole("button", { name: "صفّر القائمة" }).click();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "0");

  await page.evaluate(() => window.localStorage.setItem(
    "peche-tn:safety-checklist:v4",
    JSON.stringify({ value: "111111111111", savedAt: Date.now() - 7 * 60 * 60 * 1000 }),
  ));
  await page.reload();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "0");

  await page.evaluate(() => window.localStorage.setItem(
    "peche-tn:safety-checklist:v4",
    JSON.stringify({ value: "111111111111", savedAt: Date.now() + 24 * 60 * 60 * 1000 }),
  ));
  await page.reload();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "0");

  await page.evaluate(() => {
    localStorage.removeItem("peche-tn:safety-checklist:v4");
    Storage.prototype.setItem = () => { throw new DOMException("Storage disabled"); };
  });
  await first.click();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "1");
  await expectNoPageOverflow(page);
});

test("field safety progress expires while the page remains open", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-08T08:00:00Z") });
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await page.getByText("عاينت الكسرة عشر دقائق من مكان آمن وما شفتش قناة رغوة أو حطام تتحرك نحو عرض البحر.", { exact: true }).click();
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "1");

  await page.clock.fastForward(6 * 60 * 60 * 1000 + 100);
  await expect(page.locator(".checklist-progress")).toHaveAttribute("aria-valuenow", "0");
});

test("a field mismatch visibly overrides reliance on the forecast", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await mockForecast(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();
  await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();

  const trigger = page.getByRole("button", { name: "الواقع مختلف؟" });
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#reality-warning")).toContainText("اعتمد الواقع ووقّف الحصة وقت الشك");
  await expect(page.locator("#reality-warning a")).toHaveAttribute("href", "#field-checklist");
  await expectNoPageOverflow(page);
});

test("the standalone offline safety page is usable on a small phone", async ({ page, request }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/offline.html");
  await expect(page.getByRole("heading", { name: "السلامة تخدم حتى بلا إنترنت." })).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(12);
  await expect(page.getByRole("link", { name: "الحماية المدنية: 198" })).toHaveAttribute("href", "tel:198");
  const firstCheck = page.getByRole("checkbox", { name: /عاينت الكسرة/ });
  await firstCheck.check();
  await expect(page.locator("#progress-text")).toHaveText("1 من 12 مكتملة");
  await page.reload();
  await expect(firstCheck).toBeChecked();
  await expectNoPageOverflow(page);
  await page.getByRole("button", { name: "صفّر القائمة" }).click();
  await expect(firstCheck).not.toBeChecked();
  await expectNoPageOverflow(page);

  const worker = await request.get("/sw.js");
  expect(worker.ok()).toBeTruthy();
  expect(worker.headers()["cache-control"]).toContain("no-store");
  expect(await worker.text()).toContain('url.pathname.startsWith("/api/")');

  const manifestResponse = await request.get("/manifest.webmanifest");
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json() as { icons: Array<{ src: string; type: string }> };
  expect(manifest.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ src: "/icon-192.png", type: "image/png" }),
    expect.objectContaining({ src: "/icon-512.png", type: "image/png" }),
  ]));
});

test("an open app warns clearly when the connection is lost", async ({ page, context }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/");
  await context.setOffline(true);

  const banner = page.getByRole("status");
  await expect(banner).toContainText("الاتصال مقطوع");
  await expect(banner).toContainText("ما يأكدش حالة البحر الحالية");
  await banner.getByRole("link", { name: /قائمة السلامة/ }).click();
  await expect(page).toHaveURL(/#field-checklist$/);
  await expect(page.locator("#field-checklist")).toBeInViewport();
  await expectNoPageOverflow(page);

  await context.setOffline(false);
  await expect(banner).toHaveCount(0);
});

test("service worker returns the safety fallback instead of a stale decision", async ({ page, context }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
  });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  const cachedPaths = await page.evaluate(async () => {
    const paths: string[] = [];
    for (const cacheName of await caches.keys()) {
      const cache = await caches.open(cacheName);
      for (const request of await cache.keys()) paths.push(new URL(request.url).pathname);
    }
    return paths.sort();
  });
  expect(cachedPaths).toEqual(["/icon-192.png", "/icon-512.png", "/icon.svg", "/offline.html"]);

  await context.setOffline(true);
  await page.goto("/offline-safety-probe", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveTitle("Peche TN — وضع دون اتصال");
  await expect(page.getByRole("heading", { name: "السلامة تخدم حتى بلا إنترنت." })).toBeVisible();
  await expect(page.locator("#decision")).toHaveCount(0);
  await expectNoPageOverflow(page);
  await context.setOffline(false);
});

test("map disclosure and advanced settings are keyboard accessible", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();

  const mapToggle = page.locator(".map-toggle");
  await expect(mapToggle).toHaveAccessibleName("اخفِ الخريطة");
  await expect(mapToggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#spot-map-panel")).toBeVisible();
  await mapToggle.focus();
  await page.keyboard.press("Enter");
  await expect(mapToggle).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Enter");
  await expect(mapToggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#spot-map-panel")).toBeVisible();
  await expect(page.getByRole("button", { name: "نقطة الوقوف" })).toHaveAttribute("aria-pressed", "true");

  const seawardMode = page.getByRole("button", { name: "اتجاه عرض البحر" });
  await seawardMode.click();
  await expect(seawardMode).toHaveAttribute("aria-pressed", "true");
  const mapCanvas = page.locator(".map-canvas");
  await expect(mapCanvas).toHaveAccessibleName("خريطة لاختيار نقطة داخل البحر وحساب اتجاه البحر");
  await expect(page.locator(".orientation-help")).toContainText("من نقطة وقوفك على الساحل إلى عرض البحر");
  await expect(page.locator(".orientation-confirm")).toBeVisible();
  const mapBox = await mapCanvas.boundingBox();
  if (!mapBox) throw new Error("Map canvas has no bounding box");
  await page.mouse.click(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height * 0.25);
  await expect(page.locator(".orientation-confirm")).toHaveCount(0);
  const orientationText = await page.locator(".orientation-value strong").innerText();
  expect(orientationText).toContain("شمال");
  expect(Number(orientationText.match(/[\d.]+/)?.[0] ?? 999)).toBeLessThan(1);

  const advanced = page.locator(".advanced-settings > summary");
  await advanced.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".advanced-settings")).toHaveAttribute("open", "");
  await expect(page.getByLabel("الخبرة")).toBeVisible();
  await expectNoPageOverflow(page);
});

test("corrected Overpass orientation accepts zero degrees and preserves manual fallback", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  let shouldResolve = true;
  await page.route("**/api/v1/spots/orientation", async (route) => {
    const payload = route.request().postDataJSON() as { latitude: number; longitude: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(shouldResolve ? {
        status: "resolved",
        orientation_deg: 0,
        evidence: {
          orientation_deg: 0,
          coastline_tangent_deg: 270,
          coastline_distance_m: 42.5,
          search_radius_m: 3000,
          segments_used: 5,
          confidence: "high",
          provider: "OpenStreetMap Overpass",
          server: "https://overpass-api.de/api/interpreter",
          calculated_at: new Date().toISOString(),
          limitations_ar: ["هندسة خريطة وليست بوصلة ميدانية."],
        },
        reasons_ar: [`حُسب قرب ${payload.latitude},${payload.longitude}`],
      } : {
        status: "unavailable",
        orientation_deg: null,
        evidence: null,
        reasons_ar: ["تعذر الوصول إلى كل مرايا Overpass."],
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "رفراف" }).click();
  await expect(page.getByTestId("orientation-provenance")).toBeVisible();
  await expect(page.getByTestId("orientation-provenance")).toContainText("0.0°");
  await expect(page.getByTestId("orientation-provenance")).toContainText("270.0°");
  await expect(page.getByTestId("orientation-provenance")).toContainText("43 م");
  await expect(page.getByTestId("orientation-provenance")).toContainText("overpass-api.de");
  await expect(page.locator(".orientation-value strong")).toContainText("شمال");

  shouldResolve = false;
  const slider = page.getByLabel("اتجاه البحر بالدرجات");
  await slider.fill("123");
  await expect(page.locator(".orientation-value strong")).toContainText("123°");
  await page.getByTestId("orientation-recalculate").click();
  await expect(page.getByTestId("orientation-error")).toContainText("لم نخترع اتجاهاً بديلاً");
  await expect(page.locator(".orientation-value strong")).toContainText("123°");
  await expect(page.getByTestId("orientation-provenance")).toHaveCount(0);
  await expectNoPageOverflow(page);
});

test("Gemini key stays local, generation is explicit, and deterministic fallback remains", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 375, height: 667 });
  await mockForecast(page);
  const key = "runtime-test-key-not-for-source-control";
  let reportBody = "";
  let delayNextReport = false;
  await page.route("**/api/v1/gemini/verify", async (route) => {
    expect(route.request().headers()["x-gemini-api-key"]).toBe(key);
    expect(route.request().postData() ?? "").not.toContain(key);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: true,
        provider: "Google Gemini",
        model: "gemini-test",
        message_ar: "المفتاح صالح لهذا النموذج ولم يُخزن في الخادم.",
      }),
    });
  });
  await page.route("**/api/v1/reports/gemini", async (route) => {
    expect(route.request().headers()["x-gemini-api-key"]).toBe(key);
    reportBody = route.request().postData() ?? "";
    expect(reportBody).not.toContain(key);
    const payload = JSON.parse(reportBody) as { decision: DecisionResponse };
    expect(payload.decision.decision).toBe("go");
    expect(payload.decision.factor_assessments).toHaveLength(63);
    if (delayNextReport) {
      delayNextReport = false;
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        narrative: {
          executive_summary_ar: "سرد ملتزم بحكم المحرك وحدود البيانات.",
          timing_and_water_ar: ["التوقيت المعروض مرجع حتمي."],
          temporal_analysis_ar: ["النشاط السابق احتمال تراكمي لا مشاهدة."],
          factor_interactions_ar: ["اتجاه البحر يضبط قراءة الريح والموج."],
          field_tactics_ar: ["افحص الكسرة والمخرج قبل نصب العتاد."],
          unknowns_ar: ["العكارة والصوفة الفعليتان Unknown حتى المعاينة."],
        },
        report_text: "PECHE TN — RAPPORT GEMINI VALIDÉ\nالقرار والأرقام من المحرك الحتمي.",
        metadata: {
          generated_by: "google_gemini",
          model: "gemini-test",
          prompt_version: "peche-tn-writer-v6",
          template_version: "original-corrected-v3",
          generated_at: new Date().toISOString(),
          input_sha256: "a".repeat(64),
          decision_was_modified: false,
          numbers_are_server_rendered: true,
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "ولّد التقرير البحري" }).click();
  await expect(page.getByRole("heading", { name: "اذهب" })).toBeVisible();
  const report = page.locator("#spot-report");
  await expect(report.getByText("localStorage موش خزنة أسرار", { exact: false })).toBeVisible();
  await expect(report.getByTestId("factor-ledger").locator("article")).toHaveCount(63);

  const keyInput = report.getByTestId("gemini-key-input");
  await expect(keyInput).toHaveAttribute("type", "password");
  await keyInput.fill(key);
  await report.getByText("فهمت مخاطر التخزين المحلي", { exact: false }).click();
  await report.getByTestId("gemini-save-key").click();
  expect(await page.evaluate(() => localStorage.getItem("peche-tn:gemini-api-key"))).toBe(key);
  await report.getByTestId("gemini-test-key").click();
  await expect(report.getByTestId("gemini-status")).toContainText("المفتاح صالح");

  delayNextReport = true;
  await report.getByTestId("gemini-generate").click();
  await expect(report.getByTestId("gemini-generate")).toContainText("أوقف انتظار Gemini");
  await report.getByTestId("gemini-generate").click();
  await expect(report.getByTestId("gemini-status")).toContainText("ألغيت انتظار Gemini");
  await expect(report.getByTestId("gemini-generate")).toContainText("ولّد التقرير المنظم");

  await report.getByTestId("gemini-generate").click();
  await expect(report.getByTestId("gemini-narrative")).toContainText("سرد ملتزم");
  await expect(report.getByTestId("gemini-narrative")).toContainText("gemini-test");
  expect(reportBody).toContain('"decision":"go"');
  await report.getByRole("button", { name: "انسخ التقرير" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("RAPPORT GEMINI VALIDÉ");

  await report.getByRole("button", { name: "أغلق" }).click();
  await page.getByRole("button", { name: "التقرير الكامل + Gemini" }).click();
  await expect(page.locator("#spot-report").getByTestId("gemini-key-input")).toHaveValue(key);
  await expect(page.locator("#spot-report").getByTestId("gemini-key-input")).toHaveAttribute("type", "password");
  await page.locator("#spot-report").getByRole("button", { name: "احذف" }).click();
  expect(await page.evaluate(() => localStorage.getItem("peche-tn:gemini-api-key"))).toBeNull();
  await expect(page.locator("#spot-report").getByTestId("gemini-key-input")).toHaveValue("");
  await expectNoPageOverflow(page);
});
