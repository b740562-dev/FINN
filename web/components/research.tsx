"use client";

import { Fragment, useState } from "react";
import type { Citation, Metric, Section } from "@/lib/types";
import { crore, pct } from "@/lib/format";
import { KpiTiles, ResultsTable } from "./cards";
import { Spark } from "./spark";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

// ---------------------------------------------------------------- citations
export function CiteSheet({ c, onClose }: { c: Citation | null; onClose: () => void }) {
  if (!c) return null;
  return (
    <div className="sheet-bg" onClick={onClose} role="dialog" aria-modal>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="grab" />
        <div className="dim" style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em" }}>SOURCE [{c.id}]</div>
        <div style={{ fontWeight: 700, marginTop: 4 }}>{c.doc_label}{c.page ? ` · p.${c.page}` : ""}</div>
        <blockquote>{c.quote}</blockquote>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

/** Render text containing [c1] / [n2] markers as citation chips. */
export function Cited({ text, cites, open }: { text: string; cites: Citation[]; open: (c: Citation) => void }) {
  const parts = String(text ?? "").split(/(\[[a-z]\d+(?:\s*,\s*[a-z]\d+)*\])/gi);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[([a-z]\d+(?:\s*,\s*[a-z]\d+)*)\]$/i);
        if (!m) return <Fragment key={i}>{p}</Fragment>;
        return [...new Set(m[1].split(/\s*,\s*/))].map((id) => {
          const c = cites.find((x) => x.id.toLowerCase() === id.toLowerCase());
          return c ? <button key={`${i}-${id}`} className="cite" onClick={(e) => { e.stopPropagation(); open(c); }}>{id}</button> : null;
        });
      })}
    </>
  );
}

function CiteIds({ ids, cites, open }: { ids?: string[] | string | null; cites: Citation[]; open: (c: Citation) => void }) {
  // De-duplicate: a point can cite the same source twice, and keys must be unique.
  const list = [...new Set((Array.isArray(ids) ? ids : ids ? [ids] : []).filter(Boolean))];
  return (
    <>
      {list.map((id) => {
        const c = cites.find((x) => x.id === id);
        return c ? <button key={id} className="cite" onClick={(e) => { e.stopPropagation(); open(c); }}>{id}</button> : null;
      })}
    </>
  );
}

// ---------------------------------------------------------------- shells
export function SectionShell({ title, s, children }: { title: string; s: Section<Any> | null | "loading"; children?: React.ReactNode }) {
  const meta = s && s !== "loading" && s.model ? s.model.replace("gemini-", "") : s && s !== "loading" && s.status === "ready" ? "computed" : "";
  return (
    <section className="rsec">
      <header><h2>{title}</h2><span>{s === "loading" || !s ? "…" : meta}</span></header>
      <div className="body">
        {s === "loading" || !s ? <div className="skel sm" style={{ margin: 0 }} />
          : s.status === "error" ? <div className="err" style={{ margin: 0 }}>Couldn&apos;t build this section.</div>
          : children}
      </div>
    </section>
  );
}

function NeedsDocs() {
  return <p className="needs">📄 Add this company&apos;s concall transcripts below to unlock.</p>;
}

/** Text that shows 2 lines until tapped. */
function Clamp({ children, lines = 2 }: { children: React.ReactNode; lines?: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={open ? "" : "clamp"} style={{ WebkitLineClamp: open ? undefined : lines }} onClick={() => setOpen(!open)}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- snapshot
export function SnapshotView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  const f = s.content?.financial ?? {};
  const ttm = f.ttm ?? {};
  const r = f.ratios ?? {};
  const biz = s.content?.business;
  const lq = f.latest_quarter;
  const tiles: [string, string][] = [
    ["Mcap", f.market_cap_cr != null ? `₹${crore(f.market_cap_cr)} cr` : "–"],
    ["TTM revenue", ttm.revenue != null ? `₹${crore(ttm.revenue)} cr` : "–"],
    ["TTM PAT", ttm.pat != null ? `₹${crore(ttm.pat)} cr` : "–"],
    ["EBITDA mgn", ttm.ebitda_margin != null ? `${Number(ttm.ebitda_margin).toFixed(1)}%` : "–"],
    ["ROCE", r.roce != null ? `${r.roce}%` : "–"],
    ["ROE", r.roe != null ? `${r.roe}%` : "–"],
  ];
  return (
    <>
      <div className="kv">{tiles.map(([k, v]) => <div key={k}>{k}<b>{v}</b></div>)}</div>
      {biz?.summary && (
        <div className="bizsum">
          <Clamp><Cited text={biz.summary} cites={s.citations} open={open} /><CiteIds ids={biz.summary_citations} cites={s.citations} open={open} /></Clamp>
        </div>
      )}
      {Array.isArray(biz?.segments) && biz.segments.length > 0 && (
        <div className="chiprow">
          {biz.segments.map((g: Any, i: number) => (
            <span key={i} className="pill" title={g.note}>{g.name}{g.share_pct != null ? ` · ${g.share_pct}%` : ""}</span>
          ))}
        </div>
      )}
      {lq?.status !== "pending" && lq?.metrics && (
        <div style={{ marginTop: 12 }}>
          <div className="mini-h">Latest quarter · {lq.quarter_label}</div>
          <KpiTiles card={{ status: "ready", ...lq }} />
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- health
type Badge = [string, "good" | "warn" | "bad"];

function healthBadges(c: Any): Badge[] {
  const out: Badge[] = [];
  const t = c?.trajectory ?? {}, b = c?.balance_sheet ?? {}, cash = c?.cash ?? {};
  const g5 = t.cagr?.revenue_5y, p5 = t.cagr?.pat_5y;
  if (g5 != null) out.push([`Revenue ${pct(g5, 0)}/yr`, g5 >= 12 ? "good" : g5 >= 6 ? "warn" : "bad"]);
  if (p5 != null && g5 != null) out.push(p5 >= g5 ? ["Profit outgrowing sales", "good"] : ["Profit lagging sales", "warn"]);
  const de = (b.debt_to_equity ?? []).filter((x: number | null) => x != null).slice(-1)[0];
  if (de != null) out.push(de < 0.3 ? ["Low debt", "good"] : de < 1 ? [`D/E ${de.toFixed(1)}x`, "warn"] : [`High debt ${de.toFixed(1)}x`, "bad"]);
  const wc = (b.working_capital_days ?? []).filter((x: number | null) => x != null);
  if (wc.length >= 4) {
    const d = wc[wc.length - 1] - wc[wc.length - 4];
    if (Math.abs(d) >= 10) out.push(d > 0 ? ["Working capital stretching", "warn"] : ["Working capital tighter", "good"]);
  }
  if (cash.conversion_pct != null) {
    const cv = cash.conversion_pct;
    out.push(cv >= 90 ? ["Cash-backed profits", "good"] : cv >= 70 ? [`Cash ${Math.round(cv)}% of profit`, "warn"] : ["Weak cash conversion", "bad"]);
  }
  const fcf = (cash.fcf ?? []).slice(-5).filter((x: number | null) => x != null && x < 0).length;
  if (fcf >= 2) out.push([`FCF negative ${fcf}/5 yrs`, "bad"]);
  return out;
}

function spark(label: string, sub: string, vals: (number | null)[], fmt: (v: number | null) => string, color?: string) {
  const last = vals.length ? vals[vals.length - 1] : null;
  return (
    <div className="spark" key={label}>
      <div className="l">{label}<small>{sub}</small></div>
      <Spark values={vals} color={color} />
      <div className="num sv">{fmt(last)}</div>
    </div>
  );
}

export function HealthView({ s }: { s: Section<Any> }) {
  const [why, setWhy] = useState(false);
  const t = s.content?.trajectory ?? {}, b = s.content?.balance_sheet ?? {}, c = s.content?.cash ?? {};
  const cr = (v: number | null) => (v == null ? "–" : `${crore(v)}`);
  const badges = healthBadges(s.content);
  return (
    <>
      <div className="badges">{badges.map(([txt, k]) => <span key={txt} className={`badge ${k}`}>{txt}</span>)}</div>
      {t.years && spark("Revenue", "₹ cr · 10 yrs", t.revenue ?? [], cr)}
      {t.years && spark("Profit", "₹ cr · 10 yrs", t.pat ?? [], cr, "#7fd8e8")}
      {b.years && b.borrowings && spark("Debt", "₹ cr", b.borrowings, cr, "#ff7a6e")}
      {c.years && spark("Free cash flow", "₹ cr", c.fcf ?? [], cr, "#5be38f")}
      <button className="link" style={{ marginTop: 8 }} onClick={() => setWhy(!why)}>{why ? "Hide reasoning" : "Why these badges?"}</button>
      {why && <div className="verdicts">{[t.verdict, b.verdict, c.verdict].filter(Boolean).map((v: string) => <p key={v}>{v}</p>)}</div>}
    </>
  );
}

// ---------------------------------------------------------------- promise vs delivered
const VERDICTS = ["hit", "partial", "missed", "pending", "unverifiable"] as const;

function firstNum(s: string | null | undefined): number | null {
  const m = String(s ?? "").match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : null;
}
function lastPct(s: string | null | undefined): number | null {
  const all = String(s ?? "").match(/-?\d+(?:\.\d+)?(?=\s*%|\s*$|,)/g) ?? String(s ?? "").match(/-?\d+(?:\.\d+)?/g);
  if (!all || !all.length) return null;
  const v = Number(all[all.length - 1]);
  return Math.abs(v) <= 100 ? v : null;
}

/** Target vs actual as a bullet bar (only for % targets with a % actual). */
function TargetBar({ target, actual, tone }: { target: number; actual: number; tone: string }) {
  const max = Math.max(target, actual, 1) * 1.25;
  return (
    <div className="tbar" title={`Target ${target}% · actual ${actual}%`}>
      <div className={`fill ${tone}`} style={{ width: `${Math.max(0, (actual / max) * 100)}%` }} />
      <div className="mark" style={{ left: `${(target / max) * 100}%` }} />
      <span className="tv">{actual}%</span>
    </div>
  );
}

const METRIC_HINTS: [RegExp, string][] = [
  [/order inflow|order book/i, "Order inflow"], [/r\s*&\s*d|research and development/i, "R&D spend"],
  [/capex|capital (investment|expenditure)/i, "Capex"], [/export/i, "Exports"], [/stores?\b/i, "Stores"],
  [/volume/i, "Volume growth"], [/margin/i, "Margin"], [/revenue|sales|top ?line/i, "Revenue growth"],
  [/profit|pat\b/i, "Profit"],
];

function shortMetric(it: Any): string {
  const m = String(it.metric || "").replace(/_/g, " ").trim();
  if (m && !/^(other|target|n\/?a)$/i.test(m)) return m[0].toUpperCase() + m.slice(1);
  const text = `${it.promise ?? ""} ${it.target ?? ""}`;
  return METRIC_HINTS.find(([rx]) => rx.test(text))?.[1] ?? "Target";
}

function PromiseRow({ it, s, open }: { it: Any; s: Section<Any>; open: (c: Citation) => void }) {
  const [more, setMore] = useState(false);
  const target = firstNum(it.target);
  const actual = lastPct(it.actual);
  const isPct = /%|percent/i.test(String(it.target)) && actual !== null && target !== null;
  const tr = it.verdict === "pending" ? it.tracking : null;
  const tone = it.verdict === "hit" || tr === "ahead" || tr === "on_track" ? "good" : it.verdict === "missed" || tr === "behind" ? "bad" : "neutral";
  const status = tr === "ahead" ? "Ahead" : tr === "on_track" ? "On track" : tr === "behind" ? "Behind" : it.verdict;
  return (
    <div className="prow" onClick={() => setMore(!more)}>
      <div className="top">
        <div className="pm">
          <b>{shortMetric(it)}{it.times > 1 && <span className="said">said {it.times}×</span>}</b>
          <span>{String(it.target).replace(/more than /i, ">").replace(/\s*-?\s*plus percent/i, "%+").replace(/ percent/i, "%")} · {String(it.target_period || "").replace(/\s+/g, " ")}</span>
        </div>
        <span className={`vpill ${tone}`}>{status}</span>
      </div>
      {isPct && <TargetBar target={target!} actual={actual!} tone={tone} />}
      {more && (
        <div className="more">
          <q>{it.promise}</q>
          <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
            {it.said_in}<CiteIds ids={it.citation_id ?? it.citation_ids} cites={s.citations} open={open} />
            {it.actual && it.actual !== "n/a" ? ` · Actual: ${it.actual}` : ""}
          </div>
          {it.explanation && <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>{it.explanation}</div>}
        </div>
      )}
    </div>
  );
}

export function PromiseView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  if (s.status === "needs_docs") return <NeedsDocs />;
  const items: Any[] = s.content?.items ?? [];
  if (!items.length) return <p className="needs">No quantified guidance in these calls.</p>;
  const n = (k: string) => items.filter((i) => i.verdict === k).length;
  const ahead = items.filter((i) => i.verdict === "pending" && (i.tracking === "ahead" || i.tracking === "on_track")).length;
  const behind = items.filter((i) => i.verdict === "pending" && i.tracking === "behind").length;
  // most informative first: judged, then tracking, then the rest
  const rank = (i: Any) => (["hit", "missed", "partial"].includes(i.verdict) ? 0 : i.tracking && i.tracking !== "n/a" ? 1 : 2);
  // Guidance restated on several calls (same metric, period and number) becomes one row: "said 3×".
  const groups = new Map<string, Any>();
  for (const it of items) {
    const key = `${String(it.metric).toLowerCase()}|${String(it.target_period).toLowerCase()}|${firstNum(it.target)}`;
    const g = groups.get(key);
    if (g) g.times += 1;
    else groups.set(key, { ...it, times: 1 });
  }
  const sorted = [...groups.values()].sort((a, b) => rank(a) - rank(b) || b.times - a.times);
  return (
    <>
      <div className="scorebar">
        {VERDICTS.filter((k) => n(k)).map((k) => <div key={k} className={`seg v-${k}`} style={{ flex: n(k) }} title={`${n(k)} ${k}`} />)}
      </div>
      <div className="legend">
        {VERDICTS.filter((k) => n(k)).map((k) => <span key={k}><i className={`dot v-${k}`} />{n(k)} {k}</span>)}
      </div>
      {(ahead > 0 || behind > 0) && (
        <div className="badges" style={{ marginTop: 8 }}>
          {ahead > 0 && <span className="badge good">▲ {ahead} on/ahead of plan</span>}
          {behind > 0 && <span className="badge bad">▼ {behind} behind plan</span>}
        </div>
      )}
      <div className="plist">{sorted.slice(0, 8).map((it, i) => <PromiseRow key={i} it={it} s={s} open={open} />)}</div>
      {sorted.length > 8 && <p className="dim" style={{ fontSize: 11, marginTop: 6 }}>+{sorted.length - 8} more pending/unverifiable</p>}
    </>
  );
}

// ---------------------------------------------------------------- bull / bear
/** "OCF 59% of PAT" -> { value: "59%", label: "OCF of PAT" }; prefers a number with a unit,
 *  so "Q2 FY27 PAT -28% YoY" gives -28% rather than the 2 in Q2. */
function splitStat(stat: string): { value: string; label: string } | null {
  if (!stat) return null;
  const rx = /[-−+>~<]?\s?\d[\d,.]*\s?(%|x\b|bps?\b|cr\b|crore|lakh|million|billion|days?\b|yrs?\b)?/gi;
  const toks = [...stat.matchAll(rx)].map((m) => ({ t: m[0].trim(), unit: Boolean(m[1]) }));
  if (!toks.length) return null;
  const pick = toks.find((t) => t.unit) ?? toks[toks.length - 1];
  const label = stat.replace(pick.t, " ").replace(/\s+/g, " ").replace(/^[\s:·-]+|[\s:·-]+$/g, "");
  return { value: pick.t.replace(/^-/, "−"), label };
}

function BBRow({ p, up, s, open }: { p: Any; up: boolean; s: Section<Any>; open: (c: Citation) => void }) {
  const [more, setMore] = useState(false);
  const st = splitStat(p.stat || "");
  const title = p.title || null;
  return (
    <li className={`bbrow ${up ? "bull" : "bear"}`} onClick={() => setMore(!more)}>
      <div className="bbstat">
        {st ? (<><b>{st.value}</b><span>{st.label}</span></>) : <b className="ic">{up ? "▲" : "▼"}</b>}
      </div>
      <div className="bbbody">
        {title ? <div className="bbt">{title}</div> : <Clamp><Cited text={p.point} cites={s.citations} open={open} /></Clamp>}
        <div className="bbc"><CiteIds ids={p.citation_ids ?? p.citations} cites={s.citations} open={open} /></div>
        {more && title && <div className="bbp">{p.point}</div>}
      </div>
    </li>
  );
}

export function BullBearView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  const bull: Any[] = s.content?.bull ?? [];
  const bear: Any[] = s.content?.bear ?? [];
  return (
    <div className="bb3">
      <div className="bbh up">▲ Bull</div>
      <ul>{bull.map((p, i) => <BBRow key={`u${i}`} p={typeof p === "string" ? { point: p } : p} up s={s} open={open} />)}</ul>
      <div className="bbh dn">▼ Bear</div>
      <ul>{bear.map((p, i) => <BBRow key={`d${i}`} p={typeof p === "string" ? { point: p } : p} up={false} s={s} open={open} />)}</ul>
    </div>
  );
}

export function MetricRow({ m }: { m: Metric }) {
  return <span>{m.name} {crore(m.value)} ({pct(m.yoy_pct)} YoY)</span>;
}

export function useCiteSheet() {
  const [c, setC] = useState<Citation | null>(null);
  return { open: setC, sheet: <CiteSheet c={c} onClose={() => setC(null)} /> };
}

export { ResultsTable };
