import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { getAuthMode, getMe, login as apiLogin, UserProfile } from "./api/auth";

interface AuthContextValue {
  user: UserProfile | null;
  authMode: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  authMode: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(() => {
    const stored = localStorage.getItem("user");
    return stored ? JSON.parse(stored) : null;
  });
  const [authMode, setAuthMode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const me = await getMe();
      setUser(me);
      localStorage.setItem("user", JSON.stringify(me));
    } catch {
      setUser(null);
      localStorage.removeItem("user");
      localStorage.removeItem("token");
    }
  }, []);

  useEffect(() => {
    async function init() {
      try {
        const mode = await getAuthMode();
        setAuthMode(mode);

        const previousMode = localStorage.getItem("auth_mode");
        if (previousMode && previousMode !== mode) {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          setUser(null);
        }
        localStorage.setItem("auth_mode", mode);

        if (mode === "local") {
          const { token, user: u } = await apiLogin("local@typecast.local", "");
          localStorage.setItem("token", token);
          localStorage.setItem("user", JSON.stringify(u));
          setUser(u);
        } else if (localStorage.getItem("token")) {
          await refreshUser();
        }
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const { token, user: u } = await apiLogin(email, password);
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(u));
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, authMode, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
