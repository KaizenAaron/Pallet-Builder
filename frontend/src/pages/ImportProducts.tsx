import { useState } from "react";
import { Link } from "react-router-dom";
import { apiDownload, apiUpload } from "../api";
import { Alert, Button, Card, useAsync } from "../components/ui";

interface ImportResult {
  dry_run: boolean;
  rows_read: number;
  products_created: number;
  products_updated: number;
  boxes_created: number;
  boxes_updated: number;
  unchanged_rows: number;
  errors: { row: number; sku?: string; message: string }[];
  ignored_columns: string[];
}

export default function ImportProductsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const { busy, error, setError, run } = useAsync();

  function choose(f: File | null) {
    setFile(f);
    setPreview(null);
    setDone(null);
    setError(null);
    if (f) void run(async () => setPreview(await apiUpload<ImportResult>("/products/import?dry_run=true", f)));
  }

  const changes = (r: ImportResult) => r.products_created + r.products_updated + r.boxes_created + r.boxes_updated;

  return (
    <div style={{ maxWidth: 860 }}>
      <div className="page-head">
        <div>
          <p className="small" style={{ margin: 0 }}>
            <Link to="/products">← Products</Link>
          </p>
          <h1>Import box index</h1>
        </div>
      </div>

      <Card title="1. Get the template">
        <p className="muted">
          One row per box: SKU, Box #, L × W × H (in), weight (lb) and the stacking rules. The template's Instructions
          sheet explains each column with an example. Re-importing updates matching boxes and adds new ones —{" "}
          <strong>an import never deletes anything</strong>.
        </p>
        <div className="row">
          <Button onClick={() => run(() => apiDownload("/products/import-template.xlsx", "box-template.xlsx"))}>
            Download Excel template
          </Button>
          <Button onClick={() => run(() => apiDownload("/products/import-template.csv", "box-template.csv"))}>
            CSV template
          </Button>
          <Button variant="ghost" onClick={() => run(() => apiDownload("/products/export.xlsx", "box-index.xlsx"))}>
            Export current box index
          </Button>
        </div>
      </Card>

      <Card title="2. Upload your file">
        <div
          className={`dropzone ${drag ? "drag" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            choose(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <p style={{ marginBottom: 10 }}>{file ? <strong>{file.name}</strong> : "Drop an .xlsx or .csv file here"}</p>
          <label className="btn">
            {file ? "Choose a different file" : "Choose file"}
            <input
              type="file"
              accept=".xlsx,.csv"
              hidden
              onChange={(e) => {
                choose(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        {busy && <p className="muted" style={{ marginTop: 12 }}>Reading file…</p>}
      </Card>

      {error && <Alert kind="error">{error}</Alert>}

      {(done ?? preview) && (
        <Card title={done ? "Imported" : "3. Check and import"}>
          <Summary r={(done ?? preview)!} />
          {!done && preview && (
            <div className="row" style={{ marginTop: 14 }}>
              <Button
                variant="primary"
                disabled={busy || changes(preview) === 0}
                onClick={() => run(async () => setDone(await apiUpload<ImportResult>("/products/import?dry_run=false", file!)))}
              >
                {changes(preview) === 0
                  ? "Nothing to import"
                  : `Import ${preview.errors.length ? "the valid rows" : "now"}`}
              </Button>
              {preview.errors.length > 0 && (
                <span className="muted small">Rows with errors are skipped. Fix them and import again any time.</span>
              )}
            </div>
          )}
          {done && (
            <div className="row" style={{ marginTop: 14 }}>
              <Link className="btn btn-primary" to="/products">
                View products
              </Link>
              <Button onClick={() => choose(null)}>Import another file</Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function Summary({ r }: { r: ImportResult }) {
  const verb = r.dry_run ? "will be" : "were";
  return (
    <>
      <div className="stats">
        <Stat label={`Products ${verb} added`} value={r.products_created} />
        <Stat label={`Products ${verb} renamed`} value={r.products_updated} />
        <Stat label={`Boxes ${verb} added`} value={r.boxes_created} />
        <Stat label={`Boxes ${verb} updated`} value={r.boxes_updated} />
      </div>
      <p className="small muted">
        {r.rows_read} rows read · {r.unchanged_rows} already up to date · {r.errors.length} with errors
      </p>
      {r.ignored_columns.length > 0 && (
        <Alert kind="info">Ignored columns (not recognized): {r.ignored_columns.join(", ")}</Alert>
      )}
      {r.errors.length > 0 && (
        <>
          <Alert kind="warn">
            {r.errors.length} row{r.errors.length === 1 ? "" : "s"} can't be imported:
          </Alert>
          <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th className="num">Row</th>
                  <th>SKU</th>
                  <th>Problem</th>
                </tr>
              </thead>
              <tbody>
                {r.errors.map((e, i) => (
                  <tr key={i}>
                    <td className="num">{e.row}</td>
                    <td>{e.sku ?? "—"}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <span className="stat-value">{value.toLocaleString()}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
