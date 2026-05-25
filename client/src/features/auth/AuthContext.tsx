// Centralised auth state.
//
// On mount the provider:
//   1. Reads the persisted JWT (if any) and resolves the current user via
//      /api/users/me.
//   2. Listens for the global `aicc:auth:logout` window event the API layer
//      emits on 401, so token expiry instantly nukes UI state without
//      every component having to poll.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "@/api/auth";
import { getStoredToken } from "@/api/client";
import type { AuthUser } from "@/api/types";
import { AuthContext, type AuthContextValue } from "./AuthContextCore";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(() =>
    Boolean(getStoredToken())
  );
  // Guards against double-fetch in React 18 StrictMode dev.
  const probedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!getStoredToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await authApi.fetchMe();
      setUser(me);
    } catch {
      // 401 already wiped the token via the API layer; just clear state.
      setUser(null);
    }
  }, []);

  // Initial probe on mount: if a token exists, validate it.
  useEffect(() => {
    if (probedRef.current) return;
    probedRef.current = true;
    (async () => {
      try {
        if (getStoredToken()) {
          await refresh();
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  // 401 handler from the API client -> drop user.
  useEffect(() => {
    const onLogoutEvent = () => setUser(null);
    window.addEventListener("aicc:auth:logout", onLogoutEvent);
    return () => window.removeEventListener("aicc:auth:logout", onLogoutEvent);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password);
    const me = await authApi.fetchMe();
    setUser(me);
    return me;
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const created = await authApi.register({
        email,
        password,
        display_name: displayName ?? "",
      });
      // Auto-login right after register so the user lands inside the app.
      await authApi.login(email, password);
      const me = await authApi.fetchMe();
      setUser(me);
      return created;
    },
    []
  );

  const logout = useCallback(() => {
    authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, register, logout, refresh }),
    [user, loading, login, register, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
