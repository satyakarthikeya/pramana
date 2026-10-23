import { useEffect, useState } from "react";
import { api, type Lesson } from "../api";
import { fmtEffect, fmtP } from "../format";
import { AppShell } from "./AppShell";
import { Badge } from "./Verdict";

export function MemoryPage() {
  const [lessons, setLessons] = useState<Lesson[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    api.memory().then(setLessons, (e: Error) => setProblem(e.message));
  }, []);
  return (
    <AppShell active={{ memory: true }}>
      <div className="page-head">
        <div>
          <h1 className="page-title">Verified memory</h1>
          <p className="page-sub">
            Only claims that passed the gate are stored. On later tables they appear as hints and
            are tested again.
          </p>
        </div>
      </div>
      {problem && (
        <div className="error-card" role="alert">
          <h3>Memory is unavailable</h3>
          <p>{problem}</p>
        </div>
      )}
      {lessons && lessons.length === 0 && (
        <div className="empty">
          <h3>Nothing stored yet.</h3>
          <p>Verified findings from a run are saved here.</p>
        </div>
      )}
      {lessons && lessons.length > 0 && (
        <div className="table-wrap">
          <table className="col-table">
            <thead>
              <tr>
                <th>Lesson</th>
                <th>Verdict</th>
                <th className="num">q</th>
                <th className="num">Effect</th>
                <th>Source run</th>
              </tr>
            </thead>
            <tbody>
              {lessons.map((l) => (
                <tr key={l.record_id}>
                  <td style={{ maxWidth: 420 }}>{l.text}</td>
                  <td>
                    <Badge proof={l.proof} />
                  </td>
                  <td className="num">{fmtP(l.proof.q_value)}</td>
                  <td className="num">{fmtEffect(l.proof.effect_size)}</td>
                  <td>
                    <a className="row-link mono" href={`#/run/${l.run_id}`}>
                      {l.run_id.slice(0, 8)}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!lessons && !problem && <p className="page-sub">Loading…</p>}
    </AppShell>
  );
}
