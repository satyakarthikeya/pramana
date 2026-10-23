import { useState } from "react";
import type { ComputedAnalysis, ExactItem, Scalar } from "../api";

const SHAPES: Record<string, string> = {
  cross_section: "one row per record, no time axis",
  time_series: "one row per period",
  panel: "one row per period and group",
  transactions: "many rows per period",
};

const SECTORS: { value: string; label: string }[] = [
  { value: "auto", label: "Detect automatically" },
  { value: "finance", label: "Finance" },
  { value: "health", label: "Health" },
  { value: "general", label: "General" },
];

function cell(key: string, value: Scalar): string {
  if (value === null) return "–";
  if (typeof value === "number") {
    if (key.includes("share")) return `${(value * 100).toFixed(1)}%`;
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function Work({ item }: { item: ExactItem }) {
  const heads = item.table[0] ? Object.keys(item.table[0]) : [];
  return (
    <details className="work">
      <summary>Show the working</summary>
      <dl className="work-list">
        <dt>Formula</dt>
        <dd className="mono">{item.formula}</dd>
        <dt>Columns</dt>
        <dd className="mono">{item.columns.filter(Boolean).join(", ")}</dd>
        {item.filters.length > 0 && (
          <>
            <dt>Rows used</dt>
            <dd className="mono">{item.filters.join("; ")}</dd>
          </>
        )}
        <dt>n</dt>
        <dd className="mono">{item.n_rows.toLocaleString()}</dd>
      </dl>
      {heads.length > 0 && (
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
                    <td key={h}>{cell(h, row[h])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

/** The Exact tier: arithmetic on the table, each figure with its formula, rows and n. */
export function Computed({
  computed,
  onSector,
}: {
  computed: ComputedAnalysis;
  onSector: (sector: string | null) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const done = computed.items.filter((i) => i.status === "ok");
  const skipped = computed.items.filter((i) => i.status === "not_run");
  const { shape, sector } = computed;

  const change = async (value: string) => {
    setBusy(true);
    setProblem(null);
    try {
      await onSector(value === "auto" ? null : value);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "Could not change the sector.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel computed" aria-label="What the data says">
      <div className="computed-head">
        <div>
          <span className="label">What the data says · computed</span>
          <h3 style={{ marginTop: 4 }}>
            {done.length} figure{done.length === 1 ? "" : "s"} computed from this table
          </h3>
        </div>
        <label className="sector-pick">
          <span className="label">Read as</span>
          <select
            value="current"
            disabled={busy}
            onChange={(e) => change(e.target.value)}
            aria-label={`Sector, currently ${sector.label}`}
          >
            <option value="current" disabled hidden>
              {sector.label}
            </option>
            {SECTORS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="chips" style={{ marginTop: 12 }}>
        <span className="chip" title={sector.reasons.join("; ")}>
          sector: {sector.label.toLowerCase()}
        </span>
        <span className="chip" title={shape.reasons.join("; ")}>
          shape: {shape.shape.replace(/_/g, " ")}
        </span>
        {shape.time_column && (
          <span className="chip">
            time: {shape.time_column} · {shape.n_periods} {shape.period}s
          </span>
        )}
        {shape.entity_column && <span className="chip">group: {shape.entity_column}</span>}
      </div>
      <p className="explain" style={{ marginTop: 12 }}>
        Read as {SHAPES[shape.shape]}. {computed.scope_note} These are exact calculations, not tested
        findings: nothing here is marked verified.
      </p>
      {problem && (
        <p className="dz-error" role="alert" style={{ marginTop: 12 }}>
          {problem}
        </p>
      )}
      <ol className="exact-list">
        {done.map((item) => (
          <li key={item.id} className="exact-item">
            <div className="exact-top">
              <span className="label">{item.title}</span>
              <span className="exact-badge">EXACT</span>
            </div>
            <p className="exact-sentence">{item.sentence}</p>
            <Work item={item} />
          </li>
        ))}
      </ol>
      {skipped.length > 0 && (
        <ul className="exact-skipped">
          {skipped.map((item) => (
            <li key={item.id}>
              <span className="note-level">NOT RUN</span>
              <span>
                <strong>{item.title}.</strong> {item.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
