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
  { icon: ShieldCheck, title: "السلامة قبل الفرصة", text: "الخطر ونقص البيانات الحرجة يوقفان القرار قبل نقاط الصيد." },
  { icon: BarChart3, title: "محرك قابل للتفسير", text: "48–72 ساعة، 63 عاملاً، أرقام ومصادر وحدود ظاهرة." },
  { icon: HeartPulse, title: "مجاني وخصوصي", text: "لا حساب ولا اشتراك؛ مفتاح Gemini يبقى في متصفحك باختيارك." },
];

export default function Home() {
  return (
    <main>
      <section className="report-intro" id="top">
        <div className="report-intro-copy">
          <div className="eyebrow"><Sparkles size={15} /> مبني خصيصاً لساحل تونس</div>
          <h1>تقرير سيرفكاست دقيق<br /><em>قبل ما تمشي.</em></h1>
          <p>
            نفس الرحلة المباشرة للمشروع الأصلي: اختار البقعة واليوم واتجاه البحر، واضغط زر واحد. Peche TN يرجّع <strong>اذهب أو لا تذهب</strong> وتقريراً ميدانياً كاملاً من المحرك، موش من التخمين.
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
          <span>الإصدار 1.10.0 · المعطيات البحرية تقريبية وقد تختلف محلياً.</span>
          <a href="/api/docs" target="_blank" rel="noreferrer">واجهة المطورين</a>
        </div>
      </footer>
    </main>
  );
}
