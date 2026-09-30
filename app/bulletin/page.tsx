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
        <h1>النشرة الرسمية<br /><em>تحقّق منها بنفسك.</em></h1>
        <p>
          نشرة المعهد الوطني للرصد الجوي هي المرجع الرسمي للتحذيرات. Peche TN لا يجلبها أو
          يفحص صلاحيتها ونطاقها تلقائياً، ولذلك لا يضمّنها في القرار الآلي.
        </p>
      </section>

      <section className="bulletin-banner" role="alert">
        <AlertTriangle size={20} />
        <div>
          <strong>التحذيرات الرسمية غير مدمجة في القرار.</strong>
          <span>
            افتح النشرة مباشرةً قبل الخروج. ظهور «اذهب» في Peche TN لا يعني أن التطبيق فحص
            تحذيرات INM أو أكد خلو منطقتك منها.
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
        <h3>قبل اتخاذ قرار الخروج</h3>
        <ol>
          <li>افتح النشرة الرسمية (الروابط أعلاه) وتحقق من صلاحيتها ومنطقتها وتوقيتها.</li>
          <li>اتبع تعليمات السلطات؛ لا تعتبر قرار Peche TN بديلاً عن التحذير الرسمي أو التقدير الميداني.</li>
        </ol>
        <p className="bulletin-note">
          <ArrowLeft size={15} />
          <span>مصادر التحذيرات الرسمية لا تُجلب آلياً حالياً؛ هذا الدليل يوفّر روابط مباشرة فقط.</span>
        </p>
      </section>

      <footer className="site-footer">
        <Link className="brand footer-brand" href="/"><span className="brand-mark"><Waves size={20} /></span><strong>Peche TN</strong></Link>
        <p>أداة تونسية مجانية لدعم قرار سيرفكاست أكثر أماناً ووضوحاً.</p>
        <div className="footer-meta">
          <span>الإصدار 1.16.0 · المعطيات البحرية تقريبية وقد تختلف محلياً.</span>
          <Link href="/">الرئيسية</Link>
        </div>
      </footer>
    </main>
  );
}
