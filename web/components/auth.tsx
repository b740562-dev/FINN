"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

type AuthCtx = {
  session: Session | null;
  ready: boolean;
  signInGuest: () => Promise<void>;
  signInEmail: (email: string) => Promise<void>;
  signInGoogle: () => Promise<void>;
  saveAccountEmail: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const signInGuest = useCallback(async () => {
    const { error } = await supabase().auth.signInAnonymously();
    if (error) throw error;
  }, []);

  const signInEmail = useCallback(async (email: string) => {
    const { error } = await supabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    if (error) throw error;
  }, []);

  const signInGoogle = useCallback(async () => {
    const { error } = await supabase().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) throw error;
  }, []);

  // Guest -> permanent account without losing settings: attach an email to the
  // anonymous user (Supabase sends a confirmation link).
  const saveAccountEmail = useCallback(async (email: string) => {
    const { error } = await supabase().auth.updateUser({ email });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    await supabase().auth.signOut();
    sessionStorage.removeItem("finn.bootstrapped");
  }, []);

  return (
    <Ctx.Provider value={{ session, ready, signInGuest, signInEmail, signInGoogle, saveAccountEmail, signOut }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
