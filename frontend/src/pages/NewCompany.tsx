import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, Field, Input, useAsync } from "../components/ui";

export default function NewCompanyPage() {
  const { refresh, switchCompany } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const { busy, error, run } = useAsync();
  return (
    <div style={{ maxWidth: 520 }}>
      <div className="page-head">
        <h1>New company</h1>
      </div>
      <Card>
        <p className="muted">You'll be its owner. Each company has its own products, shipments and team.</p>
        {error && <Alert kind="error">{error}</Alert>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const c = await api<{ id: number }>("/companies", { body: { name }, company: false });
              await refresh();
              switchCompany(c.id);
              navigate("/");
            });
          }}
        >
          <Field label="Company name" htmlFor="name">
            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Button variant="primary" disabled={busy}>
            Create company
          </Button>
        </form>
      </Card>
    </div>
  );
}
