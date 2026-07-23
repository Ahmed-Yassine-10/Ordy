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
};
