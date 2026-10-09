import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth";

export default function Login() {
  const { login, setupRequired, loading, user, authMode } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  // There is nobody to sign in as yet, so signing in is impossible. Without
  // this a fresh multi-user deployment shows a login form that can never be
  // satisfied, which was the dead end the setup page exists to remove.
  if (!loading && setupRequired) return <Navigate to="/setup" replace />;

  // Already signed in, so there is nothing to do here. Cannot loop with App's
  // redirect: that one fires only when there is no user, this one only when
  // there is.
  if (!loading && user) return <Navigate to="/" replace />;

  // Single sign-on: the proxy signs people in, so a password form would only
  // ever fail. The app shell shows the right screen instead.
  if (!loading && authMode === "proxy") return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-tc-page flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-center mb-8 text-tc-primary">Typecast</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent"
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent"
            />
          </div>
          {error && <p className="text-sm text-tc-error">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors text-tc-primary"
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
