import { useEffect, useRef, useState, type ReactNode } from "react";
import type { RunStatus } from "../api";
import { fmtInt } from "../format";
import { useAuth } from "../auth";
import { useWorkspace } from "../store";
import { Check, Close, Cross, Logo, Upload } from "./Icons";

function StatusGlyph({ status }: { status: RunStatus | null }) {
  if (status === "completed" || status === "degraded") {
    return <Check className="rail-glyph" style={{ color: "var(--accent)" }} aria-label="analysed" />;
  }
  if (status === "failed") {
    return <Cross className="rail-glyph" style={{ color: "var(--reject)" }} aria-label="failed" />;
  }
  if (status === "running" || status === "pending") {
    return (
      <svg className="rail-glyph" viewBox="0 0 20 20" role="img" aria-label="analysing">
        <circle cx="10" cy="10" r="7" fill="none" stroke="#D9D1C4" strokeWidth="2" />
        <path className="spin" d="M10 3a7 7 0 0 1 7 7" fill="none" stroke="#0F5C58" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  return <span className="rail-glyph" aria-hidden="true" />;
}

export function useFilePicker(onFile: (file: File) => void) {
  const input = useRef<HTMLInputElement>(null);
  const element = (
    <input
      ref={input}
      type="file"
      accept=".csv,.xlsx"
      hidden
      onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onFile(file);
      }}
    />
  );
  return { element, open: () => input.current?.click() };
}

export function AppShell({
  active,
  children,
}: {
  active: { dataset?: string; memory?: boolean };
  children: ReactNode;
}) {
  const { datasets, stage, starting, notice, dismiss } = useWorkspace();
  const { user, signOut } = useAuth();
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    let depth = 0;
    const hasFiles = (event: DragEvent) => event.dataTransfer?.types.includes("Files") ?? false;
    const enter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth += 1;
      setDragging(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const over = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault();
    };
    const drop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragging(false);
      const file = event.dataTransfer?.files[0];
      // while a table is uploading, a drop would replace it mid-flight; ignore it
      if (file && !starting) stage(file);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [stage, starting]);

  return (
    <div className="app">
      <a className="skip" href="#content">
        Skip to content
      </a>
      <aside className="rail" aria-label="Workspace">
        <a className="wordmark" href="#/" aria-label="PRAMANA home">
          <Logo /> PRAMANA
        </a>
        <a className="btn btn-primary rail-new" href="#/" onClick={() => stage(null)}>
          <Upload /> New analysis
        </a>

        <nav className="rail-section" aria-label="Datasets">
          <span className="label">Datasets</span>
          {datasets === null && <p className="rail-empty">Loading…</p>}
          {datasets?.length === 0 && <p className="rail-empty">None yet. Upload a CSV or XLSX.</p>}
          <ul className="ds-list">
            {datasets?.map((d) => (
              <li key={d.dataset_id}>
                <a
                  className="ds-item"
                  href={`#/d/${d.dataset_id}`}
                  aria-current={active.dataset === d.dataset_id ? "page" : undefined}
                >
                  <span className="ds-name">{d.name}</span>
                  <StatusGlyph status={d.last_status} />
                  <span className="ds-meta">
                    {fmtInt(d.rows)} × {fmtInt(d.columns)}
                    {d.run_count > 0 ? ` · ${d.run_count} run${d.run_count === 1 ? "" : "s"}` : ""}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <nav className="rail-foot" aria-label="Library">
          <a className="ds-item" href="#/memory" aria-current={active.memory ? "page" : undefined}>
            <span className="ds-name">Verified memory</span>
            <span className="ds-meta">Findings that passed the gate</span>
          </a>
        </nav>

        <div className="rail-user">
          <span className="rail-email" title={user?.email}>
            {user?.email}
          </span>
          <button type="button" className="btn btn-ghost btn-compact" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main id="content" className="content">
        {children}
      </main>

      {dragging && (
        <div className="drop-overlay" role="presentation">
          <p>Drop a CSV or XLSX to start a new analysis</p>
        </div>
      )}
      {notice && (
        <div className="toast" role="alert">
          <span>{notice}</span>
          <button type="button" className="toast-close" onClick={dismiss} aria-label="Dismiss">
            <Close />
          </button>
        </div>
      )}
    </div>
  );
}
