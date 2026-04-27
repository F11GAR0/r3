import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { jsonFetch, getToken, setToken } from "./api";

type User = {
  id: number;
  username: string;
  role: string;
  redmine_user_id: number | null;
  has_redmine_api_key?: boolean;
  redmine_skip_tls?: boolean;
  /** Effective merged AI system prompts */
  ai_prompts?: Record<string, string>;
};
type Ctx = {
  user: User | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<Ctx | null>(null);

/**
 * App-wide session from JWT; loads /api/auth/me when token is present.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await jsonFetch<User>("/api/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await jsonFetch<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(res.access_token);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const v = useMemo(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh]
  );

  return <AuthContext.Provider value={v}>{children}</AuthContext.Provider>;
}

/**
 * Return auth context; throws if used outside provider.
 */
export function useAuth(): Ctx {
  const c = useContext(AuthContext);
  if (!c) {
    throw new Error("useAuth");
  }
  return c;
}

/**
 * Return true for admin and superadmin roles.
 */
export function isAdmin(user: User | null): boolean {
  if (!user) {
    return false;
  }
  return user.role === "admin" || user.role === "superadmin";
}

/** True only for superadmin (can assign superadmin role in admin UI). */
export function isSuperAdmin(user: User | null): boolean {
  return user?.role === "superadmin";
}

/**
 * Return true for product manager or higher in reporting views.
 */
export function isPM(user: User | null): boolean {
  if (!user) {
    return false;
  }
  return ["superadmin", "admin", "product_manager"].includes(user.role);
}
