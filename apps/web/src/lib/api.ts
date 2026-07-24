// Thin API client for the dashboard shell. In later phases this is replaced by the
// generated SDK (packages/sdk, from the OpenAPI contract — doc 09 §3). Until then,
// raw fetch against the FastAPI service via the /api proxy rewrite.

const BASE = "/api/v1";

let accessToken: string | null = null;

export function setToken(token: string | null) {
  accessToken = token;
  if (typeof window !== "undefined") {
    if (token) window.localStorage.setItem("ordy_access", token);
    else window.localStorage.removeItem("ordy_access");
  }
}

export function loadToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    accessToken = window.localStorage.getItem("ordy_access");
  }
  return accessToken;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = loadToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    const problem = await res.json().catch(() => ({}));
    throw new ApiError(res.status, problem.code ?? "ERROR", problem.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
}

export interface Restaurant {
  id: string;
  slug: string;
  name: string;
  status: string;
  currency: string;
  default_language: string;
  role: string;
}

export interface Source {
  id: string;
  kind: string;
  config: Record<string, unknown>;
  status: string;
}

export interface Run {
  id: string;
  source_id: string;
  status: string;
  stats: Record<string, unknown>;
  error: Record<string, unknown> | null;
}

export interface DraftItem {
  name: string;
  category: string | null;
  price_minor: number | null;
  currency: string;
  variants: { name: string; price_minor: number }[];
  needs_review: boolean;
}

export interface ReviewData {
  run: Run;
  menu_draft: { items: DraftItem[]; coverage: Record<string, unknown>; stats: Record<string, unknown> } | null;
  capability_map: { capabilities: { action: string; adapter: string; feasible: boolean }[] } | null;
  warnings: string[];
}

export interface PublishResult {
  published_products: number;
  published_categories: number;
  capability_map_activated: boolean;
  run_status: string;
}

export interface SearchHit {
  chunk_id: string;
  content: string;
  score: number;
  document_id: string | null;
  provenance: { source_url?: string; doc_type?: string };
  language: string | null;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, name: string) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),
  myRestaurants: () => request<Restaurant[]>("/restaurants"),
  createRestaurant: (name: string) =>
    request<Restaurant>("/restaurants", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  // --- ingestion (Phase 3) ---
  createSource: (rid: string, kind: string, url: string) =>
    request<Source>(`/restaurants/${rid}/sources`, {
      method: "POST",
      body: JSON.stringify({ kind, config: { url } }),
    }),
  triggerRun: (rid: string, sourceId: string) =>
    request<Run>(`/restaurants/${rid}/sources/${sourceId}/runs`, { method: "POST" }),
  getReview: (rid: string, runId: string) =>
    request<ReviewData>(`/restaurants/${rid}/runs/${runId}/review`),
  submitReview: (rid: string, runId: string, exclude: string[]) =>
    request<PublishResult>(`/restaurants/${rid}/runs/${runId}/review`, {
      method: "POST",
      body: JSON.stringify({
        approve_menu: true,
        approve_capability_map: true,
        overrides: Object.fromEntries(exclude.map((name) => [name, { exclude: true }])),
      }),
    }),

  // --- retrieval (Phase 4) ---
  searchKnowledge: (rid: string, query: string, k = 5) =>
    request<SearchHit[]>(`/restaurants/${rid}/knowledge/search`, {
      method: "POST",
      body: JSON.stringify({ query, k }),
    }),

  // --- agent sandbox (Phase 5) ---
  startSandbox: (rid: string) =>
    request<SandboxRef>(`/restaurants/${rid}/sandbox/conversations`, { method: "POST" }),
  sandboxTurn: (rid: string, cid: string, text: string) =>
    request<TurnResponse>(`/restaurants/${rid}/sandbox/conversations/${cid}/turns`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};

export interface SandboxRef {
  conversation_id: string;
  language: string;
}

export interface AgentTrace {
  route: string;
  intent?: string;
  grounding?: { grounded: boolean; unsupported: string[] };
  retrieved?: { chunk_id: string; score: number; source?: string }[];
}

export interface TurnResponse {
  reply: string;
  trace: AgentTrace;
  status: string;
}
