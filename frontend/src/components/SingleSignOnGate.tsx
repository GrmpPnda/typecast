import { LogIn, LogOut, ShieldAlert } from "lucide-react";
import { useAuth } from "@/auth";

/**
 * Shown under single sign-on when the proxy has signed someone in but the app
 * cannot let them in. Two cases, worded differently because the fix differs:
 * no account here (ask an administrator, or sign out to switch accounts), or
 * the forwarded sign-in aged out (sign in again).
 */
export default function SingleSignOnGate() {
  const { accessDenied, loginUrl, logoutUrl } = useAuth();

  return (
    <div className="min-h-screen bg-tc-page flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        <h1 className="text-2xl font-bold mb-6 text-tc-primary">Typecast</h1>
        {accessDenied ? (
          <>
            <div className="flex items-center justify-center gap-2 mb-3 text-tc-secondary">
              <ShieldAlert size={16} className="text-tc-error" />
              <span className="text-sm">You are signed in, but you cannot use this server</span>
            </div>
            <p className="text-sm text-tc-muted mb-6">{accessDenied}</p>
            {logoutUrl && (
              <a
                href={logoutUrl}
                className="inline-flex items-center gap-2 px-4 py-2 bg-tc-hover hover:bg-tc-active rounded-lg text-sm font-medium transition-colors"
              >
                <LogOut size={14} />
                Sign out to use a different account
              </a>
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-tc-muted mb-6">Your sign-in needs renewing.</p>
            {loginUrl && (
              <a
                href={loginUrl}
                className="inline-flex items-center gap-2 px-4 py-2 bg-tc-accent hover:bg-tc-accent-hover rounded-lg text-sm font-medium text-tc-primary transition-colors"
              >
                <LogIn size={14} />
                Sign in
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
