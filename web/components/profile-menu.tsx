"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { put } from "@/lib/api";
import { inr } from "@/lib/format";
import { useAuth } from "./auth";
import { DEFAULT_NAME, Face, isVerified, profileCompleteness, useData, VerifiedTick } from "./data";
import { Ring } from "./ring";

/** Top-right avatar on every screen: who you are, a glance at the account,
 *  shortcuts to settings, and the account actions (save, reset, sign out). */
export function ProfileButton() {
  const { session, signOut } = useAuth();
  const { me, unread, refreshMe, profile } = useData();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const user = session?.user as { email?: string | null; is_anonymous?: boolean; created_at?: string; email_confirmed_at?: string | null } | undefined;
  const guest = Boolean(user?.is_anonymous);
  const email = user?.email || null;
  const face = <Face profile={profile} email={email} guest={guest} />;
  const verified = isVerified(user);
  const displayName = profile?.full_name || (guest ? DEFAULT_NAME : email ?? "Signed in");
  const workLine = [profile?.work_role, profile?.work_company].filter(Boolean).join(" · ");
  const since = user?.created_at ? new Date(user.created_at).toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : null;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  async function reset() {
    setBusy("reset");
    try {
      await put("/holdings", (me?.holdings ?? []).map((h) => ({ symbol: h.symbol, quantity: 0 })));
      await refreshMe();
      setConfirmReset(false);
      setOpen(false);
    } finally {
      setBusy(null);
    }
  }

  async function out() {
    setBusy("out");
    await signOut();
    setOpen(false);
    router.replace("/login");
  }

  return (
    <>
      <button className={`avatar-btn ${open ? "on" : ""} ${guest ? "guest" : ""}`} onClick={() => setOpen(!open)} aria-label="Profile and settings" aria-expanded={open}>
        {face}
        {unread > 0 && <i className="dotbadge" />}
      </button>

      {open && (
        <>
          <div className="pm-backdrop" onClick={() => setOpen(false)} />
          <div className="pm-panel" role="menu">
            <div className="pm-head">
              <div className={`pm-av ${guest ? "guest" : ""}`}>{face}</div>
              <div style={{ minWidth: 0 }}>
                <div className="pm-name">{displayName}{verified && <VerifiedTick />}</div>
                {workLine && <div className="pm-work">{workLine}</div>}
                <div className="pm-sub">
                  <span className={`pm-tag ${guest ? "guest" : me?.user.is_admin ? "admin" : ""}`}>{guest ? "Guest" : me?.user.is_admin ? "Admin" : "Account"}</span>
                  {since && <span>since {since}</span>}
                </div>
              </div>
            </div>

            <button className="pm-edit" onClick={() => go("/profile")}>
              <span>✎</span>Edit profile<Ring pct={profileCompleteness(profile, email)} size={30} stroke={3} />
            </button>

            <div className="pm-stats">
              <div><b>{me ? inr(me.totals.value, { compact: true }) : "–"}</b><span>Portfolio</span></div>
              <div><b>{me?.holdings.length ?? "–"}</b><span>Holdings</span></div>
              <div><b>{unread}</b><span>Unread</span></div>
            </div>

            {guest && (
              <button className="pm-cta" onClick={() => go("/login")}>
                <span>→</span><div><b>Log in</b><small>Verify your email with a code · keeps this portfolio</small></div>
              </button>
            )}

            <nav className="pm-list">
              <button onClick={() => go("/you#portfolio")}><span>◫</span>Portfolio &amp; holdings</button>
              <button onClick={() => go("/you#rules")}><span>⚡</span>Alert rules</button>
              <button onClick={() => go("/alerts")}><span>◉</span>Alerts{unread > 0 && <em>{unread}</em>}</button>
              <button onClick={() => go("/you#sources")}><span>ⓘ</span>Data sources &amp; your documents</button>
            </nav>

            <div className="pm-list danger">
              {confirmReset ? (
                <div className="pm-confirm">
                  <span>Set all {me?.holdings.length ?? 0} holdings to 0? The companies stay on your list.</span>
                  <div>
                    <button onClick={() => setConfirmReset(false)}>Cancel</button>
                    <button className="yes" onClick={reset} disabled={busy === "reset"}>{busy === "reset" ? "…" : "Reset"}</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setConfirmReset(true)} disabled={!me?.holdings.some((h) => h.quantity > 0)}><span>↺</span>Reset portfolio</button>
              )}
              <button className="out" onClick={out} disabled={busy === "out"}><span>⏻</span>{busy === "out" ? "Signing out…" : "Sign out"}</button>
            </div>

            <div className="pm-foot">FINN v1.0 · Not investment advice · <Link href="/you#sources" onClick={() => setOpen(false)}>Sources</Link></div>
          </div>
        </>
      )}
    </>
  );
}
