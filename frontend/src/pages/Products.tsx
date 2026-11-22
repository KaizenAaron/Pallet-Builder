import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiDownload, type ProductSummary } from "../api";
import { useAuth } from "../auth";
import { MOBILE, useMediaQuery } from "../hooks";
import { Alert, Badge, Button, Card, Input, useAsync } from "../components/ui";

interface ListResponse {
  total: number;
  missing_boxes: number;
  items: ProductSummary[];
}

export default function ProductsPage() {
  const { company } = useAuth();
  const navigate = useNavigate();
  const mobile = useMediaQuery(MOBILE);
  const [q, setQ] = useState("");
  const [missingOnly, setMissingOnly] = useState(false);
  const [data, setData] = useState<ListResponse | null>(null);
  const { error, setError, run } = useAsync();
  const isAdmin = company?.role === "owner" || company?.role === "admin";

  useEffect(() => {
    if (!company) return;
    const t = setTimeout(() => {
      const params = new URLSearchParams({ q, missing_boxes: String(missingOnly), limit: "500" });
      api<ListResponse>(`/products?${params}`)
        .then(setData)
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [company, q, missingOnly, setError]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Products & boxes</h1>
          <p className="muted" style={{ margin: 0 }}>
            The box index: which boxes each product ships in. One unit ships in all of its boxes.
          </p>
        </div>
        <span className="spacer" />
        <div className="row">
          {isAdmin && (
            <Link className="btn" to="/products/import">
              Import spreadsheet
            </Link>
          )}
          <Button onClick={() => run(() => apiDownload("/products/export.xlsx", "box-index.xlsx"))}>Export</Button>
          <Link className="btn btn-primary" to="/products/new">
            + Add product
          </Link>
        </div>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {data && data.missing_boxes > 0 && !missingOnly && (
        <Alert kind="warn">
          {data.missing_boxes} product{data.missing_boxes === 1 ? " has" : "s have"} no box data yet and will be left out of
          estimates.{" "}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setMissingOnly(true);
            }}
          >
            Show them
          </a>
        </Alert>
      )}
      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <div style={{ flex: "1 1 260px", maxWidth: 420 }}>
            <Input placeholder="Search SKU or name…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search products" />
          </div>
          <label className="row small" style={{ gap: 6 }}>
            <input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} />
            Missing box data only
          </label>
          <span className="spacer" />
          {data && <span className="muted small">{data.total.toLocaleString()} products</span>}
        </div>
        {!data ? (
          <p className="muted">Loading…</p>
        ) : data.items.length === 0 ? (
          <div style={{ padding: "24px 0", textAlign: "center" }}>
            <p className="muted">{q || missingOnly ? "No products match." : "No products yet."}</p>
            {!q && !missingOnly && (
              <div className="row" style={{ justifyContent: "center" }}>
                {isAdmin && (
                  <Link className="btn" to="/products/import">
                    Import from a spreadsheet
                  </Link>
                )}
                <Link className="btn btn-primary" to="/products/new">
                  Add a product
                </Link>
              </div>
            )}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table table-hover">
              <thead>
                <tr>
                  <th>SKU</th>
                  {!mobile && <th>Name</th>}
                  <th className="num">Boxes</th>
                  <th className="num">Weight / unit</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id} onClick={() => navigate(`/products/${p.id}`)} style={{ cursor: "pointer" }}>
                    <td>
                      <Link to={`/products/${p.id}`} onClick={(e) => e.stopPropagation()}>
                        <strong>{p.sku}</strong>
                      </Link>
                      {mobile && <div className="muted small">{p.name}</div>}
                    </td>
                    {!mobile && <td>{p.name}</td>}
                    <td className="num">{p.box_count === 0 ? <Badge tone="pending">none</Badge> : p.box_count}</td>
                    <td className="num">{p.box_count ? `${fmt(p.unit_weight)} lb` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.total > data.items.length && (
              <p className="small muted" style={{ marginTop: 10 }}>
                Showing the first {data.items.length} — search to narrow down.
              </p>
            )}
          </div>
        )}
      </Card>
    </>
  );
}

export function fmt(n: number, digits = 2): string {
  return Number(n.toFixed(digits)).toLocaleString();
}
