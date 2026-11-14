"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type OtpKind, useAuth } from "@/components/auth";
import { devModeAvailable } from "@/lib/devauth";
import { LogoMark } from "@/components/logo";

const GOOGLE = process.env.NEXT_PUBLIC_GOOGLE_AUTH === "1";
const RESEND_AFTER = 45; // seconds

const FEATURES: { title: string; icon: React.ReactNode }[] = [
  {
    title: "Key news",
    icon: <path d="M3 3v18h18M7 15l4-4 3 3 5-6" />,
  },
  {
    title: "Smart alerts",
    icon: <><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>,
  },
  {
    title: "Cited research",
    icon: <><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>,
  },
];

/** Supabase's auth errors, in plain words. Unknown errors keep their own text. */
function friendlyAuthError(e: unknown, step: string, guest: boolean): string {
  const err = e as { message?: string; status?: number; code?: string };
  const m = (err.message ?? "").toLowerCase();
  const stay = guest ? "keep using FINN as a guest" : "continue as a guest";
  if (err.status === 429 || m.includes("rate limit") || err.code === "over_email_send_rate_limit") {
    return `Too many code emails right now. Try again in a few minutes, or ${stay}.`;
  }
  if (m.includes("error sending") || m.includes("smtp") || m.includes("email provider")) {
    return `Email log-in is temporarily unavailable. Please ${stay} for now.`;
  }
  if (step === "verify" && (m.includes("expired") || m.includes("invalid") || m.includes("token"))) {
    return "That code is wrong or has expired. Check the latest email, or tap Resend code.";
  }
  if (m.includes("email") && (m.includes("invalid") || m.includes("valid email"))) {
    return "That doesn't look like a valid email address.";
  }
  if (m.includes("failed to fetch") || m.includes("network") || m.includes("load failed")) {
    return "Couldn't reach the sign-in service. Check your connection and try again.";
  }
  if (m.includes("signups not allowed") || m.includes("signup is disabled")) {
    return "New sign-ups are paused right now. You can still continue as a guest.";
  }
  return err.message || "Something went wrong. Please try again.";
}

export default function Login() {
  const { session, ready, signInGuest, sendCode, verifyCode, signInGoogle } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<OtpKind | null>(null);   // set once a code has been sent
  const [wait, setWait] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [devMode, setDevMode] = useState(false);
  const codeRef = useRef<HTMLInputElement>(null);

  const guest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);

  useEffect(() => setDevMode(devModeAvailable()), []);
  // A real (non-guest) session has nothing to do here. Guests come here to log in.
  useEffect(() => {
    if (ready && session && !guest) router.replace("/");
  }, [ready, session, guest, router]);
  useEffect(() => {
    if (!wait) return;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);
  useEffect(() => { if (kind) codeRef.current?.focus(); }, [kind]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(friendlyAuthError(e, label, guest));
    } finally {
      setBusy(null);
    }
  }

  const send = () => run("send", async () => {
    setKind(await sendCode(email.trim()));
    setCode("");
    setWait(RESEND_AFTER);
  });

  const verify = () => run("verify", async () => {
    if (!kind) return;
    await verifyCode(email.trim(), code, kind);
    router.replace("/");
  });

  return (
    <main className="login">
      {guest && <Link href="/" className="lg-back">‹ Back</Link>}
      <div className="lg-brand">
        <span className="lg-row"><LogoMark size={44} /><span className="logo">FINN</span></span>
        <span className="lg-quote">Your trusted investment companion</span>
      </div>
      <h1>{guest ? <>Log in<br />Keep your portfolio</> : <>Invest with<br />clarity</>}</h1>
      {!guest && (
        <ul className="feat">
          {FEATURES.map((f) => (
            <li key={f.title}>
              <span className="feat-ic">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
                  strokeLinecap="round" strokeLinejoin="round" aria-hidden>{f.icon}</svg>
              </span>
              <b className="feat-tx">{f.title}</b>
            </li>
          ))}
        </ul>
      )}

      <div className="actions">
        <div className="or" style={{ marginTop: 0 }}>{kind ? "ENTER THE CODE" : "LOG IN WITH EMAIL"}</div>
        {GOOGLE && !kind && (
          <button className="btn block" disabled={!!busy} onClick={() => run("google", signInGoogle)}>
            Continue with Google
          </button>
        )}

        {!kind ? (
          <form onSubmit={(e) => { e.preventDefault(); if (email) send(); }} style={{ display: "grid", gap: 8 }}>
            <input className="txt" type="email" placeholder="you@example.com" value={email}
              onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            <button className="btn primary block" disabled={!!busy || !email}>
              {busy === "send" ? "Sending code…" : "Send me a code"}
            </button>
            {guest && <div className="note" style={{ margin: 0 }}>Your guest portfolio, alerts and settings come with you.</div>}
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); if (code.length >= 6) verify(); }} style={{ display: "grid", gap: 8 }}>
            <div className="lg-sent">We sent a code to <b>{email}</b></div>
            <input ref={codeRef} className="txt otp" inputMode="numeric" autoComplete="one-time-code" maxLength={10}
              placeholder="••••••" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              aria-label="One-time code" />
            <button className="btn primary block" disabled={!!busy || code.length < 6}>
              {busy === "verify" ? "Verifying…" : "Verify and log in"}
            </button>
            <div className="lg-row">
              <button type="button" className="link" onClick={() => { setKind(null); setCode(""); setErr(null); }}>Change email</button>
              <button type="button" className="link" disabled={wait > 0 || !!busy} onClick={send}>
                {wait > 0 ? `Resend in ${wait}s` : "Resend code"}
              </button>
            </div>
          </form>
        )}

        {!guest && (
          <>
            <div className="or">OR</div>
            <button className="btn block" disabled={!!busy}
              onClick={() => run("guest", async () => { await signInGuest(); router.replace("/"); })}>
              {busy === "guest" ? "Setting up your demo portfolio…" : "Try as guest →"}
            </button>
          </>
        )}
        {err && <div className="err" style={{ margin: 0 }}>{err}</div>}
        {devMode && <div className="flag" style={{ textAlign: "center" }}>Local demo mode</div>}
      </div>
    </main>
  );
}
