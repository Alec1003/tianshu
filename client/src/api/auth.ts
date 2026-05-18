// Auth endpoints — register / login / logout / me.
// All routes live under /api/* so nginx (prod) and the dev proxy share the
// same prefix.

import { apiCall, setStoredToken } from "./client";
import type { AuthTokenResponse, AuthUser } from "./types";

export interface RegisterPayload {
  email: string;
  password: string;
  display_name?: string;
}

export async function register(payload: RegisterPayload): Promise<AuthUser> {
  return apiCall<AuthUser>("/api/auth/register", {
    method: "POST",
    json: payload,
  });
}

/** Logs in and persists the token. */
export async function login(
  email: string,
  password: string
): Promise<AuthTokenResponse> {
  const token = await apiCall<AuthTokenResponse>("/api/auth/jwt/login", {
    method: "POST",
    // fastapi-users requires the OAuth2 password-flow form encoding here.
    form: { username: email, password },
  });
  setStoredToken(token.access_token);
  return token;
}

export async function fetchMe(): Promise<AuthUser> {
  return apiCall<AuthUser>("/api/users/me");
}

export async function updateMe(patch: {
  display_name?: string;
  password?: string;
}): Promise<AuthUser> {
  return apiCall<AuthUser>("/api/users/me", {
    method: "PATCH",
    json: patch,
  });
}

/** Logs out by dropping the token client-side. The server-side JWT endpoint
 * is a no-op for stateless bearer tokens. */
export function logout(): void {
  setStoredToken(null);
  window.dispatchEvent(new Event("aicc:auth:logout"));
}
