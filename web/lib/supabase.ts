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
