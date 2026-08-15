const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";
const TOKEN_KEY = "wow_admin_token";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

/** True once a login has been completed (dev logins may store an empty token). */
export function hasSession(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(TOKEN_KEY) !== null;
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type FetchOptions = {
  method?: string;
  body?: unknown;
  /** attach the stored admin bearer + bounce to /login on 401 (default true) */
  auth?: boolean;
  /** verify this token instead of the stored one (used by the login page) */
  token?: string;
};

async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, token } = opts;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const bearer = token !== undefined ? token : auth ? getToken() : "";
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Please try again.");
  }

  if (res.status === 401 && auth && token === undefined && typeof window !== "undefined") {
    clearToken();
    // deliberate hard navigation: this can fire outside any React component
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// ---- types mirroring the server's response schemas ----

export interface Lead {
  id: string;
  name: string;
  phone: string;
  source: string;
  consent: boolean;
  dnc: boolean;
  created_at: string;
}

export type CallStatus =
  | "requested"
  | "ringing"
  | "in_progress"
  | "completed"
  | "failed"
  | "no_answer"
  | "busy";

export interface Call {
  id: string;
  lead_id: string;
  provider_call_id: string | null;
  status: CallStatus;
  language: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  created_at: string;
  lead: Lead;
}

export interface Turn {
  id: string;
  role: "user" | "assistant";
  text: string;
  t_offset_ms: number;
  created_at: string;
}

export interface Qualification {
  id: string;
  intent: string | null;
  geography: string | null;
  budget: string | null;
  timeline: string | null;
  language: string | null;
  sentiment: string | null;
  disposition: string | null;
  next_action: string | null;
  summary: string | null;
  created_at: string;
}

export interface CallDetail extends Call {
  turns: Turn[];
  qualification: Qualification | null;
  recording_url: string | null;
}

// ---- endpoints ----

/** Public landing page: request a call. No auth, no 401 redirect. */
export function requestCall(name: string, phone: string): Promise<Call> {
  return apiFetch<Call>("/api/calls", {
    method: "POST",
    body: { name, phone, consent: true },
    auth: false,
  });
}

/** Login probe: 200 iff the token is accepted by the server. */
export function verifyToken(token: string): Promise<{ authenticated: boolean; mode: string }> {
  return apiFetch("/api/me", { token });
}

export function listCalls(limit = 50, offset = 0): Promise<Call[]> {
  return apiFetch(`/api/calls?limit=${limit}&offset=${offset}`);
}

export function getCall(id: string): Promise<CallDetail> {
  return apiFetch(`/api/calls/${id}`);
}

export function listLeads(limit = 100, offset = 0): Promise<Lead[]> {
  return apiFetch(`/api/leads?limit=${limit}&offset=${offset}`);
}

/**
 * The recording endpoint is bearer-gated, so an <audio src> can't reach it
 * directly. Fetch it with the token and hand back an object URL.
 */
export async function fetchRecordingObjectUrl(recordingUrl: string): Promise<string> {
  const headers: Record<string, string> = {};
  const bearer = getToken();
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
  const res = await fetch(`${API_BASE}${recordingUrl}`, { headers });
  if (!res.ok) throw new ApiError(res.status, "Could not load the recording");
  return URL.createObjectURL(await res.blob());
}
