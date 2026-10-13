import {
  BarChart3,
  BookOpenCheck,
  Database,
  FileText,
  HeartPulse,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react";
import { DecisionApp } from "@/components/DecisionApp";
import { SafetyChecklist } from "@/components/SafetyChecklist";

const TRUST_ITEMS = [
  { icon: ShieldCheck, title: "الموانع قبل أي رقم", text: "ريح، موج، جرّ، عكارة، رعد أو نشرة: ساعة ممنوعة لا تُفتح بترتيب السمك." },
  { icon: BarChart3, title: "محرك قابل للتفسير", text: "ساعة بساعة: الموانع ظاهرة، والنشاط ترتيب نسبي لا وعد سمك." },
  { icon: HeartPulse, title: "مجاني وخصوصي", text: "لا حساب ولا اشتراك؛ مفتاح Gemini يبقى في متصفحك باختيارك." },
];

export default function Home() {
  return (
    <main>
      <section className="report-intro" id="top">
        <div className="report-intro-copy">
          <div className="eyebrow"><Sparkles size={15} /> مبني خصيصاً لساحل تونس</div>
          <h1>قرار الخرجة<br /><em>قبل ما تشدّ الطريق.</em></h1>
          <p>
            اختار البقعة واليوم. اتجاه البحر يُجلب آلياً. المحرك يحسم <strong>اذهب أو لا تذهب</strong> من الموانع المحسوبة ساعة بساعة — مو تخمين ولا وعد سمك.
          </p>
          <div className="intro-badges">
            <span><ShieldCheck size={16} /> قرار ثنائي محافظ</span>
            <span><Database size={16} /> طقس وبحر + رصد محطة</span>
            <span><FileText size={16} /> تقرير حتمي + Gemini اختياري</span>
          </div>
        </div>
        <aside className="report-contract" aria-label="عقد التقرير">
          <span className="contract-icon"><BookOpenCheck size={25} /></span>
          <div>
            <small>عقد Peche TN</small>
            <strong>المحرك يحسب ويحسم</strong>
            <p>Gemini ينظم السرد فقط، ولا يغيّر القرار أو الأرقام. الصوفة والعكارة احتمالان معلنان، لا رصد مؤكد.</p>
          </div>
        </aside>
      </section>

      <DecisionApp />

      <section className="trust-strip" id="how-it-works" aria-label="كيف يعمل Peche TN">
        {TRUST_ITEMS.map(({ icon: Icon, title, text }) => (
          <article key={title}>
            <span className="trust-icon"><Icon size={20} /></span>
            <div><strong>{title}</strong><p>{text}</p></div>
          </article>
        ))}
      </section>

      <SafetyChecklist />

      <section className="safety-note">
        <ShieldCheck size={22} />
        <div>
          <strong>القرار مساعد، موش بديل عن تقييمك للمكان.</strong>
          <span>عاين البحر من الشاطئ، احترم تحذيرات السلطات، وما تخاطرش وقت الشك.</span>
        </div>
      </section>

      <footer className="site-footer">
        <a className="brand footer-brand" href="#top"><span className="brand-mark"><Waves size={20} /></span><strong>Peche TN</strong></a>
        <p>أداة تونسية مجانية لدعم قرار سيرفكاست أكثر أماناً ووضوحاً.</p>
        <div className="footer-meta">
          <span>التطبيق 1.16.0 · محرك القرار يظهر في حالة الخدمة أعلاه · البحر في النموذج تقريبي وقد يختلف على الشاطئ.</span>
          <a href="/api/docs" target="_blank" rel="noreferrer">واجهة المطورين</a>
        </div>
      </footer>
    </main>
  );
}
