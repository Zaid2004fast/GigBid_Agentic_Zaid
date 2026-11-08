import { useState } from "react";
import { api, call } from "@/lib/api/client";

export default function LoginPage({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (mode === "login") await call(api.POST("/api/auth/login", { body: { email, password } }));
      else await call(api.POST("/api/auth/register", { body: { email, password, name, persona: "aiml" } }));
      onDone();
      // full navigation so the app boots with the fresh session cookie (no stale auth state)
      window.location.assign(mode === "login" ? "/inbox" : "/onboarding");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card stack" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
        <div className="brand"><span className="brand-dot" aria-hidden>✓</span>GigBid</div>
        <h1>{mode === "login" ? "Sign in" : "Create your account"}</h1>
        <p className="muted">Agents find, assess and draft. You decide what gets sent.</p>
        {mode === "register" && <label><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} required /></label>}
        <label><span>Email</span><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" data-testid="email" /></label>
        <label><span>Password</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
               autoComplete={mode === "login" ? "current-password" : "new-password"} data-testid="password" /></label>
        {err && <div className="banner danger" role="alert">{err}</div>}
        <button className="btn-primary" disabled={busy} data-testid="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="btn-ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}