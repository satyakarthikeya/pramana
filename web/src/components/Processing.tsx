import { useEffect, useState } from "react";
import type { RunView } from "../api";
import { elapsed, fmtInt } from "../format";
import { Check, Cross } from "./Icons";

const STAGES = [
  "Profile data",
  "Propose claims",
  "Run tests",
  "Verify and record",
] as const;

type StageState = "pending" | "running" | "done" | "failed";

/** The run only exposes a progress line, so the stage is read from that line, never faked. */
function activeStage(progress: string): number {
  if (progress.startsWith("Writing")) return 3;
  if (progress.startsWith("Testing") || progress.startsWith("Checking")) return 2;
  if (progress.startsWith("Proposing") || progress === "Data preview ready") return 1;
  return 0;
}

export function stageStates(run: RunView): StageState[] {
  if (run.status === "completed" || run.status === "degraded") {
    return STAGES.map(() => "done");
  }
  const at = activeStage(run.progress);
  return STAGES.map((_, i) => {
    if (i < at) return "done";
    if (i > at) return "pending";
    return run.status === "failed" ? "failed" : "running";
  });
}

const NOTES: Record<number, string> = {
  2: "Permutation tests run in a sandbox; every claim is tested once.",
  3: "Correcting across all tested claims, applying the gate, writing proofs.",
};

function Glyph({ state }: { state: StageState }) {
  if (state === "done") return <Check className="glyph" style={{ color: "var(--accent)" }} />;
  if (state === "failed") return <Cross className="glyph" style={{ color: "var(--reject)" }} />;
  if (state === "running") {
    return (
      <svg className="glyph" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="7" fill="none" stroke="#D9D1C4" strokeWidth="2" />
        <path className="spin" d="M10 3a7 7 0 0 1 7 7" fill="none" stroke="#0F5C58" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className="glyph" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="6" fill="none" stroke="#BFB5A5" strokeWidth="1.5" />
    </svg>
  );
}

export function Processing({ run }: { run: RunView }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const states = stageStates(run);
  const live = run.status === "pending" || run.status === "running";
  const preview = run.preview;
  return (
    <div className="proc">
      <div>
        <div className="label" style={{ marginBottom: 12 }}>
          {run.file_name} · <span className="mono">{elapsed(run.created_at, live ? null : run.finished_at)}</span>
        </div>
        <ol className="stages" aria-label="Pipeline stages" aria-live="polite">
          {STAGES.map((name, i) => (
            <li key={name} className="stage" data-state={states[i]}>
              <Glyph state={states[i]} />
              <span className="name">{name}</span>
              <span className="time">
                {states[i] === "done" ? "done" : states[i] === "running" ? "running" : ""}
              </span>
              {states[i] === "running" && (
                <span className="stage-note">
                  {run.progress}
                  {NOTES[i] ? ` — ${NOTES[i]}` : ""}
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>

      <div style={{ display: "grid", gap: 24 }}>
        {preview ? (
          <section className="panel" aria-label="What PRAMANA understood">
            <span className="label">What PRAMANA read</span>
            <h3 style={{ marginTop: 4 }}>
              <span className="mono">{fmtInt(preview.rows)}</span> rows,{" "}
              <span className="mono">{fmtInt(preview.columns)}</span> columns
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
                {preview.detected_columns.slice(0, 14).map((c) => (
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
            {preview.detected_columns.length > 14 && (
              <p className="explain" style={{ marginTop: 8 }}>
                and {preview.detected_columns.length - 14 + preview.omitted_columns} more columns
              </p>
            )}
          </section>
        ) : (
          <section className="note-card">
            <h3>Reading your file</h3>
            <p>The detected columns appear here as soon as the table is cleaned.</p>
          </section>
        )}

        {run.past_lessons.length > 0 && (
          <section className="panel" aria-label="Hints from earlier runs">
            <span className="label">Hints from earlier runs</span>
            <p className="explain" style={{ marginTop: 4 }}>
              Verified before on similar tables. These are hints only and are tested again on this
              data; none is reported unless it passes.
            </p>
            <div className="hint-list">
              {run.past_lessons.slice(0, 3).map((h) => (
                <div className="hint" key={h.lesson.record_id}>
                  <p>{h.lesson.text}</p>
                  <span className="mono">similarity {h.similarity.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
