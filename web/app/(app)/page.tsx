"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Digest } from "@/lib/types";
import { inr, pct, tone } from "@/lib/format";
import { useData } from "@/components/data";
import { EventCard, RoutineList } from "@/components/cards";
import { BriefButton, briefScript } from "@/components/brief";
import { PortfolioChart } from "@/components/portfolio-chart";
import { ProfileButton } from "@/components/profile-menu";

const WINDOWS = [
  { key: "24h", label: "24H", spoken: "last 24 hours" },
  { key: "7d", label: "7D", spoken: "last 7 days" },
  { key: "30d", label: "30D", spoken: "last 30 days" },
] as const;

export default function Today() {
  const { me, meError, bootstrapped } = useData();
  const [win, setWin] = useState<(typeof WINDOWS)[number]["key"]>("24h");
  const [asOf, setAsOf] = useState<string>("");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const w = localStorage.getItem("finn.window");
      if (w === "24h" || w === "7d" || w === "30d") setWin(w);
    } catch {}
  }, []);

  useEffect(() => {
    if (!bootstrapped) return;
    let alive = true;
    setLoading(true);
    const qs = new URLSearchParams({ window: win });
    if (asOf) qs.set("as_of", asOf);
    api<Digest>(`/digest?${qs}`)
      .then((d) => { if (alive) { setDigest(d); setErr(null); } })
      .catch((e) => alive && setErr(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [win, asOf, bootstrapped]);

  function pick(w: (typeof WINDOWS)[number]["key"]) {
    setWin(w);
    try { localStorage.setItem("finn.window", w); } catch {}
  }

  const spoken = WINDOWS.find((w) => w.key === win)?.spoken ?? "window";
  const script = useMemo(() => briefScript(me, digest, spoken), [me, digest, spoken]);
  const dateLabel = asOf
    ? new Date(asOf).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })
    : new Date().toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  const t = me?.totals;

  return (
    <>
      <header className="topbar">
        <ProfileButton />
        <div className="brand">
          <span className="logo">FINN<b>.</b></span>
          <span className="when">{dateLabel}{asOf ? " · replay" : " · EOD"}</span>
        </div>
        <div className="seg">
          {WINDOWS.map((w) => (
            <button key={w.key} className={win === w.key ? "on" : ""} onClick={() => pick(w.key)}>{w.label}</button>
          ))}
          <span className="spacer" />
          <input
            type="date"
            className={`asof ${asOf ? "on" : ""}`}
            value={asOf}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setAsOf(e.target.value)}
            aria-label="Replay the digest as of a date"
            title="Replay: see the digest as it looked on a past date"
          />
          {asOf && <button onClick={() => setAsOf("")} aria-label="Back to today">✕</button>}
        </div>
      </header>

      <section className="pulse">
        <div className="row">
          <div>
            {t ? (
              <>
                <span className="v num">{inr(t.value, { compact: true })}</span>
                <span className={`d num ${tone(t.day_pnl)}`}>
                  {t.day_pnl >= 0 ? "▲" : "▼"} {pct(t.day_pct, 2)} · {inr(t.day_pnl, { sign: true, compact: true })}
                </span>
              </>
            ) : (
              <span className="v num dim">{meError ? "–" : "₹ …"}</span>
            )}
          </div>
          <BriefButton script={script} />
        </div>
        <PortfolioChart />
        <div className="counts">
          <span><b>{digest?.counts.matters ?? "–"}</b> matter</span>
          <span><b>{digest?.counts.routine_filings ?? "–"}</b> routine set aside</span>
          <span><b>{me?.holdings.length ?? "–"}</b> holdings</span>
          {t?.as_of && <span className="dim">prices {new Date(t.as_of).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>}
        </div>
      </section>

      {err && <div className="err">{err}</div>}

      <div className="sec"><span>── What matters</span>{digest && <span>{digest.counts.filings} filings scanned</span>}</div>

      {loading && !digest ? (
        <>
          <div className="skel" />
          <div className="skel" />
          <div className="skel sm" />
        </>
      ) : digest && digest.matters.length === 0 ? (
        <div className="empty">
          <b>Quiet {win === "24h" ? "day" : "stretch"}.</b>
          Nothing material across your holdings in the {spoken}
          {digest.counts.routine_filings ? `; ${digest.counts.routine_filings} routine filings set aside` : ""}.
          {win !== "30d" && (
            <div><button className="btn" onClick={() => pick(win === "24h" ? "7d" : "30d")}>See last {win === "24h" ? "7" : "30"} days</button></div>
          )}
        </div>
      ) : (
        digest?.matters.map((e) => <EventCard key={`${e.symbol}-${e.filing_ids[0]}`} e={e} />)
      )}

      {digest && <RoutineList items={digest.routine} mix={digest.routine_mix} />}
    </>
  );
}
