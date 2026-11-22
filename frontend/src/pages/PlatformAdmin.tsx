import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Badge, Button, Card, useAsync } from "../components/ui";

interface CompanyRow {
  id: number;
  name: string;
  plan: string;
  members: number;
  created_at: string;
  suspended: boolean;
}

export default function PlatformAdminPage() {
  const [rows, setRows] = useState<CompanyRow[]>([]);
  const { error, setError, run } = useAsync();
  const load = useCallback(() => api<CompanyRow[]>("/admin/companies", { company: false }).then(setRows), []);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  return (
    <>
      <div className="page-head">
        <h1>Platform</h1>
        <span className="muted">All companies on this Pallet Builder server.</span>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <Card title={`Companies (${rows.length})`}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Plan</th>
                <th className="num">Members</th>
                <th>Created</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.plan}</td>
                  <td className="num">{c.members}</td>
                  <td className="small">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td>{c.suspended ? <Badge tone="expired">suspended</Badge> : <Badge>active</Badge>}</td>
                  <td className="num">
                    <Button
                      size="sm"
                      variant={c.suspended ? "default" : "danger"}
                      onClick={() =>
                        run(async () => {
                          await api(`/admin/companies/${c.id}/${c.suspended ? "unsuspend" : "suspend"}`, {
                            method: "POST",
                            company: false,
                          });
                          await load();
                        })
                      }
                    >
                      {c.suspended ? "Reactivate" : "Suspend"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
