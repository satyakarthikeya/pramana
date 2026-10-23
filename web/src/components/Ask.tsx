import { useEffect, useRef, useState } from "react";
import {
  api,
  type ChatAnswer,
  type ChatExchange,
  type ChatLedger,
  type DatasetView,
  type Evidence,
  type SystemStatus,
} from "../api";
import { fmtInt, fmtP } from "../format";
import { Arrow, Dash } from "./Icons";
import { ProofDrawer } from "./Results";
import { Badge } from "./Verdict";

const MAX_QUESTION = 1000;

/** What kind of answer this is, always stated, never left for the reader to infer. */
function KindLabel({ answer }: { answer: ChatAnswer }) {
  if (answer.tested) return <Badge proof={answer.tested.row.proof} single />;
  switch (answer.kind) {
    case "exploratory":
      return (
        <span className="badge badge-nt" aria-label="Exploratory, not verified: no significance test was run">
          <Dash /> EXPLORATORY, NOT VERIFIED
        </span>
      );
    case "descriptive":
      return <span className="chip">DESCRIPTIVE · COMPUTED FROM THE TABLE</span>;
    case "not_tested":
      return (
        <span className="badge badge-nt" aria-label="Not tested: nothing was marked verified">
          <Dash /> NOT TESTED
        </span>
      );
    default:
      return <span className="chip">NO ANSWER</span>;
  }
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? fmtInt(value) : String(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** The tool result behind an answer: scalars as a list, lists of records as a table. */
function EvidenceView({ item }: { item: Evidence }) {
  const out = item.output ?? {};
  const scalars = Object.entries(out).filter(([, v]) => typeof v !== "object" || v === null);
  const lists = Object.entries(out).filter(
    ([, v]) => Array.isArray(v) && v.length > 0 && typeof v[0] === "object" && v[0] !== null,
  ) as [string, Record<string, unknown>[]][];
  return (
    <div className="evidence-item">
      <div className="chips">
        <span className="chip">{item.entry_id}</span>
        <span className="chip">{item.tool}</span>
        {Object.entries(item.args).map(([k, v]) => (
          <span className="chip" key={k}>
            {k}: {String(v)}
          </span>
        ))}
      </div>
      {scalars.length > 0 && (
        <dl className="kv" style={{ margin: "12px 0 0" }}>
          {scalars.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{cell(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {lists.map(([name, rows]) => {
        const heads = Object.keys(rows[0]);
        return (
          <div key={name} style={{ overflowX: "auto", marginTop: 12 }}>
            <table className="data-table">
              <caption className="label" style={{ textAlign: "left" }}>
                {name.replace(/_/g, " ")}
              </caption>
              <thead>
                <tr>
                  {heads.map((h) => (
                    <th key={h}>{h.replace(/_/g, " ")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    {heads.map((h) => (
                      <td key={h}>{cell(r[h])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

function Exchange({ item, onOpen }: { item: ChatExchange; onOpen: (id: string) => void }) {
  const a = item.answer;
  const d = a.tested?.disclosure;
  const w = a.work;
  return (
    <li className="chat-turn">
      <p className="chat-q">
        <span className="label">You asked</span>
        {item.question}
      </p>
      <article className="chat-a" aria-label="Answer">
        <div className="claim-top">
          <KindLabel answer={a} />
          <span className="label">{new Date(item.created_at).toLocaleString()}</span>
        </div>
        <p className="chat-text">{a.text}</p>
        {d && (
          <div className="chips">
            <span className="chip">test {d.test_number} on this dataset</span>
            <span className="chip">tested alone</span>
            <span className="chip">asked after seeing results</span>
            <span className="chip">not corrected for earlier tests</span>
          </div>
        )}
        {a.tested && (
          <div>
            <button
              type="button"
              className="btn btn-secondary btn-compact"
              onClick={() => onOpen(item.message_id)}
            >
              Open proof <Arrow />
            </button>
          </div>
        )}
        {a.notes.map((n) => (
          <p className="explain" key={n}>
            {n}
          </p>
        ))}
        {a.evidence.length > 0 && (
          <details className="evidence">
            <summary>
              Where these numbers came from ({a.evidence.length} tool{" "}
              {a.evidence.length === 1 ? "result" : "results"})
            </summary>
            {a.evidence.map((e) => (
              <EvidenceView item={e} key={e.entry_id} />
            ))}
          </details>
        )}
        <p className="chat-work mono">
          {w.turns} model {w.turns === 1 ? "call" : "calls"} · {w.tool_calls} tool{" "}
          {w.tool_calls === 1 ? "step" : "steps"} · {fmtInt(w.input_tokens + w.output_tokens)} tokens
        </p>
      </article>
    </li>
  );
}

function Ledger({ ledger }: { ledger: ChatLedger }) {
  return (
    <section className="panel" aria-label="Testing ledger">
      <span className="label">Testing ledger</span>
      <h3 style={{ marginTop: 4 }}>
        <span className="mono">{ledger.chat_tests}</span> claims tested in chat,{" "}
        <span className="mono">{ledger.run_tests}</span> in analysis runs
      </h3>
      <p className="explain" style={{ marginTop: 8 }}>
        Each claim asked here is tested on its own and is not corrected for the others, so read its
        q-value next to this count. Chat may test up to {ledger.limit} claims on this dataset.
      </p>
      {ledger.records.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>All {ledger.records.length} chat tests</summary>
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Claim</th>
                  <th>Result</th>
                  <th>q</th>
                  <th>n</th>
                </tr>
              </thead>
              <tbody>
                {ledger.records.map((r) => (
                  <tr key={r.message_id}>
                    <td>{r.test_number}</td>
                    <td>{r.claim}</td>
                    <td>{r.label.replace("_", " ")}</td>
                    <td>{fmtP(r.q_value)}</td>
                    <td>{fmtInt(r.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

export function Ask({ dataset, system }: { dataset: DatasetView; system: SystemStatus | null }) {
  const id = dataset.dataset_id;
  const [history, setHistory] = useState<ChatExchange[] | null>(null);
  const [ledger, setLedger] = useState<ChatLedger | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  // Answers for another dataset must never land here: ignore anything that arrives late.
  useEffect(() => {
    let current = true;
    setHistory(null);
    setLedger(null);
    setOpen(null);
    Promise.all([api.chat(id), api.chatLedger(id)]).then(
      ([h, l]) => {
        if (!current) return;
        setHistory(h);
        setLedger(l);
        setLoadError(null);
      },
      (e: unknown) => {
        if (current) setLoadError(e instanceof Error ? e.message : "Could not load the conversation.");
      },
    );
    return () => {
      current = false;
    };
  }, [id]);

  const submit = async () => {
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setAskError(null);
    try {
      const exchange = await api.ask(id, text);
      setHistory((h) => [...(h ?? []), exchange]);
      setQuestion("");
      api.chatLedger(id).then(setLedger, () => undefined);
      setTimeout(() => end.current?.scrollIntoView({ block: "nearest" }), 0);
    } catch (e) {
      setAskError(e instanceof Error ? e.message : "The question could not be answered.");
    } finally {
      setAsking(false);
    }
  };

  const tested = history?.find((h) => h.message_id === open)?.answer.tested ?? null;
  const blocked = system !== null && !system.chat_ready;

  return (
    <div className="chat">
      <div className="chat-main">
        {loadError && (
          <div className="error-card" role="alert">
            <h3>The conversation could not be loaded</h3>
            <p>{loadError}</p>
          </div>
        )}

        {history && history.length === 0 && !loadError && (
          <div className="empty">
            <h3>Ask about {dataset.name}</h3>
            <p>
              Counts, averages, group summaries and missing values are computed from the table and
              labelled descriptive. A question like "is age associated with glucose?" is sent to the same
              permutation test and gate as an analysis run, and the answer says Verified or
              Rejected with the proof. Anything that was not tested says so.
            </p>
          </div>
        )}

        {history && history.length > 0 && (
          <ol className="chat-list" aria-label="Conversation">
            {history.map((item) => (
              <Exchange item={item} key={item.message_id} onOpen={setOpen} />
            ))}
          </ol>
        )}
        <div ref={end} />

        {blocked ? (
          <div className="note-card" role="status">
            <h3>Chat is unavailable</h3>
            <p>
              It needs a model, and {system?.chat_blockers.join("; ")}. Add them to the server's{" "}
              <span className="mono">.env</span> and restart. Nothing is answered without them.
            </p>
          </div>
        ) : (
          <form
            className="chat-form"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label className="question">
              <span className="label">Ask a question about this table</span>
              <input
                type="text"
                value={question}
                maxLength={MAX_QUESTION}
                disabled={asking}
                placeholder="For example: what is the average age, or is age associated with glucose?"
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={asking || !question.trim()}>
              {asking ? "Working…" : "Ask"} <Arrow />
            </button>
          </form>
        )}
        {asking && (
          <p className="explain" role="status">
            The assistant is looking at the table. A question that needs a test can take up to a
            minute.
          </p>
        )}
        {askError && (
          <p className="dz-error" role="alert">
            {askError} Nothing was marked verified.
          </p>
        )}
      </div>

      <aside className="chat-side">{ledger && <Ledger ledger={ledger} />}</aside>

      {tested && (
        <ProofDrawer row={tested.row} chat={tested.disclosure} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
