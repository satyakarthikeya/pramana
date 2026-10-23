import type { ColumnBrief, ColumnNote, DataBrief } from "../api";

function Note({ note }: { note: ColumnNote }) {
  const evidence = Object.entries(note.evidence);
  return (
    <li className="brief-note">
      <span className="note-level" data-level={note.level}>
        {note.level === "check" ? "CHECK" : "NOTE"}
      </span>
      <div>
        <p>{note.message}</p>
        {note.suggestion && <p className="brief-suggest">{note.suggestion}</p>}
        {evidence.length > 0 && (
          <div className="chips" style={{ marginTop: 6 }}>
            {evidence.map(([key, value]) => (
              <span className="chip" key={key}>
                {key.replace(/_/g, " ")}: {String(value)}
              </span>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

function Column({ column }: { column: ColumnBrief }) {
  return (
    <article className="brief-col">
      <div className="brief-head">
        <span className="mono brief-name">{column.name}</span>
        <span className="label">{column.role.replace(/_/g, " ")}</span>
      </div>
      {(column.label || column.coding) && (
        <p className="brief-label">
          {column.label}
          {column.unit ? ` (${column.unit})` : ""}
        </p>
      )}
      {column.coding && (
        <div className="chips" style={{ marginBottom: 8 }}>
          {Object.entries(column.coding).map(([code, meaning]) => (
            <span className="chip" key={code}>
              {code} = {meaning}
            </span>
          ))}
        </div>
      )}
      {column.notes.length > 0 && (
        <ul className="brief-notes">
          {column.notes.map((note, i) => (
            <Note key={`${note.kind}-${i}`} note={note} />
          ))}
        </ul>
      )}
    </article>
  );
}

/** What the Data Reader found: counted by code, and things worth checking before trusting results. */
export function Brief({ brief }: { brief: DataBrief }) {
  const flagged = brief.columns.filter((c) => c.notes.length > 0 || c.label);
  const plain = brief.columns.filter((c) => c.notes.length === 0 && !c.label);
  return (
    <section className="panel" aria-label="Data reader findings">
      <span className="label">Data reader</span>
      <h3 style={{ marginTop: 4 }}>{brief.headline}</h3>
      <p className="explain" style={{ marginTop: 6 }}>
        Counted from your table by code. Nothing here changes your data or decides a result.
        {brief.recognised > 0 &&
          ` ${brief.recognised} column${brief.recognised === 1 ? "" : "s"} follow standard NHANES variable names, so their labels, units and codes are filled in. Confirm them against the documentation for your survey cycle.`}
      </p>
      <div className="brief-list">
        {flagged.map((c) => (
          <Column key={c.name} column={c} />
        ))}
      </div>
      {plain.length > 0 && (
        <p className="explain" style={{ marginTop: 12 }}>
          Nothing to note for: {plain.map((c) => c.name).join(", ")}.
        </p>
      )}
    </section>
  );
}
