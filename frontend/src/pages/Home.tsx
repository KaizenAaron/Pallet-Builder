import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Badge, Card } from "../components/ui";

interface PalletType {
  id: number;
  name: string;
  length: number;
  width: number;
  deck_height: number;
  tare_weight: number;
  max_total_height: number;
  max_gross_weight: number;
  max_overhang: number;
  is_default: boolean;
}

export default function HomePage() {
  const { me, company } = useAuth();
  const [pallets, setPallets] = useState<PalletType[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) return;
    setPallets(null);
    api<PalletType[]>("/pallet-types")
      .then(setPallets)
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

      <Alert kind="info">
        Shipments, the box index and the 3D pallet view arrive in the next phases. For now you can manage your company
        and invite your team.
      </Alert>

      <Card title="Pallet types">
        {error && <Alert kind="error">{error}</Alert>}
        {!pallets ? (
          !error && <p className="muted">Loading…</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="num">Footprint (in)</th>
                  <th className="num">Deck (in)</th>
                  <th className="num">Tare (lb)</th>
                  <th className="num">Max height (in)</th>
                  <th className="num">Max gross (lb)</th>
                  <th className="num">Overhang (in)</th>
                </tr>
              </thead>
              <tbody>
                {pallets.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {p.name} {p.is_default && <Badge>default</Badge>}
                    </td>
                    <td className="num">
                      {p.length} × {p.width}
                    </td>
                    <td className="num">{p.deck_height}</td>
                    <td className="num">{p.tare_weight}</td>
                    <td className="num">{p.max_total_height}</td>
                    <td className="num">{p.max_gross_weight.toLocaleString()}</td>
                    <td className="num">{p.max_overhang}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
          Editing pallet types comes with the box index (phase 4).
        </p>
      </Card>
    </>
  );
}
