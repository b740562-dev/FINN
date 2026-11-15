"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/** Supabase traffic goes through our own domain (/sb → project, see
 *  next.config.ts) so it works on networks that block *.supabase.co.
 *  Set NEXT_PUBLIC_SUPABASE_DIRECT=1 to talk to Supabase directly instead. */
function supabaseUrl(): string {
  if (process.env.NEXT_PUBLIC_SUPABASE_DIRECT === "1" || typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_SUPABASE_URL as string;
  }
  return `${window.location.origin}/sb`;
}

/** Back from Google with "this email already has an account" (Supabase uses
 *  several codes for it, depending on how the account was first created). */
export function accountTaken(q: URLSearchParams): boolean {
  const code = q.get("error_code") ?? "";
  const desc = q.get("error_description") ?? "";
  return ["identity_already_exists", "email_exists", "user_already_exists"].includes(code)
    || /already (been )?registered|already exists|already linked/i.test(desc);
}

/** Set while FINN retries a Google sign-in into the existing account, so a
 *  second failure is shown instead of looping. */
export const GOOGLE_RETRY = "finn.googleRetry";

/** Which sign-in methods are switched on in Supabase (public endpoint). */
export async function googleEnabled(): Promise<boolean> {
  try {
    const r = await fetch(`${supabaseUrl()}/auth/v1/settings`, {
      headers: { apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string },
    });
    if (!r.ok) return false;
    const d = (await r.json()) as { external?: { google?: boolean } };
    return Boolean(d.external?.google);
  } catch {
    return false;
  }
}

export function supabase(): SupabaseClient {
  if (!client) {
    client = createClient(supabaseUrl(), process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        // Keep the same storage key whichever URL is used, so sessions survive a switch.
        storageKey: "finn-auth",
      },
    });
  }
  return client;
}
