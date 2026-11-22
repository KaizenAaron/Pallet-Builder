import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, getStoredCompanyId, setActiveCompanyId, type CompanyRef, type Me } from "./api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  company: CompanyRef | null;
  setMe: (me: Me | null) => void;
  refresh: () => Promise<Me | null>;
  switchCompany: (id: number) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function pickCompany(me: Me | null, preferred: number | null): CompanyRef | null {
  if (!me || me.companies.length === 0) return null;
  return me.companies.find((c) => c.id === preferred) ?? me.companies[0];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState<number | null>(getStoredCompanyId());

  // The API client's company header is updated synchronously here (not in an effect): child pages'
  // effects run before this provider's effects, so their first request would go out without it.
  const company = useMemo(() => {
    const c = pickCompany(me, companyId);
    if (me) setActiveCompanyId(c?.id ?? null);
    return c;
  }, [me, companyId]);

  const setMe = useCallback((m: Me | null) => setMeState(m), []);

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me", { company: false });
      setMeState(m);
      return m;
    } catch {
      setMeState(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const switchCompany = useCallback((id: number) => {
    setActiveCompanyId(id);
    setCompanyId(id);
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST", company: false }).catch(() => undefined);
    setMeState(null);
  }, []);

  const value = useMemo(
    () => ({ me, loading, company, setMe, refresh, switchCompany, logout }),
    [me, loading, company, setMe, refresh, switchCompany, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return null;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}
