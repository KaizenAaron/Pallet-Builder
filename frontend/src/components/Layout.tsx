import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { MOBILE, useMediaQuery } from "../hooks";
import { Badge } from "./ui";

function useClickOutside(onOutside: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onOutside();
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onOutside]);
  return ref;
}

function Menu({ label, children }: { label: ReactNode; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside(() => setOpen(false));
  return (
    <div className="menu" ref={ref}>
      <button className="btn btn-ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {label} <span aria-hidden>▾</span>
      </button>
      {open && <div className="menu-pop">{children(() => setOpen(false))}</div>}
    </div>
  );
}

export default function Layout() {
  const { me, company, switchCompany, logout } = useAuth();
  const navigate = useNavigate();
  const mobile = useMediaQuery(MOBILE);
  if (!me) return null;
  const isAdmin = company?.role === "owner" || company?.role === "admin";

  const links = [
    { to: "/", label: "Home", show: true, end: true },
    { to: "/products", label: "Products", show: !!company },
    { to: "/pallet-types", label: "Pallet types", show: !!company },
    { to: "/members", label: "Members", show: !!company },
    { to: "/company", label: "Company", show: !!company && isAdmin },
    { to: "/admin", label: "Platform", show: me.is_platform_admin },
  ].filter((l) => l.show);

  const companyMenu = (
    <Menu label={<strong>{company?.name ?? "No company"}</strong>}>
      {(close) => (
        <>
          <div className="menu-label">Switch company</div>
          {me.companies.map((c) => (
            <button
              key={c.id}
              onClick={() => {
                switchCompany(c.id);
                close();
                navigate("/");
              }}
            >
              {c.id === company?.id ? "✓ " : ""}
              {c.name} <Badge tone={c.role}>{c.role}</Badge>
            </button>
          ))}
          <div className="menu-sep" />
          <button
            onClick={() => {
              close();
              navigate("/companies/new");
            }}
          >
            + New company…
          </button>
        </>
      )}
    </Menu>
  );

  const userMenu = (
    <Menu label={mobile ? "☰" : me.name || me.email}>
      {(close) => (
        <>
          <div className="menu-label">{me.email}</div>
          <Link to="/account" onClick={close}>
            Account
          </Link>
          <button
            onClick={async () => {
              close();
              await logout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </>
      )}
    </Menu>
  );

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand" style={{ textDecoration: "none" }}>
            <span className="brand-mark">PB</span>
            {!mobile && "Pallet Builder"}
          </Link>
          {!mobile && (
            <nav className="nav">
              {links.map((l) => (
                <NavLink key={l.to} to={l.to} end={l.end}>
                  {l.label}
                </NavLink>
              ))}
            </nav>
          )}
          <span className="spacer" />
          {companyMenu}
          {userMenu}
        </div>
        {mobile && (
          <nav className="mobile-nav">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end}>
                {l.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="page">
        {company?.suspended && (
          <div className="alert alert-error">This company's account is suspended. Contact support.</div>
        )}
        <Outlet />
      </main>
    </>
  );
}
