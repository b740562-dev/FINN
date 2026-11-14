"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";
import { DataProvider } from "@/components/data";
import { AskBar } from "@/components/ask-bar";
import { Tabs } from "@/components/tabs";
import { Logo } from "@/components/logo";

/** The floating Ask-me button and the tab bar. Reads the URL, so it lives in
 *  its own Suspense boundary (the page itself can still prerender). The Surya
 *  chat is full-screen with its own composer, so it shows neither. */
function Chrome() {
  const path = usePathname() || "/";
  if (path.startsWith("/surya")) return null;
  return (
    <>
      <AskBar />
      <Tabs />
    </>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !session) router.replace("/login");
  }, [ready, session, router]);

  if (!ready || !session) {
    return (
      <div className="shell">
        <div className="topbar"><div className="brand"><Logo size={28} /></div></div>
        <div className="skel" style={{ marginTop: 16 }} />
        <div className="skel" />
      </div>
    );
  }

  return (
    <DataProvider>
      <div className="shell">{children}</div>
      <Suspense fallback={null}><Chrome /></Suspense>
    </DataProvider>
  );
}
