# نشر Peche TN على Vercel — مسار ثانوي

> الإصدار الحالي مذكور في أعلى `CHANGELOG.md`.

النشر الأساسي الموصى به لهذا الإصدار هو Render الكامل كما في [`RENDER.md`](RENDER.md). بقي دعم Vercel اختيارياً.

## التصحيح في 1.2.0

أثبت الفحص الحي أن:

- rewrite إصدار 1.0.1 أعاد مطابقة `/api` وأفشل البوابة.
- `routes` مع `request.path transforms` في 1.1.0 بُنيت بنجاح محلياً، لكنها أعادت HTML 500 في Vercel الحقيقي.

لذلك لا يستعمل 1.2.0 أي `routes` أو `rewrites` مخصصة للـAPI. يعتمد على عقد Vercel الأصلي: وجود `api/index.py` يجعله catch-all لـ`/api` و`/api/*`. يحتفظ `vercel.json` فقط بـ`includeFiles` لحزم مصدر المحرك.

## الإعداد

1. Root Directory: جذر المستودع.
2. Framework Preset: Next.js.
3. Build Command وOutput Directory: تلقائيان.
4. لا تضف مفتاح Gemini إلى Environment Variables.

## شرط القبول

بعد النشر:

```bash
python scripts/smoke_deployment.py https://peche-tn.vercel.app
```

لا تعتبر `Ready` نجاحاً. لا يُقبل النشر إلا إذا ظهر `ALL PASS`. إذا أعاد Vercel 500 مرة أخرى، استخدم Render ولا تعِد تعديل التوجيه عشوائياً؛ يلزم عندها أول traceback من Function Runtime Logs.
