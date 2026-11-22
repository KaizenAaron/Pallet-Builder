import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PalletType } from "../api";
import { useAuth } from "../auth";
import { Alert, Badge, Card } from "../components/ui";

interface ProductStats {
  total: number;
  missing_boxes: number;
}

export default function HomePage() {
  const { me, company } = useAuth();
  const [stats, setStats] = useState<ProductStats | null>(null);
  const [pallets, setPallets] = useState<PalletType[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = company?.role === "owner" || company?.role === "admin";

  useEffect(() => {
    if (!company) return;
    setStats(null);
    setError(null);
    Promise.all([api<ProductStats>("/products?limit=1"), api<PalletType[]>("/pallet-types")])
      .then(([s, p]) => {
        setStats(s);
        setPallets(p);
      })
      .catch((e: Error) => setError(e.message));
  }, [company]);

  if (!company) {
    return (
      <Card title="No company yet">
        <p>You aren't a member of any company.</p>
        <Link className="btn btn-primary" to="/companies/new">
          Create a company
        </Link>
      </Card>
    );
  }

  const def = pallets?.find((p) => p.is_default);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            {company.name} <Badge tone={company.role}>{company.role}</Badge>
          </h1>
          <p className="muted" style={{ margin: 0 }}>
            Welcome, {me?.name || me?.email}.
          </p>
        </div>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {stats && (
        <div className="stats">
          <Card>
            <div className="stat">
              <span className="stat-value">{stats.total.toLocaleString()}</span>
              <span className="stat-label">
                <Link to="/products">Products</Link>
              </span>
            </div>
          </Card>
          <Card>
            <div className="stat">
              <span className="stat-value" style={{ color: stats.missing_boxes ? "var(--warn)" : undefined }}>
                {stats.missing_boxes.toLocaleString()}
              </span>
              <span className="stat-label">Missing box data</span>
            </div>
          </Card>
          <Card>
            <div className="stat">
              <span className="stat-value">{pallets?.length ?? "—"}</span>
              <span className="stat-label">
                <Link to="/pallet-types">Pallet types</Link>
                {def && ` · default ${def.name}`}
              </span>
            </div>
          </Card>
        </div>
      )}

      {stats && stats.total === 0 && (
        <Card title="Get started">
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.9 }}>
            <li>
              {isAdmin ? (
                <>
                  <Link to="/products/import">Import your box index</Link> from the spreadsheet template, or{" "}
                </>
              ) : null}
              <Link to="/products/new">add a product</Link> with its box sizes and weights.
            </li>
            <li>
              Check your <Link to="/pallet-types">pallet types</Link> (a 48 × 40 is set up for you).
            </li>
            <li>
              <Link to="/members">Invite your team.</Link>
            </li>
          </ol>
        </Card>
      )}

      <Alert kind="info">Shipments, pallet estimates and the 3D view arrive in the next phases.</Alert>
    </>
  );
}
