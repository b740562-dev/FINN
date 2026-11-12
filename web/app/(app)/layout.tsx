"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";
import { DataProvider } from "@/components/data";
import { AskBar } from "@/components/ask-bar";
import { Tabs } from "@/components/tabs";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, ready } = useAuth();
  const router = useRouter();
  const path = usePathname() || "/";
  const fullScreen = path.startsWith("/surya");   // the chat window has its own composer

  useEffect(() => {
    if (ready && !session) router.replace("/login");
  }, [ready, session, router]);

  if (!ready || !session) {
    return (
      <div className="shell">
        <div className="topbar"><div className="brand"><span className="logo">FINN<b>.</b></span></div></div>
        <div className="skel" style={{ marginTop: 16 }} />
        <div className="skel" />
      </div>
    );
  }

  return (
    <DataProvider>
      <div className={`shell ${fullScreen ? "full" : ""}`}>{children}</div>
      {!fullScreen && <AskBar />}
      {!fullScreen && <Tabs />}
    </DataProvider>
  );
}
