import type { InsightReport, Insight } from "../api";
import { ExactChartView } from "./ReportCharts";

const SECTION_TITLES: Record<Insight["section"], string> = {
  outcome: "The outcome",
  drivers: "What goes with the outcome",
  time: "Change over time",
  comparison: "How they compare",
  relationships: "Relationships",
  quality: "Data quality",
};

function InsightCard({ insight, lead, rows }: { insight: Insight; lead: boolean; rows: number }) {
  return (
    <article className={lead ? "insight insight-lead" : "insight"} aria-label={insight.title}>
      <span className="label">{SECTION_TITLES[insight.section]}</span>
      <h3 className="insight-title">{insight.title}</h3>
      <p className="insight-text">{insight.text}</p>
      {insight.chart && <ExactChartView item={{ chart: insight.chart, n_rows: rows }} />}
      {insight.claim && (
        <p className="explain insight-claim">
          Descriptive. Press Analyse to test this with the verification gate.
        </p>
      )}
    </article>
  );
}

/** The analyst's read, shown first: what the table is about and what stands out. */
export function Insights({ report }: { report: InsightReport }) {
  const [lead, ...rest] = report.insights;
  const quality = rest.filter((i) => i.section === "quality");
  const main = rest.filter((i) => i.section !== "quality");
  return (
    <section className="report insights" aria-label="Key insights">
      <div className="panel report-summary">
        <span className="label">Key insights</span>
        <h2 className="report-title">What an analyst would tell you first</h2>
        <p className="explain" style={{ marginTop: 8 }}>
          {report.grain}
          {report.target
            ? ` The outcome looks like ${report.target.column} (${report.target.reason}).`
            : " No single outcome column stands out, so this looks at change and relationships."}
        </p>
        {report.set_aside.length > 0 && (
          <details style={{ marginTop: 12 }}>
            <summary>Columns set aside ({report.set_aside.length})</summary>
            <ul className="insight-list">
              {report.set_aside.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
      {lead && <InsightCard insight={lead} lead rows={report.rows} />}
      <div className="insight-grid">
        {main.map((i) => (
          <InsightCard key={i.id} insight={i} lead={false} rows={report.rows} />
        ))}
      </div>
      {(quality.length > 0 || report.questions.length > 0) && (
        <div className="panel">
          {quality.length > 0 && (
            <>
              <span className="label">Before trusting the numbers</span>
              <ul className="insight-list">
                {quality.map((q) => (
                  <li key={q.id}>{q.text}</li>
                ))}
              </ul>
            </>
          )}
          {report.questions.length > 0 && (
            <>
              <span className="label" style={{ display: "block", marginTop: 12 }}>
                Questions to ask next
              </span>
              <ul className="insight-list">
                {report.questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
