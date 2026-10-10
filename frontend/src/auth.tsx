import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getAuthState,
  getMe,
  login as apiLogin,
  completeSetup as apiCompleteSetup,
  openUploadsSession,
  closeUploadsSession,
  UserProfile,
} from "./api/auth";

/**
 * Before the user is set, so the first images the app renders already have the
 * cookie. A failure is logged rather than thrown: the app works without it,
 * only images and custom fonts do not load.
 */
async function withUploadsSession(): Promise<void> {
  try {
    await openUploadsSession();
  } catch (err) {
    console.warn("Could not open the uploads session; images may not load.", err);
  }
}

interface AuthContextValue {
  user: UserProfile | null;
  authMode: string | null;
  /** Multi-user mode with no accounts yet: send the visitor to /setup. */
  setupRequired: boolean;
  /** Proxy (single sign-on) mode: signed in, but this server has no account
   * for that person, or it is disabled. The server's explanation. */
  accessDenied: string | null;
  /** Proxy mode: the proxy's sign-in and sign-out URLs. */
  loginUrl: string | null;
  logoutUrl: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  completeSetup: (payload: {
    email: string;
    username: string;
    display_name: string;
    password: string;
  }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  authMode: null,
  setupRequired: false,
  accessDenied: null,
  loginUrl: null,
  logoutUrl: null,
  loading: true,
  login: async () => {},
  completeSetup: async () => {},
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
  const queryClient = useQueryClient();
  const [authMode, setAuthMode] = useState<string | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [accessDenied, setAccessDenied] = useState<string | null>(null);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [logoutUrl, setLogoutUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const me = await getMe();
      await withUploadsSession();
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
        const state = await getAuthState();
        setAuthMode(state.mode);
        setSetupRequired(state.setup_required);

        const previousMode = localStorage.getItem("auth_mode");
        if (previousMode && previousMode !== state.mode) {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          setUser(null);
        }
        localStorage.setItem("auth_mode", state.mode);

        if (state.mode === "proxy") {
          // The proxy has already signed this person in and forwards who they
          // are with every request; there is no token of ours to hold.
          localStorage.removeItem("token");
          setLoginUrl(state.login_url ?? null);
          setLogoutUrl(state.logout_url ?? null);
          if (state.login_url) localStorage.setItem("proxy_login_url", state.login_url);
          try {
            const me = await getMe();
            setUser(me);
            localStorage.setItem("user", JSON.stringify(me));
          } catch (err) {
            const status = (err as { response?: { status?: number } })?.response?.status;
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
              ?.detail;
            setUser(null);
            localStorage.removeItem("user");
            // 403: signed in, but no account here (or a disabled one). 401 is
            // handled by the client interceptor, which renews the sign-in.
            if (status === 403) setAccessDenied(detail ?? "You do not have access to this server.");
          }
        } else if (state.setup_required) {
          // No account exists, so any stored token is stale (a rebuilt or
          // emptied database). Clear it rather than letting /setup 401.
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          setUser(null);
        } else if (state.mode === "local") {
          const { token, user: u } = await apiLogin("local@typecast.local", "");
          localStorage.setItem("token", token);
          localStorage.setItem("user", JSON.stringify(u));
          await withUploadsSession();
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

  const login = useCallback(
    async (email: string, password: string) => {
      const { token, user: u } = await apiLogin(email, password);
      localStorage.setItem("token", token);
      localStorage.setItem("user", JSON.stringify(u));
      // Drop anything cached for whoever was here before, so the incoming user
      // never sees another account's works, chapters, or codex entries.
      queryClient.clear();
      await withUploadsSession();
      setUser(u);
    },
    [queryClient]
  );

  const completeSetup = useCallback(
    async (payload: {
      email: string;
      username: string;
      display_name: string;
      password: string;
    }) => {
      const { token, user: u } = await apiCompleteSetup(payload);
      localStorage.setItem("token", token);
      localStorage.setItem("user", JSON.stringify(u));
      await withUploadsSession();
      setUser(u);
      // Clearing this is what releases the redirect guard on every route.
      setSetupRequired(false);
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    // Not awaited: sign-out must not wait on the network. The cookie also
    // expires with the token.
    closeUploadsSession().catch(() => {});
    if (logoutUrl) {
      // Signing out of the proxy ends the single sign-on session; clearing our
      // own state alone would just sign you straight back in.
      queryClient.clear();
      window.location.href = logoutUrl;
      return;
    }
    // Without this the manuscripts stay in memory and the next user to sign in
    // on this browser is served them from cache before any request goes out.
    queryClient.clear();
    setUser(null);
  }, [queryClient, logoutUrl]);

  return (
    <AuthContext.Provider
      value={{
        user,
        authMode,
        setupRequired,
        accessDenied,
        loginUrl,
        logoutUrl,
        loading,
        login,
        completeSetup,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
