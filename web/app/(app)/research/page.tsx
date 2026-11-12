"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useData } from "@/components/data";
import { ProfileButton } from "@/components/profile-menu";

type Co = { symbol: string; name: string; sector: string | null; market_cap_cr: number | null };
type Tag = "important" | "volatile" | "promising" | "steady";
type Signal = {
  symbol: string; name: string; weight?: number; tags: Tag[]; primary: Tag;
  vol_20d: number | null; ret_1m: number | null; ret_3m: number | null; pat_yoy: number | null; quarter: string | null;
  news: { materiality: number; category: string; headline: string } | null;
};
type Signals = { items: Signal[]; counts: Record<Tag, number>; rules: Record<Tag, string> };

// Companies with their annual report and four concall transcripts loaded: full document-based research.
const RESEARCH_SET = ["BEL", "TITAN", "ASIANPAINT", "KPITTECH"];
const TAG: Record<Tag, { label: string; icon: string }> = {
  important: { label: "Important", icon: "!" },
  volatile: { label: "Volatile", icon: "≋" },
  promising: { label: "Promising", icon: "↗" },
  steady: { label: "Steady", icon: "–" },
};

/** How much is going on: important news counts most, then a promising set-up, then volatility. */
const WEIGHT: Record<Tag, number> = { important: 3, promising: 2, volatile: 1, steady: 0 };
const score = (x: Signal) => x.tags.reduce((n, t) => n + WEIGHT[t], 0);

/** One plain sentence on why a company is worth a look, built from its numbers. */
function whyLine(x: Signal): string | null {
  if (x.news) return x.news.headline;
  if (x.tags.includes("promising")) {
    return `Profit ${pctTxt(x.pat_yoy)} YoY${x.quarter ? ` in ${x.quarter}` : ""}, with the price ${pctTxt(x.ret_3m)} over 3 months.`;
  }
  if (x.tags.includes("volatile") && x.vol_20d !== null) {
    return `Swinging about ${x.vol_20d.toFixed(0)}% a year over the last 20 days; ${pctTxt(x.ret_1m)} in a month.`;
  }
  return null;
}

function pctTxt(v: number | null) {
  if (v === null || v === undefined) return "–";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function Index() {
  const params = useSearchParams();
  const router = useRouter();
  const { me } = useData();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [all, setAll] = useState<Co[] | null>(null);
  const [sig, setSig] = useState<Signals | null>(null);
  const [filter, setFilter] = useState<Tag | null>(null);
  const [otherSig, setOtherSig] = useState<Signals | null>(null);
  const [showSteady, setShowSteady] = useState(false);

  useEffect(() => {
    api<Co[]>(`/companies?q=${encodeURIComponent(q.length >= 2 ? q : "")}`).then(setAll).catch(() => setAll([]));
  }, [q]);
  useEffect(() => {
    api<Signals>("/holdings/signals").then(setSig).catch(() => setSig(null));
  }, [me?.holdings.length]);

  const held = new Set(me?.holdings.map((h) => h.symbol) ?? []);
  const list = all ?? [];
  const searching = q.length >= 2;
  const picks = list.filter((c) => RESEARCH_SET.includes(c.symbol));
  const others = list.filter((c) => !held.has(c.symbol) && !RESEARCH_SET.includes(c.symbol));
  const holdings = (sig?.items ?? []).filter((x) => !filter || x.tags.includes(filter));
  const mcap = new Map(list.map((c) => [c.symbol, c.market_cap_cr]));
  const otherKey = others.map((c) => c.symbol).join(",");
  useEffect(() => {
    if (!otherKey || searching) return;
    api<Signals>(`/signals?symbols=${encodeURIComponent(otherKey)}`).then(setOtherSig).catch(() => setOtherSig(null));
  }, [otherKey, searching]);
  const otherShown = (otherSig?.items ?? []).filter((x) => !filter || x.tags.includes(filter))
    .sort((a, b) => score(b) - score(a) || (mcap.get(b.symbol) ?? 0) - (mcap.get(a.symbol) ?? 0));
  const featured = otherShown.filter((x) => x.primary !== "steady").slice(0, 3);
  const rest = otherShown.filter((x) => !featured.includes(x) && x.primary !== "steady");
  const steady = otherShown.filter((x) => x.primary === "steady");

  const worthCard = (x: Signal, big = false) => (
    <Link key={x.symbol} href={`/research/${x.symbol}`} className={`wc-card ${x.primary} ${big ? "big" : ""}`}>
      <div className="wc-top">
        <span className={`hs-ic ${x.primary}`} aria-hidden>{TAG[x.primary].icon}</span>
        <span className="wc-who"><b>{x.symbol}</b><small>{x.name}</small></span>
        <span className="hs-tags">{x.tags.map((t) => <span key={t} className={`hs-tag ${t}`}>{TAG[t].label}</span>)}</span>
      </div>
      {whyLine(x) && <p className="wc-why">{whyLine(x)}</p>}
      <div className="hs-stats">
        <span><small>3M</small><b className={(x.ret_3m ?? 0) >= 0 ? "up" : "dn"}>{pctTxt(x.ret_3m)}</b></span>
        <span><small>Volatility</small><b className={(x.vol_20d ?? 0) >= 35 ? "warn" : ""}>{x.vol_20d === null ? "–" : `${x.vol_20d.toFixed(0)}%`}</b></span>
        <span><small>PAT YoY</small><b className={(x.pat_yoy ?? 0) >= 0 ? "up" : "dn"}>{pctTxt(x.pat_yoy)}</b></span>
        <span><small>Mcap</small><b>{mcap.get(x.symbol) ? `₹${(mcap.get(x.symbol)! / 100000).toFixed(1)}L cr` : "–"}</b></span>
      </div>
      {big && <span className="wc-cta">Open research →</span>}
    </Link>
  );

  const legend = (s: Signals) => (
    <div className="hs-legend">
      {(Object.keys(TAG) as Tag[]).filter((t) => s.counts[t]).map((t) => (
        <button key={t} className={`hs-key ${t} ${filter === t ? "on" : ""}`} title={s.rules[t]}
          onClick={() => setFilter(filter === t ? null : t)} aria-pressed={filter === t}>
          <i />{s.counts[t]} {TAG[t].label}
        </button>
      ))}
    </div>
  );

  const row = (c: Co, cls = "other") => (
    <Link key={c.symbol} href={`/research/${c.symbol}`} className={`card ${cls}`} style={{ display: "block" }}>
      <div className="ch">
        <span><span className="tk">{c.symbol}</span> <span className="muted" style={{ fontSize: 12 }}>{c.name}</span></span>
        <span className="src">{c.market_cap_cr ? `₹${Math.round(c.market_cap_cr).toLocaleString("en-IN")} cr` : ""}</span>
      </div>
      {c.sector && <div className="co">{c.sector}</div>}
    </Link>
  );

  return (
    <>
      <header className="topbar">
        <ProfileButton />
        <div className="brand"><span className="logo">RESEARCH</span><span className="when">primary sources only</span></div>
        <form style={{ marginTop: 10 }} onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/research/${encodeURIComponent(q.trim().toUpperCase())}`); }}>
          <input className="txt" placeholder="Any NSE ticker · TCS, HAL, DMART" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
      </header>
      {!all && <><div className="skel sm" style={{ marginTop: 12 }} /><div className="skel sm" /></>}

      {searching ? (
        list.length > 0 && (
          <section>
            <div className="sec"><span>── Matches</span><span>{list.length}</span></div>
            {list.map((c) => row(c))}
          </section>
        )
      ) : (
        <>
          {picks.length > 0 && (
            <section>
              <div className="sec rp-h"><span>── Top research picks</span><span>full documents</span></div>
              <div className="rp-grid">
                {picks.map((c) => (
                  <Link key={c.symbol} href={`/research/${c.symbol}`} className="rp-card">
                    <span className="rp-badge">★ Deep research</span>
                    <b>{c.symbol}</b>
                    <small>{c.name}</small>
                    <span className="rp-meta">Annual report + 4 concalls</span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {sig && sig.items.length > 0 && (
            <section>
              <div className="sec"><span>── Your holdings</span><span>{sig.items.length}</span></div>
              {legend(sig)}
              {holdings.map((x) => (
                <Link key={x.symbol} href={`/research/${x.symbol}`} className={`hs-card ${x.primary}`}>
                  <div className="hs-top">
                    <span className={`hs-ic ${x.primary}`} aria-hidden>{TAG[x.primary].icon}</span>
                    <span className="hs-who"><b>{x.symbol}</b><small>{x.name}</small></span>
                    <span className="hs-tags">
                      {x.tags.map((t) => <span key={t} className={`hs-tag ${t}`}>{TAG[t].label}</span>)}
                    </span>
                  </div>
                  <div className="hs-stats">
                    <span><small>3M</small><b className={(x.ret_3m ?? 0) >= 0 ? "up" : "dn"}>{pctTxt(x.ret_3m)}</b></span>
                    <span><small>Volatility</small><b className={(x.vol_20d ?? 0) >= 35 ? "warn" : ""}>{x.vol_20d === null ? "–" : `${x.vol_20d.toFixed(0)}%`}</b></span>
                    <span><small>PAT YoY{x.quarter ? ` · ${x.quarter}` : ""}</small><b className={(x.pat_yoy ?? 0) >= 0 ? "up" : "dn"}>{pctTxt(x.pat_yoy)}</b></span>
                    <span><small>Weight</small><b>{(x.weight ?? 0).toFixed(0)}%</b></span>
                  </div>
                  {x.news && <div className="hs-news"><i aria-hidden>!</i>{x.news.headline}</div>}
                </Link>
              ))}
            </section>
          )}

          {others.length > 0 && (
            <section className="wc">
              <div className="wc-head">
                <div>
                  <h2>Worth checking</h2>
                  <p>Beyond your portfolio · ranked by what changed</p>
                </div>
                <span className="wc-count">Top {others.length}</span>
              </div>
              {otherSig ? (
                <>
                  {legend(otherSig)}
                  {featured.map((x) => worthCard(x, true))}
                  {rest.map((x) => worthCard(x))}
                  {steady.length > 0 && (
                    showSteady || filter === "steady"
                      ? steady.map((x) => worthCard(x))
                      : <button className="wc-more" onClick={() => setShowSteady(true)}>Show {steady.length} steady companies ▾</button>
                  )}
                </>
              ) : others.map((c) => row(c))}
            </section>
          )}
        </>
      )}

      {all && searching && list.length === 0 && (
        <div className="empty"><b>Not tracked yet</b>FINN can fetch it now.
          <div><Link className="btn" href={`/research/${encodeURIComponent(q.toUpperCase())}`}>Research {q.toUpperCase()} →</Link></div>
        </div>
      )}
    </>
  );
}

export default function ResearchIndex() {
  return <Suspense fallback={<div className="skel" style={{ marginTop: 16 }} />}><Index /></Suspense>;
}
