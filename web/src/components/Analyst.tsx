import type { AnalystFact, DatasetView, Scalar } from "../api";

const TASKS: Record<string, string> = {
  driver_regression: "predict a number",
  driver_classification: "predict a group",
  segments: "find groups of rows",
  anomalies: "find unusual rows",
  components: "find the main directions",
};

function cell(value: Scalar): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function FactTable({ fact, heads }: { fact: AnalystFact; heads: [string, string][] }) {
  return (
    <div className="analyst-table">
      <span className="label">{fact.title}</span>
      <table className="col-table">
        <thead>
          <tr>
            {heads.map(([, title]) => (
              <th key={title}>{title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fact.table.map((row, i) => (
            <tr key={i}>
              {heads.map(([key]) => (
                <td key={key} className="mono">
                  {cell(row[key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The analyst's reading of the results: written by the model, every number checked by code. */
export function Analyst({ dataset }: { dataset: DatasetView }) {
  const read = dataset.analyst;
  if (!read) {
    if (!dataset.measured) return null;
    return (
      <section className="panel report-section" aria-label="Analyst" aria-busy="true">
        <span className="label">Analyst</span>
        <h3>Reading the results</h3>
        <p className="explain" role="status">
          The analyst is choosing extra analyses and reading the results. This page checks again by
          itself.
        </p>
      </section>
    );
  }
  const boards = read.facts.filter((f) => f.id.startsWith("leaderboard:"));
  const associations = read.facts.find((f) => f.id === "associations");
  const asked = read.requests.filter((r) => r.accepted);
  return (
    <section className="panel report-section analyst" aria-label="Analyst">
      <span className="label">Analyst</span>
      <h3>What the data shows</h3>
      <p className="explain">
        {read.source === "model"
          ? "Written by the model from the results below. Code computed every number, and a paragraph is shown only if each number in it appears in the results it cites."
          : `Written by code from the results below${read.fallback_reason ? ` (the model's text was not used: ${read.fallback_reason})` : ""}.`}
        {read.paragraphs_dropped > 0 && ` ${read.paragraphs_dropped} paragraph${read.paragraphs_dropped === 1 ? "" : "s"} failed the check and ${read.paragraphs_dropped === 1 ? "is" : "are"} not shown.`}
      </p>
      <div className="analyst-text">
        {read.paragraphs.map((p, i) => (
          <div key={i}>
            <p>{p.text}</p>
            {(p.checks ?? []).map((c, j) => (
              <p key={j} className="statement-check explain" data-status={c.status}>
                <span className="label">Checked by code: {c.status.replace(/_/g, " ")}</span> {c.headline}
              </p>
            ))}
          </div>
        ))}
      </div>
      {asked.length > 0 && (
        <p className="explain">
          The analyst also asked for {asked.length} extra analys{asked.length === 1 ? "is" : "es"}
          , which code ran:{" "}
          {asked.map((r) => `${TASKS[r.task] ?? r.task}${r.target ? ` (${r.target})` : ""}`).join("; ")}.
        </p>
      )}
      {read.steps.length > 0 && (
        <details className="work">
          <summary>
            What the agent ran ({read.steps.length} step{read.steps.length === 1 ? "" : "s"})
          </summary>
          <ol className="how-list">
            {read.steps.map((step) => (
              <li key={step.id}>
                <strong>{step.tool === "python" ? "Python" : step.tool}</strong>
                {step.ok ? "" : " (failed)"}
                <pre className="code" tabIndex={0}>
                  {step.summary}
                </pre>
                <span className="explain">Result: {step.output}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
      {associations && (
        <FactTable
          fact={associations}
          heads={[
            ["column_a", "Column"],
            ["column_b", "Column"],
            ["rank_correlation", "Rank correlation"],
            ["rows", "Rows"],
          ]}
        />
      )}
      {boards.map((fact) => (
        <FactTable
          key={fact.id}
          fact={fact}
          heads={[
            ["model", "Model"],
            ["held_out_score", "Score on unseen rows"],
            ["folds_won", "Folds won"],
          ]}
        />
      ))}
    </section>
  );
}
