import { useEffect, useState, type FormEvent } from "react";
import { api, type AuthStatus } from "../api";
import { useAuth } from "../auth";
import { Arrow, Logo } from "./Icons";

export function AuthPage() {
  const { signIn } = useAuth();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.authStatus().then(
      (found) => {
        setStatus(found);
        if (!found.has_accounts) setMode("signup");
      },
      () => setStatus({ has_accounts: true, signup_open: true }),
    );
  }, []);

  const first = status !== null && !status.has_accounts;
  const signup = mode === "signup";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      signIn(signup ? await api.signup(email, password) : await api.login(email, password));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not sign in. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <section className="auth-side on-dark">
        <span className="wordmark" style={{ color: "var(--on-dark-1)" }}>
          <Logo /> PRAMANA
        </span>
        <div>
          <h1 className="display">Only claims that survive testing are called findings.</h1>
          <p className="lead">
            Upload a table, and PRAMANA tests every claim about it, corrects for testing many at
            once, and keeps the rejected ones visible with the reason.
          </p>
        </div>
        <p className="label">Association is never presented as cause.</p>
      </section>

      <main className="auth-main">
        <form className="auth-card" onSubmit={submit} aria-labelledby="auth-title">
          <h2 id="auth-title">
            {first ? "Create the first account" : signup ? "Create an account" : "Sign in"}
          </h2>
          {first && (
            <p className="explain">
              This server has no accounts yet. The first one also takes any datasets already
              stored here.
            </p>
          )}
          <label className="question">
            <span className="label">Email</span>
            <input
              type="email"
              value={email}
              required
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="question">
            <span className="label">Password</span>
            <input
              type="password"
              value={password}
              required
              minLength={signup ? 8 : undefined}
              autoComplete={signup ? "new-password" : "current-password"}
              onChange={(e) => setPassword(e.target.value)}
            />
            {signup && <span className="dz-meta">At least 8 characters</span>}
          </label>
          {error && (
            <p className="dz-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy || status === null}>
            {busy ? "Please wait…" : signup ? "Create account" : "Sign in"} <Arrow />
          </button>
          {!first && status?.signup_open !== false && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setMode(signup ? "signin" : "signup");
                setError(null);
              }}
            >
              {signup ? "I already have an account" : "Create an account"}
            </button>
          )}
        </form>
      </main>
    </div>
  );
}
