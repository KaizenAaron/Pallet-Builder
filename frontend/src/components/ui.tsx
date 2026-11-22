import { useState, type ReactNode, type InputHTMLAttributes, type SelectHTMLAttributes, type ButtonHTMLAttributes } from "react";

type Variant = "default" | "primary" | "danger" | "ghost";

export function Button({
  variant = "default",
  size,
  block,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm"; block?: boolean }) {
  const cls = ["btn", variant !== "default" && `btn-${variant}`, size && `btn-${size}`, block && "btn-block", className]
    .filter(Boolean)
    .join(" ");
  return <button className={cls} {...rest} />;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="select" {...props} />;
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Card({ children, title, actions }: { children: ReactNode; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="row" style={{ marginBottom: 12 }}>
          {title && <h2 style={{ margin: 0 }}>{title}</h2>}
          <span className="spacer" />
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Alert({ kind = "info", children }: { kind?: "error" | "ok" | "info" | "warn"; children: ReactNode }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ""}`}>{children}</span>;
}

export function CopyLink({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-box">
      <input className="input" readOnly value={link} onFocus={(e) => e.currentTarget.select()} aria-label="Link" />
      <Button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          } catch {
            /* clipboard blocked — the field is selectable */
          }
        }}
      >
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

/** Shown when the server returns a link because email isn't configured (local testing). */
export function DevLink({ link, label }: { link: string | null | undefined; label: string }) {
  if (!link) return null;
  const path = (() => {
    try {
      const u = new URL(link);
      return u.pathname + u.search;
    } catch {
      return link;
    }
  })();
  return (
    <Alert kind="warn">
      <strong>Email isn't set up on this server</strong>, so here's the link that would have been emailed:{" "}
      <a href={path}>{label}</a>
    </Alert>
  );
}

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="brand" style={{ marginBottom: 18, justifyContent: "center" }}>
          <span className="brand-mark">PB</span> Pallet Builder
        </div>
        <div className="card">{children}</div>
      </div>
    </div>
  );
}

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}
