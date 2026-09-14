# معمارية Peche TN

## المبدأ

Peche TN أداة قرار deterministic أولاً: المزودات تجمع أدلة، وطبقة domain وحدها تحسب، والواجهة وGemini تعرضان النتيجة ولا تعيدان الحسم.

```text
Next.js RTL PWA
  ├─ planner + GPS/presets + manual orientation
  ├─ deterministic report + 63-factor ledger
  └─ optional Gemini key in consented browser localStorage
              │ same-origin /api/* over HTTPS
              ▼
FastAPI transport
  ├─ strict Pydantic validation + structured errors + request ID
  ├─ Open-Meteo Weather/Marine adapter ─ model forecasts
  ├─ AviationWeather.gov adapter ─ current airport METAR (optional)
  ├─ Overpass adapter ─ coastline geometry through bounded mirrors
  ├─ Copernicus WMTS adapter ─ optional Sentinel-2 TUR/SPM/CHL context
  └─ Gemini adapter ─ optional structured prose with runtime key
              │ normalization / QC / times / distances / provenance
              ▼
ForecastDataset + OrientationEvidence + optional CoastalWaterContext
              │
              ▼
DecisionEngine (pure deterministic domain)
  ├─ 48–72 h antecedent features and coverage
  ├─ signed wind/wave/current orientation math
  ├─ shadow wind-stress, circular-coherence and wave-crossing diagnostics
  ├─ safety policy and station/model reconciliation
  ├─ holding/fouling/turbidity/rip screening proxies
  ├─ opportunity ranking independent from safety
  ├─ confidence and critical-data gates
  ├─ complete 63-factor runtime ledger
  └─ binary GO/NO_GO + reason + automated-gate-passing windows
              │
              ├─ deterministic report renderer (always available)
              └─ Evidence Packet → Gemini prose → schema/semantic guard
```

## حدود الطبقات

### `domain/`

لا يعرف HTTP أو FastAPI أو المزودات. يقبل `ForecastDataset` typed، ويبقى قابلاً لإعادة الإنتاج على fixture أو أرشيف. القيم الغائبة تبقى `None/Unknown`. القرار الرئيسي لا يقبل إلا `go` أو `no_go`، ويثبت validator وجود 63 عاملاً فريداً. الخطر الساعي يدخل `avoid_windows` ولا يلغي زمناً منفصلاً اجتاز البوابات؛ ومؤشرا الصوفة والعكارة غير المعايرين يخفضان ترتيب التنفيذ ويطلبان فحصاً لكنهما لا يفرضان `no_go` بلا رصد.

### `services/`

كل adapter يحفظ نوع الدليل:

- `open_meteo.py`: Weather وMarine model forecasts؛ لا يسمي الخلية رصد Spot.
- `aviation_weather.py`: ينظف METAR ويحسب العمر والمسافة؛ لا ينسخ محطة المطار إلى البحر.
- `coast_orientation.py`: يجلب coastline ways، يحسب أقرب projection والمماس والعمود ويعيد provenance أو `unavailable`.
- `copernicus_water.py`: يأخذ عينة ثابتة 1 كم على محور البحر، يقرأ أحدث TUR صالح قابل للتحقق ثم يطلب SPM/CHL عند نقطة العينة والتاريخ نفسيهما، ويحفظ provenance أو `unavailable`؛ إذا تعذر حسم تاريخ أحدث فلا يصف قيمة أقدم بأنها الأحدث، ولا يدخل السياق القرار.
- `gemini.py`: يبني Evidence Packet مصغرة للكاتب بلا إحداثيات أو سلاسل رقمية خام (مع كل الساعات تصنيفياً وكل العوامل الـ63)، يطلب JSON من Google ضمن مهلة كلية 40 ثانية، ويتحقق من schema واللغة الممنوعة، ثم يركب النص الرقمي server-side. المفتاح لا يدخل cache أو log أو disk.
- `SpotReport.tsx`: يعرض القالب الحتمي والأرقام الساعية ويولد TXT والطباعة؛ لا يعيد حساب القرار.

فشل METAR أو Sentinel‑2 أو Overpass أو Gemini اختياري ومعلن. غياب السلسلة العلمية الأساسية أو التاريخ الحرج لا يتحول إلى قيم صفرية، بل إلى خطأ upstream أو no-go بسبب نقص البيانات بحسب المرحلة.

### `api/`

مسؤول عن validation ونطاق تونس وتواريخ الطلب وheaders وسياسة cache والأخطاء، لا عن معادلات العلم. endpoints الرئيسة موثقة في `/api/docs`.

### الواجهة

Next.js + strict TypeScript + MapLibre، mobile-first وRTL. تستعمل same-origin `/api/*` فقط. اتجاه الساحل يعاد حسابه بعد GPS/Spot ويمكن للمستخدم تعديله؛ إلغاء/sequence guard يمنع استجابة قديمة من الكتابة فوق تدخل يدوي. التقرير يعرض مشتقات كل ساعة في جدول داخل حاوية تمرير لا توسع الصفحة الصغيرة، ويزيل الحد الأدنى للعرض عند الطباعة كي تتكرر رؤوس الجدول على الصفحات.

التقرير الحتمي هو الأصل. Gemini يظهر فقط بطلب المستخدم. يحفظ المفتاح دائماً في `localStorage` **بعد موافقة صريحة على المخاطر** وفق قرار المنتج، مع إخفاء/اختبار/حذف. هذا استثناء موثق، وليس ادعاء أن `localStorage` خزنة أسرار؛ راجع [`local-api-policy.md`](local-api-policy.md).

## لماذا Gemini لا يملك سلطة؟

- القرار والأرقام يجب أن تكون قابلة للاختبار والتكرار.
- LLM قد يهلوس أو يغير النبرة إلى أمر متناقض.
- لذلك لا يطلب prompt من Gemini إعادة القرار أو الأرقام؛ JSON غير الصالح قد يعاد توليده مرة واحدة ضمن سقف أربع اتصالات إجمالي ومهلة كلية 40 ثانية، بينما النص المحتوي على رقم أو أمر قرار يُرفض فوراً بلا إعادة توليد. يمكن للمستخدم إلغاء الطلب، ويوقف cutoff المتصفح الـspinner بعد 42 ثانية كحد أقصى.
- القالب النهائي يلصق decision والقيم المرجعية من `DecisionResponse` فقط، ويسجل model/prompt/input hash/generated time.

## اتجاه Overpass

`POST /api/v1/spots/orientation` يجرب mirrors وأنصاف بحث محدودة. الهندسة تعتمد أقرب إسقاط على segment، لا nearest vertex، وتتعامل مع `0°` كزاوية صحيحة. توحد الأعمدة المجاورة قبل التنعيم، ثم تختار الجهة غير المتعارضة مع نقطة الوقوف أو اتفاقية OSM حين تقع النقطة على الخط. النتيجة تقدير خريطة قابل للتعديل وليست bathymetry أو survey.

## استراتيجية الأخطاء

- `400`: تاريخ خارج النطاق أو قاعدة طلب واضحة.
- `401`: مفتاح Gemini مفقود/مرفوض للendpoint الاختياري.
- `422`: payload أو structured Gemini output غير صالح.
- `502/503/504`: فشل/مهلة upstream حسب النوع.
- `500`: خطأ داخلي مع `X-Request-ID` ومن دون secret في الرسالة.
- نقص متغيرات السلامة داخل Dataset ينتج قراراً مفسراً، لا exception ولا افتراض هدوء.
- فشل Gemini يعيد الواجهة إلى التقرير الحتمي الكامل.

## cache والتوازي

- Next.js يحفظ تطابق طلب القرار عشر دقائق في `sessionStorage`.
- FastAPI يستعمل TTL عشر دقائق وsingle-flight داخل warm instance لتوقعات الأرصاد، وTTL ست ساعات للسياق الفضائي المتقطع.
- يجري توقع Open‑Meteo وسياق Copernicus الاختياري بالتوازي؛ مهلة الأخير الكلية ثماني ثوان، وأي فشل يعيد `unavailable/Unknown` ولا يلغي نتيجة التوقع.
- نتيجة Overpass `unavailable` لا تحجز، كي يعمل زر إعادة الحساب بعد عطل transient.
- تقرير Gemini ومفتاحه لا يدخلان cache.

## الأمن والخصوصية

الإصدار 1.0 بلا حسابات أو قاعدة بيانات. لا يضم ZIP/Git أي مفتاح. يمنع source من طباعة `X-Gemini-API-Key`، ويعطل سجلات URL الروتينية من `httpx` لأنها قد تحمل إحداثيات الاستعلام، وتعيد مسارات Gemini `Cache-Control: no-store`. لا تخزن الإحداثيات أو Evidence Packet على الخادم. الاستضافة وGoogle لهما سياساتهما الخارجية، ويجب على المستخدم تقييد المفتاح وإلغاؤه عند الاشتباه.

## ما يلزم قبل رفع الثقة العلمية

1. Spot registry تونسية موثقة فيها orientation survey وتاريخ وثقة وتعرض ونوع ساحل.
2. bathymetry ومصبات ورصد breaking-wave/current/turbidity/weed قريب قانوني ومحدث.
3. سجل رحلات مجهول يشمل المحاولات الصفرية والتحقق الميداني لكل proxy.
4. فصل زمني train/validation/test ومعايرة فرصة المصيد قبل تسميتها احتمالاً.
5. أولوية false negatives للسلامة، مع بقاء بوابة السلامة rule-based مستقلة.
