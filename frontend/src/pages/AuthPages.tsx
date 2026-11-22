import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type LinkResponse, type Me } from "../api";
import { useAuth } from "../auth";
import { Alert, AuthShell, Button, DevLink, Field, Input, useAsync } from "../components/ui";

const MIN_PW = 10;

export function LoginPage() {
  const { setMe, me } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [unverified, setUnverified] = useState(false);
  const [resent, setResent] = useState<LinkResponse | null>(null);
  const { busy, error, run } = useAsync();

  useEffect(() => {
    if (me) navigate(next, { replace: true });
  }, [me, navigate, next]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setUnverified(false);
    await run(async () => {
      try {
        const m = await api<Me>("/auth/login", { body: { email, password }, company: false });
        setMe(m);
      } catch (err) {
        if (err instanceof ApiError && err.code === "email_unverified") setUnverified(true);
        throw err;
      }
    });
  }

  return (
    <AuthShell>
      <h1>Sign in</h1>
      <p className="muted">Welcome back.</p>
      {error && <Alert kind="error">{error}</Alert>}
      {unverified && (
        <Alert kind="info">
          Didn't get the email?{" "}
          <a
            href="#"
            onClick={async (e) => {
              e.preventDefault();
              setResent(await api<LinkResponse>("/auth/resend-verification", { body: { email }, company: false }));
            }}
          >
            Send it again
          </a>
        </Alert>
      )}
      {resent && <Alert kind="ok">{resent.message}</Alert>}
      <DevLink link={resent?.dev_link} label="Verify your email" />
      <form onSubmit={submit}>
        <Field label="Email" htmlFor="email">
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button variant="primary" block disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="small" style={{ marginTop: 16 }}>
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
      <p className="small muted">
        New here? <Link to="/signup">Create an account</Link>
      </p>
    </AuthShell>
  );
}

export function SignupPage() {
  const [form, setForm] = useState({ name: "", email: "", password: "", company_name: "" });
  const [done, setDone] = useState<LinkResponse | null>(null);
  const { busy, error, run } = useAsync();
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  if (done) {
    return (
      <AuthShell>
        <h1>Check your email</h1>
        <p className="muted">
          We sent a link to <strong>{form.email}</strong>. Click it to verify your address and finish signing up.
        </p>
        <DevLink link={done.dev_link} label="Verify your email" />
        <p className="small">
          <Link to="/login">Back to sign in</Link>
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <h1>Create your account</h1>
      <p className="muted">Set up your company. You can invite your team afterwards.</p>
      {error && <Alert kind="error">{error}</Alert>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => setDone(await api<LinkResponse>("/auth/signup", { body: form, company: false })));
        }}
      >
        <Field label="Your name" htmlFor="name">
          <Input id="name" autoComplete="name" required value={form.name} onChange={set("name")} />
        </Field>
        <Field label="Work email" htmlFor="email">
          <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Password" htmlFor="password" hint={`At least ${MIN_PW} characters.`}>
          <Input id="password" type="password" autoComplete="new-password" minLength={MIN_PW} required value={form.password} onChange={set("password")} />
        </Field>
        <Field label="Company name" htmlFor="company">
          <Input id="company" autoComplete="organization" required value={form.company_name} onChange={set("company_name")} />
        </Field>
        <Button variant="primary" block disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>
      <p className="small muted" style={{ marginTop: 16 }}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthShell>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { setMe } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice; the token is single-use
    started.current = true;
    api<Me>("/auth/verify-email", { body: { token }, company: false })
      .then((m) => {
        setMe(m);
        navigate("/", { replace: true });
      })
      .catch((e: Error) => setError(e.message));
  }, [token, setMe, navigate]);

  return (
    <AuthShell>
      <h1>Verifying your email…</h1>
      {error && (
        <>
          <Alert kind="error">{error}</Alert>
          <p className="small">
            <Link to="/login">Sign in</Link> to request a new link.
          </p>
        </>
      )}
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<LinkResponse | null>(null);
  const { busy, error, run } = useAsync();
  return (
    <AuthShell>
      <h1>Reset your password</h1>
      {done ? (
        <>
          <Alert kind="ok">{done.message}</Alert>
          <DevLink link={done.dev_link} label="Reset your password" />
        </>
      ) : (
        <>
          <p className="muted">Enter your email and we'll send you a reset link.</p>
          {error && <Alert kind="error">{error}</Alert>}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => setDone(await api<LinkResponse>("/auth/forgot-password", { body: { email }, company: false })));
            }}
          >
            <Field label="Email" htmlFor="email">
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Button variant="primary" block disabled={busy}>
              Send reset link
            </Button>
          </form>
        </>
      )}
      <p className="small" style={{ marginTop: 16 }}>
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { setMe } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAsync();
  return (
    <AuthShell>
      <h1>Choose a new password</h1>
      {error && <Alert kind="error">{error}</Alert>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            setMe(await api<Me>("/auth/reset-password", { body: { token, password }, company: false }));
            navigate("/", { replace: true });
          });
        }}
      >
        <Field label="New password" htmlFor="password" hint={`At least ${MIN_PW} characters. This signs you out everywhere else.`}>
          <Input id="password" type="password" autoComplete="new-password" minLength={MIN_PW} required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button variant="primary" block disabled={busy}>
          Save password
        </Button>
      </form>
    </AuthShell>
  );
}
