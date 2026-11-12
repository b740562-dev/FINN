"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { DEV_TOKEN, DEV_USER_ID, devModeAvailable, devSignedIn, setDevSignedIn } from "@/lib/devauth";
import { clearChatState } from "@/lib/chat-store";

type AuthCtx = {
  session: Session | null;
  ready: boolean;
  signInGuest: () => Promise<void>;
  /** Email a one-time code. Returns which verification the code is for. */
  sendCode: (email: string) => Promise<OtpKind>;
  verifyCode: (email: string, code: string, kind: OtpKind) => Promise<void>;
  signInGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
};

/** "email": sign in (or sign up) with a code. "email_change": a guest attaching
 *  an email to their own account, which keeps their portfolio and settings. */
export type OtpKind = "email" | "email_change";

const Ctx = createContext<AuthCtx | null>(null);

/** Minimal session object for local demo mode (see lib/devauth.ts). */
function devSession(): Session {
  // NEXT_PUBLIC_DEV_MEMBER=1 (with the API's FINN_DEV_MEMBER=1) demos the logged-in experience locally.
  const member = process.env.NEXT_PUBLIC_DEV_MEMBER === "1";
  return {
    access_token: DEV_TOKEN, refresh_token: "", expires_in: 3600, token_type: "bearer",
    user: { id: DEV_USER_ID, is_anonymous: !member, email: member ? "demo@finn.local" : undefined,
            email_confirmed_at: member ? new Date().toISOString() : undefined, aud: "authenticated",
            app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString() },
  } as unknown as Session;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (devModeAvailable()) {            // local demo mode: no Supabase calls at all
      setSession(devSignedIn() ? devSession() : null);
      setReady(true);
      return;
    }
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const signInGuest = useCallback(async () => {
    clearChatState();                    // a new login starts Surya with a fresh chat
    if (devModeAvailable()) {
      setDevSignedIn(true);
      setSession(devSession());
      return;
    }
    const { error } = await supabase().auth.signInAnonymously();
    if (error) throw error;
  }, []);

  const sendCode = useCallback(async (email: string): Promise<OtpKind> => {
    if (devModeAvailable()) {
      throw new Error("Email log-in runs on the live app. Local demo mode doesn't reach Supabase.");
    }
    const sb = supabase();
    const { data } = await sb.auth.getSession();
    if (data.session?.user.is_anonymous) {
      // Guest: attach the email to this account, so the portfolio comes along.
      const { error } = await sb.auth.updateUser({ email });
      if (!error) return "email_change";
      if (!/already|registered|exists/i.test(error.message)) throw error;
      // The email already has an account: sign in to that one instead.
    }
    const { error } = await sb.auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
    if (error) throw error;
    return "email";
  }, []);

  const verifyCode = useCallback(async (email: string, code: string, kind: OtpKind) => {
    const sb = supabase();
    const { error } = await sb.auth.verifyOtp({ email, token: code.trim(), type: kind });
    if (error) throw error;
    clearChatState();
    if (kind === "email_change") await sb.auth.refreshSession();   // pick up the verified email
  }, []);

  const signInGoogle = useCallback(async () => {
    const { error } = await supabase().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    if (devModeAvailable()) {
      setDevSignedIn(false);
      setSession(null);
    } else {
      await supabase().auth.signOut();
    }
    sessionStorage.removeItem("finn.bootstrapped");
    clearChatState();
  }, []);

  return (
    <Ctx.Provider value={{ session, ready, signInGuest, sendCode, verifyCode, signInGoogle, signOut }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
