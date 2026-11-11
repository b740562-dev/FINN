"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useData } from "@/components/data";

type Co = { symbol: string; name: string; sector: string | null; market_cap_cr: number | null };
const RESEARCH_SET = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"];

function Index() {
  const params = useSearchParams();
  const router = useRouter();
  const { me } = useData();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [all, setAll] = useState<Co[] | null>(null);

  useEffect(() => {
    api<Co[]>(`/companies?q=${encodeURIComponent(q.length >= 2 ? q : "")}`).then(setAll).catch(() => setAll([]));
  }, [q]);

  const held = new Set(me?.holdings.map((h) => h.symbol) ?? []);
  const list = all ?? [];
  const groups: [string, Co[]][] = q.length >= 2
    ? [["Matches", list]]
    : [
        ["Research picks", list.filter((c) => RESEARCH_SET.includes(c.symbol))],
        ["Your holdings", list.filter((c) => held.has(c.symbol))],
        ["Other tracked", list.filter((c) => !held.has(c.symbol) && !RESEARCH_SET.includes(c.symbol))],
      ];

  return (
    <>
      <header className="topbar">
        <div className="brand"><span className="logo">RESEARCH</span><span className="when">primary sources only</span></div>
        <form style={{ marginTop: 10 }} onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/research/${encodeURIComponent(q.trim().toUpperCase())}`); }}>
          <input className="txt" placeholder="Any NSE ticker, e.g. TCS, HAL, DMART" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
      </header>
      <p className="sub" style={{ padding: "10px 16px 0", color: "var(--dim)", fontSize: 11.5 }}>
        Works on any NSE company: numbers load instantly from its filings; add its annual report and concall transcripts to unlock
        promise-vs-delivered and cited narrative.
      </p>
      {!all && <><div className="skel sm" style={{ marginTop: 12 }} /><div className="skel sm" /></>}
      {groups.filter(([, xs]) => xs.length).map(([title, xs]) => (
        <section key={title}>
          <div className="sec"><span>── {title}</span><span>{xs.length}</span></div>
          {xs.map((c) => (
            <Link key={c.symbol} href={`/research/${c.symbol}`} className="card other" style={{ display: "block" }}>
              <div className="ch">
                <span><span className="tk">{c.symbol}</span> <span className="muted" style={{ fontSize: 12 }}>{c.name}</span></span>
                <span className="src">{c.market_cap_cr ? `₹${Math.round(c.market_cap_cr).toLocaleString("en-IN")} cr` : ""}</span>
              </div>
              {c.sector && <div className="co">{c.sector}</div>}
            </Link>
          ))}
        </section>
      ))}
      {all && q.length >= 2 && list.length === 0 && (
        <div className="empty"><b>Not tracked yet.</b>Open it anyway: FINN will fetch {q.toUpperCase()} on demand.
          <div><Link className="btn" href={`/research/${encodeURIComponent(q.toUpperCase())}`}>RESEARCH {q.toUpperCase()} →</Link></div>
        </div>
      )}
    </>
  );
}

export default function ResearchIndex() {
  return <Suspense fallback={<div className="skel" style={{ marginTop: 16 }} />}><Index /></Suspense>;
}
