import { createContext } from "react";

import type { AuthUser } from "@/api/types";

export interface AuthContextValue {
  user: AuthUser | null;
  /** True until the initial me() probe resolves. Routes should render a
   * splash instead of redirecting while this is true to avoid bouncing
   * authenticated users to /login on hard refresh. */
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (
    email: string,
    password: string,
    displayName?: string
  ) => Promise<AuthUser>;
  logout: () => void;
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
