import { useState } from "react";
import { api, type StatementCheck, type StatementStatus } from "../api";

const WORDS: Record<StatementStatus, string> = {
  matches: "MATCHES THE TABLE",
  off_by: "DOES NOT MATCH",
  ambiguous: "DEPENDS ON THE READING",
  tested: "TESTED BY THE GATEWAY",
  not_tested: "NOT TESTED YET",
  not_testable: "NOT TESTABLE FROM A TABLE",
  cannot_check: "COULD NOT BE CHECKED",
};

function Result({ item }: { item: StatementCheck }) {
  const r = item.result;
  return (
    <li className="statement-result" data-status={r.status}>
      <span className="label">{WORDS[r.status]}</span>
      <p className="statement-headline">{r.headline}</p>
      {r.detail && <p className="explain">{r.detail}</p>}
      {r.readings.length > 1 && (
        <ul className="statement-readings">
          {r.readings.map((reading) => (
            <li key={reading.label} className="mono">
              {reading.label}: {reading.value === null ? "n/a" : reading.value.toFixed(r.kind === "rank" ? 2 : 1)}
              {r.kind === "rank" ? "" : "%"}
              {reading.matches ? " (matches)" : ""}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Type a sentence from a report; a model reads it and code recomputes it from the table. */
export function CheckStatement({ datasetId }: { datasetId: string }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<StatementCheck[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api.checkStatements(datasetId, text);
      setFound(out.results);
      setNotes(out.notes);
    } catch (e) {
      setFound(null);
      setError(e instanceof Error ? e.message : "Could not check that sentence.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel report-section" aria-label="Check a statement">
      <span className="label">Check a statement</span>
      <h3>Is this sentence true of your table?</h3>
      <p className="explain">
        Paste a claim, such as "revenue fell 12% in Q3". The analyst reads it, and code recomputes it
        from your rows. Causes and projections are said to be not testable, with the reason.
      </p>
      <div className="statement-input">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && text.trim().length > 2 && !busy && submit()}
          placeholder="Revenue fell 12% in Q3"
          maxLength={600}
          aria-label="A sentence to check"
        />
        <button type="button" className="btn btn-primary" disabled={busy || text.trim().length < 3} onClick={submit}>
          {busy ? "Checking" : "Check"}
        </button>
      </div>
      {error && <p className="explain" role="alert">{error}</p>}
      {found && found.length === 0 && (
        <p className="explain">The analyst found nothing in that sentence it could check against this table.</p>
      )}
      {found && found.length > 0 && (
        <ul className="statement-results">
          {found.map((item, i) => (
            <Result key={i} item={item} />
          ))}
        </ul>
      )}
      {notes.length > 0 && <p className="explain">Not used: {notes.join("; ")}.</p>}
    </section>
  );
}
