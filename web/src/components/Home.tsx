import { useEffect, useState } from "react";
import { useWorkspace } from "../store";
import { fmtInt } from "../format";
import { AppShell, useFilePicker } from "./AppShell";
import { Arrow, Upload } from "./Icons";

const MAX_NAME = 120;

function suggestedName(file: File): string {
  const stem = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  return (stem || file.name).slice(0, MAX_NAME);
}

function size(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** One focused screen: choose a table, name it, start. The rest happens on its own page. */
export function Home() {
  const { datasets, staged, stage, start, starting } = useWorkspace();
  const picker = useFilePicker((file) => stage(file));
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");

  useEffect(() => {
    setName(staged ? suggestedName(staged) : "");
    setQuestion("");
  }, [staged]);

  const ready = staged !== null && name.trim().length > 0 && !starting;

  return (
    <AppShell active={{}}>
      <div className="home">
        <h1 className="page-title">Analyse a table</h1>
        <p className="page-sub">
          Upload a CSV or XLSX and give it a name. PRAMANA computes the figures from your data,
          proposes claims and tests each one. Only claims that pass testing are called findings.
        </p>

        {staged === null ? (
          <section className="start-drop" aria-label="Choose a table">
            <div>
              <h2>Drop a table here</h2>
              <p className="dz-meta">CSV or XLSX · first sheet only · one row per record</p>
            </div>
            <button type="button" className="btn btn-primary" onClick={picker.open}>
              <Upload /> Choose file
            </button>
            {picker.element}
          </section>
        ) : (
          <form
            className="start-form"
            aria-label="Name and start"
            onSubmit={(event) => {
              event.preventDefault();
              if (ready) start(staged, name.trim(), question);
            }}
          >
            <div className="start-file">
              <span className="mono">{staged.name}</span>
              <span className="dz-meta">{size(staged.size)}</span>
              <button
                type="button"
                className="btn btn-ghost btn-compact"
                disabled={starting}
                onClick={picker.open}
              >
                Choose another
              </button>
              {picker.element}
            </div>
            <label className="question">
              <span className="label">Name</span>
              <input
                type="text"
                value={name}
                maxLength={MAX_NAME}
                required
                autoFocus
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="question">
              <span className="label">Question (optional)</span>
              <input
                type="text"
                value={question}
                maxLength={400}
                placeholder="For example: which region accounts for the growth?"
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <div className="dz-actions">
              <button type="submit" className="btn btn-primary btn-hero" disabled={!ready}>
                {starting ? "Uploading and starting…" : "Start analysis"} <Arrow />
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={starting}
                onClick={() => stage(null)}
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {datasets && datasets.length > 0 && (
          <section style={{ marginTop: 48 }}>
            <div className="section-head">
              <h2>Your datasets</h2>
              <span className="label">{datasets.length} stored</span>
            </div>
            <div className="table-wrap">
              <table className="col-table">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Added</th>
                    <th className="num">Rows</th>
                    <th className="num">Columns</th>
                    <th className="num">Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((d) => (
                    <tr key={d.dataset_id}>
                      <td>
                        <a className="row-link" href={`#/d/${d.dataset_id}`}>
                          {d.name}
                        </a>
                      </td>
                      <td className="mono" style={{ fontSize: 13 }}>
                        {new Date(d.created_at).toLocaleString()}
                      </td>
                      <td className="num">{fmtInt(d.rows)}</td>
                      <td className="num">{fmtInt(d.columns)}</td>
                      <td className="num">{d.run_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </AppShell>
  );
}
