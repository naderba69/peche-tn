import type { Metadata } from "next";
import { BookOpen, Info } from "lucide-react";
import { ENCYCLOPEDIA_INTRO, ENCYCLOPEDIA_SECTIONS, type TrustTag } from "@/lib/encyclopedia";

export const metadata: Metadata = {
  title: "موسوعة العوامل",
  description: "فيزياء وميدان وتراث السيرفكاست معايرة للساحل التونسي — بلا وعد مصيد.",
};

const TAG_CLASS: Record<TrustTag, string> = {
  فيزياء: "tag-physics",
  ميداني: "tag-field",
  تراث: "tag-folk",
};

export default function EncyclopediaPage() {
  return (
    <main className="encyclopedia-page">
      <section className="encyclopedia-hero" id="top">
        <div className="eyebrow">
          <BookOpen size={15} /> موسوعة السيرفكاست · تونس
        </div>
        <h1>
          {ENCYCLOPEDIA_INTRO.title}
          <br />
          <em>أرقام موسومة، قرار منفصل.</em>
        </h1>
        <p>{ENCYCLOPEDIA_INTRO.lead}</p>
        <div className="encyclopedia-tags" aria-label="منهجية التوثيق">
          <span className="tag-physics">فيزياء — قانون</span>
          <span className="tag-field">ميداني — خبرة متكررة</span>
          <span className="tag-folk">تراث — دليل علمي ضعيف</span>
        </div>
      </section>

      <aside className="encyclopedia-tunisia" aria-label="معايرة تونس">
        <Info size={18} />
        <div>
          <strong>معايرة هذا الساحل — ليست أكادير ولا بريتاني</strong>
          <ul>
            {ENCYCLOPEDIA_INTRO.tunisia.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </aside>

      <nav className="encyclopedia-toc" aria-label="فصول الموسوعة">
        {ENCYCLOPEDIA_SECTIONS.map((section) => (
          <a key={section.id} href={`#${section.id}`}>
            {section.title}
          </a>
        ))}
      </nav>

      {ENCYCLOPEDIA_SECTIONS.map((section) => (
        <article key={section.id} id={section.id} className="encyclopedia-section">
          <header>
            <h2>{section.title}</h2>
            <span className={TAG_CLASS[section.tag]}>{section.tag}</span>
          </header>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          {section.tables?.map((table) => (
            <div key={table.caption} className="encyclopedia-table-wrap">
              <p className="encyclopedia-caption">{table.caption}</p>
              <table>
                <thead>
                  <tr>
                    {table.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row) => (
                    <tr key={row.join("-")}>
                      {row.map((cell, index) => (
                        <td key={`${row[0]}-${index}`}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {section.engine ? (
            <p className="encyclopedia-engine">
              <strong>في المحرك:</strong> {section.engine}
            </p>
          ) : null}
        </article>
      ))}
    </main>
  );
}
