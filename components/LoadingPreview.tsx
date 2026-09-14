import { Check, CloudSun, LoaderCircle, ShieldCheck, Waves } from "lucide-react";

export function LoadingPreview() {
  return (
    <section className="analysis-progress" id="analysis-progress" role="status" aria-live="polite">
      <div className="analysis-progress-head">
        <span className="analysis-pulse"><LoaderCircle className="spin" size={20} /></span>
        <div>
          <strong>نحضّر قرار الحصة</strong>
          <span>عادةً العملية تكمل في ثوانٍ قليلة</span>
        </div>
      </div>
      <div className="analysis-steps" aria-label="مراحل التحليل">
        <div className="done"><Check size={15} /><span>تثبيت البقعة</span></div>
        <div className="active"><CloudSun size={15} /><span>جلب الأرصاد</span></div>
        <div><Waves size={15} /><span>تحليل البحر</span></div>
        <div><ShieldCheck size={15} /><span>فحص السلامة</span></div>
      </div>
      <div className="analysis-bar"><span /></div>
    </section>
  );
}
