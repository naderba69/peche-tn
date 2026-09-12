# Changelog

## 1.10.0 — 2026-09-12 (engine 1.6.8, schema 3.9)

### إعادة تصميم شاملة — "Marine Glass" (UI/UX فقط، لا تغيير في المحرك أو المخطط)

- **هوية بصرية مصقولة على الثيم البحري الليلي الحالي** بدل كسره: أسطح زجاجية متدرجة، خطوط أكبر، تباعد أوسع، بطاقات أنعم، ولوحة توكنز محدثة. خطا **Cairo/Tajawal** يُحمّلان الآن ذاتياً عبر `next/font` (أوفلاين وفي المعاينة) بدل الاكتفاء بذكرهما في الحزمة دون تحميل.
- **توافق الهايت:** `100dvh` في كل مكان (مع `100vh` كخلفية متوافقة)، و`scroll-margin-top`/`scroll-padding-top` مربوطان بارتفاع الهيدر اللاصق بدل القيم الثابتة الضئيلة (كانت 18px).
- **هيدر موحّد** في مكوّن واحد (`components/SiteNav.tsx`) بدل تكرار `site-header` يدوياً في الصفحات الأربع؛ زجاجي لاصق مع تمييز الرابط النشط.
- **تنقّل موبايل سفلي** بأسلوب تطبيق (`BottomNav`) بأربعة تبويبات بأيقونات، ظاهر فقط ≤760px؛ الهيدر العلوي يُبقي الشعار والشارة. إزالة شريط `workspace-tabs` المكرر نهائياً.
- **التقرير الكامل يُعرض بتبويبات لاصقة** بدل الجدار المرقّم: الملخص / التوقيت والنوافذ / الأسماك / التنفيذ والعوامل / المراجع والمصادر؛ كل تبويب لوحة مستقلة، مع وضع طباعة يعرض الأقسام كاملة.
- **إصلاح الريسبانسيف في الأقسام الجديدة:**
  - جدول نشاط الأنواع (كان `min-width: 520px` بتمرير أفقي) يتحوّل على الهاتف إلى **بطاقات فترات** لكل نوع.
  - منحنى النشاط الساعي أعيد ضبطه (حدّ أدنى أوسع للأعمدة، ارتفاع أكبر) ليبقى مقروءاً.
  - ألوان الحالة (`act-strong/medium/weak/low/none`) تعمل الآن على الخلايا والبطاقات معاً.
- تعديل `ConnectionStatus` و`planner-action-bar` ليرتفعا فوق الشريط السفلي على الهاتف.
- App `1.9.10 → 1.10.0` (طبقة العرض فقط؛ المحرك `1.6.8` والمخطط `3.9` دون تغيير).

## 1.9.10 — 2026-09-12 (engine 1.6.8, schema 3.9)

### Fix: Render 404 on clean-URL pages (/calendar, /wilayas, /bulletin)

- Next's static export writes each route as `<route>.html` (e.g. `calendar.html`) beside a `<route>/` directory of RSC navigation payloads. Starlette's `StaticFiles(html=True)` only serves `index.html` inside directories, so the clean URLs 404'd on Render while `/` and `/api/*` worked. `deploy/render_app.py` now registers explicit clean-URL routes for every exported top-level `.html` page before mounting the catch-all static files.
- Regression test: `test_render_app_serves_clean_urls_for_exported_pages`.
- App `1.9.9 → 1.9.10` (deployment layer only; engine and schema unchanged).

## 1.9.9 — 2026-09-12 (engine 1.6.8, schema 3.9)

### Daily fish-activity indicator per species (reporting only, 0–100 relative)

- Added a **relative activity indicator (0–100)** for the four species + general, shown across **six periods of the day** (فجر/صباح/ظهيرة/عصر/غسق/ليل) plus a **per-hour curve** per species, in a new "نشاط الأسماك خلال فترات اليوم" panel inside the full report and a compact block in the TXT report.
- Score is deterministic and transparent: base 50 + the same documented low-weight priors used elsewhere in the engine — feeding window (twilight/night bonus per species), water temperature (preferred/tolerated/outside), seasonal availability from published studies (dominant ±15/6/−6/−20), shore match (±3), and sea-state fit (+5). "صيد عام" uses only the twilight/night bonus.
- Strictly reporting-only: the indicator **never** feeds the binary `go/no_go` and is **never a statistical probability** — `is_probability: false` on every species block, and the basis text states it needs a calibrated Tunisian catch log (including zero-catch trips) to become a probability. No fabrication (D10/D11).
- New models `SpeciesActivity`, `PeriodActivity`, `HourActivity`; `DecisionResponse.species_activity` list (5 entries). Period boundaries are presentation buckets; the hourly scores already carry the model sunrise/sunset twilight flags.
- Schema `3.8 → 3.9` (additive `species_activity`), engine `1.6.7 → 1.6.8`.
- New tests: `apps/api/tests/test_species_activity.py` (7 cases).

## 1.9.8 — 2026-09-12 (engine 1.6.7, schema 3.8)

### Evidence-gated trip-ruining factors + quasi-live satellite data for the spot

- Added the five trip-ruining factors the engine previously only hinted at, each evidence-gated and always disclosing its source and age: **dense fouling/weed, turbidity, jellyfish, marine heatwave, storm debris** — rendered in a new "ما قد يُفسد الخرجة" panel in the full report, a compact line in the mini report, and a new `TripRuinFactor` list in the API.
- Quasi-live spot data: the Copernicus ocean-colour NRT product (TUR/SPM/CHL, daily Sentinel-2/3-derived) now feeds the fouling ladder — a dense bloom (CHL ≥ 10 mg/m³) **plus** high onshore transport escalates to confirmed fouling force-majeure; the satellite context also carries an optional `sea_surface_temperature_c` (shown when present).
- Blocking policy stays strict: only **confirmed evidence** blocks (satellite-strong fouling, or a fresh dense field report for jellyfish/debris/turbidity → new reason code `trip_ruin_confirmed` + `ForceMajeureKind.TRIP_RUIN`); forecast/proxy stays a caution, unsupported stays Unknown (D11).
- Every live datum shows its age: satellite (image date + hours), field report (hours), or "تنبؤ نموذجي" — and old data is never presented as fresh.
- Jellyfish and storm debris have no operational satellite product (remote-sensing jellyfish models are statistical only, ~60–70% accuracy), so they remain `Unknown` unless a fresh field report exists — no fabrication.
- `FieldReport.kind` extended with `jellyfish` and `debris`; `DecisionReasonCode.TRIP_RUIN_CONFIRMED` added.
- Schema `3.7 → 3.8` (additive `trip_ruin_factors` + `CoastalWaterContext.sea_surface_temperature_c`), engine `1.6.6 → 1.6.7`.
- New tests: `apps/api/tests/test_trip_ruin.py` (8 cases).

## 1.9.7 — 2026-09-12 (engine 1.6.6, schema 3.7)

### Sea-state × month dimension for each species (reporting only)

- Added a **sea-state × month** axis to every profiled species: the day's sea state is classified from model wave height (**هادئ** < 0.6m, **معتدل** 0.6–1.1m, **هائج** > 1.1m) plus a model-estimated **foam/whitecaps** hint (wave ≥ 0.8m or sustained wind ≥ 22 km/h), always disclosed as an estimate, not an observation.
- Each species carries a published sea-state preference: القاروص — بحر متكسر مع رغوة (Cervera et al. 2024; FishBase); السار — موج يتكسر على الصخور (FishBase Ref. 13780; PLOS ONE 2016); الوراطة — كسرة معتدلة على رمل/أعشاب (FishBase; JMSE 2023); المرمار — ماء هادئ على رمل ضحل/منطقة الغسل (WoRMS/FishBase/Monaco; Buxton et al. 1984).
- These are published **Mediterranean/general patterns disclosed as such** (no Tunisian surf-zone study exists yet); the mormyrus "calm" preference is shown as a disclosed general inference per the user's choice. Unsupported values stay `Unknown`; no legal rules (D10/D11).
- Surfaced in the full report (`sea_state_ar` line + per-species `sea_state_fit` chip), the mini report, and the calendar page ("حالة البحر المفضلة" card per species). The dimension never re-orders the species list and never changes the binary `go/no_go`.
- `SpeciesMatch` gains `sea_state_ar`, `sea_state_preference_ar`, `sea_state_fit`; `SpeciesAxes` gains `sea_state_ar`.
- Schema `3.6 → 3.7` (additive), engine `1.6.5 → 1.6.6`.
- New tests: `test_sea_state_fit_tracks_wave_and_wind`, `test_sea_state_is_report_only_and_disclosed`.

## 1.9.6 — 2026-09-12 (engine 1.6.5, schema 3.6)

### Species seasonality rebuilt on published Tunisian / Mediterranean studies

- Replaced the month × zone presence matrices in `species.py` and `lib/seasonalCalendar.ts` so every availability level is derived from published scientific studies, not undifferentiated expert opinion: Mouine et al. 2007 (السار، خليج تونس), Hadj-Taieb et al. 2013 (الوراطة، خليج قابس), Cybium 2016 (المرمار، خليج قابس), Bauchot 1987 / Cervera et al. 2024 / FAO-MEDRAP (القاروص), plus Chaoui et al. 2006 and Kallianiotis et al. 2005 for the general Mediterranean patterns — a `SOURCE_REGISTRY` of eight cited references now backs the matrices.
- Added `SpeciesMatch.sources_ar` and `SpeciesAxes.sources_ar` (aggregated bibliography); the engine fills them from `SOURCE_REGISTRY` with full citations, so every species match carries its scientific source in the API response and on the calendar page and full report.
- Where no Tunisian study exists yet (القاروص), the Mediterranean pattern is used and explicitly disclosed as not locally verified; unsupported values stay `Unknown`, and no legal rules (sizes/closed seasons) ever enter the species axis (D10/D11).
- The species-match list remains report-only: no catch probability, and it never changes the binary `go/no_go`.
- Updated `docs/SOURCES-AUDIT.md` §3 and §5 with the exact citations and URLs.
- Schema `3.5 → 3.6` (additive `sources_ar` on `SpeciesMatch`/`SpeciesAxes`), engine `1.6.4 → 1.6.5`.

## 1.9.5 — 2026-09-11 (engine 1.6.4, schema 3.5)

### Fish availability + matching species (reporting only)

- Added `SpeciesAxes.species_matches`: for every profiled species (القاروص، الوراطة، السار، المرمار) the engine now reports today's **availability** (قوي/متوسط/ضعيف/غير متوفر from the audited month × zone matrix), the **thermal** fit (SST preferred/tolerated/outside), the **habitat** fit, and a combined **match status** (مناسب/محايد/غير مناسب) sorted best-first, with Arabic reasons.
- The species block no longer leaves a "صيد عام" request with only Unknown axes: the match list answers "ما الأسماك المتوافرة الآن التي تتماشى مع العوامل الحالية؟" while staying strictly report-only — no catch probability, no legal rules (D10/D11).
- Rendered in the full report (SpotReport) and summarized in the mini report ("الأفضل توفراً: …").
- Schema `3.4 → 3.5` (additive field on `SpeciesAxes`), engine `1.6.3 → 1.6.4`.
- New tests: `test_species_matches_report_availability_and_match_for_all_profiled_species`, `test_species_matches_availability_reflects_zone_x_month`, `test_species_matches_thermal_and_habitat_priors`, `test_species_matches_honour_missing_sst_without_fabricating_thermal`.

## 1.9.4 — 2026-09-11 (engine 1.6.3)

### Decision-engine correction from the experiment pass

- Fixed a false no-go: a day whose best window is CAUTION (not clean GO) is no longer returned as `no_go/safety_hazard`. `_day_decision` now blocks only on a NO_GO window (defensive); a CAUTION window is a "go with caution" (`اذهب بحذر`) with its caution factors visible in the summary and key factors.
- Added a near-limit escalation rule in `_safety`: two or more independent safety gates simultaneously within 10% of their no-go threshold (still inside the caution band) escalate the hour to NO_GO (`multiple_near_limit_cautions`), so a single near-limit caution never cancels the day but several combined ones still do.
- The GO summary now reads "اذهب بحذر" when the best window is CAUTION.
- New regression tests lock the behavior (`test_all_caution_day_is_go_with_caution_not_no_go`, `test_high_uv_all_day_is_go_with_caution`, `test_multiple_near_limit_cautions_escalate_to_no_go`, `test_single_near_limit_caution_stays_go`).
- New experiment harness `scripts/engine_experiments.py` (55 checks + 3000-case property fuzz) — all green; results in `docs/engine-experiments-results.json`.

## 1.9.3 — 2026-09-11

### QA pass: deployment tooling, dead code and documentation drift

- Fixed the post-deployment smoke test (`scripts/smoke_deployment.py`): it pinned `1.3.2` / schema `2.1` / engine `1.1.1` and would have failed on every current release. It now reads the expected versions from the repository source (`__version__`, `ENGINE_VERSION`, `SCHEMA_VERSION`), overridable via `PECHE_TN_EXPECTED_*`, and falls back to consistency checks outside a checkout. Verified end-to-end against a local Render-topology run (static frontend + FastAPI on one origin): `ALL PASS`.
- Removed an unreachable `dense_fouling` branch in `_fouling_evidence` (a single dense report was already covered by the single-user-report rule; the dead branch contradicted the "several consistent reports → force-majeure" design).
- Removed a hard-coded `1.7.0` API-version fallback in the frontend; an offline→online transition now re-checks health instead of fabricating a version.
- Fixed `compose.yaml`: added `PORT=8000` so the container listens on the port mapped and health-checked by Compose.
- Corrected stale version references in `README.md` (schema/engine), `RENDER.md`, `VERCEL.md`, `TERMUX-GITHUB.md`, `apps/api/README.md` and the `/calendar` footer.
- Advanced the application to `1.9.3` (engine `1.6.2`, schema `3.4` unchanged).

## 1.9.2 — 2026-09-10

### Final review fixes: QNH/SLP pressure gate and a duplicated request field

- Station pressure is now compared against model mean sea-level pressure only when the METAR reports a real SLP (`pressure_kind == "sea_level_pressure"`); a QNH altimeter setting no longer triggers false model/station pressure divergence (review §3.7). The divergence note now states the comparison was skipped rather than "approximate".
- Removed a duplicated `official_warning` field on `ForecastDecisionRequest` (harmless re-declaration, cleaned up during the final pass).
- Added a regression test locking the QNH non-comparison behaviour; full suite now **202 passed**.
- Advanced the application to `1.9.2` and the engine to `1.6.2` (schema unchanged at `3.4`).

## 1.9.1 — 2026-09-10

### Numerical-accuracy review fixes (docs/NUMERICAL-REVIEW.md)

- Full audit of every number, formula and threshold (physics, policy, priors, data units) — see `docs/NUMERICAL-REVIEW.md`. Verified against Open-Meteo conventions (waves "from", current "towards", km/h), Large & Pond drag, linear wave theory, CERC longshore proxy, haversine/Mercator and species SST ranges.
- Fixed `tunisian_zone()`: the northwest (سراط) coast climbs past 37°N, so longitude is now tested before latitude (Cap Serrat / Sidi Mechreg now classify `northwest`); the Cap Bon tip (Haouaria) no longer falls into the Gulf of Tunis band; and the Gulf of Gabès box was split so all of Djerba classifies stably as `south` instead of flipping with a 0.01° step.
- Documented the Open-Meteo caveat that high-resolution currents and sea level are only available in Central Europe/North America (interpolated global model for Tunisia) in both the source metadata and the spring/neap limitations.
- Relabelled the opportunity indicator across the UI to "مؤشر الفرصة النسبي" (relative indicator) so the 0–100 figure is never read as a catch probability; the binary go/no_go headline is untouched.
- Advanced the application to `1.9.1` and the engine to `1.6.1` (schema unchanged at `3.4`). Added zone-classifier regression tests (northwest past 37°N, Cap Bon tip, Djerba stability).

## 1.9.0 — 2026-09-10

### INM bulletin page and wider spot catalogue (v2 phase 7 close-out)

- Added the official INM bulletin page (D14) at `/bulletin`: lists the five official coastal zones (سراط، خليج تونس، خليج الحمامات، الشابة، جربة) and deep-links the four official bulletins (coastal, large, BMS, vigilance map). It opens in the site navigation (home, wilayas, calendar).
- Engineering decision documented: INM renders its bulletin tables client-side with no stable machine-readable API, so the app never auto-asserts "no warning"; the official bulletin remains the authoritative source and the existing manual official-warning selector stays the safety gate (`NO_GO / OFFICIAL_WARNING / ACCESS_LEGAL`).
- Expanded the spot catalogue in `lib/spots.ts` with 12 named spots (Bizerte, Ghar el Melh, Gammarth, La Goulette, Haouaria, Korba, Beni Khiar, Hammamet, Sousse, Monastir, Chebba, Ben Guerdane) so the wilaya ranking page covers every coastal governorate with real, defensible candidates. All orientations remain initial approximations and stay honest on the map.
- Advanced the application to `1.9.0` (engine `1.6.0`, schema `3.4` unchanged).

## 1.8.0 — 2026-09-10

### Source audit and the seasonal calendar (v2 phase 1 + D15)

- Completed the source audit (`docs/SOURCES-AUDIT.md`): the six Tunisian coastal zones are now fixed with geographic references, tide harmonics stay FES2014/TPXO via CMEMS (no lunar rule), and the four species (seabass, gilthead seabream, white seabream, striped seabream) have month × zone presence matrices synthesized from published reproduction/migration biology — no legal sizes, no legal seasonal bans (D10).
- Wired the audited matrix into the engine: the "seasonal availability" species axis now reports the month/zone presence level (strong/medium/weak/unavailable) instead of Unknown, with an explicit "expert synthesis, not a catch log" note. The `tunisian_zone(lat, lon)` classifier places any coordinate in one of the six zones.
- Added the seasonal calendar page (D15) at `/calendar`: a month × Tunisian-region color table per species with a legend and honest disclaimers.
- Advanced the deterministic engine to `1.6.0` and the application to `1.8.0` (schema unchanged at `3.4`). Added regression tests for the seasonal axis and the zone classifier.

## 1.7.0 — 2026-09-10

### Wilaya ranking, post-session loop and the official-warning gate (v2 phase 7)

- Added the "choose wilaya(s) → ranked spots" page (D13): a separate `/wilayas` page where the angler picks one or more governorates, and the engine analyzes the known spots in them for one day and ranks them best-to-weakest, each with go/no-go, best hour, field feasibility, the relative opportunity indicator and the species axes. Backed by a new `POST /api/v1/decisions/rank-spots` endpoint and `DecisionEngine.rank_spots` (ranking: go/no-go first, then field feasibility, then opportunity; failed fetches stay last with an explanatory error).
- Added the post-session feedback loop (local-first): a ten-field form under every result (lead holding, setup, drift, fouling, turbidity, rip current, catch, blank casts, actual duration, notes), stored only in the browser's localStorage with JSON export and clear. Calibration-only: it never enters any live decision.
- Added the official-warning gate (D14): an optional `official_warning` on the request (INM source, kind, level). Any valid official warning is a hard no-go above every local threshold — reason `official_warning`, force-majeure kind `access_legal`. The Planner exposes an INM-warning selector; automatic INM bulletin fetching remains pending a stable feed.
- Advanced Decision API schema to `3.4`, engine to `1.5.0`, application to `1.7.0`. Added regression tests for ranking order, failed-fetch handling, and the official-warning override.

## 1.6.0 — 2026-09-10

### Species axes block (v2 phase 6 / E7)

- Added a reporting-only `species_axes` block to the decision response: five separate axes (seasonal availability, habitat match, surf approach, feeding window, prey evidence) plus an overall confidence and an explicit `unknown_axes` list. The axes never aggregate into a single "catch probability" and never change the binary go/no-go: a weak fish profile cannot veto a safe executable window.
- Spring/neap now enters the species layer through the surf-approach axis as a physical factor (range, level-rate, tidal-current rating) — never a lunar-phase claim. The per-species `spring_neap_response` stays Unknown until a Tunisian catch log is calibrated, and seasonal availability stays Unknown until the source audit; no legal sizes or seasonal bans (D10).
- Extended `SpeciesProfile` with habitat and calibration placeholders; the mini report shows a compact species line and the full report renders the five-axis block with favourable/neutral/unfavourable/unknown chips.
- Advanced Decision API schema to `3.3`, engine to `1.4.0`, application to `1.6.0`. Added regression tests locking the axis structure and the "species never vetoes a safe window" invariant.

## 1.5.0 — 2026-09-10

### Fouling evidence ladder and spring/neap classification (v2 phase 4–5)

- Added the five-rung fouling/debris/turbidity evidence ladder. Transport proxies stay caution-only (levels 1–2); recent field reports (user/community/official) and a real test cast can reach levels 4–5. Confirmed evidence (`level >= 4`) is a force majeure that overrides a safe GO into NO_GO with reason `FOULING_CONFIRMED` and kind `fouling`. Reports are time-bounded (fresh within 24 h, not future beyond 1 h) and capped at 10.
- Added spring/neap classification computed solely from the modelled sea-level series: the target day's range divided by the series median range (spring `>= 1.3`, neap `<= 0.7`, otherwise intermediate). No lunar-phase rule. The Gulf of Gabès tide zone (lat 33.5–34.9, lon 9.7–11.4) is flagged with reduced confidence, and folk labels (حيّة / مات / وسط) are shown beside the physical range/rate values. Species response remains Unknown until the species-calibration phase.
- Extended the request/dataset with optional `field_reports` and `test_cast`, and the response with `fouling_evidence` and `spring_neap`. The Planner now collects field reports and a test cast, and the mini report and full report render both new blocks.
- Advanced Decision API schema to `3.2`, engine to `1.3.0`, application to `1.5.0`. Added regression tests for the evidence ladder and spring/neap classification.

## 1.4.0 — 2026-09-10

### Quick-summary layer, holding-breakdown and gear recommendation (v2 phase 1–3)

- Added a `MiniReport` quick-summary layer above the full deterministic report (decision D12): a binary go/no-go badge, the force-majeure cause or best window, six short factor chips with descriptive labels, and the proposed gear. The full report and all 63 factors stay untouched underneath.
- Split the single line-holding difficulty into four diagnostic mechanisms via a new `holding_breakdown` field: longshore current, near-bed orbital motion (from the linear dispersion relation `ω² = g·k·tanh(k·h)` and `Ub = πH/(T·sinh(k·h))` across a declared 1.5–5.0 m depth band), return flow, and tidal current, plus a dominant mechanism and bounded confidence (≤30). This is diagnostic only: the existing `holding_difficulty` gate and its computation are unchanged, so no binary decision changes.
- Added a lead catalog and `gear_recommendation`: three bottom-agnostic scenarios (shape + weight band + montage class + snag/hold notes) chosen from the dominant holding mechanism, always conditional on the rod rating, never a single gram value and never a brand. The bottom under the cast stays Unknown, so a rocky/Posidonia scenario always appears last.
- Added `force_majeure_kind` (`none|safety|holding|fouling|access_legal|data`) derived from the reason code; fouling and access_legal are reserved for the evidence ladder and the official INM bulletin phases.
- Advanced Decision API schema to `3.0`, engine to `1.2.0`, application to `1.4.0`. Added regression tests for the dispersion solver, near-bed orbital velocity, the four-mechanism breakdown, gear recommendation invariants and force-majeure mapping.

## 1.3.2 — 2026-09-10

### Truthful time-local windows and proxy authority

- Made high fouling/debris and turbidity transport potentials caution-only unless confirmed in the field. They still reduce the transparent field score and require inspection, but uncalibrated model proxies can no longer veto an otherwise safe window or masquerade as observed water quality.
- Kept physical line-holding difficulty, critical missing data and safety hazards as hard gates. A localized thunder hour now remains an explicit avoid window while a separate multi-hour window may receive `go` when it passes every applicable gate.
- Aligned the displayed primary reason with `decision_reason_code` and the deterministic summary instead of the most severe factor found anywhere in the day. Period badges now say `سلامة` explicitly, the factor balance warns that it aggregates the full day, and reports explain that a time-local hazard does not contaminate separate hours.
- Added a regression combining one WMO thunderstorm hour with three-family high turbidity potential: the storm hour is excluded, the proxy remains a field warning, and the independent safe window survives.
- Advanced the application to `1.3.2`, engine to `1.1.1`, factor catalog to `matrix-v3-audit-5`, Gemini prompt to `peche-tn-writer-v6`, and deterministic Gemini template to `original-corrected-v3`; schema remains `2.1`.

## 1.3.1 — 2026-09-10

### Bounded Gemini generation

- Replaced the duplicated full request/decision prompt with a purpose-limited writer packet: all 63 audited factors and every evaluated hour remain represented categorically, while coordinates, raw antecedent hours and raw hourly numbers stay server-side for the deterministic report. A representative maximum-history regression fixture reduced the outgoing prompt from about 334 kB to 37 kB.
- Added a 64 kB hard packet guard, a shared 40-second server deadline and shorter retry delays. Structural regeneration and transient retries still share the same four-call ceiling, but successive transport timeouts can no longer multiply into a multi-minute wait.
- Added a 42-second browser cutoff and turned the busy generation button into an explicit cancel control. Abort ownership is race-safe, so timeout or cancellation always releases the spinner while preserving the complete deterministic report.
- Classified bounded provider timeouts separately, advanced the constrained writer to `peche-tn-writer-v5`, and added packet-size, deadline and cancellation regressions. Decision schema `2.1`, engine `1.1.0`, catalog `matrix-v3-audit-4` and every authority boundary are unchanged.

## 1.3.0 — 2026-09-10

### Defensible directional and forcing diagnostics

- Kept the legacy absolute alongshore wind/wave fields, corrected their documented equation to `|V sin Δ|`, and added signed fields on the declared positive axis `bearing=(S+90) mod 360`; current remains a `towards` vector while wind and wave remain `from` bearings.
- Added vector neutral wind stress in pascals using `rho_air Cd |U10| U10_vector` and the documented Large–Pond drag relation, including signed shore-axis projections and the positive-shoreward 48-hour `Pa·h` integral. These are Shadow diagnostics and add no safety threshold or duplicate score.
- Added speed-weighted circular wind-direction coherence over six hours with calm exclusion, minimum sample coverage and the existing maximum adjacent-hour shift shown alongside it.
- Split wind-wave/swell crossing into the circular angle and weaker-system `H²` share. Removed the former uncalibrated crossing-angle caution and opportunity penalty; no CSI or replacement threshold was invented.
- Added signed relative alongshore wave forcing, explicit air-minus-sea and air-minus-dew differences, and strict `null → Unknown` behavior for every new derivation.

### Hourly evidence and Sentinel-2 pilot

- Replaced the single reference-hour equation panel with a responsive, printable table covering every evaluated hour, plus ranges, absolute peaks and per-diagnostic coverage. Text downloads and server-rendered Gemini reports now carry the same hourly deterministic diagnostics.
- Added an optional no-secret Copernicus Marine WMTS adapter for the 100 m Sentinel‑2 Mediterranean TUR/SPM/CHL product. It samples one fixed point 1 km along the declared seaward axis, searches only backwards in time for the latest valid daily TUR pixel, then requests SPM and CHL at that exact point/date.
- Preserved product provenance: valid time, layer age, sample and pixel coordinates, distances, spatial resolution and original units (`FNU`, `g/m³`, `mg/m³`). Null/NaN, cloud-invalid or upstream failures remain `Unknown`; no sideways valid-pixel search or gap filling occurs, and an older value is not labelled latest when a newer date could not be resolved.
- Kept remote-sensing values outside GO/NO_GO, safety, feasibility, fishing-opportunity and confidence scores. TUR is never converted to NTU, and TUR/SPM/CHL are never relabelled as field measurements, future forecasts, weed/rip-current observations or catch probability.
- Advanced the Decision API to schema `2.1`, the deterministic engine to `1.1.0`, factor catalog to `matrix-v3-audit-4`, the Gemini writer/template to `v4/v2`, and the application/package to `1.3.0`.

## 1.2.3 — 2026-09-09

### Gemini structured-output resilience

- Advanced the constrained writer contract to `peche-tn-writer-v3`, with explicit property ordering and one-to-four-item bounds for every list.
- Raised the output budget to `8192`, requested one candidate, and selected low thinking for Gemini 3 models to reduce the chance that reasoning consumes the response budget and truncates JSON.
- Made response extraction ignore thought parts and accept a BOM, a complete JSON fence, or double-encoded JSON; blocked finish reasons and token-limit truncation now receive explicit classifications.
- Added at most one structural regeneration after malformed or schema-invalid JSON. Both generations share one strict four-request budget with transient 408/429/5xx retries and backoff.
- Kept semantic violations fail-fast: prose that adds digits or repeats the engine decision is never regenerated, and the deterministic report and verdict remain independent.
- Added regressions for `MAX_TOKENS` with truncated output, successful structural recovery, the global request cap, wrapper normalization, and semantic fail-fast behavior.
- Advanced the application to 1.2.3; Decision API schema 2.0 and deterministic engine 1.0.1 are unchanged.

## 1.2.2 — 2026-09-09

- Corrected report units: sea-level rate now uses `م/ساعة` with useful precision, and the SST change is correctly labelled as a 24-hour change.
- Rounded factor-ledger visibility to kilometres, added the current-impulse unit, made pressure trends explicitly signed, localized shore/orientation and METAR comparison labels, and stopped rendering missing gusts as `— كم/س`.
- Clarified that fouling/turbidity counters are different operational signal families, not independent observations or data sources; no decision threshold changed.
- Resolved the matrix-count presentation: 63 is the corrected operational total, while the source's original 62 remains provenance metadata only (`matrix-v3-audit-3`).
- Replaced claims of an “آمنة” window with the narrower statement that it passed available automated limits and is not a field-safety certificate.
- Marked windows that end after midnight as “اليوم التالي”, clarified elapsed day-parts, and deduplicated hourly forecast-horizon confidence reasons.
- Added an explicit storm-surge limitation: absolute model sea level alone cannot isolate a surge component; surfaced CAPE beside weather code and the optional lightning proxy so a missing sub-variable is not mistaken for “no lightning”.
- Advanced the application to 1.2.2, deterministic output text to engine 1.0.1, and the constrained Gemini instructions to `peche-tn-writer-v2`.

## 1.2.1 — 2026-09-08

- Added bounded Gemini retries with exponential backoff and jitter for transport failures, HTTP 408/429 and all 5xx provider responses.
- Kept 400/401/403 and all other non-transient failures fail-fast; four attempts is the hard upper bound.
- Preserved the deterministic report as the permanent fallback and kept the API key out of request bodies, responses and retry logs.
- Added coverage for `503 → success` and persistent 503 exhaustion; the latter now returns an explicit HTTP 503 only after retries finish.
- Made the deployment smoke use tomorrow's forecast so a correct late-evening lack of remaining hours cannot produce a false deployment failure.
- Advanced API, frontend, CI and smoke contracts together to 1.2.1.

## 1.2.0 — 2026-09-08

### Production deployment
- Added a production-ready, two-stage Docker build that exports the Next.js interface and serves it with FastAPI from one Render web service and one origin.
- Added a Render Blueprint for the Free plan in Frankfurt, application-level `/api/health` checks and a no-secret deployment path.
- Added a dedicated Render ASGI adapter, `.dockerignore`, complete deployment guide, generic live smoke test instructions and a CI gate that builds and boots the final container.
- Removed the Vercel `routes/request.path transforms` that returned HTML 500 in the real deployment. The optional Vercel path now relies on its native `api/index.py` file routing and retains only source inclusion.

### Verification and release integrity
- Advanced the application version to 1.2.0 and updated API, frontend, tests and smoke assertions together.
- Preserved the deterministic decision engine, schema 2.0, engine 1.0.0, 63-factor ledger, 48–72-hour history and optional Gemini writer without changing their authority boundaries.
- Documented the Render Free cold-start limitation explicitly; a platform status is never accepted without the live end-to-end smoke test.

## 1.1.0 — 2026-09-08

> Production correction: Vercel accepted and deployed this release, but live `/api` and `/api/*` requests still returned a Next.js HTML 500 page. The route-transform approach is superseded by 1.2.0 and must not be republished.

### Fixed
- Replaced the self-matching `/api/* → /api` Vercel rewrites from 1.0.1 with one-pass `routes` that target `api/index.py` and explicitly transform the ASGI request path. The destination no longer re-enters the same rule.
- Restored the top-level entrypoint as a directly detectable FastAPI application and added route-contract tests for root, health and methodology paths.
- Hardened browser API parsing so a Vercel HTML error page is reported as a gateway failure instead of being mistaken for valid JSON.
- Added an in-product public API connectivity probe and clear no-fabrication state when the backend is unavailable.

### Interface and report
- Reworked the entry experience after auditing the original `frontend/index.html`: compact report workspace, map open by default, side-by-side settings, one primary report action and an automatically opened report.
- Kept the original copy/download/share workflow and added WhatsApp sharing, while retaining the current deterministic decision, 48–72-hour context, 63-factor ledger and provenance.
- Removed the fictional preview score and kept Gemini visibly optional and subordinate to the deterministic engine.
- Added `docs/ORIGINAL-UI-AUDIT.md` to record what was retained and what scientifically unsafe behavior was deliberately not copied.

## 1.0.1 — 2026-09-08

> Production correction: the deployment built successfully, but the self-matching rewrites below caused live `/api/*` requests to return Vercel HTML 500 responses. This release and its first routing correction are superseded by 1.2.0.


### Fixed
- Restored production FastAPI packaging and catch-all `/api/*` routing on Vercel with an explicit function bundle and rewrite.
- Added a minimal root runtime dependency manifest so the Python function no longer depends on frontend framework detection.

### Changed
- Made the post-analysis location of field-risk evidence and optional Gemini reporting explicit in the planner.
- Renamed the result action to **التقرير الكامل + Gemini** so the key controls are discoverable.

## 1.0.0 — 2026-09-08

### Binary pre-trip decision

- Made the public headline strictly binary: `go/اذهب` or `no_go/لا تذهب`; hourly `caution` and `unknown` remain diagnostic states only.
- Added an explicit reason code for every headline: automated-gate-passing window (the stable API code is `safe_window`), safety hazard, critical-data gap, field infeasibility or conservative uncertainty.
- Ordered the gate as safety, critical data, execution and confidence before opportunity; a weak fishing-opportunity score alone no longer cancels an otherwise gate-passing, executable trip.
- Suppressed recommended windows on every no-go response, so an attractive fishing hour cannot visually contradict the headline.

### 48–72 hour sea history, fouling and turbidity

- Added up to 72 normalized antecedent hours to schema output and prior 24/48/72-hour rain, wave maxima, active-wave hours, relative wave-energy integral, onshore-wind impulse, shoreward-current impulse and per-variable coverage.
- Reworked weed/debris transport into a multi-signal probability, not an observation. A high level requires at least three distinct operational signal families; those families are not independent observations or sources, and sea energy alone cannot issue no-go.
- Added a separate turbidity-potential screen with the same multi-signal safety boundary. It never invents a measured NTU value or uses atmospheric visibility as water clarity.
- Made unknown critical feasibility inputs conservative rather than silently treating missing history as calm water.

### Complete 63-factor ledger

- Added exactly one runtime `factor_assessment` for every audited matrix heading, including decision, context, proxy, Unknown and excluded statuses.
- Added value, source variables, rationale and `affects_final_decision` to each record; uniqueness and the exact count of 63 are contract-validated.
- Extended the deterministic and downloadable report to expose the full ledger instead of only aggregate coverage counts.

### Corrected automatic coastline orientation

- Added `POST /api/v1/spots/orientation` using OpenStreetMap coastline ways through bounded, ordered Overpass mirrors and 3/5/10 km search radii.
- Fixed the original geometry by accepting 0°, projecting onto segments rather than selecting the nearest vertex, aligning neighboring normals and selecting the non-conflicting seaward perpendicular.
- Added visible provenance: orientation, tangent, coastline distance, server, search radius, segment count, confidence and limitations.
- Preserved manual editing and recalculation. Exhausted mirrors return `unavailable` and never fabricate or cache a false direction; manual interaction wins request races.

### Optional Google Gemini report writer

- Added direct Google Gemini structured output for optional report prose; the deterministic engine remains the only authority for decisions, numbers and factors.
- Added a normalized Evidence Packet with raw history, timestamps, distances, sources, derivatives, all 63 assessments and Unknowns.
- Added server-side JSON/schema validation, semantic rejection of decision commands or numeric prose, and server-rendered canonical decision/numeric sections.
- Added report metadata for model, prompt/template versions, generation time and SHA-256 input hash.
- Added an interface-controlled runtime key with warning/consent, masked input, verify and delete actions. It is stored only in browser `localStorage` after consent, sent transiently over HTTPS and never kept or logged by the server.
- Kept the complete deterministic report as the no-key and failure fallback.

### Contract, docs and verification

- Advanced the Decision API to `schema_version: 2.0`, the deterministic engine to `1.0.0` and the application/package to `1.0.0`.
- Updated local-secret policy, methodology, API examples, Vercel and Termux release instructions for the new contract.
- Expanded backend and responsive E2E regression coverage for binary decisions, historical signals, ledger integrity, coastline geometry/failover and Gemini authority boundaries.

## 0.9.0 — 2026-09-08

### Peche TN release identity

- Renamed the public product, web metadata, PWA manifest, offline shell, reports, download names, package metadata and deployment documentation to **Peche TN**.
- Kept the internal Python import package `spotdata` to avoid a needless compatibility-breaking source-tree migration; it is an implementation namespace, not public branding.

### Audited shore-direction geometry

- Made the input contract explicit: `seaward_orientation_deg` is the true-north bearing from the standing point to open sea; wind and wave bearings are source/`from` directions, while current is a destination/`towards` direction.
- Added exact wind shoreward/alongshore components and wave normal/alongshore alignments to every hourly result, so the geometry is numerically inspectable.
- Added a neutral `alongshore` wind sector from 80° through 100° instead of assigning an exactly shore-parallel wind arbitrarily to the land side.
- Replaced the ambiguous rotating compass glyph with a true 0°-north bearing arrow and added an in-product instruction that prevents entering wave travel or wind-flow direction as the spot orientation.
- Added rotation-invariant, wrap-around, opposite-direction, component-sign and explicit sector-boundary tests for wind and waves.

### Observation and local API hardening

- METAR pressure now prefers reported sea-level pressure (`slp`); altimeter/QNH (`altim`) is retained only as a clearly labelled approximation and is never claimed as a direct SLP value.
- Future-dated METAR observations are rejected from reconciliation instead of being assigned a misleading non-negative age.
- Documented a zero-cost local connector policy: keyless endpoints need no Vercel configuration, secrets are never exposed in browser bundles, and any future secret-backed provider must pass through a local/server-side proxy with an ignored local environment file.

### Contract

- Decision API schema advanced to `1.5`; engine ruleset to `0.5.0`; application version to `0.9.0`.

## 0.8.0 — 2026-09-08

### Direct observation layer

- Added a no-key AviationWeather.gov METAR connector for eight Tunisian coastal/near-coastal airport stations, fetched server-side in one cached request for same-day decisions.
- Selects the nearest returned station by the haversine formula, retains station coordinates, distance, report/retrieval time, raw METAR, QC flag and normalized wind/temperature/dew-point/pressure/visibility values.
- Keeps the observation explicitly separate from Open-Meteo model forecasts: `is_direct_observation=true` and `is_spot_observation=false`; it is never presented as a marine or surf-zone measurement.
- METAR failure degrades safely to an explicit unavailable observation and never makes the required weather/marine forecast request fail.

### Reconciliation and decision behavior

- Added age-, distance- and time-gated station/model reconciliation with transparent differences for wind speed/direction, air temperature and pressure.
- A fresh station within 75 km can lower confidence and raise near-term caution when materially divergent; data 75–150 km away remains comparison-only, and observations older than 120 minutes or farther than 150 km do not enter the decision.
- A METAR thunderstorm within 30 km creates a near-term hard safety stop; 30–75 km creates caution. Hazardous station wind creates caution rather than being spatially copied to the selected coast.
- Marine wave, current, level and SST values remain model forecasts because METAR does not observe the sea. Weed, turbidity, jellyfish, nets, bait, surf-zone bathymetry and actual rip currents remain `Unknown`/field checks.

### Interface and contract

- Added a responsive direct-observation panel and report evidence block showing station, distance, age, raw values, model differences and the strict “station, not Spot” boundary.
- Decision API schema advanced to `1.4`; engine ruleset to `0.4.0`; application version to `0.8.0`.

## 0.7.0 — 2026-09-08

### Matrix audit and scientific integrity

- Audited all numbered headings in `TUN-SURFCAST-MATRICE-v3-UNIFIE.html`: the file claims 62 factors but actually contains 63.
- Added a runtime factor registry and `GET /api/methodology/factors`, classifying every factor as automated decision, context-only, low-confidence proxy, field/external requirement, or excluded unsupported relation.
- Added factor provenance (`basis`, `rule_nature`, `is_direct_observation=false`) and a `factor_coverage` summary to every decision.
- Removed automatic catch weighting from pressure tendency and flat/mirror sea; both remain transparent context where available.
- Explicitly excluded general Solunar/lunar catch weights, DO-from-SST, universal Secchi↔NTU conversion, inferred weed/jellyfish/fish presence, and universal jellyfish-vinegar advice.

### Forecast and equations

- Renamed hourly API output from `observed` to `forecast`; Open-Meteo values are model forecasts, not live surf-zone observations.
- Added apparent temperature, dew point, cloud cover, shortwave radiation, UV index and model lightning potential to the free weather adapter.
- Expanded fetched context to three preceding days and added guarded gust factor, adjacent-hour circular wind shift, 24-hour pressure/SST changes, prior wind/wave maxima and target-day sea-level range.
- Replaced the rounded deep-water wavelength coefficient with `L0 = gT²/(2π)` using standard gravity, while retaining explicit deep-water/surf-zone limitations.
- Added reversible knot/km/h and km/h/m/s conversion tests; `25 kn` is represented as `46.3 km/h`.

### Product and contract

- Added matrix coverage and provenance labels to the responsive result and full printable/TXT report.
- Expanded the shared online/offline field protocol from 8 to 12 checks covering lightning, water anomalies, jellyfish, people/nets, bait, gear, access and test casting.
- Decision API schema advanced to `1.3`; engine ruleset to `0.3.0`; application version to `0.7.0`.
- Browser decision/checklist and offline precache namespaces advanced so older contracts cannot be mistaken for this release.

## 0.6.0 — 2026-09-08

### Added

- A fourth, independent field-feasibility axis alongside safety, opportunity and guidance confidence.
- Conservative hourly screens for line-holding difficulty, transport potential for weed/debris **if material is present**, and rip-current potential.
- Prior-context features for 24-hour rain, 12-hour onshore-wind persistence and 12-hour wave-energy persistence, with coverage counts.
- Separate wind-wave and swell height/period/direction fields from Open-Meteo through the Python and TypeScript contracts.
- A responsive field-feasibility panel, hourly field signals, report section and eight-point online/offline field checklist.

### Decision behavior

- Recommended windows now rank safety first, then the worst field-feasibility status and score, then opportunity and confidence.
- A daily `go` requires a best window that passes the automated safety policy and has favorable field-feasibility; workable or difficult execution downgrades the combined recommendation to caution.
- High rip-current potential creates a caution signal, never a claim that a rip was observed.
- Line-holding and material-transport screens can lower opportunity ranking but cannot fabricate a hard no-go observation.

### Contract and integrity

- Decision API schema advanced to `1.2`; decision engine ruleset advanced to `0.2.0`.
- All automated weed/debris/rip fields expose `is_direct_observation: false`, carry their own limitations and are capped at `50/100` confidence.
- A low proxy signal explicitly does not rule out danger; field inspection and a test cast override the model.
- Browser decision cache and checklist namespaces advanced to prevent older records from being mistaken for the new contract.

## 0.5.0 — 2026-09-08

### Added

- A complete, deterministic spot report with executive summary, modelled water movement, ranked windows, day-part breakdown, factor balance, field guidance, reference ranges and provenance.
- Full-report copy, UTF-8 TXT download and dedicated print/PDF presentation.
- Sunrise and sunset in the decision API response (`schema_version: 1.1`) so report timings come from the weather provider rather than client guesses.
- Responsive report layouts tested from 320px phones to wide desktops.

### Scientific integrity

- The report calls the score an opportunity index, never a catch-success probability.
- Lunar transit and solunar estimates are not presented as tide observations; water events remain derived from the modelled sea-level series.
- Casting distance, sinker weight and bait are not fabricated without rod, line, seabed, prey or local catch evidence.
- Missing day parts and variables stay explicitly unavailable, and all generated guidance remains traceable to evaluated inputs or engine output.

## 0.4.0 — 2026-09-08

### Added

- A field safety checklist that works without an account, survives reloads and expires automatically after six hours.
- An explicit “reality differs” control that tells the angler to stop relying on the forecast when observed conditions are worse or uncertain.
- A live connection-loss banner that immediately marks an open decision as unable to reflect current sea conditions.
- A production service worker and fully self-contained Arabic offline safety page with Tunisia Civil Protection number 198.
- PWA shortcuts for the planner and field checklist.
- E2E coverage for checklist persistence/expiry, the field-mismatch warning, live connection loss and an actual service-worker fallback at 320px.

### Safety behavior

- Forecast/API responses are deliberately never cached by the service worker, so Peche TN does not present an old decision as current while offline.
- Offline navigation falls back to the safety checklist instead of a stale forecast screen.

## 0.3.0 — 2026-09-08

### Changed

- Rebuilt the RTL experience around a focused three-step planning flow.
- Added a location-first GPS action, coastal preset chips and a collapsible precision map.
- Reworked date, orientation, shore and advanced controls for clearer mobile use and larger touch targets.
- Redesigned decision results with a stronger verdict hierarchy, ranked windows, selectable hourly cards and condition summaries.
- Added professional loading, network-error and stale-result states; evaluated inputs now remain tied to their result.
- Added sharing, printing, safe-area handling, reduced-motion behavior and print styles.
- Expanded responsive layouts for 320px phones, tablets, desktops and wide screens.

### Added

- Playwright Chromium E2E coverage for 320/375/768/1024/1440px viewports, horizontal overflow, loading, result freshness and keyboard disclosures.
- Responsive E2E execution in GitHub Actions.

## 0.2.0 — 2026-09-07

### Added

- Mobile-first RTL interface with Next.js 16, React and strict TypeScript.
- MapLibre location picker, GPS, editable shore orientation and Tunisia presets.
- Decision dashboard, ranked windows, no-go periods and hourly timeline.
- Hourly observed conditions, factor explanations and modelled sea-level chart.
- PWA metadata and same-origin Vercel full-stack layout (`api/index.py`).
- Ten-minute browser cache plus warm serverless TTL/single-flight cache.
- Frontend lint, typecheck and production build in GitHub Actions.
- Zero-cost Vercel deployment guide.

## 0.1.0 — 2026-09-07

### Added

- Clean professional rebuild on `rebuild/decision-engine-v1`.
- Typed deterministic decision domain and FastAPI contract.
- Safety gate independent from fishing opportunity.
- Explicit `unknown` state for missing critical inputs.
- Real modelled sea-level/current variables from Open-Meteo.
- Wave steepness, H²×T energy proxy, directional projections and limitations.
- Personal safety policy by experience and shore type.
- Non-overlapping 2–4 hour windows and past-window exclusion for today.
- Arabic explanations, source provenance and confidence decomposition.
- Docker, CI, Ruff, mypy and offline tests.

### Removed from the decision path

- Mandatory Gemini dependency.
- Synthetic lunar high/low tide times.
- False Tunisia-wide claim that tides are always weak.
- Missing-value-to-zero fallback.
- Uncalibrated “success probability”, invented cast distance and asserted active-fish list.
