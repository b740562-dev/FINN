"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DigestEvent } from "@/lib/types";
import { crShort } from "./cards";
import { NewsRow, useNewsSheet } from "./news";

type Result = {
  company: { symbol: string; name: string | null; sector: string | null; market_cap_cr: number | null };
  held: boolean;
  days: number;
  counts: { filings: number; matters: number; routine_filings: number };
  matters: DigestEvent[];
  routine: DigestEvent[];
};

const WINDOWS = [[30, "30D"], [90, "90D"], [365, "1Y"]] as const;

/** "Before I buy it: has this company said anything important lately?"
 *  Works for any NSE company, held or not. */
export function NewsSearch() {
  const [q, setQ] = useState("");
  const [sugg, setSugg] = useState<{ symbol: string; name: string }[]>([]);
  const [sym, setSym] = useState<string | null>(null);
  const [days, setDays] = useState<number>(90);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [focus, setFocus] = useState(false);
  const sheet = useNewsSheet();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setSugg([]); return; }
    const h = setTimeout(() => api<{ symbol: string; name: string }[]>(`/companies?q=${encodeURIComponent(t)}`)
      .then((r) => setSugg(r.slice(0, 6))).catch(() => setSugg([])), 180);
    return () => clearTimeout(h);
  }, [q]);

  useEffect(() => {
    if (!sym) return;
    let alive = true;
    setBusy(true);
    setErr(null);
    api<Result>(`/news/${encodeURIComponent(sym)}?days=${days}`)
      .then((r) => { if (alive) setRes(r); })
      .catch((e) => { if (alive) { setRes(null); setErr((e as Error).message); } })
      .finally(() => alive && setBusy(false));
    return () => { alive = false; };
  }, [sym, days]);

  function pick(s: string) {
    setSym(s.toUpperCase());
    setQ("");
    setSugg([]);
    inputRef.current?.blur();
  }

  function clear() {
    setSym(null); setRes(null); setErr(null);
  }

  const typed = q.trim().toUpperCase().replace(/\s+/g, "");
  const exact = sugg.some((s) => s.symbol === typed);
  const showList = focus && q.trim().length >= 2;
  const important = res?.matters ?? [];

  return (
    <section className="ns-box">
      <form className="ns-search" onSubmit={(e) => { e.preventDefault(); if (sugg[0]) pick(sugg[0].symbol); else if (typed) pick(typed); }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
          <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
        </svg>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder="Check any company for important news" aria-label="Search a company" autoComplete="off" />
        {q && <button type="button" className="ns-clr" onClick={() => setQ("")} aria-label="Clear">✕</button>}
      </form>

      {showList && (sugg.length > 0 || typed) && (
        <div className="ns-sugg">
          {sugg.map((s) => (
            <button key={s.symbol} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(s.symbol)}>
              <b>{s.symbol}</b><span>{s.name}</span>
            </button>
          ))}
          {!exact && /^[A-Z0-9&-]{2,20}$/.test(typed) && (
            <button className="ns-any" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(typed)}>
              <b>{typed}</b><span>Look up this NSE symbol</span>
            </button>
          )}
        </div>
      )}

      {sym && (
        <div className="ns-res">
          <div className="ns-rh">
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="ns-rt">
                <b>{res?.company.symbol ?? sym}</b>
                {res && <span className={`ns-held ${res.held ? "on" : ""}`}>{res.held ? "In your portfolio" : "Not held"}</span>}
              </div>
              <div className="ns-rs">
                {res ? [res.company.name, res.company.sector, res.company.market_cap_cr ? `₹${crShort(res.company.market_cap_cr)} mcap` : null].filter(Boolean).join(" · ") : busy ? `Reading ${sym}'s latest filings…` : ""}
              </div>
            </div>
            <button className="ns-x2" onClick={clear} aria-label="Close search result">✕</button>
          </div>

          <div className="seg ns-win">
            {WINDOWS.map(([d, l]) => (
              <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{l}</button>
            ))}
          </div>

          {busy && !res && <div className="skel sm" style={{ margin: "10px 0 0" }} />}
          {err && <div className="err" style={{ margin: "10px 0 0" }}>{err}</div>}

          {res && (
            <>
              <div className={`ns-verdict ${important.length ? "hot" : "calm"}`}>
                <span className="ns-big">{important.length || "✓"}</span>
                <span>
                  <b>{important.length ? `important ${important.length === 1 ? "update" : "updates"}` : "Nothing important"}</b>
                  <small>
                    last {days === 365 ? "year" : `${days} days`} · {res.counts.filings} filings read
                    {res.counts.routine_filings ? ` · ${res.counts.routine_filings} routine` : ""}
                  </small>
                </span>
              </div>
              {important.length > 0 && (
                <div className="nlist" style={{ margin: "10px 0 0" }}>
                  {important.map((e) => <NewsRow key={`${e.symbol}-${e.filing_ids[0]}`} e={e} onOpen={sheet.open} />)}
                </div>
              )}
              <div className="ns-foot">
                <span>FINN reads the company&apos;s own exchange filings.</span>
                <Link className="link" href={`/research/${res.company.symbol}`}>Research {res.company.symbol} →</Link>
              </div>
            </>
          )}
        </div>
      )}
      {sheet.sheet}
    </section>
  );
}
