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

async function raiseFor(res: Response): Promise<never> {
  let detail: unknown = null;
  try {
    detail = (await res.json())?.detail;
  } catch {
    /* not JSON */
  }
  const { message, code } = messageFrom(detail, `Request failed (${res.status})`);
  throw new ApiError(res.status, message, code);
}

/** Multipart upload (file imports). */
export async function apiUpload<T = unknown>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const headers: Record<string, string> = {};
  if (activeCompanyId != null) headers["X-Company-Id"] = String(activeCompanyId);
  const res = await fetch(`/api${path}`, { method: "POST", body: fd, headers, credentials: "same-origin" });
  if (!res.ok) await raiseFor(res);
  return (await res.json()) as T;
}

/** Download a file from an endpoint that needs the company header (so a plain link won't do). */
export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (activeCompanyId != null) headers["X-Company-Id"] = String(activeCompanyId);
  const res = await fetch(`/api${path}`, { headers, credentials: "same-origin" });
  if (!res.ok) await raiseFor(res);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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

export interface Box {
  id?: number;
  box_no: number;
  name: string;
  qty_per_unit: number;
  units_per_box: number;
  length: number;
  width: number;
  height: number;
  weight: number;
  this_side_up: boolean;
  stackable: boolean;
  max_load_on_top: number;
}
export interface ProductSummary {
  id: number;
  sku: string;
  name: string;
  source: "manual" | "import" | "odoo";
  box_count: number;
  unit_weight: number;
  updated_at: string | null;
}
export interface Product extends ProductSummary {
  boxes: Box[];
}
export interface PalletType {
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
