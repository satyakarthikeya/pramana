import { useWorkspace } from "../store";
import { fmtInt } from "../format";
import { AppShell, useFilePicker } from "./AppShell";
import { Upload } from "./Icons";

export function Home() {
  const { datasets, upload, uploading } = useWorkspace();
  const picker = useFilePicker(upload);
  return (
    <AppShell active={{}}>
      <div className="page-head">
        <div>
          <h1 className="page-title">Analyse a table</h1>
          <p className="page-sub">
            Upload a CSV or XLSX. PRAMANA reads it, then you decide when to analyse it. Only claims
            that pass testing are called findings.
          </p>
        </div>
      </div>

      <section className="upload-card" aria-label="Upload a dataset">
        <div>
          <h2>Add a dataset</h2>
          <p className="dz-meta">CSV, XLSX · first sheet only · one row per record · drop it anywhere on this page</p>
        </div>
        <div className="dz-actions">
          <button type="button" className="btn btn-primary" disabled={uploading} onClick={picker.open}>
            <Upload /> {uploading ? "Reading…" : "Choose file"}
          </button>
          {picker.element}
        </div>
      </section>

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
    </AppShell>
  );
}
