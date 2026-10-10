import type { SignInProvider } from "@/api/auth";

/**
 * "Sign in with Microsoft / Google". Plain links: the server runs the sign-in
 * and comes back to /login with a single-use code or an error.
 */
export default function ProviderButtons({ providers }: { providers: SignInProvider[] }) {
  if (!providers.length) return null;
  return (
    <div className="space-y-2">
      {providers.map((p) => (
        <a
          key={p.id}
          href={p.start_url}
          className="flex w-full items-center justify-center gap-2 py-2 bg-tc-overlay hover:bg-tc-hover border border-tc-subtle rounded-lg text-sm font-medium text-tc-primary transition-colors"
        >
          Sign in with {p.name}
        </a>
      ))}
    </div>
  );
}
