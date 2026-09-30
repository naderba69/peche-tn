# Peche TN Web

واجهة PWA عربية Mobile-first مبنية بـ Next.js وTypeScript.

## التطوير المحلي

شغّل الـ API أولاً:

```bash
make dev-api
```

وفي نافذة أخرى:

```bash
make web-dev
```

`PECHE_TN_API_ORIGIN` يفعّل proxy محلياً فقط. في Vercel تعمل الواجهة وFastAPI تحت نفس النطاق وتستعمل `/api/*` مباشرة.

## الجودة

```bash
npm run lint
npm run typecheck
npm run build
```

الخريطة تعمل بـ MapLibre وطبقات OpenStreetMap مع attribution ظاهر. المواقع الجاهزة مجرد بدايات؛ بعد اختيار Spot أو GPS يطلب المخطط عمود الساحل المصحح من Overpass ويعرض provenance، مع بقاء التعديل والتأكيد اليدويين لأن هندسة الخريطة ليست مسحاً ميدانياً.

تقرير Gemini اختياري وصريح. مفتاح المستخدم لا يدخل bundle أو env؛ يُحفظ في `localStorage` فقط بعد تنبيه/موافقة، ويمكن اختباره وحذفه. التقرير الحتمي يعمل دائماً بدونه.
