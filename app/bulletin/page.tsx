import Link from "next/link";
import {
  ArrowLeft,
  AlertTriangle,
  ExternalLink,
  MapPinned,
  ShieldAlert,
  Waves,
} from "lucide-react";

const INM_ZONES = [
  "منطقة سراط",
  "خليج تونس",
  "خليج الحمامات",
  "الشابة",
  "جربة",
];

const INM_LINKS = [
  {
    label: "النشرة البحرية الساحلية",
    hint: "الريح، القوة، الهول، الرؤية لكل منطقة ساحلية",
    href: "https://www.meteo.tn/fr/meteo-marine-zone-cotiere",
  },
  {
    label: "النشرة البحرية العريضة (Large)",
    hint: "توقع العرض البحري بعيداً عن الساحل",
    href: "https://www.meteo.tn/fr/prevision-marine-large",
  },
  {
    label: "النشرات الخاصة BMS",
    hint: "تحذيرات الرياح القوية والبحار الهائجة السارية",
    href: "https://www.meteo.tn/fr/bms",
  },
  {
    label: "خريطة اليقظة",
    hint: "درجات الإنذار حسب الولاية",
    href: "https://www.meteo.tn/fr/vigilance-meterologique",
  },
];

export default function BulletinPage() {
  return (
    <main>
      <section className="calendar-hero" id="top">
        <div className="eyebrow"><ShieldAlert size={15} /> النشرة الرسمية INM (D14)</div>
        <h1>تحذير رسمي ساري؟<br /><em>الرحلة تتلغى آلياً.</em></h1>
        <p>
          نشرة المعهد الوطني للرصد الجوي هي المرجع الرسمي. في المحرك، أي تحذير رسمي ساري
          على البقعة يحوّل النتيجة إلى <strong>لا تذهب</strong> بسبب «تحذير رسمي» وقوة قاهرة
          <strong> قانونية/تحذير</strong> — فوق كل العتبات المحلية.
        </p>
      </section>

      <section className="bulletin-banner" role="alert">
        <AlertTriangle size={20} />
        <div>
          <strong>لا يعرض التطبيق «لا تحذير» آلياً.</strong>
          <span>
            معهد الرصد يرسم بيانات النشرة بالجافاسكريبت دون واجهة API ثابتة، لذا يطلب منك Peche TN
            فتح النشرة الرسمية دائماً وتفعيل التحذير يدوياً عند وجوده — لن نخترع أبداً حالة «البحر آمن رسمياً».
          </span>
        </div>
      </section>

      <section className="bulletin-grid">
        <article className="bulletin-card">
          <h3><MapPinned size={17} /> المناطق الساحلية الرسمية الخمس</h3>
          <p>المناطق التي تغطيها نشرة INM الساحلية:</p>
          <ul className="bulletin-zones">
            {INM_ZONES.map((zone) => <li key={zone}>{zone}</li>)}
          </ul>
        </article>

        <article className="bulletin-card">
          <h3><ExternalLink size={17} /> افتح النشرة الرسمية</h3>
          <ul className="bulletin-links">
            {INM_LINKS.map((link) => (
              <li key={link.href}>
                <a href={link.href} target="_blank" rel="noopener noreferrer">
                  <span><strong>{link.label}</strong><small>{link.hint}</small></span>
                  <ExternalLink size={15} />
                </a>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="bulletin-howto">
        <h3>كيفاش تطبّق التحذير في تقرير البقعة؟</h3>
        <ol>
          <li>افتح النشرة الرسمية (الروابط فوق) وتأكد من وجود تحذير ساري على منطقتك.</li>
          <li>
            <Link href="/#planner">ارجع لتقرير البقعة</Link> ← «إعدادات متقدمة» ← «تحذير رسمي ساري (INM)».
          </li>
          <li>اختر نوع التحذير (رياح قوية / بحر هائج / أمطار غزيرة / آخر) وحدّث القرار.</li>
          <li>المحرك يرجع <strong>لا تذهب — تحذير رسمي</strong> تلقائياً مهما كانت العتبات الأخرى.</li>
        </ol>
        <p className="bulletin-note">
          <ArrowLeft size={15} />
          <span>النشرة الرسمية تُقرأ كما هي؛ التحذير اليدوي بوابة أمان إضافية، وليس بديلاً عن قراءة النص الكامل وخرائط اليقظة.</span>
        </p>
      </section>

      <footer className="site-footer">
        <Link className="brand footer-brand" href="/"><span className="brand-mark"><Waves size={20} /></span><strong>Peche TN</strong></Link>
        <p>أداة تونسية مجانية لدعم قرار سيرفكاست أكثر أماناً ووضوحاً.</p>
        <div className="footer-meta">
          <span>الإصدار 1.10.0 · المعطيات البحرية تقريبية وقد تختلف محلياً.</span>
          <Link href="/">الرئيسية</Link>
        </div>
      </footer>
    </main>
  );
}
