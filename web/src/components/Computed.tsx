import type { ComputedAnalysis, ExactItem, Scalar } from "../api";
import { ExactChartView } from "./ReportCharts";

const SHAPES: Record<string, string> = {
  cross_section: "one row per record, no time axis",
  time_series: "one row per period",
  panel: "one row per period and group",
  transactions: "many rows per period",
};

/** Report sections, in reading order; each lists the kinds of figure it holds. */
const SECTIONS: { title: string; kinds: string[] }[] = [
  { title: "What changed", kinds: ["period_change", "variance_decomposition"] },
  { title: "Health measures", kinds: ["prevalence", "weighted_means", "rates"] },
  { title: "Where it is concentrated", kinds: ["concentration", "segment_ranking"] },
  { title: "Patterns across the year", kinds: ["seasonality"] },
  { title: "Unusual values", kinds: ["outliers"] },
  { title: "Checks on the data", kinds: ["identity", "data_quality"] },
];

function cell(key: string, value: Scalar): string {
  if (value === null) return "–";
  if (typeof value === "number") {
    if (key.includes("share")) return `${(value * 100).toFixed(1)}%`;
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function Work({ item }: { item: ExactItem }) {
  const heads = item.table[0] ? Object.keys(item.table[0]) : [];
  return (
    <details className="work">
      <summary>Show the working</summary>
      <dl className="work-list">
        <dt>Formula</dt>
        <dd className="mono">{item.formula}</dd>
        <dt>Columns</dt>
        <dd className="mono">{item.columns.filter(Boolean).join(", ")}</dd>
        {item.filters.length > 0 && (
          <>
            <dt>Rows used</dt>
            <dd className="mono">{item.filters.join("; ")}</dd>
          </>
        )}
        <dt>n</dt>
        <dd className="mono">{item.n_rows.toLocaleString()}</dd>
      </dl>
      {heads.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table className="data-table">
            <thead>
              <tr>
                {heads.map((h) => (
                  <th key={h}>{h.replace(/_/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {item.table.map((row, i) => (
                <tr key={i}>
                  {heads.map((h) => (
                    <td key={h}>{cell(h, row[h])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function Figure({ item }: { item: ExactItem }) {
  return (
    <li className="exact-item" id={`fig-${item.id}`}>
      <div className="exact-top">
        <span className="label">{item.title}</span>
        <span className="exact-badge">EXACT</span>
      </div>
      <p className="exact-sentence">{item.sentence}</p>
      <ExactChartView item={item} />
      <Work item={item} />
    </li>
  );
}

/** The report: a short summary, then every computed figure grouped by theme, with charts. */
export function Computed({ computed }: { computed: ComputedAnalysis }) {
  const done = computed.items.filter((i) => i.status === "ok");
  const skipped = computed.items.filter((i) => i.status === "not_run");
  const { shape, summary } = computed;
  const placed = new Set(SECTIONS.flatMap((s) => s.kinds));
  const sections = [
    ...SECTIONS,
    { title: "Other figures", kinds: [...new Set(done.map((i) => i.kind))].filter((k) => !placed.has(k)) },
  ]
    .map((s) => ({ title: s.title, items: done.filter((i) => s.kinds.includes(i.kind)) }))
    .filter((s) => s.items.length > 0);

  return (
    <section className="report" aria-label="What the data says">
      <div className="panel report-summary">
        <span className="label">What the data says</span>
        <h2 className="report-title">
          {done.length} figure{done.length === 1 ? "" : "s"} computed from this table
        </h2>
        <div className="chips" style={{ marginTop: 12 }}>
          <span className="chip" title={shape.reasons.join("; ")}>
            shape: {shape.shape.replace(/_/g, " ")}
          </span>
          {shape.time_column && (
            <span className="chip">
              time: {shape.time_column} · {shape.n_periods} {shape.period}s
            </span>
          )}
          {shape.entity_column && <span className="chip">group: {shape.entity_column}</span>}
        </div>
        {summary && summary.lines.length > 0 && (
          <ol className="summary-list">
            {summary.lines.map((line) => (
              <li key={line.item_id}>
                <a href={`#fig-${line.item_id}`} onClick={(e) => {
                  e.preventDefault();
                  document.getElementById(`fig-${line.item_id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}>
                  {line.text}
                </a>
              </li>
            ))}
          </ol>
        )}
        <p className="explain" style={{ marginTop: 12 }}>
          Read as {SHAPES[shape.shape]}. {computed.scope_note} These are exact calculations, not
          tested findings: nothing here is marked verified.{" "}
          {summary?.source === "model"
            ? "The summary was worded by DeepSeek from the figures below, and every number in it was checked against them."
            : "The summary lists the figures below in code-written words."}
          {summary?.fallback_reason && ` Model wording was not used: ${summary.fallback_reason}.`}
        </p>
      </div>

      {sections.map((section) => (
        <div className="panel report-section" key={section.title}>
          <h3>{section.title}</h3>
          <ol className="exact-list">
            {section.items.map((item) => (
              <Figure key={item.id} item={item} />
            ))}
          </ol>
        </div>
      ))}

      {skipped.length > 0 && (
        <div className="panel report-section">
          <h3>Not run on this table</h3>
          <ul className="exact-skipped">
            {skipped.map((item) => (
              <li key={item.id}>
                <span className="note-level">NOT RUN</span>
                <span>
                  <strong>{item.title}.</strong> {item.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
