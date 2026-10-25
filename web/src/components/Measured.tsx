import type {
  DatasetView,
  MeasuredAnalysis,
  MeasuredItem,
  MeasuredKind,
  MeasuredStatus,
  Scalar,
} from "../api";
import { fmtInt, fmtNum } from "../format";
import { ExactChartView } from "./ReportCharts";

/** Report parts, in reading order; each lists the kinds of Measured item it holds. */
const PARTS: { title: string; kinds: MeasuredKind[] }[] = [
  { title: "What drives the outcome", kinds: ["driver_regression", "driver_classification"] },
  { title: "Adjusted association", kinds: ["adjusted_association"] },
  { title: "Segments", kinds: ["segments"] },
  { title: "Unusual rows", kinds: ["anomalies"] },
  { title: "Columns that move together", kinds: ["components"] },
  { title: "Forecast", kinds: ["forecast"] },
  { title: "Where the relationship bends", kinds: ["threshold"] },
];

function statusTag(status: MeasuredStatus): string {
  switch (status) {
    case "ok":
      return "";
    case "no_lift":
      return "NO LIFT";
    case "withheld":
      return "WITHHELD";
    case "not_run":
      return "NOT RUN";
    default: {
      const unreachable: never = status;
      return unreachable;
    }
  }
}

function cell(key: string, value: Scalar): string {
  if (value === null) return "–";
  if (typeof value === "number") {
    if (key.includes("pct")) return `${value.toFixed(1)}%`;
    return fmtNum(value);
  }
  return String(value);
}

function MeasuredTable({ item }: { item: MeasuredItem }) {
  // rows of one table can carry different columns (shared-column rows and flagged rows), so use all of them
  const heads = [...new Set(item.table.flatMap((r) => Object.keys(r)))];
  if (heads.length === 0) return null;
  return (
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
                <td key={h}>{cell(h, row[h] ?? null)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Baseline X vs model Y on data it did not see (± spread)", from the item's own numbers. */
function ScoreLine({ item }: { item: MeasuredItem }) {
  if (item.model_score === null || item.baseline_score === null) return null;
  return (
    <p className="measured-score">
      baseline{item.baseline ? ` (${item.baseline})` : ""} {fmtNum(item.baseline_score)} vs model
      {item.model_family ? ` (${item.model_family})` : ""} {fmtNum(item.model_score)} on data it did
      not see
      {item.spread !== null ? ` (± ${fmtNum(item.spread)} between folds)` : ""}
      {item.metric ? `, ${item.metric}` : ""}
    </p>
  );
}

function Working({ item }: { item: MeasuredItem }) {
  return (
    <details className="work">
      <summary>Show the working</summary>
      <dl className="work-list">
        {item.target && (
          <>
            <dt>Predicts</dt>
            <dd className="mono">{item.target}</dd>
          </>
        )}
        {item.features.length > 0 && (
          <>
            <dt>Columns</dt>
            <dd className="mono">{item.features.join(", ")}</dd>
          </>
        )}
        <dt>Models tried</dt>
        <dd className="mono">{item.models_tried}</dd>
        {item.split && (
          <>
            <dt>Split</dt>
            <dd>{item.split}</dd>
          </>
        )}
        <dt>n</dt>
        <dd className="mono">{fmtInt(item.n_rows)}</dd>
      </dl>
    </details>
  );
}

function MeasuredFigure({ item }: { item: MeasuredItem }) {
  const tag = statusTag(item.status);
  return (
    <li className="exact-item" id={`fig-${item.id}`}>
      <div className="exact-top">
        <span className="label">{item.title}</span>
        <span style={{ display: "flex", gap: 8 }}>
          {tag && <span className="exact-badge exact-badge-dashed">{tag}</span>}
          <span className="exact-badge measured-badge">MEASURED</span>
        </span>
      </div>
      {item.status === "not_run" ? (
        <p className="explain" style={{ marginTop: 8 }}>
          Not run: {item.reason ?? "no reason was recorded."}
        </p>
      ) : item.status === "withheld" ? (
        <>
          <p className="exact-sentence">Withheld: too good to be true. Check for leakage.</p>
          <p className="explain" style={{ marginTop: 8 }}>
            {item.reason ?? item.sentence} No score is shown as a result.
          </p>
        </>
      ) : (
        <>
          {item.status === "no_lift" && <p className="exact-sentence">No model beat the baseline.</p>}
          {item.sentence && (
            <p className={item.status === "no_lift" ? "explain" : "exact-sentence"}>{item.sentence}</p>
          )}
          <ScoreLine item={item} />
          {item.status === "ok" && <ExactChartView item={item} />}
          {item.status === "ok" && <MeasuredTable item={item} />}
        </>
      )}
      {item.leakage.length > 0 && (
        <div className="measured-leak">
          <span className="label">Columns kept out of the model</span>
          <ul>
            {item.leakage.map((e) => (
              <li key={e.column}>
                <span className="mono">{e.column}</span>: {e.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {item.status !== "not_run" && <Working item={item} />}
    </li>
  );
}

/** The Measured tier: models scored on rows they did not see, against a baseline. */
export function Measured({ dataset }: { dataset: DatasetView }) {
  const m = dataset.measured;
  if (!m) {
    if (dataset.measured_pending) {
      return (
        <section className="panel report-section measured" aria-label="Measured results" aria-busy="true">
          <span className="label">Measured</span>
          <h3>Fitting models on this table</h3>
          <p className="explain" role="status">
            Models are being fitted and scored on rows they did not see. This can take a minute, and
            the page checks again by itself. Nothing is shown until the scores exist.
          </p>
        </section>
      );
    }
    if ((dataset.measured_failed_version ?? 0) > 0) {
      return (
        <section className="panel report-section measured" aria-label="Measured results">
          <span className="label">Measured</span>
          <h3>Models could not be fitted on this table</h3>
          <p className="explain">The exact figures above are unaffected. Nothing was measured.</p>
        </section>
      );
    }
    return null;
  }
  return <MeasuredBody analysis={m} />;
}

/**
 * Measured results for one table, whoever asked for them: the report's default plan, or
 * the analyses the planner chose for a run (`title` says which).
 */
export function MeasuredBody({
  analysis: m,
  title = "Models scored on data they did not see",
}: {
  analysis: MeasuredAnalysis;
  title?: string;
}) {
  const parts = PARTS.map((part) => ({
    title: part.title,
    items: m.items.filter((i) => part.kinds.includes(i.kind)),
  })).filter((p) => p.items.length > 0);
  return (
    <>
      <section className="panel report-section measured" aria-label="Measured results">
        <span className="label">Measured</span>
        <h3>{title}</h3>
        <p className="explain" style={{ marginTop: 8 }}>
          Each result below compares a model with a plain baseline on rows held back from fitting
          {m.sampled_rows !== null
            ? ` (the table was sampled to ${fmtInt(m.sampled_rows)} rows, seed ${m.seed})`
            : ""}
          . These are measurements, not tested findings: they have not been through the verification
          gate and nothing here is marked verified. {m.items.length} analys
          {m.items.length === 1 ? "is" : "es"} on {fmtInt(m.n_rows)} rows.
        </p>
        {m.excluded.length > 0 && (
          <div className="measured-leak">
            <span className="label">Kept out of every model</span>
            <ul>
              {m.excluded.map((e) => (
                <li key={e.column}>
                  <span className="mono">{e.column}</span>: {e.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
      {parts.map((part) => (
        <section className="panel report-section" key={part.title} aria-label={part.title}>
          <h3>{part.title}</h3>
          <ol className="exact-list">
            {part.items.map((item) => (
              <MeasuredFigure key={item.id} item={item} />
            ))}
          </ol>
        </section>
      ))}
    </>
  );
}

function num(v: Scalar | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * A short headline for the Report tab: the Measured forecast, labelled MEASURED, with the
 * next periods, their interval and the comparison with the seasonal-naive baseline. Only
 * numbers in the item's own values and table are used; with no finished forecast on the
 * dataset view, nothing is shown.
 */
export function ForecastHeadline({ dataset }: { dataset: DatasetView }) {
  const item = dataset.measured?.items.find((i) => i.kind === "forecast" && i.status === "ok");
  if (!item || item.table.length === 0) return null;
  const level = num(item.values.interval_level);
  const mase = num(item.values.mase_model);
  const base = num(item.values.mase_baseline);
  const cut = num(item.values.error_reduction_pct);
  const rows = item.table.slice(0, 4);
  return (
    <section className="panel report-section forecast-headline" aria-label="Forecast headline">
      <div className="exact-top">
        <span className="label">{item.title}</span>
        <span className="exact-badge measured-badge">MEASURED</span>
      </div>
      <p className="exact-sentence">
        Next {item.table.length} period{item.table.length === 1 ? "" : "s"}:{" "}
        {rows.map((r, i) => (
          <span key={String(r.period)}>
            {i > 0 && "; "}
            <span className="mono">{String(r.period)}</span> {cell("forecast", r.forecast ?? null)}
            {level !== null &&
              ` (${Math.round(level * 100)}% interval ${cell("lower", r.lower ?? null)} to ${cell("upper", r.upper ?? null)})`}
          </span>
        ))}
        {item.table.length > rows.length ? "; more in the full forecast below" : ""}.
      </p>
      <p className="explain">
        {cut !== null && mase !== null && base !== null
          ? `Beats the ${item.baseline ?? "baseline"} baseline on periods it did not see: ${fmtNum(cut)}% less error (scaled error ${fmtNum(mase)} against ${fmtNum(base)}).`
          : `Beats the ${item.baseline ?? "baseline"} baseline on periods it did not see.`}{" "}
        A measurement, not a verified finding.
      </p>
    </section>
  );
}
