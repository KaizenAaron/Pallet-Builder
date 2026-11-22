// Thin fetch wrapper: sends the session cookie and the active company header, and turns error
// responses into ApiError with a readable message (and the server's code, when it sends one).

const COMPANY_KEY = "pb.companyId";

export function getStoredCompanyId(): number | null {
  try {
    const v = localStorage.getItem(COMPANY_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function storeCompanyId(id: number | null) {
  try {
    if (id == null) localStorage.removeItem(COMPANY_KEY);
    else localStorage.setItem(COMPANY_KEY, String(id));
  } catch {
    /* storage unavailable — the switcher still works for this page load */
  }
}

let activeCompanyId: number | null = getStoredCompanyId();
export function setActiveCompanyId(id: number | null) {
  activeCompanyId = id;
  storeCompanyId(id);
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function messageFrom(detail: unknown, fallback: string): { message: string; code?: string } {
  if (typeof detail === "string") return { message: detail };
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
      return { message: field && field !== "body" ? `${field}: ${first.msg}` : first.msg };
    }
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; code?: string };
    if (d.message) return { message: d.message, code: d.code };
  }
  return { message: fallback };
}

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; company?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.company !== false && activeCompanyId != null) headers["X-Company-Id"] = String(activeCompanyId);
  const res = await fetch(`/api${path}`, {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    credentials: "same-origin",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const { message, code } = messageFrom(
      (data as { detail?: unknown } | null)?.detail,
      res.status === 429 ? "Too many attempts. Please wait and try again." : `Request failed (${res.status})`,
    );
    throw new ApiError(res.status, message, code);
  }
  return data as T;
}

// ---- shared types
export type Role = "owner" | "admin" | "member";
export interface CompanyRef {
  id: number;
  name: string;
  role: Role;
  suspended: boolean;
}
export interface Me {
  id: number;
  email: string;
  name: string;
  is_platform_admin: boolean;
  companies: CompanyRef[];
}
export interface LinkResponse {
  message: string;
  dev_link: string | null;
}
