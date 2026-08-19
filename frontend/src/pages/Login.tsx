import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth";

export default function Login() {
  const { login } = useAuth();
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
