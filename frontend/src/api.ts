// Thin API client. If the backend sets DASHBOARD_TOKEN, enter it once in Settings.
export const getToken = () => localStorage.getItem("dashboard_token") || "";
export const setToken = (t: string) => localStorage.setItem("dashboard_token", t);

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const j = await res.json();
      msg = j.detail || JSON.stringify(j);
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T = any>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

// Media URLs need the token as a query param (video/img tags can't send headers).
export const fileUrl = (u?: string | null) => (u ? u + (getToken() ? `?token=${encodeURIComponent(getToken())}` : "") : "");

export const fmtDur = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
export const fmtDate = (d?: string | null) =>
  d ? new Date(d).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const usd = (n?: number | null) => (n == null ? "—" : `$${n.toFixed(2)}`);

export type VideoSummary = {
  id: number; kind: string; parent_id: number | null; status: string; title: string; duration_s: number;
  scheduled_at: string | null; youtube_url: string; upload_status: string; created_at: string; updated_at: string;
  error: string; spend: number; estimate: number | null; thumbnail: string | null; qc_passed: boolean | null;
};
