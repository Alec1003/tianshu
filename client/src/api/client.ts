// Thin fetch wrapper.
//
// Responsibilities:
//  - Read the JWT from localStorage on every call and attach as Bearer token.
//  - Pick the right API base URL: explicit VITE_AI_SERVER_URL when set
//    (local dev hitting :8000 directly), otherwise relative paths so the
//    nginx reverse proxy in production rewrites `/api/*` to the server.
//  - Centralise 401 handling: emit a `tianshu:auth:logout` window event so the
//    AuthProvider can clear state and the router can bounce to /login.
//  - Throw `ApiError` carrying status + parsed detail for callers to format.

import {
  readStorageItem,
  removeStorageItem,
  writeStorageItem,
} from "@/lib/legacyStorage";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const TOKEN_KEY = "tianshu.auth.token";
let runtimeScenarioContext = "";

export function setRuntimeScenarioContext(
  scenarioId: string | null | undefined
): void {
  runtimeScenarioContext = (scenarioId ?? "").trim();
}

export function getStoredToken(): string | null {
  return readStorageItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    writeStorageItem(TOKEN_KEY, token);
  } else {
    removeStorageItem(TOKEN_KEY);
  }
}

function resolveBaseUrl(): string {
  // In production the client is served by nginx (port 3002) and `/api/*` is
  // proxied to the server. In `npm run dev`, vite is the dev server and
  // there is NO proxy yet -- we fall back to the explicit AI server URL.
  const explicit = import.meta.env.VITE_AI_SERVER_URL as string | undefined;
  if (explicit && explicit.length > 0 && explicit !== "/") {
    // Strip trailing slash so `${base}/api/...` joins cleanly.
    return explicit.replace(/\/$/, "");
  }
  return ""; // relative => nginx proxy handles it
}

type RequestInitNoBody = Omit<RequestInit, "body">;

interface CallOptions extends RequestInitNoBody {
  json?: unknown;
  form?: Record<string, string>;
}

export async function apiCall<T = unknown>(
  path: string,
  options: CallOptions = {}
): Promise<T> {
  const base = resolveBaseUrl();
  const url = `${base}${path}`;
  const headers = new Headers(options.headers);

  const token = getStoredToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (
    runtimeScenarioContext &&
    (path.startsWith("/api/ai/runtime") ||
      path.startsWith("/api/ai/command") ||
      path.startsWith("/api/ai/internal-skills") ||
      path.startsWith("/api/ai/chat") ||
      path.startsWith("/api/ai/skills"))
  ) {
    headers.set("X-TianShu-Scenario-Id", runtimeScenarioContext);
  }

  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  } else if (options.form !== undefined) {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
    body = new URLSearchParams(options.form).toString();
  }

  const response = await fetch(url, { ...options, headers, body });

  if (response.status === 401) {
    // Token expired / invalid: nuke it and let the AuthProvider react.
    setStoredToken(null);
    window.dispatchEvent(new Event("tianshu:auth:logout"));
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      // ignore body parse errors
    }
    throw new ApiError(401, detail, "未登录或登录已过期");
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      try {
        detail = await response.text();
      } catch {
        // ignore
      }
    }
    throw new ApiError(response.status, detail);
  }

  // 204 No Content -> nothing to parse.
  if (response.status === 204) return undefined as T;

  // We assume JSON for every other 2xx body.
  return (await response.json()) as T;
}
