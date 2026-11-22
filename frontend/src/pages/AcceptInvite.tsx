import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Me } from "../api";
import { useAuth } from "../auth";
import { Alert, AuthShell, Button, Field, Input, useAsync } from "../components/ui";

interface InviteInfo {
  company_name: string;
  email: string;
  role: string;
  account_exists: boolean;
  signed_in_as: string | null;
}

export default function AcceptInvitePage() {
  const { token = "" } = useParams();
  const { setMe, switchCompany, logout } = useAuth();
  const navigate = useNavigate();
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAsync();

  useEffect(() => {
    api<InviteInfo>(`/invites/${token}`, { company: false })
      .then(setInfo)
      .catch((e: Error) => setLoadError(e.message));
  }, [token]);

  async function accept(body: object) {
    await run(async () => {
      const r = await api<{ company_id: number; me: Me }>(`/invites/${token}/accept`, { body, company: false });
      setMe(r.me);
      switchCompany(r.company_id);
      navigate("/", { replace: true });
    });
  }

  if (loadError) {
    return (
      <AuthShell>
        <h1>Invitation unavailable</h1>
        <Alert kind="error">{loadError}</Alert>
        <p className="small">Ask whoever invited you to send a new link.</p>
      </AuthShell>
    );
  }
  if (!info) return <AuthShell>Loading…</AuthShell>;

  const signedInAsInvitee = info.signed_in_as === info.email;
  const signedInAsOther = info.signed_in_as && !signedInAsInvitee;

  return (
    <AuthShell>
      <h1>Join {info.company_name}</h1>
      <p className="muted">
        You've been invited as <strong>{info.role}</strong> ({info.email}).
      </p>
      {error && <Alert kind="error">{error}</Alert>}

      {signedInAsInvitee && (
        <Button variant="primary" block disabled={busy} onClick={() => accept({})}>
          Join {info.company_name}
        </Button>
      )}

      {signedInAsOther && (
        <>
          <Alert kind="warn">
            You're signed in as {info.signed_in_as}. This invitation is for {info.email}.
          </Alert>
          <Button
            block
            onClick={async () => {
              await logout();
              navigate(`/login?next=${encodeURIComponent(`/invite/${token}`)}`);
            }}
          >
            Sign out and switch account
          </Button>
        </>
      )}

      {!info.signed_in_as && info.account_exists && (
        <>
          <p>You already have an account. Sign in to accept.</p>
          <Link className="btn btn-primary btn-block" to={`/login?next=${encodeURIComponent(`/invite/${token}`)}`}>
            Sign in as {info.email}
          </Link>
        </>
      )}

      {!info.signed_in_as && !info.account_exists && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void accept({ name, password });
          }}
        >
          <Field label="Your name" htmlFor="name">
            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Choose a password" htmlFor="password" hint="At least 10 characters.">
            <Input id="password" type="password" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button variant="primary" block disabled={busy}>
            Create account and join
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
