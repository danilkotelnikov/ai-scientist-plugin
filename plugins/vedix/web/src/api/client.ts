import { clearToken, getToken } from "../lib/auth";

/**
 * Base URL of the Vedix SaaS API. Override with `VITE_API_BASE` at build
 * time (e.g. for staging or self-hosted deployments). Falls back to the
 * production endpoint.
 */
export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "https://api.vedix.ai";

export class ApiError extends Error {
  public readonly status: number;
  public readonly body: string;
  public readonly path: string;

  constructor(status: number, body: string, path: string) {
    super(`API ${status} ${path}: ${body.slice(0, 200)}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.path = path;
  }
}

interface FetchOptions extends RequestInit {
  /** When true, return the raw Response instead of parsing JSON. */
  raw?: boolean;
}

/**
 * Typed fetch wrapper. Automatically injects the `Authorization: Bearer …`
 * header when a JWT is in localStorage, throws `ApiError` on non-2xx, and
 * clears the token on 401 (so the app falls back to the login flow).
 */
export async function api<T>(path: string, init: FetchOptions = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body != null && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, { ...init, headers });

  if (response.status === 401) {
    clearToken();
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body, path);
  }

  if (init.raw) {
    return response as unknown as T;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/**
 * Build a URL with query-string parameters. Skips undefined/null values.
 */
export function buildUrl(
  path: string,
  params: Record<string, string | number | boolean | null | undefined> = {},
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}
