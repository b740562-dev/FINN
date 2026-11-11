"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { post } from "@/lib/api";
import { inr } from "@/lib/format";
import { useAuth } from "./auth";
import { initialsOf, profileCompleteness, useData } from "./data";
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

  const user = session?.user as { email?: string | null; is_anonymous?: boolean; created_at?: string } | undefined;
  const guest = Boolean(user?.is_anonymous);
  const email = user?.email || null;
  const initial = initialsOf(profile, email, guest);
  const displayName = profile?.full_name || (guest ? "Guest investor" : email ?? "Signed in");
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
      await post("/holdings/reset");
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
      <button className={`avatar-btn ${open ? "on" : ""}`} onClick={() => setOpen(!open)} aria-label="Profile and settings" aria-expanded={open}>
        {initial}
        {unread > 0 && <i className="dotbadge" />}
      </button>

      {open && (
        <>
          <div className="pm-backdrop" onClick={() => setOpen(false)} />
          <div className="pm-panel" role="menu">
            <div className="pm-head">
              <div className="pm-av">{initial}</div>
              <div style={{ minWidth: 0 }}>
                <div className="pm-name">{displayName}</div>
                {workLine && <div className="pm-work">{workLine}</div>}
                <div className="pm-sub">
                  <span className={`pm-tag ${guest ? "guest" : ""}`}>{guest ? "Guest" : "Account"}</span>
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
              <button className="pm-cta" onClick={() => go("/profile")}>
                <span>☁</span><div><b>Save your account</b><small>Keep this portfolio across devices</small></div>
              </button>
            )}

            <nav className="pm-list">
              <button onClick={() => go("/you#portfolio")}><span>◫</span>Portfolio &amp; holdings</button>
              <button onClick={() => go("/you#rules")}><span>⚡</span>Alert rules</button>
              <button onClick={() => go("/alerts")}><span>◉</span>Alerts{unread > 0 && <em>{unread}</em>}</button>
              {me?.user.is_admin && <button onClick={() => go("/you#usage")}><span>⚙</span>How FINN thinks<em>admin</em></button>}
              <button onClick={() => go("/you#sources")}><span>ⓘ</span>Data sources &amp; your documents</button>
            </nav>

            <div className="pm-list danger">
              {confirmReset ? (
                <div className="pm-confirm">
                  <span>Replace your holdings with the 18-stock demo portfolio?</span>
                  <div>
                    <button onClick={() => setConfirmReset(false)}>Cancel</button>
                    <button className="yes" onClick={reset} disabled={busy === "reset"}>{busy === "reset" ? "…" : "Reset"}</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setConfirmReset(true)}><span>↺</span>Reset demo portfolio</button>
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
