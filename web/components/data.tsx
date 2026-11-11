"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, post } from "@/lib/api";
import type { Me } from "@/lib/types";

type DataCtx = {
  me: Me | null;
  meError: string | null;
  unread: number;
  setUnread: (n: number) => void;
  refreshMe: () => Promise<void>;
  bootstrapped: boolean;
};

const Ctx = createContext<DataCtx | null>(null);

/** Per-session app data: the user's portfolio (/me) and the unread-alert badge.
 *  On first load of a session it calls /bootstrap, which backfills the last
 *  30 days of alerts so a brand-new account opens to a live inbox. */
export function DataProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);
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
    })();
  }, [refreshMe]);

  return <Ctx.Provider value={{ me, meError, unread, setUnread, refreshMe, bootstrapped }}>{children}</Ctx.Provider>;
}

export function useData(): DataCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useData outside DataProvider");
  return c;
}
