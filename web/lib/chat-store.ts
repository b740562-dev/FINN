"use client";

/** Where the open Surya conversation lives between screens.
 *
 *  Per user and per browser session (sessionStorage), and wiped on every
 *  log-in and sign-out, so a new login always starts with a fresh chat and
 *  nobody sees the previous person's conversation on a shared device. Saved
 *  conversations for logged-in users live on the server (History). */

const PREFIX = "finn.surya.";

export function chatKey(userId: string | undefined): string {
  return `${PREFIX}v3:${userId ?? "anon"}`;
}

export function clearChatState(): void {
  try {
    for (const store of [sessionStorage, localStorage]) {
      for (let i = store.length - 1; i >= 0; i--) {
        const k = store.key(i);
        if (k?.startsWith(PREFIX)) store.removeItem(k);    // includes the old shared v1/v2 keys
      }
    }
  } catch {}
}
