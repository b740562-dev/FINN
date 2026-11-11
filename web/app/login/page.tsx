"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";
import { devModeAvailable } from "@/lib/devauth";

const GOOGLE = process.env.NEXT_PUBLIC_GOOGLE_AUTH === "1";

export default function Login() {
  const { session, ready, signInGuest, signInEmail, signInGoogle } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [devMode, setDevMode] = useState(false);

  useEffect(() => setDevMode(devModeAvailable()), []);
  useEffect(() => {
    if (ready && session) router.replace("/");
  }, [ready, session, router]);

  async function run(kind: string, fn: () => Promise<void>) {
    setBusy(kind);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="login">
      <span className="logo">FINN<b className="amber">.</b></span>
      <h1>Your portfolio,<br />filtered.</h1>
      <div className="feat">
        <div><b>◎</b><span>What matters</span></div>
        <div><b>⚡</b><span>Your alerts</span></div>
        <div><b>❝</b><span>Cited research</span></div>
      </div>

      <div className="actions">
        <div className="or" style={{ marginTop: 0 }}>SIGN IN</div>
        {GOOGLE && (
          <button className="btn block" disabled={!!busy} onClick={() => run("google", signInGoogle)}>
            Continue with Google
          </button>
        )}
        {sent ? (
          <div className="ok">Check {email} for a sign-in link.</div>
        ) : (
          <form
            onSubmit={(e) => { e.preventDefault(); if (email) run("email", async () => { await signInEmail(email); setSent(true); }); }}
            style={{ display: "grid", gap: 8 }}
          >
            <input className="txt" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            <button className="btn block" disabled={!!busy || !email}>{busy === "email" ? "SENDING…" : "EMAIL ME A SIGN-IN LINK"}</button>
          </form>
        )}

        <div className="or">OR</div>
        <button className="btn primary block" disabled={!!busy} onClick={() => run("guest", signInGuest)}>
          {busy === "guest" ? "SETTING UP YOUR DEMO PORTFOLIO…" : "TRY AS GUEST →"}
        </button>
        <div className="note" style={{ marginTop: 0 }}>7-stock demo portfolio · no sign-up</div>
        {err && <div className="err" style={{ margin: 0 }}>{err}</div>}
        {devMode && (
          <div className="flag" style={{ textAlign: "center" }}>Local demo mode</div>
        )}
        <div className="note">EOD data · NSE/BSE filings · not investment advice</div>
      </div>
    </main>
  );
}
