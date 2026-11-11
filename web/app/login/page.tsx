"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";

const GOOGLE = process.env.NEXT_PUBLIC_GOOGLE_AUTH === "1";

export default function Login() {
  const { session, ready, signInGuest, signInEmail, signInGoogle } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
      <h1>Your portfolio, filtered.<br />Only what matters, and why.</h1>
      <p>FINN watches every filing and end-of-day move across your holdings, ranks what&apos;s material, and buries the rest.</p>
      <ul>
        <li><span>01</span>A ranked daily digest: results as numbers, new executives with a bio, routine paperwork folded away.</li>
        <li><span>02</span>Alerts on the moves you define as unusual.</li>
        <li><span>03</span>Research on any NSE company, grounded in its own filings, with every claim cited.</li>
      </ul>

      <div className="actions">
        <button className="btn primary block" disabled={!!busy} onClick={() => run("guest", signInGuest)}>
          {busy === "guest" ? "SETTING UP YOUR DEMO PORTFOLIO…" : "TRY AS GUEST →"}
        </button>
        <div className="note" style={{ marginTop: 0 }}>Starts with an 18-stock demo portfolio. Nothing to fill in.</div>

        <div className="or">OR SIGN IN</div>
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
        {err && <div className="err" style={{ margin: 0 }}>{err}</div>}
        <div className="note">End-of-day data · NSE/BSE filings via screener.in · Not investment advice.</div>
      </div>
    </main>
  );
}
