import type { ExplorationSummary, SplitRecord } from "../api";
import { fmtInt } from "../format";

const ENGINE: Record<ExplorationSummary["engine"], string> = {
  scan: "Rule scan (no model)",
  agent: "Analysis agent (model with tools)",
  api: "Model proposer (summaries only)",
  planner: "Planner (model reading results from the exploration rows)",
};

/** Says plainly how many hypotheses were looked at versus tested, so nothing is hidden. */
export function Exploration({
  summary,
  split = null,
}: {
  summary: ExplorationSummary;
  /** The run's split, when the claims were chosen on rows the gate did not test on. */
  split?: SplitRecord | null;
}) {
  const held = split !== null && split.method !== "none";
  const screened = !held && summary.engine !== "api" && summary.examined > summary.tested;
  const dropped = summary.plan?.dropped ?? [];
  return (
    <section className="panel" aria-label="How these claims were found">
      <span className="label">How these claims were found</span>
      <h3 style={{ marginTop: 4 }}>{ENGINE[summary.engine]}</h3>
      <div className="stats" style={{ margin: "16px 0" }}>
        {summary.engine !== "api" && (
          <div>
            <span className="label">Looked at</span>
            <b>{fmtInt(summary.examined)}</b>
          </div>
        )}
        <div>
          <span className="label">Proposed</span>
          <b>{fmtInt(summary.proposed)}</b>
        </div>
        <div>
          <span className="label">Tested</span>
          <b>{fmtInt(summary.tested)}</b>
        </div>
        {summary.engine === "agent" && (
          <>
            <div>
              <span className="label">Model turns</span>
              <b>{summary.turns}</b>
            </div>
            <div>
              <span className="label">Tokens in / out</span>
              <b>
                {fmtInt(summary.input_tokens)} / {fmtInt(summary.output_tokens)}
              </b>
            </div>
          </>
        )}
      </div>
      {held && split && (
        <p className="explain">
          Claims were chosen on {fmtInt(split.n_exploration)} exploration rows and tested on{" "}
          {fmtInt(split.n_confirmation)} rows held back from that choice, so looking at many
          candidates first does not make the tested results look stronger than they are.
        </p>
      )}
      {dropped.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>
            Left out of the plan ({dropped.length})
          </summary>
          <ul className="exact-skipped" style={{ marginTop: 8 }}>
            {dropped.map((d, i) => (
              <li key={i}>
                <span className="note-level">{d.reason_code.replace(/_/g, " ").toUpperCase()}</span>
                <span>
                  <span className="mono">{d.item}</span>: {d.reason}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {summary.engine === "api" && (
        <p className="explain">
          A model proposed these claims from column summaries alone; no pair statistics were
          computed before testing.
        </p>
      )}
      {screened && (
        <p className="explain">
          {fmtInt(summary.examined)} column pairs were looked at and {fmtInt(summary.tested)} were
          tested. The correction for testing many claims covers only the {fmtInt(summary.tested)}{" "}
          tested ones, so treat borderline q-values with care: the pairs that were screened out
          first are not counted in it.
        </p>
      )}
      {summary.python_runs > 0 && (
        <p className="explain">
          The analyst also ran {summary.python_runs} free-form Python step
          {summary.python_runs === 1 ? "" : "s"}. What those looked at cannot be counted, so the
          figure above is a minimum.
        </p>
      )}
      {summary.entries.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>Exploration log ({summary.entries.length} steps)</summary>
          <table className="data-table" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>Step</th>
                <th>Tool</th>
                <th>Looked at</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {summary.entries.map((e) => (
                <tr key={e.entry_id}>
                  <td>{e.entry_id}</td>
                  <td>{e.name}</td>
                  <td>{e.examined}</td>
                  <td style={{ textAlign: "left", whiteSpace: "normal" }}>
                    {e.ok ? e.summary.slice(0, 110) : `failed: ${e.summary.slice(0, 100)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}
