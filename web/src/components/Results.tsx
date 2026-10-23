import { useEffect, useRef } from "react";
import type { ClaimDisclosure, ResultRow, RunResults } from "../api";
import { api } from "../api";
import { claimTypeLabel, fmtEffect, fmtInt, fmtP, metricSymbol } from "../format";
import { ClaimChart } from "./Charts";
import { Exploration } from "./Exploration";
import { Arrow, Close, Download } from "./Icons";
import { Badge } from "./Verdict";

/** Insight IDs are built as `<claim_type>-<columns>`; fall back to the chart's kind. */
function typeOf(row: ResultRow): string {
  const prefix = row.insight_id.split("-")[0];
  if (["correlation", "trend", "distribution"].includes(prefix)) return claimTypeLabel(prefix);
  if (row.insight_id.startsWith("group")) return "GROUP DIFFERENCE";
  if (row.chart?.kind === "groups") return "GROUP DIFFERENCE";
  return "CLAIM";
}

function variablesOf(row: ResultRow): string[] {
  const c = row.chart;
  if (!c) return [];
  return c.kind === "scatter" ? [c.x, c.y] : [c.group, c.value];
}

function ClaimCard({
  row,
  selected,
  onOpen,
}: {
  row: ResultRow;
  selected: boolean;
  onOpen: (id: string) => void;
}) {
  const p = row.proof;
  return (
    <article className="claim" data-selected={selected}>
      <div className="claim-top">
        <span className="label">{typeOf(row)}</span>
        <Badge proof={p} />
      </div>
      <p className="claim-sentence">{row.claim}</p>
      <div className="chips">
        {variablesOf(row).map((v) => (
          <span className="chip" key={v}>
            col: {v}
          </span>
        ))}
      </div>
      <div className="stats">
        <div>
          <span className="label">q-value</span>
          <b>{fmtP(p.q_value)}</b>
        </div>
        <div>
          <span className="label">effect {metricSymbol(p.effect_metric)}</span>
          <b>
            {fmtEffect(p.effect_size)}
            {row.effect_strength ? ` (${row.effect_strength})` : ""}
          </b>
        </div>
        <div>
          <span className="label">rows used</span>
          <b>n = {fmtInt(row.complete_rows)}</b>
        </div>
      </div>
      {row.chart && <ClaimChart chart={row.chart} verified inset />}
      <div className="claim-foot">
        <span className="explain">{row.explanation}</span>
        <button type="button" className="btn btn-secondary btn-compact" onClick={() => onOpen(row.insight_id)}>
          Open proof <Arrow />
        </button>
      </div>
    </article>
  );
}

function RejectedRow({
  row,
  selected,
  onOpen,
}: {
  row: ResultRow;
  selected: boolean;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className="rej-row"
      data-selected={selected}
      onClick={() => onOpen(row.insight_id)}
      aria-label={`Open proof for rejected claim: ${row.claim}`}
    >
      <span className="rej-sentence">{row.claim}</span>
      <Badge proof={row.proof} />
      <span className="rej-reason">
        <b>REASON</b>
        {row.explanation ?? "Rejected by the gate."}
        {row.proof.q_value !== null ? ` q = ${fmtP(row.proof.q_value)}.` : ""}
      </span>
    </button>
  );
}

export function ProofDrawer({
  row,
  onClose,
  chat,
}: {
  row: ResultRow;
  onClose: () => void;
  /** Set for a claim asked in chat: it was tested alone and is not corrected for earlier tests. */
  chat?: ClaimDisclosure;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const p = row.proof;
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const verified = p.verdict === "PASS";
  return (
    <aside className="drawer" aria-label="Proof">
      <div className="drawer-head">
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <Badge proof={p} single={Boolean(chat)} />
          <span className="label" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {p.insight_id}
          </span>
        </div>
        <button ref={closeRef} type="button" className="close" onClick={onClose} aria-label="Close proof">
          <Close />
        </button>
      </div>
      <div className="drawer-body">
        <div className="sec">
          <div className="chips" style={{ marginBottom: 12 }}>
            {variablesOf(row).map((v) => (
              <span className="chip" key={v}>
                col: {v}
              </span>
            ))}
            <span className="chip">n={fmtInt(row.complete_rows)}</span>
            {p.test_type && <span className="chip">{p.test_type} test</span>}
            {p.seed !== null && <span className="chip">seed {p.seed}</span>}
            <span className="chip">{chat ? "single test, uncorrected" : "BH FDR"}</span>
          </div>
          <h3>{row.claim}</h3>
          <p className="explain" style={{ marginTop: 8 }}>
            {row.explanation}
          </p>
        </div>

        {chat && (
          <div className="sec">
            <span className="label">How this was tested</span>
            <p className="explain">
              Asked in chat after seeing results, and tested on its own (test {chat.test_number} on
              this dataset: {chat.earlier_chat_tests} earlier in chat, {chat.earlier_run_tests} in
              analysis runs). Its q-value equals its raw p-value and is not corrected for those
              earlier tests, so a chance result is more likely than in an analysis run.
            </p>
          </div>
        )}

        <div className="sec">
          <span className="label">Numbers</span>
          <dl className="kv" style={{ margin: 0 }}>
            <dt>Raw p-value (permutation)</dt>
            <dd>{fmtP(p.p_value)}</dd>
            <dt>{chat ? "q-value (family of 1, equals the raw p)" : "q-value after correction"}</dt>
            <dd>{fmtP(p.q_value)}</dd>
            <dt>Effect size ({metricSymbol(p.effect_metric)})</dt>
            <dd>{fmtEffect(p.effect_size)}</dd>
            <dt>Effect band</dt>
            <dd>{row.effect_strength ?? "n/a"}</dd>
            <dt>{chat ? "Tests it was not corrected for" : "Claims in the correction family"}</dt>
            <dd>
              {chat
                ? fmtInt(chat.earlier_chat_tests + chat.earlier_run_tests)
                : fmtInt(p.n_hypotheses_in_batch)}
            </dd>
            <dt>Permutations</dt>
            <dd>{fmtInt(row.n_permutations)}</dd>
            <dt>Asserted / observed direction</dt>
            <dd>
              {p.asserted_direction ?? "none"} / {p.observed_direction ?? "n/a"}
            </dd>
            <dt>Gate outcome</dt>
            <dd>{p.gate_outcome}</dd>
          </dl>
          {p.failure_reason && (
            <p className="explain" style={{ marginTop: 12 }}>
              Note: {p.failure_reason}
            </p>
          )}
        </div>

        {row.chart && (
          <div className="sec">
            <span className="label">The data</span>
            <ClaimChart chart={row.chart} verified={verified} inset />
          </div>
        )}

        {p.falsification_code && (
          <div className="sec">
            <span className="label">Falsification code that ran</span>
            <pre className="code" tabIndex={0}>
              {p.falsification_code}
            </pre>
            <p className="explain" style={{ marginTop: 8 }}>
              Re-running this code with seed {p.seed ?? "n/a"} on the same data reproduces the
              numbers above.
            </p>
          </div>
        )}

        <div className="sec">
          <details>
            <summary>Raw proof object</summary>
            <pre className="code" tabIndex={0}>
              {JSON.stringify(p, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </aside>
  );
}

export function Results({
  results,
  selected,
  onSelect,
}: {
  results: RunResults;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const all = [...results.verified_insights, ...results.rejected_claims];
  const open = all.find((r) => r.insight_id === selected) ?? null;
  const tested = all.length;
  const run = results.run;
  const sorted = [...results.verified_insights].sort(
    (a, b) => Math.abs(b.proof.effect_size ?? 0) - Math.abs(a.proof.effect_size ?? 0),
  );
  return (
    <>
      <div className="summary" role="group" aria-label="Run summary">
        <div>
          <span className="label">Tested</span>
          <b>{tested}</b>
        </div>
        <div>
          <span className="label">Verified</span>
          <b style={{ color: "var(--accent)" }}>{results.verified_insights.length}</b>
        </div>
        <div>
          <span className="label">Rejected</span>
          <b style={{ color: "var(--reject-ink)" }}>{results.rejected_claims.length}</b>
        </div>
        {results.unverified_candidate_count > 0 && (
          <div>
            <span className="label">Not tested</span>
            <b>{results.unverified_candidate_count}</b>
          </div>
        )}
        <div style={{ marginLeft: "auto", alignContent: "end", display: "flex", gap: 8 }}>
          <a className="btn btn-secondary btn-compact" href={api.exportUrl(run.run_id, "json")} download>
            <Download /> JSON
          </a>
          <a className="btn btn-secondary btn-compact" href={api.exportUrl(run.run_id, "csv")} download>
            <Download /> CSV
          </a>
        </div>
      </div>

      {results.exploration && (
        <div style={{ marginBottom: 32 }}>
          <Exploration summary={results.exploration} />
        </div>
      )}

      <div className="results">
        <div>
          <div className="section-head">
            <h2>Verified findings</h2>
            <span className="label">Ordered by effect size</span>
          </div>
          {sorted.length === 0 ? (
            <div className="empty">
              <h3>No claim survived testing</h3>
              <p>
                {tested} tested, 0 verified, {results.rejected_claims.length} rejected. This is a
                result. Nothing was marked verified, and every reason is below.
              </p>
            </div>
          ) : (
            <div className="stack">
              {sorted.map((row) => (
                <ClaimCard
                  key={row.insight_id}
                  row={row}
                  selected={selected === row.insight_id}
                  onOpen={onSelect}
                />
              ))}
            </div>
          )}

          <div className="section-head">
            <h2>Not a finding ({results.rejected_claims.length})</h2>
            <span className="label">Rejected, with the reason</span>
          </div>
          {results.rejected_claims.length === 0 ? (
            <div className="empty">
              <p>No claim was rejected in this run.</p>
            </div>
          ) : (
            <div className="stack" style={{ gap: 8 }}>
              {results.rejected_claims.map((row) => (
                <RejectedRow
                  key={row.insight_id}
                  row={row}
                  selected={selected === row.insight_id}
                  onOpen={onSelect}
                />
              ))}
            </div>
          )}
        </div>

      </div>

      {open && <ProofDrawer row={open} onClose={() => onSelect(null)} />}
    </>
  );
}
