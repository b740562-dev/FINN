"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth";
import { DataProvider } from "@/components/data";
import { AskBar } from "@/components/ask-bar";
import { Tabs } from "@/components/tabs";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, ready } = useAuth();
  const router = useRouter();

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
      <div className="shell">{children}</div>
      <AskBar />
      <Tabs />
    </DataProvider>
  );
}
