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

/** Initials for an avatar: "Asha Rao" -> "AR", email -> "A", guest -> "G". */
export function initialsOf(profile: Profile | null, email: string | null | undefined, guest: boolean): string {
  const name = profile?.full_name?.trim();
  if (name) return name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  if (email && !guest) return email[0].toUpperCase();
  return "G";
}
