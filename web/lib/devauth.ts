"use client";

// Local demo mode (development only): lets the app run on a network that
// blocks *.supabase.co. Active ONLY when NEXT_PUBLIC_DEV_AUTH=1 AND the page
// is served from localhost; the API independently requires FINN_DEV_AUTH=1
// and a request from 127.0.0.1. Never set either flag in a deployment.
export const DEV_TOKEN = "dev-local-demo";
export const DEV_USER_ID = "00000000-0000-4000-8000-00000000f1a0";
const KEY = "finn.devSession";

export function devModeAvailable(): boolean {
  if (process.env.NEXT_PUBLIC_DEV_AUTH !== "1" || typeof window === "undefined") return false;
  return ["localhost", "127.0.0.1"].includes(window.location.hostname);
}

export function devSignedIn(): boolean {
  try {
    return devModeAvailable() && sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setDevSignedIn(on: boolean): void {
  try {
    if (on) sessionStorage.setItem(KEY, "1");
    else sessionStorage.removeItem(KEY);
  } catch {}
}
