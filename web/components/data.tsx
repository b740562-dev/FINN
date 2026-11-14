"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, post } from "@/lib/api";
import type { Me, Profile } from "@/lib/types";

type DataCtx = {
  me: Me | null;
  meError: string | null;
  unread: number;
  setUnread: (n: number) => void;
  refreshMe: () => Promise<void>;
  profile: Profile | null;
  setProfile: (p: Profile) => void;
  bootstrapped: boolean;
};

const Ctx = createContext<DataCtx | null>(null);

/** Per-session app data: the user's portfolio (/me), their profile, and the
 *  unread-alert badge. On first load of a session it calls /bootstrap, which
 *  backfills the last 30 days of alerts so a brand-new account opens to a live inbox. */
export function DataProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  const refreshMe = useCallback(async () => {
    try {
      setMe(await api<Me>("/me"));
      setMeError(null);
    } catch (e) {
      setMeError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (!sessionStorage.getItem("finn.bootstrapped")) {
        try {
          await post("/bootstrap");
          sessionStorage.setItem("finn.bootstrapped", "1");
        } catch {
          /* non-fatal: inbox fills on the next scheduler run */
        }
      }
      setBootstrapped(true);
      await refreshMe();
      try {
        const a = await api<{ unread: number }>("/alerts?limit=1");
        setUnread(a.unread);
      } catch {}
      try {
        setProfile(await api<Profile>("/profile"));
      } catch {}
    })();
  }, [refreshMe]);

  return (
    <Ctx.Provider value={{ me, meError, unread, setUnread, refreshMe, profile, setProfile, bootstrapped }}>
      {children}
    </Ctx.Provider>
  );
}

export function useData(): DataCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useData outside DataProvider");
  return c;
}

const COMPLETENESS_FIELDS = ["full_name", "gender", "city", "work_company", "work_role", "education", "experience", "bio"] as const;

/** Share of the profile that's filled in (8 profile fields + email), 0-100. */
export function profileCompleteness(p: Partial<Profile> | null, email: string | null | undefined): number {
  const filled = COMPLETENESS_FIELDS.filter((k) => String(p?.[k] ?? "").trim() !== "").length + (email ? 1 : 0);
  return Math.round((filled / (COMPLETENESS_FIELDS.length + 1)) * 100);
}

/** Name shown for a guest who hasn't set their own. */
export const DEFAULT_NAME = "Guest";

/** Initials for an avatar: "Asha Rao" -> "AR", email -> "A". */
export function initialsOf(profile: Profile | null, email: string | null | undefined, guest: boolean): string {
  const name = profile?.full_name?.trim();
  if (name) return name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  if (email && !guest) return email[0].toUpperCase();
  return "G";
}

/** Avatar contents: the generic person silhouette for guests, initials otherwise. */
export function Face({ profile, email, guest }: { profile: Profile | null; email: string | null | undefined; guest: boolean }) {
  if (guest) {
    return (
      <svg className="face-guest" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
        strokeLinecap="round" aria-label="Guest">
        <circle cx="12" cy="8.5" r="4" />
        <path d="M4.5 20.5c0-4.1 3.4-6.5 7.5-6.5s7.5 2.4 7.5 6.5" />
      </svg>
    );
  }
  return <EmailPhoto email={email} photo={profile?.avatar_url} fallback={initialsOf(profile, email, guest)} />;
}

/** The account's photo: Google's when signed in with Google, else the public photo tied to the email (Gravatar, looked up by a SHA-256 hash, so
 *  the address itself never leaves the app). Initials until it loads, and for
 *  good if the email has no photo. */
function EmailPhoto({ email, photo, fallback }: { email: string | null | undefined; photo?: string | null; fallback: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  useEffect(() => {
    setOk(false);
    setSrc(null);
    if (photo) { setSrc(photo); return; }            // Google's own photo wins
    const e = email?.trim().toLowerCase();
    if (!e || !globalThis.crypto?.subtle) return;
    let live = true;
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(e)).then((buf) => {
      const hex = Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
      if (live) setSrc(`https://gravatar.com/avatar/${hex}?s=160&d=404`);
    }).catch(() => {});
    return () => { live = false; };
  }, [email, photo]);
  return (
    <>
      {!ok && fallback}
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="face-img" src={src} alt="" referrerPolicy="no-referrer" style={ok ? undefined : { display: "none" }}
          onLoad={() => setOk(true)} onError={() => setSrc(null)} />
      )}
    </>
  );
}

type AuthUser = { is_anonymous?: boolean; email?: string | null; email_confirmed_at?: string | null } | undefined;

/** A real account whose email was confirmed with the one-time code. */
export function isVerified(u: AuthUser): boolean {
  return Boolean(u && !u.is_anonymous && u.email && u.email_confirmed_at);
}

export function VerifiedTick({ size = 15 }: { size?: number }) {
  return (
    <span className="vtick" title="Email verified" aria-label="Email verified" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62} fill="none" stroke="currentColor"
        strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
    </span>
  );
}
