// Relative by default: Next.js proxies /api/* to the FastAPI backend (see next.config.js), so one public URL serves everything.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export type SessionUser = { id: number; username: string; full_name: string; role: string; role_label: string; email: string };

export function getSession(): { token: string; user: SessionUser } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("aml_session");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export function setSession(s: { token: string; user: SessionUser } | null) {
  if (s) window.localStorage.setItem("aml_session", JSON.stringify(s));
  else window.localStorage.removeItem("aml_session");
}
export const analystName = () => getSession()?.user.username ?? "analyst.demo";
export const roleName = () => getSession()?.user.role ?? "ANALYST";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = any;

function authHeaders(): Record<string, string> {
  const s = getSession();
  return s ? { Authorization: `Bearer ${s.token}`, "X-Analyst": s.user.username } : {};
}

export async function api<T = Json>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init.headers || {}) },
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    setSession(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      const d = body.detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((e: Json) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ") : msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const post = <T = Json>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T = Json>(path: string, body?: unknown) =>
  api<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T = Json>(path: string, body?: unknown) =>
  api<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) });

/** Download a text endpoint (CSV / XML) through a temporary link. */
export async function download(path: string, filename: string) {
  const res = await fetch(`${API_BASE}/api${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
