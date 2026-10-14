import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import type { DecisionResponse } from "@/lib/types";

// The live decision is either GO or NO_GO depending on real conditions; tests accept both.
const DECISION_HEADING = /^(اذهب|لا تذهب|حذر|المعطيات ناقصة)$/;

const viewports = [
  { name: "small-phone", width: 320, height: 568 },
  { name: "phone", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "small-desktop", width: 1024, height: 768 },
  { name: "wide-desktop", width: 1440, height: 900 },
];

// Live-GO tests need a coastline orientation that OpenStreetMap/Overpass verifies. That lookup is
// unreliable from CI (ReadTimeout / HTTP errors observed), so those tests run only when explicitly
// enabled with PECHE_TN_LIVE_GO=1 in an environment where Overpass is reachable.
const LIVE_GO = process.env.PECHE_TN_LIVE_GO === "1";
const LIVE_GO_SKIP_REASON = "needs a live-verified coastline orientation (Overpass); run with PECHE_TN_LIVE_GO=1";

// Layout and planner tests must not depend on live Overpass latency: the startup
// auto-fetch would otherwise keep the action button in its loading label for as long
// as a public mirror takes. Tests that need a specific orientation register their own
// route, which takes precedence. Live-GO runs keep the real network path.
test.beforeEach(async ({ page }) => {
  if (LIVE_GO) return;
  await page.route("**/api/v1/spots/orientation", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "unavailable",
        orientation_deg: null,
        evidence: null,
        reasons_ar: ["اختبار: لا يُستعمل Overpass الحقيقي في اختبارات التخطيط."],
      }),
    });
  });
});

// Clicks the first preset chip that is not already selected and waits for the real orientation response.
// Then analyzes only if the API verified the coastline; otherwise the analyze button stays blocked.
async function analyzeFirstVerifiedSpot(page: Page) {
  const presets = page.locator(".quick-spots .spot-chip:not([aria-pressed='true'])");
  const total = await presets.count();
  for (let index = 0; index < total; index += 1) {
    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().includes("/api/v1/spots/orientation")),
      presets.nth(index).click(),
    ]);
    expect(response.status()).toBe(200);
    const analyze = page.getByRole("button", { name: /^(حلّل 24 ساعة|محجوب)/ });
    await expect(analyze).toBeVisible();
    const verified = page.getByRole("button", { name: "حلّل 24 ساعة" });
    if (await verified.count()) {
      await verified.click();
      return;
    }
  }
  throw new Error("no coastal preset produced a verified orientation from live data");
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
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /قرار الخرجة/ })).toBeVisible();
    await expect(page.locator("nav a.active:visible")).toContainText("القرار");
    await expectNoPageOverflow(page);

    await expect(page.getByRole("heading", { name: "وين باش تصطاد؟" })).toBeVisible();
    await page.locator("#planner").scrollIntoViewIfNeeded();
    await expect(page.getByRole("heading", { name: "وقتاش الحصة؟" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "اتجاه الشاطئ" })).toBeVisible();
    await expectNoPageOverflow(page);

    await expect(page.getByRole("button", { name: /^(حلّل 24 ساعة|محجوب)/ })).toBeVisible();

    if (LIVE_GO) {
      await analyzeFirstVerifiedSpot(page);

    // القرار والبطاقة الميدانية ظاهران فوراً بلا فتح أي تبويب.
    await expect(page.getByTestId("field-brief")).toBeVisible();
    await expect(page.getByTestId("result-tabs")).toBeVisible();

    // تبويب التوقيت هو الافتراضي.
    await expect(page.getByRole("heading", { name: "القرار ساعة بساعة" })).toBeVisible();

    // تبويب الظروف يحمل الرصد والقمر الصناعي وقابلية التنفيذ.
    await page.getByRole("tab", { name: "الظروف" }).click();
    await expect(page.getByRole("heading", { name: "رصد جوي فعلي الآن" })).toBeVisible();
    await expect(page.getByTestId("actual-observation")).toContainText("DTTA");
    await expect(page.getByTestId("actual-observation")).toContainText("ليس داخل الـSpot");
    await expect(page.getByTestId("coastal-water-context")).toContainText("0.32 FNU");
    await expect(page.getByTestId("coastal-water-context")).toContainText("بروكسي النقل وحده لا يمنع");
    await expect(page.getByTestId("coastal-water-context")).toContainText("الثقة");
    await expect(page.getByRole("heading", { name: "هل يمكن تنفيذ الحصة ميدانياً؟" })).toBeVisible();
    await expect(page.getByTestId("field-feasibility")).toContainText("موش رصد");
    await expectNoPageOverflow(page);
    await page.locator("#spot-report-trigger").click();
    await expect(page.getByTestId("report-equations")).toContainText("V∥=−VsinΔ");
    await expect(page.locator(".report-diagnostic-table tbody tr")).toHaveCount(8);
    await expect(page.getByTestId("report-water-context")).toContainText("سياق جودة الماء");
    await expectNoPageOverflow(page);
    }
  });
}

test("mobile result stays readable, interactive, and marks stale choices", async ({ page }) => {
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();
  await analyzeFirstVerifiedSpot(page);

  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();
  await expect(page.getByRole("heading", { name: "القرار ساعة بساعة" })).toBeVisible();
  await expectNoPageOverflow(page);

  await page.locator(".hour-card").nth(3).click();
  await expect(page.getByRole("heading", { name: /تفاصيل الساعة/ })).toBeVisible();
  await expect(page.locator(".hour-card").nth(3)).toHaveAttribute("aria-pressed", "true");

  // التقرير الميداني المنظم صار داخل تبويب «العتاد والتكتيك».
  await page.getByRole("tab", { name: "العتاد والتكتيك" }).click();
  const fieldReport = page.getByTestId("fisherman-report");
  await fieldReport.scrollIntoViewIfNeeded();
  await expect(fieldReport.getByRole("heading", { name: "التقرير الميداني المنظّم" })).toBeVisible();
  await expect(fieldReport).toContainText("ترتيب نسبي");
  await expect(fieldReport).toContainText("لا يفتح ساعة ممنوعة");
  await expect(fieldReport).toContainText("العبور القمري العلوي");
  await expectNoPageOverflow(page);

  await page.locator("#planner").scrollIntoViewIfNeeded();
  await page.locator(".date-chip").nth(1).click();
  await expect(page.getByText("هذه النتيجة تخص الاختيارات السابقة.")).toBeVisible();
  await expect(page.getByRole("button", { name: "حدّث التقرير والقرار" })).toBeVisible();
  await page.locator("#spot-report-trigger").click();
  await expect(page.locator("#spot-report .report-stale")).toContainText("التقرير يخص آخر تحليل");
  await expectNoPageOverflow(page);
});

test("the result answers in a couple of screens and tabs stay keyboard reachable", async ({ page }) => {
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await analyzeFirstVerifiedSpot(page);
  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();

  // انحدار التكدس: كانت النتيجة ‎15.8 شاشة مفتوحة دفعة واحدة على الهاتف.
  const resultScreens = await page.evaluate(() => {
    const shell = document.querySelector("#decision");
    if (!shell) return 99;
    return shell.getBoundingClientRect().height / window.innerHeight;
  });
  expect(resultScreens).toBeLessThan(9);

  // الجواب الأساسي بلا أي ضغطة: القرار، النافذة، ورياح/موج (والرصاص متى توفر
  // اقتراح عتاد؛ هذا المحاكي بلا gear_recommendation فيُحذف بندُه بصدق).
  const brief = page.getByTestId("field-brief");
  await expect(brief).toContainText("الرياح");
  await expect(brief).toContainText("الموج");

  // التبويبات تتبع نمط ARIA: سهم واحد ينقل التركيز والتحديد.
  const tablist = page.getByRole("tablist", { name: "تفاصيل القرار" });
  await expect(tablist).toBeVisible();
  const first = page.getByRole("tab", { name: "التوقيت" });
  await first.focus();
  await expect(first).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "الظروف" })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "العمليات" })).toHaveAttribute("aria-selected", "true");
  await expectNoPageOverflow(page);
});

test("the full spot report is scientific, complete, downloadable, and mobile-safe", async ({ page, context }) => {
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/");
  await analyzeFirstVerifiedSpot(page);
  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();
  await page.locator("#spot-report-trigger").click();
  const report = page.locator("#spot-report");
  const reportTitle = report.getByRole("heading", { name: "تقرير نابل" });
  await expect(report).toBeVisible();
  await expect(reportTitle).toBeVisible();
  const primaryReason = report.locator(".report-primary-reason");
  await expect(primaryReason).toContainText("لا مانع محسوب");
  await expect(primaryReason).not.toContainText("الأنشط فيها");
  await expect(report).toContainText("نسخة علمية، موش تنجيم");
  await expect(report).toContainText("مؤشر الفرصة");
  await expect(report).toContainText("مؤشر التنفيذ النموذجي");
  await expect(report).toContainText("الرصد الجوي الفعلي الأقرب");
  await expect(report).toContainText("محطة مطار، موش قياس داخل البقعة");
  await expect(report).toContainText("الهبة غير مسجلة");
  await expect(report).toContainText("لا تثبت وجودها أو تمنع وحدها");
  await expect(report).toContainText("الخطر مربوط بوقته");
  await expect(report).toContainText("دعم أدلة التنفيذ");
  await expect(report).toContainText(/تغطية \d+\/\d+/);
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
  expect(text).toContain("القرار النهائي: اذهب");
  expect(text).toContain("السبب: قرار «اذهب»");
  expect(text).toContain("النافذة التي ينطبق عليها القرار");
  expect(text).toContain("دعم بيانات التوقع");
  expect(text).toContain("مؤشرات النقل النموذجية");
  expect(text).toContain("هذه تقديرات نموذجية وليست مشاهدات");
  expect(text).toContain("رصد محطة جوية، وليس قياساً داخل بقعة الصيد");
  expect(text).toContain("البيانات الخام — توقعات النموذج بالساعة");
  expect(text).toContain("اتجاه الريح:");
  expect(text).toContain("ضغط سطح البحر:");
  expect(text).toContain("METAR");
  expect(text).toContain("بيانات الأقمار الصناعية الخام والسياق");
  expect(text).toContain("TUR");
  expect(text).not.toContain("مؤشر ترتيب وليس نسبة نجاح");
  expect(text).not.toContain("V⊥=VcosΔ");
  expect(text).not.toContain("[F-1]");
  expect(text.length).toBeGreaterThan(6000);
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

test("loading feedback appears while the forecast is being prepared", async ({ page }) => {
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await page.locator("#planner").scrollIntoViewIfNeeded();
  await analyzeFirstVerifiedSpot(page);

  await expect(page.getByRole("status").filter({ hasText: "نحضّر قرار الحصة" })).toBeVisible();
  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();
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
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
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
  await analyzeFirstVerifiedSpot(page);

  const error = page.locator("#planner-error");
  await expect(error).toContainText("ما قدرناش نكمّلوا التحليل");
  await expect(error).toContainText("المصدر البحري غير متاح مؤقتاً");
  await expect(page.getByRole("button", { name: "حلّل 24 ساعة" })).toBeEnabled();
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
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "إعداد تقرير السيرفكاست" })).toBeVisible();
  await analyzeFirstVerifiedSpot(page);
  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();

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

  const banner = page.locator(".connection-banner");
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

test("map selection shows automatic coast data and offers a separate manual shore selector", async ({ page }) => {
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
  await expect(page.getByRole("button", { name: "اتجاه عرض البحر" })).toHaveCount(0);
  const mapCanvas = page.locator(".map-canvas");
  await expect(mapCanvas).toHaveAccessibleName("خريطة لاختيار نقطة الوقوف على الساحل");
  await expect(page.locator(".orientation-help").first()).toContainText("بلا اتجاه موثوق لا نقول اذهب");

  await expect(page.locator(".advanced-settings")).toHaveCount(0);
  await expect(page.getByLabel("مستوى الخبرة")).toHaveCount(0);
  await expect(page.getByLabel("مدة الجلسة المخططة")).toHaveCount(0);
  await expect(page.getByTestId("automatic-spot-profile-status")).toBeVisible();
  await expect(page.getByTestId("manual-shore-type-field")).toBeVisible();
  await expect(page.getByLabel("نوع الشاطئ الذي اخترته")).toBeVisible();
  await expectNoPageOverflow(page);
});

test("startup auto-fetches coast direction, manual shore choice clears only the missing-type block, and waits if direction is unavailable", async ({ page }) => {
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
  await expect(page.getByTestId("orientation-provenance")).toBeVisible();
  await expect(page.getByTestId("orientation-provenance")).toContainText("0.0°");
  await expect(page.getByTestId("shore-type-caution")).toContainText("اختره يدوياً");
  await expect(page.locator(".primary-action")).toBeEnabled();
  await page.getByLabel("نوع الشاطئ الذي اخترته").selectOption("sandy");
  await expect(page.getByTestId("shore-type-caution")).toHaveCount(0);
  await expect(page.getByLabel("نوع الشاطئ الذي اخترته")).toHaveValue("sandy");
  await page.getByRole("button", { name: "رفراف" }).click();
  await expect(page.getByTestId("shore-type-caution")).toBeVisible();
  await expect(page.getByTestId("orientation-provenance")).toBeVisible();
  await expect(page.getByTestId("orientation-provenance")).toContainText("0.0°");
  await expect(page.getByTestId("orientation-provenance")).toContainText("270.0°");
  await expect(page.getByTestId("orientation-provenance")).toContainText("43 م");
  await expect(page.getByTestId("orientation-provenance")).toContainText("overpass-api.de");
  await expect(page.locator(".orientation-value strong")).toContainText("0.0°");

  shouldResolve = false;
  await page.getByTestId("orientation-recalculate").click();
  await expect(page.getByTestId("orientation-error")).toContainText("لم نخترع اتجاهاً بديلاً");
  await expect(page.locator(".orientation-value strong")).toContainText("غير متاح");
  await expect(page.getByTestId("orientation-provenance")).toHaveCount(0);
  await expect(page.getByLabel("اتجاه البحر بالدرجات")).toHaveCount(0);
  await expect(page.locator(".primary-action")).toBeDisabled();
  await expect(page.locator(".primary-action")).toContainText("اتجاه الساحل غير موثق");
  await expectNoPageOverflow(page);
});

test("Gemini key stays local, generation is explicit, and deterministic fallback remains", async ({ page, context }) => {
  test.skip(!LIVE_GO, LIVE_GO_SKIP_REASON);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 375, height: 667 });
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
      // الإلغاء يحتاج طلباً معلّقاً فعلاً؛ 800مس كانت تنتهي أحياناً قبل وصول
      // نقرة الإلغاء فيتحوّل الحالة إلى "نجاح" ويسقط الاختبار بشكل متقطع.
      await new Promise((resolve) => setTimeout(resolve, 4000));
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
  await analyzeFirstVerifiedSpot(page);
  await expect(page.getByRole("heading", { name: DECISION_HEADING })).toBeVisible();

  // التقرير الكامل نسخة علمية حتمية — لا يحتوي Gemini.
  await page.locator("#spot-report-trigger").click();
  const report = page.locator("#spot-report");
  await expect(report.getByTestId("factor-ledger").locator("article")).toHaveCount(63);
  await report.getByRole("button", { name: "أغلق" }).click();

  // تقرير Gemini صار داخل تبويب «العمليات» في آخر الصفحة.
  await page.getByRole("tab", { name: "العمليات" }).click();
  const gemini = page.locator(".report-gemini");
  await expect(gemini.getByText("localStorage موش خزنة أسرار", { exact: false })).toBeVisible();
  const keyInput = gemini.getByTestId("gemini-key-input");
  await expect(keyInput).toHaveAttribute("type", "password");
  await keyInput.fill(key);
  await gemini.getByText("فهمت مخاطر التخزين المحلي", { exact: false }).click();
  await gemini.getByTestId("gemini-save-key").click();
  expect(await page.evaluate(() => localStorage.getItem("peche-tn:gemini-api-key"))).toBe(key);
  await gemini.getByTestId("gemini-test-key").click();
  await expect(gemini.getByTestId("gemini-status")).toContainText("المفتاح صالح");

  delayNextReport = true;
  await gemini.getByTestId("gemini-generate").click();
  await expect(gemini.getByTestId("gemini-generate")).toContainText("أوقف انتظار Gemini");
  await gemini.getByTestId("gemini-generate").click();
  await expect(gemini.getByTestId("gemini-status")).toContainText("ألغيت انتظار Gemini");
  await expect(gemini.getByTestId("gemini-generate")).toContainText("ولّد التقرير المنظم");

  await gemini.getByTestId("gemini-generate").click();
  await expect(gemini.getByTestId("gemini-narrative")).toContainText("سرد ملتزم");
  await expect(gemini.getByTestId("gemini-narrative")).toContainText("gemini-test");
  expect(reportBody).toContain('"decision":"go"');

  // النسخة العلمية تنسخ النص الحتمي فقط (Gemini سرد منفصل في آخر الصفحة).
  await page.locator("#spot-report-trigger").click();
  await report.getByRole("button", { name: "انسخ التقرير" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("تقرير Peche TN الميداني");
  await report.getByRole("button", { name: "أغلق" }).click();

  await expect(gemini.getByTestId("gemini-key-input")).toHaveValue(key);
  await gemini.getByRole("button", { name: "احذف" }).click();
  expect(await page.evaluate(() => localStorage.getItem("peche-tn:gemini-api-key"))).toBeNull();
  await expect(gemini.getByTestId("gemini-key-input")).toHaveValue("");
  await expectNoPageOverflow(page);
});
