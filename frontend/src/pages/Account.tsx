import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Me } from "../api";
import { useAuth } from "../auth";
import { Alert, Button, Card, Field, Input, useAsync } from "../components/ui";

export default function AccountPage() {
  const { me, setMe } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(me?.name ?? "");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const profile = useAsync();
  const password = useAsync();
  const everywhere = useAsync();

  return (
    <div style={{ maxWidth: 560 }}>
      <div className="page-head">
        <h1>Account</h1>
      </div>
      {msg && <Alert kind="ok">{msg}</Alert>}
      <Card title="Profile">
        {profile.error && <Alert kind="error">{profile.error}</Alert>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void profile.run(async () => {
              setMe(await api<Me>("/auth/me", { method: "PUT", body: { name }, company: false }));
              setMsg("Profile saved.");
            });
          }}
        >
          <Field label="Email">
            <Input value={me?.email ?? ""} disabled />
          </Field>
          <Field label="Name" htmlFor="name">
            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Button variant="primary" disabled={profile.busy}>
            Save
          </Button>
        </form>
      </Card>
      <Card title="Password">
        {password.error && <Alert kind="error">{password.error}</Alert>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void password.run(async () => {
              await api("/auth/me/password", { method: "PUT", body: pw, company: false });
              setPw({ current_password: "", new_password: "" });
              setMsg("Password changed. Other devices have been signed out.");
            });
          }}
        >
          <Field label="Current password" htmlFor="cur">
            <Input id="cur" type="password" autoComplete="current-password" required value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
          </Field>
          <Field label="New password" htmlFor="new" hint="At least 10 characters.">
            <Input id="new" type="password" autoComplete="new-password" minLength={10} required value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
          </Field>
          <Button variant="primary" disabled={password.busy}>
            Change password
          </Button>
        </form>
      </Card>
      <Card title="Sessions">
        <p className="muted">Signed in on a shared or lost device? Sign out of every session, including this one.</p>
        <Button
          variant="danger"
          disabled={everywhere.busy}
          onClick={() =>
            everywhere.run(async () => {
              await api("/auth/logout-all", { method: "POST", company: false });
              setMe(null);
              navigate("/login");
            })
          }
        >
          Sign out everywhere
        </Button>
      </Card>
    </div>
  );
}
