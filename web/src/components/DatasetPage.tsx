import { useCallback, useEffect, useState } from "react";
import { api, type DatasetView, type RunView, type SystemStatus } from "../api";
import { useRun } from "../hooks";
import { fmtInt } from "../format";
import { useWorkspace } from "../store";
import { AppShell } from "./AppShell";
import { Ask } from "./Ask";
import { Brief } from "./Brief";
import { Overview } from "./Charts";
import { Arrow } from "./Icons";
import { Processing } from "./Processing";
import { Results } from "./Results";

type Tab = "overview" | "findings" | "ask";

function bytes(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

function Overviewtab({ dataset }: { dataset: DatasetView }) {
  const p = dataset.preview;
  const heads = p.sample_rows[0] ? Object.keys(p.sample_rows[0]) : [];
  return (
    <div className="results split">
      <div className="col-stack">
        {dataset.brief && <Brief brief={dataset.brief} />}
        <section className="panel" aria-label="What PRAMANA understood">
          <span className="label">What PRAMANA understood</span>
          <h3 style={{ marginTop: 4 }}>
            <span className="mono">{fmtInt(p.rows)}</span> rows, <span className="mono">{fmtInt(p.columns)}</span>{" "}
            columns, <span className="mono">{dataset.usable_columns}</span> usable
          </h3>
          <table className="col-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Detected as</th>
                <th>Used</th>
              </tr>
            </thead>
            <tbody>
              {p.detected_columns.map((c) => (
                <tr key={c.name}>
                  <td className="mono" style={{ fontSize: 13 }}>
                    {c.name}
                  </td>
                  <td>{c.role.replace(/_/g, " ")}</td>
                  <td title={c.reasons.join("; ")}>{c.usable ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {p.detected_columns.some((c) => !c.usable && c.reasons.length > 0) && (
            <p className="explain" style={{ marginTop: 12 }}>
              Not used:{" "}
              {p.detected_columns
                .filter((c) => !c.usable && c.reasons.length > 0)
                .map((c) => `${c.name} (${c.reasons[0]})`)
                .join("; ")}
              .
            </p>
          )}
        </section>

        {heads.length > 0 && (
          <section className="panel" aria-label="First rows">
            <span className="label">First {p.sample_rows.length} rows, after cleaning</span>
            <div style={{ overflowX: "auto", marginTop: 12 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    {heads.map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {p.sample_rows.map((row, i) => (
                    <tr key={i}>
                      {heads.map((h) => (
                        <td key={h}>{row[h]}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      <div>
        {dataset.overview ? (
          <Overview overview={dataset.overview} />
        ) : (
          <div className="empty">
            <h3>No data summary</h3>
            <p>No column in this table could be summarised.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function FindingsTab({
  dataset,
  runs,
  runId,
  onRunFinished,
}: {
  dataset: DatasetView;
  runs: RunView[];
  runId: string | null;
  onRunFinished: () => void;
}) {
  const { run, results, problem } = useRun(runId, onRunFinished);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setSelected(null), [runId]);

  if (runs.length === 0) {
    return (
      <div className="empty">
        <h3>Nothing analysed yet</h3>
        <p>
          Analyse proposes claims about {dataset.name}, tests each with 10,000 permutations,
          corrects for testing many at once, and lists what survived and what did not, with
          reasons.
        </p>
      </div>
    );
  }

  let body: React.ReactNode = null;
  if (problem) {
    body = (
      <div className="error-card" role="alert">
        <h3>This run could not be loaded</h3>
        <p>{problem}</p>
      </div>
    );
  } else if (!run) {
    body = <p className="page-sub">Loading run…</p>;
  } else if (run.status === "pending" || run.status === "running") {
    body = <Processing run={run} />;
  } else if (run.status === "failed" && !results) {
    body = (
      <div className="error-card" role="alert">
        <h3>The run failed</h3>
        <p>{run.error ?? "The run failed."} Nothing was marked verified.</p>
      </div>
    );
  } else if (results) {
    body = (
      <>
        {run.error && (
          <div className="error-card" role="status" style={{ marginBottom: 24 }}>
            <h3>{run.status === "degraded" ? "Finished with a problem" : "Run problem"}</h3>
            <p>{run.error}</p>
          </div>
        )}
        <Results results={results} selected={selected} onSelect={setSelected} />
      </>
    );
  } else {
    body = (
      <div className="note-card">
        <h3>No results were produced</h3>
        <p>{run.error ?? "This run finished without a result snapshot."} Nothing was marked verified.</p>
      </div>
    );
  }

  return (
    <>
      {runs.length > 1 && (
        <div className="run-picker" role="tablist" aria-label="Runs">
          {runs.map((r, i) => (
            <a
              key={r.run_id}
              role="tab"
              aria-selected={r.run_id === runId}
              className="chip run-chip"
              href={`#/d/${dataset.dataset_id}/findings/${r.run_id}`}
            >
              {i === 0 ? "Latest" : new Date(r.created_at).toLocaleString()} · {r.status}
            </a>
          ))}
        </div>
      )}
      {body}
    </>
  );
}

export function DatasetPage({ id, tab, runId }: { id: string; tab: Tab; runId: string | null }) {
  const { refresh } = useWorkspace();
  const [dataset, setDataset] = useState<DatasetView | null>(null);
  const [runs, setRuns] = useState<RunView[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await api.datasetRuns(id));
    } catch {
      /* keep the last known list */
    }
  }, [id]);

  useEffect(() => {
    api.system().then(setSystem, () => setSystem(null));
  }, []);

  useEffect(() => {
    setDataset(null);
    setProblem(null);
    api.dataset(id).then(setDataset, (e: Error) => setProblem(e.message));
    loadRuns();
  }, [id, loadRuns]);

  const finished = useCallback(() => {
    loadRuns();
    refresh();
  }, [loadRuns, refresh]);

  const analyse = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const run = await api.analyse(id, question);
      await Promise.all([loadRuns(), refresh()]);
      window.location.hash = `#/d/${id}/findings/${run.run_id}`;
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "Could not start the analysis.");
    } finally {
      setStarting(false);
    }
  };

  const active = runs.find((r) => r.status === "running" || r.status === "pending");
  const shownRun = runId ?? runs[0]?.run_id ?? null;

  return (
    <AppShell active={{ dataset: id }}>
      {problem && (
        <div className="error-card" role="alert">
          <h3>This dataset could not be loaded</h3>
          <p>{problem}</p>
        </div>
      )}
      {!problem && !dataset && <p className="page-sub">Loading…</p>}
      {dataset && (
        <>
          <div className="page-head">
            <div>
              <h1 className="page-title">{dataset.name}</h1>
              <div className="chips" style={{ marginTop: 12 }}>
                <span className="chip">{fmtInt(dataset.preview.rows)} rows</span>
                <span className="chip">{fmtInt(dataset.preview.columns)} columns</span>
                <span className="chip">{bytes(dataset.size_bytes)}</span>
                <span className="chip">added {new Date(dataset.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          </div>

          <form
            className="analyse-bar"
            onSubmit={(event) => {
              event.preventDefault();
              if (!starting && !active && dataset.usable_columns > 0) analyse();
            }}
          >
            <label className="question">
              <span className="label">Question (optional)</span>
              <input
                type="text"
                value={question}
                maxLength={400}
                placeholder="For example: does blood pressure rise with age?"
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={
                starting ||
                Boolean(active) ||
                dataset.usable_columns === 0 ||
                (system?.blockers.length ?? 0) > 0
              }
            >
              {active ? "Analysing…" : starting ? "Starting…" : "Analyse"} <Arrow />
            </button>
          </form>
          {system && (
            <div className="system-line">
              <span className="chip">
                Analyst: {system.analysis_engine === "deterministic" ? "rule scan, no model" : system.analysis_engine === "agent" ? "model agent with tools" : "model proposer"}
              </span>
              <span className="chip">
                Test code: {system.verification_generator === "llm" ? "model-written" : "built-in templates"}
              </span>
              {system.blockers.length > 0 && (
                <p className="dz-error" role="alert">
                  A model is switched on but cannot run: {system.blockers.join("; ")}. Add them to
                  the server's <span className="mono">.env</span> and restart, or switch to the
                  offline profile.
                </p>
              )}
            </div>
          )}
          {dataset.usable_columns === 0 && (
            <p className="dz-error" role="alert" style={{ marginTop: 12 }}>
              No usable measurement columns remain after cleaning, so this table cannot be analysed.
            </p>
          )}
          {startError && (
            <p className="dz-error" role="alert" style={{ marginTop: 12 }}>
              {startError}
            </p>
          )}

          <div className="tabs" role="tablist" aria-label="Dataset sections">
            <a role="tab" aria-selected={tab === "overview"} href={`#/d/${id}`}>
              Overview
            </a>
            <a role="tab" aria-selected={tab === "findings"} href={`#/d/${id}/findings`}>
              Findings{runs.length > 0 ? ` (${runs.length})` : ""}
            </a>
            <a role="tab" aria-selected={tab === "ask"} href={`#/d/${id}/ask`}>
              Ask
            </a>
          </div>

          {tab === "overview" ? (
            <Overviewtab dataset={dataset} />
          ) : tab === "ask" ? (
            <Ask key={id} dataset={dataset} system={system} />
          ) : (
            <FindingsTab dataset={dataset} runs={runs} runId={shownRun} onRunFinished={finished} />
          )}
        </>
      )}
    </AppShell>
  );
}
