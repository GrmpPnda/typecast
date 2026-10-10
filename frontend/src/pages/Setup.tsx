import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { useAuth } from "@/auth";
import ProviderButtons from "@/components/ProviderButtons";

/**
 * First-run setup: creates the administrator on a deployment with no accounts.
 *
 * Reachable without credentials, which is safe only because the server refuses
 * /auth/setup the moment any account exists. Once that happens this page
 * redirects away, so it cannot be used to add a second admin.
 */
export default function Setup() {
  const { setupRequired, loading, completeSetup, providers } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    display_name: "",
    username: "",
    password: "",
    confirm: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen bg-tc-page flex items-center justify-center">
        <div className="text-tc-muted text-sm">Loading...</div>
      </div>
    );
  }

  // Already set up, so there is nothing to do here.
  if (!setupRequired) return <Navigate to="/" replace />;

  const mismatch = form.confirm.length > 0 && form.password !== form.confirm;
  const tooShort = form.password.length > 0 && form.password.length < 8;
  const canSubmit =
    form.email.length > 0 &&
    form.display_name.length > 0 &&
    form.username.length >= 3 &&
    form.password.length >= 8 &&
    form.password === form.confirm &&
    !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await completeSetup({
        email: form.email,
        username: form.username,
        display_name: form.display_name,
        password: form.password,
      });
      navigate("/", { replace: true });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      setError(detail || "Could not complete setup.");
    } finally {
      setSubmitting(false);
    }
  };

  const field =
    "w-full bg-tc-overlay border border-tc-subtle rounded-lg px-3 py-2 text-sm text-tc-primary focus:outline-none focus:border-tc-accent";

  return (
    <div className="min-h-screen bg-tc-page flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-center text-tc-primary">Typecast</h1>
        <div className="flex items-center justify-center gap-2 mt-3 mb-2">
          <Shield size={14} className="text-tc-accent" />
          <p className="text-sm text-tc-secondary">Create your administrator account</p>
        </div>
        <p className="text-xs text-tc-muted text-center mb-8">
          This is a new installation with no accounts yet. The account you create here can
          manage every other account from Settings.
        </p>

        {providers.length > 0 && (
          <div className="mb-6 space-y-4">
            <ProviderButtons providers={providers} />
            <p className="text-xs text-tc-muted text-center">
              The first person to sign in becomes the administrator, and that account will
              always sign in that way.
            </p>
            <div className="flex items-center gap-3 text-xs text-tc-muted">
              <div className="flex-1 border-t border-tc-subtle" />
              or create a password account
              <div className="flex-1 border-t border-tc-subtle" />
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Email</label>
            <input
              type="email"
              autoComplete="username"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              className={field}
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Display name</label>
            <input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              required
              className={field}
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Username</label>
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
              minLength={3}
              className={field}
            />
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              minLength={8}
              className={field}
            />
            {tooShort && (
              <p className="text-xs text-tc-error mt-1">Use at least 8 characters.</p>
            )}
          </div>
          <div>
            <label className="block text-sm text-tc-tertiary mb-1">Confirm password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              required
              className={field}
            />
            {mismatch && (
              <p className="text-xs text-tc-error mt-1">Passwords do not match.</p>
            )}
          </div>

          {error && <p className="text-sm text-tc-error">{error}</p>}

          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full py-2 bg-tc-accent hover:bg-tc-accent-hover disabled:opacity-50 rounded-lg text-sm font-medium transition-colors text-tc-primary"
          >
            {submitting ? "Creating account..." : "Create account and sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
