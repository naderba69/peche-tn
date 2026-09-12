# أمثلة API — schema 2.1

العقد الكامل والتفاعلي موجود في `GET /api/docs` و`GET /api/openapi.json`. الأمثلة التالية **مقتطفات مختصرة**؛ الاستجابة الفعلية صارمة وتحتوي كل الحقول المطلوبة.

## 1. قرار توقع

```http
POST /api/v1/decisions/forecast
Content-Type: application/json
```

```json
{
  "location": {
    "latitude": 37.20,
    "longitude": 10.24,
    "name": "رفراف"
  },
  "target_date": "2026-09-09",
  "spot": {
    "shore_type": "sandy",
    "seaward_orientation_deg": 0,
    "orientation_source": "manual",
    "orientation_evidence": null,
    "exposure": "open"
  },
  "angler": {
    "experience": "intermediate",
    "session_hours": 3,
    "target_species": "general"
  }
}
```

مقتطف استجابة توضيحي:

```jsonc
{
  "schema_version": "2.1",
  "engine_version": "1.1.1",
  "decision": "go",
  "decision_reason_code": "safe_window",
  "decision_label_ar": "اذهب",
  "summary_ar": "...",
  "opportunity_score": 42,
  "score_is_success_probability": false,
  "confidence": {
    "score": 71,
    "band": "high",
    "reasons_ar": ["..."],
    "is_accuracy_probability": false
  },
  "field_feasibility": {
    "status": "favorable",
    "score": 78,
    "confidence": 46,
    "holding_difficulty": "low",
    "fouling_transport_potential": "moderate",
    "turbidity_potential": "low",
    "rip_current_potential": "low",
    "fouling_evidence_count": 2,
    "turbidity_evidence_count": 1,
    "antecedent_window_hours": 48,
    "reasons_ar": ["..."],
    "limitations_ar": ["هذا فحص احتمالي وليس رصداً داخل البقعة."],
    "is_direct_observation": false
  },
  "recommended_windows": [
    {
      "start": "2026-09-09T05:00:00+01:00",
      "end": "2026-09-09T08:00:00+01:00",
      "safety": "go",
      "field_feasibility": "favorable",
      "field_score": 78,
      "opportunity_score": 42,
      "confidence_score": 71,
      "headline_ar": "...",
      "key_factors_ar": ["..."]
    }
  ],
  "hourly": [
    {
      "time": "2026-09-09T05:00:00+01:00",
      "safety": "go",
      "opportunity_score": 44,
      "confidence": { "score": 71, "band": "high", "reasons_ar": ["..."], "is_accuracy_probability": false },
      "field_feasibility": { "...": "..." },
      "factors": ["..."],
      "forecast": { "...": "..." },
      "derived": {
        "wind_relation": "cross_onshore",
        "wave_incidence": "direct",
        "rain_48h_mm": 3.2,
        "rain_72h_mm": 4.1,
        "max_wave_height_48h_m": 1.3,
        "wave_energy_integral_48h": 167.4,
        "onshore_wind_impulse_48h_kmh_h": 104.2,
        "onshore_wind_stress_impulse_48h_pa_h": 0.83,
        "wind_alongshore_signed_component_kmh": -0.84,
        "alongshore_positive_bearing_deg": 90,
        "wind_stress_pa": 0.0245,
        "wind_stress_shoreward_pa": 0.023,
        "wind_stress_alongshore_pa": -0.0084,
        "wave_alongshore_signed_alignment": -0.05,
        "alongshore_wave_signed_proxy": -0.31,
        "wave_component_angle_deg": 34,
        "wave_component_secondary_energy_share": 0.28,
        "wind_direction_coherence_6h": 0.94,
        "wind_direction_data_hours_6h": 6,
        "air_sea_temperature_difference_c": 2.1,
        "dew_point_depression_c": 5.4,
        "shoreward_current_impulse_48h_kmh_h": 4.6,
        "history_hours_48h": 48,
        "wave_energy_data_hours_48h": 48,
        "wind_data_hours_48h": 48,
        "current_data_hours_48h": 42
      }
    }
  ],
  "antecedent_hours": ["حتى 72 ForecastHour خاماً مطبعاً قبل اليوم/الحصة"],
  "sources": ["Open-Meteo Weather API", "Open-Meteo Marine API", "AviationWeather.gov METAR", "Copernicus Marine Sentinel-2 WMTS"],
  "current_weather_observation": { "is_direct_observation": true, "is_spot_observation": false, "...": "..." },
  "coastal_water_context": {
    "availability": "available",
    "provider": "Copernicus Marine Service",
    "product_id": "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205",
    "dataset_id": "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m_202107",
    "data_kind": "remote_sensing_estimate",
    "sample_strategy": "fixed_1000m_seaward_axis",
    "sample_latitude": 37.20899,
    "sample_longitude": 10.24,
    "sample_distance_from_spot_m": 1000.0,
    "pixel_latitude": 37.2088,
    "pixel_longitude": 10.2401,
    "pixel_distance_from_spot_m": 982.4,
    "pixel_distance_from_sample_m": 22.7,
    "spatial_resolution_m": 100,
    "valid_time": "2026-09-06T00:00:00Z",
    "retrieved_at": "2026-09-09T14:12:00Z",
    "age_hours": 86.2,
    "search_days": 10,
    "turbidity_fnu": 0.32,
    "turbidity_unit": "FNU",
    "suspended_particulate_matter_g_m3": 0.18,
    "suspended_particulate_matter_unit": "g/m³",
    "chlorophyll_a_mg_m3": 0.54,
    "chlorophyll_a_unit": "mg/m³",
    "reason_ar": "أحدث TUR صالح عند نقطة العينة الثابتة؛ SPM وCHL من النقطة والتاريخ نفسيهما.",
    "affects_final_decision": false,
    "is_direct_observation": false,
    "is_spot_observation": false,
    "is_forecast": false
  },
  "observation_comparison": { "status": "consistent", "...": "..." },
  "factor_coverage": { "audited_total": 63, "...": "..." },
  "factor_assessments": [
    {
      "matrix_id": "2.2",
      "chapter_ar": "البحر والموج",
      "title_ar": "الأعشاب والحطام العالق",
      "status": "proxy",
      "decision_axis": "قابلية التنفيذ",
      "value_ar": "احتمال متوسط؛ عائلتان من القرائن التشغيلية وليستا رصدين مستقلين",
      "evidence_variables": ["wave_energy_integral_48h", "rain_48h_mm"],
      "rationale_ar": "لا يثبت وجود الصوفة؛ يلزم تحقق ميداني.",
      "affects_final_decision": false
    }
    // ... بالضبط 63 عاملاً فريداً، بما فيها Unknown والمستبعد
  ],
  "limitations_ar": ["..."],
  "generated_at": "2026-09-09T15:12:00+01:00"
}
```

`decision_label_ar` لا يقبل إلا `اذهب` أو `لا تذهب`. إذا كان القرار `no_go` تكون `recommended_windows` فارغة ويبين `decision_reason_code` أحد الأسباب: `safety_hazard` أو `critical_data_missing` أو `field_infeasible` أو `conservative_uncertainty`.

القيم داخل `hourly[].forecast` و`antecedent_hours` توقعات نموذجية، لا رصد Spot. `current_weather_observation` وحده قد يكون METAR مباشراً من محطة مطار، مع `is_spot_observation=false` والمسافة والعمر والسطر الخام. `coastal_water_context` استعادة Sentinel‑2 يومية متقطعة عند نقطة بحرية ثابتة؛ ليست قياساً ميدانياً أو توقعاً للساعات، ولا تدخل القرار. `null/NaN` يبقى `Unknown` ولا يصبح صفراً.

## 2. اتجاه الساحل الآلي

```http
POST /api/v1/spots/orientation
Content-Type: application/json
```

```json
{ "latitude": 37.20, "longitude": 10.24 }
```

عند النجاح:

```json
{
  "status": "resolved",
  "orientation_deg": 0,
  "evidence": {
    "orientation_deg": 0,
    "coastline_tangent_deg": 90,
    "coastline_distance_m": 38.4,
    "search_radius_m": 3000,
    "segments_used": 5,
    "confidence": "high",
    "provider": "OpenStreetMap Overpass",
    "server": "https://overpass-api.de/api/interpreter",
    "calculated_at": "2026-09-08T14:10:00+01:00",
    "limitations_ar": ["تقدير من هندسة الخريطة؛ يمكن تصحيحه يدوياً."]
  },
  "reasons_ar": ["حُسب الاتجاه من أقرب إسقاط على الساحل."]
}
```

عند تعذر كل mirrors لا تُخترع زاوية:

```json
{
  "status": "unavailable",
  "orientation_deg": null,
  "evidence": null,
  "reasons_ar": ["تعذر حساب اتجاه الساحل آلياً؛ أبقِ التعديل اليدوي."]
}
```

## 3. Gemini الاختياري

المفتاح يمر وقت الطلب فقط ولا يخزن في الخادم:

```http
POST /api/v1/gemini/verify
X-Gemini-API-Key: <runtime-key>
```

```http
POST /api/v1/reports/gemini
Content-Type: application/json
X-Gemini-API-Key: <runtime-key>

{ "request": { "...": "ForecastDecisionRequest" }, "decision": { "...": "DecisionResponse schema 2.1" } }
```

يعيد التقرير السردي المقيد و`report_text` المركب في الخادم وmetadata مثل:

```json
{
  "metadata": {
    "generated_by": "google_gemini",
    "model": "gemini-3.8-flash",
    "prompt_version": "peche-tn-writer-v6",
    "template_version": "original-corrected-v3",
    "generated_at": "2026-09-08T14:12:00+01:00",
    "input_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "decision_was_modified": false,
    "numbers_are_server_rendered": true
  }
}
```

القيمة الأخيرة توضيحية فقط؛ البصمة الحقيقية 64 خانة hex. Gemini لا يعيد القرار أو الأرقام كسلطة. لا ترسل حزمة الكاتب إحداثيات أو raw history أو الأرقام الخام لكل ساعة؛ تبقى هذه في التقرير الحتمي. يجوز إعادة توليد JSON غير الصالح مرة واحدة ضمن سقف عالمي من أربع اتصالات ومهلة كلية 40 ثانية، ثم يُرفض؛ أما محاولة إضافة رقم أو إعطاء أمر قرار فتُرفض فوراً بلا إعادة توليد.
