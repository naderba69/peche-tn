# نشر Peche TN كاملاً على Render

> الإصدار الحالي مذكور في أعلى `CHANGELOG.md`؛ استبدل أرقام الإصدارات القديمة إن وردت في أي ملف.

هذا الإصدار يشغّل **الواجهة وFastAPI في خدمة Docker واحدة وعلى نطاق واحد**. لا يوجد CORS بين خدمتين، ولا قاعدة بيانات، ولا متغيرات سرية، ولا حاجة لإضافة مفتاح Gemini إلى Render.

## ماذا يفعل البناء؟

1. يبني واجهة Next.js كملفات static داخل مرحلة Node 22.
2. يثبت محرك FastAPI داخل صورة Python 3.12 النهائية.
3. يشغّل Uvicorn على `0.0.0.0:$PORT`.
4. يخدم `/api/*` من FastAPI وبقية المسارات من الواجهة المبنية.
5. يفحص Render المسار `/api/health` قبل اعتبار النشر جاهزاً.

## الطريقة الأسهل — Blueprint

بعد رفع الإصدار الحالي إلى فرع `main` في GitHub، افتح:

<https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fnaderba69%2Fpeche-tn>

ثم:

1. سجّل الدخول إلى Render.
2. وافق على Blueprint الظاهر من `render.yaml`.
3. تأكد أن الخطة **Free** والمنطقة **Frankfurt** وRuntime هو **Docker**.
4. لا تضف أي Environment Variable ولا مفتاح Gemini.
5. اضغط **Apply / Deploy** وانتظر حتى تصبح الخدمة `Live`.

سيعطيك Render رابطاً شبيهاً بـ:

```text
https://peche-tn-xxxx.onrender.com
```

## من دون ربط GitHub

لأن المستودع عام، يمكن من Render اختيار **New → Web Service → Public Git Repository** ثم وضع:

```text
https://github.com/naderba69/peche-tn
```

اختر Docker وFree وFrankfurt واترك Dockerfile في `./Dockerfile`. هذه الطريقة لا تدعم Auto-Deploy؛ عند كل تحديث استعمل **Manual Deploy**.

## الاختبار الحقيقي بعد النشر

من داخل مستودعك في Termux، استبدل الرابط برابط خدمتك:

```bash
python scripts/smoke_deployment.py https://peche-tn-xxxx.onrender.com
```

لا تعتمد على كلمة `Live` وحدها. النجاح هو ظهور:

```text
ALL PASS — ... is serving Peche TN (الإصدار الحالي) frontend and API contracts.
```

الفحص يختبر الواجهة، health، المنهجية، OpenAPI، Swagger، قراراً حقيقياً، 63 عاملاً، تاريخ 48–72 ساعة، عقد Sentinel‑2 الصريح، وعقد اتجاه البحر.

## حدود الخطة المجانية

- خدمة Render المجانية تنام بعد نحو 15 دقيقة من عدم وجود زيارات.
- أول فتح بعد النوم قد يستغرق قرابة دقيقة؛ هذا تأخير استيقاظ لا قراراً مخزناً.
- لا يوجد SLA، وقد تتغير حصص Render أو المزودات الخارجية.
- لا يحفظ التطبيق قرارات المستخدم أو مفتاح Gemini في Render؛ المفتاح الاختياري يبقى في متصفح المستخدم ويرسل وقت الطلب فقط.
