import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ShipmentSummary } from "../api";
import { useAuth } from "../auth";
import { MOBILE, useMediaQuery } from "../hooks";
import { Alert, Badge, Card, Input } from "../components/ui";
import { useFormat } from "../units";

export function StatusBadge({ s }: { s: Pick<ShipmentSummary, "status" | "stale"> }) {
  if (s.status === "draft") return <Badge>draft</Badge>;
  if (s.stale) return <Badge tone="pending">out of date</Badge>;
  return <Badge tone="ok">calculated</Badge>;
}

export function ShipmentTable({ rows }: { rows: ShipmentSummary[] }) {
  const navigate = useNavigate();
  const f = useFormat();
  const mobile = useMediaQuery(MOBILE);
  return (
    <div className="table-wrap">
      <table className="table table-hover">
        <thead>
          <tr>
            <th>Shipment</th>
            {!mobile && <th>Customer</th>}
            {!mobile && <th>Reference</th>}
            {!mobile && <th>Ship date</th>}
            <th className="num">Pallets</th>
            <th className="num">Gross</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/shipments/${s.id}`)}>
              <td>
                <Link to={`/shipments/${s.id}`} onClick={(e) => e.stopPropagation()}>
                  <strong>{s.number}</strong>
                </Link>
                {mobile && (s.customer || s.reference) && (
                  <div className="muted small">{[s.customer, s.reference].filter(Boolean).join(" · ")}</div>
                )}
              </td>
              {!mobile && <td>{s.customer || <span className="muted">—</span>}</td>}
              {!mobile && <td>{s.reference || <span className="muted">—</span>}</td>}
              {!mobile && <td>{s.ship_date ? new Date(s.ship_date + "T00:00").toLocaleDateString() : <span className="muted">—</span>}</td>}
              <td className="num">{s.status === "calculated" ? s.pallet_count : "—"}</td>
              <td className="num">{s.status === "calculated" ? f.weight(s.total_gross_weight, 0) : "—"}</td>
              <td>
                <StatusBadge s={s} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ShipmentsPage() {
  const { company } = useAuth();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<ShipmentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) return;
    const t = setTimeout(() => {
      api<ShipmentSummary[]>(`/shipments?${new URLSearchParams({ q })}`)
        .then(setRows)
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [company, q]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Shipments</h1>
          <p className="muted" style={{ margin: 0 }}>
            Pallet estimates: how many pallets an order needs, their size and weight.
          </p>
        </div>
        <span className="spacer" />
        <Link className="btn btn-primary" to="/shipments/new">
          + New shipment
        </Link>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <div style={{ flex: "1 1 260px", maxWidth: 420 }}>
            <Input placeholder="Search number, customer or reference…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search shipments" />
          </div>
        </div>
        {!rows ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <div style={{ padding: "24px 0", textAlign: "center" }}>
            <p className="muted">{q ? "No shipments match." : "No shipments yet."}</p>
            {!q && (
              <Link className="btn btn-primary" to="/shipments/new">
                Create your first shipment
              </Link>
            )}
          </div>
        ) : (
          <ShipmentTable rows={rows} />
        )}
      </Card>
    </>
  );
}
