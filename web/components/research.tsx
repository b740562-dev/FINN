"use client";

import { Fragment, useState } from "react";
import type { Citation, Metric, Section } from "@/lib/types";
import { crore, pct } from "@/lib/format";
import { ResultsTable } from "./cards";
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
        <div className="mono dim" style={{ fontSize: 10, letterSpacing: "0.1em" }}>SOURCE [{c.id}]</div>
        <div style={{ fontWeight: 600, marginTop: 4 }}>{c.doc_label}{c.page ? ` · page ${c.page}` : ""}</div>
        <blockquote>{c.quote}</blockquote>
        <button className="btn" onClick={onClose}>CLOSE</button>
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
        return m[1].split(/\s*,\s*/).map((id) => {
          const c = cites.find((x) => x.id.toLowerCase() === id.toLowerCase());
          return c ? <button key={i + id} className="cite" onClick={() => open(c)}>{id}</button> : null;
        });
      })}
    </>
  );
}

function CiteIds({ ids, cites, open }: { ids?: string[] | string | null; cites: Citation[]; open: (c: Citation) => void }) {
  const list = (Array.isArray(ids) ? ids : ids ? [ids] : []).filter(Boolean);
  return (
    <>
      {list.map((id) => {
        const c = cites.find((x) => x.id === id);
        return c ? <button key={id} className="cite" onClick={() => open(c)}>{id}</button> : null;
      })}
    </>
  );
}

// ---------------------------------------------------------------- shells
export function SectionShell({ title, s, children }: { title: string; s: Section<Any> | null | "loading"; children?: React.ReactNode }) {
  const meta = s && s !== "loading" && s.model ? s.model.replace("gemini-", "") : s && s !== "loading" && s.status === "ready" ? "deterministic" : "";
  return (
    <section className="rsec">
      <header><h2>{title}</h2><span>{s === "loading" || !s ? "loading…" : meta}</span></header>
      <div className="body">
        {s === "loading" || !s ? (
          <div className="skel sm" style={{ margin: 0 }} />
        ) : s.status === "error" ? (
          <div className="err" style={{ margin: 0 }}>Couldn&apos;t build this section{s.error ? `: ${s.error}` : ""}.</div>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

function NeedsDocs({ what }: { what: string }) {
  return (
    <p className="needs">
      <b>Needs primary documents.</b> {what} Add this company&apos;s concall transcripts (and annual report) below. FINN only
      analyses what the company itself published.
    </p>
  );
}

// ---------------------------------------------------------------- snapshot
export function SnapshotView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  const f = s.content?.financial ?? {};
  const ttm = f.ttm ?? {};
  const r = f.ratios ?? {};
  const biz = s.content?.business;
  const lq = f.latest_quarter;
  return (
    <>
      {biz ? (
        <>
          {biz.summary && (
            <p><Cited text={biz.summary} cites={s.citations} open={open} /><CiteIds ids={biz.summary_citations} cites={s.citations} open={open} /></p>
          )}
          {Array.isArray(biz.segments) && biz.segments.length > 0 && (
            <table className="t" style={{ marginTop: 6 }}>
              <thead><tr><th>Segment</th><th>Share</th></tr></thead>
              <tbody>
                {biz.segments.map((g: Any, i: number) => (
                  <tr key={i}>
                    <td className="lbl">{g.name}{g.note ? <span className="dim"> · {g.note}</span> : null}<CiteIds ids={g.citation_id} cites={s.citations} open={open} /></td>
                    <td>{g.share_pct != null ? `${g.share_pct}%` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : (
        <p className="needs">Business mix needs the annual report. Numbers below come straight from reported financials.</p>
      )}
      <div className="kv">
        <div>MCAP ₹CR<b>{crore(f.market_cap_cr)}</b></div>
        <div>TTM REV<b>{crore(ttm.revenue)}</b></div>
        <div>TTM PAT<b>{crore(ttm.pat)}</b></div>
        <div>EBITDA MGN<b>{ttm.ebitda_margin != null ? `${Number(ttm.ebitda_margin).toFixed(1)}%` : "–"}</b></div>
        <div>ROCE<b>{r.roce != null ? `${r.roce}%` : "–"}</b></div>
        <div>ROE<b>{r.roe != null ? `${r.roe}%` : "–"}</b></div>
      </div>
      {lq?.status !== "pending" && lq?.metrics && (
        <div style={{ marginTop: 10 }}>
          <div className="mono dim" style={{ fontSize: 10, letterSpacing: "0.1em" }}>LATEST QUARTER · {lq.headline}</div>
          <ResultsTable card={{ status: "ready", ...lq }} />
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- health
function series(label: string, sub: string, years: string[], vals: (number | null)[], fmt: (v: number | null) => string, color?: string) {
  const last = vals.length ? vals[vals.length - 1] : null;
  return (
    <div className="spark" key={label}>
      <div className="l">{label}<small>{sub} · {years[0]}–{years[years.length - 1]}</small></div>
      <Spark values={vals} color={color} />
      <div className="num" style={{ minWidth: 70, textAlign: "right" }}>{fmt(last)}</div>
    </div>
  );
}

function Verdict({ text }: { text?: string | null }) {
  if (!text) return null;
  const warn = /flag|weak|declin|compress|rising debt|stretch|below|lag|negative|worse/i.test(text);
  return <div className={`verdict ${warn ? "warn" : ""}`}>{text}</div>;
}

export function HealthView({ s }: { s: Section<Any> }) {
  const t = s.content?.trajectory ?? {};
  const b = s.content?.balance_sheet ?? {};
  const c = s.content?.cash ?? {};
  const cagr = t.cagr ?? {};
  const cr = (v: number | null) => crore(v);
  return (
    <>
      <div className="mono dim" style={{ fontSize: 10, letterSpacing: "0.1em" }}>TRAJECTORY</div>
      {t.years && series("Revenue", `3y CAGR ${pct(cagr.revenue_3y)} · 5y ${pct(cagr.revenue_5y)}`, t.years, t.revenue ?? [], cr)}
      {t.years && series("PAT", `3y CAGR ${pct(cagr.pat_3y)} · 5y ${pct(cagr.pat_5y)}`, t.years, t.pat ?? [], cr)}
      {t.years && t.opm && t.opm.some((x: number | null) => x != null) && series("Operating margin", "OPM %", t.years, t.opm, (v) => (v == null ? "–" : `${v}%`), "var(--blue)")}
      <Verdict text={t.verdict} />

      <div className="mono dim" style={{ fontSize: 10, letterSpacing: "0.1em", marginTop: 12 }}>BALANCE SHEET</div>
      {b.years && series("Borrowings", "₹ cr", b.years, b.borrowings ?? [], cr, "var(--dn)")}
      {b.years && b.debt_to_equity && series("Debt / equity", "x", b.years, b.debt_to_equity, (v) => (v == null ? "–" : `${Number(v).toFixed(2)}x`), "var(--dn)")}
      {b.years && b.working_capital_days && b.working_capital_days.some((x: number | null) => x != null) &&
        series("Working capital", "days", b.years, b.working_capital_days, (v) => (v == null ? "–" : `${Math.round(v)}d`), "var(--violet)")}
      <Verdict text={b.verdict} />

      <div className="mono dim" style={{ fontSize: 10, letterSpacing: "0.1em", marginTop: 12 }}>CASH QUALITY</div>
      {c.years && series("Cash from operations", "₹ cr", c.years, c.cfo ?? [], cr, "var(--up)")}
      {c.years && series("Free cash flow", "CFO − capex", c.years, c.fcf ?? [], cr, "var(--up)")}
      {c.conversion_pct != null && (
        <div className="kv"><div>CFO / PAT<b className={c.conversion_pct < 70 ? "amber" : "up"}>{Math.round(c.conversion_pct)}%</b></div></div>
      )}
      <Verdict text={c.verdict} />
    </>
  );
}

// ---------------------------------------------------------------- promise vs delivered
export function PromiseView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  if (s.status === "needs_docs") return <NeedsDocs what="Promise vs delivered compares what management guided on its calls with what it then reported." />;
  const sc = s.content?.score ?? {};
  const items: Any[] = s.content?.items ?? [];
  return (
    <>
      <div className="score">
        {["hit", "partial", "missed", "pending", "unverifiable"].filter((k) => sc[k]).map((k) => (
          <span key={k} className={`v-${k}`}>{sc[k]} {k}</span>
        ))}
      </div>
      {items.length === 0 && <p className="needs">No explicit, quantified guidance found in the transcripts provided.</p>}
      {items.map((it, i) => (
        <div className="promise" key={i}>
          <div className="top">
            <q>{it.promise}</q>
            <span className={`pv v-${it.verdict}`}>{it.verdict}</span>
          </div>
          <dl className="vs">
            <dt>SAID</dt><dd>{it.said_in}<CiteIds ids={it.citation_id ?? it.citation_ids} cites={s.citations} open={open} /></dd>
            {it.target && (<><dt>TARGET</dt><dd>{it.target}</dd></>)}
            <dt>ACTUAL</dt><dd>{it.actual ?? "–"}</dd>
            {it.explanation && (<><dt>WHY</dt><dd className="muted">{it.explanation}</dd></>)}
          </dl>
        </div>
      ))}
      {s.content?.verification && (
        <p className="sub dim" style={{ marginTop: 8, fontSize: 10.5 }}>
          Quote check: {JSON.stringify(s.content.verification).replace(/[{}"]/g, "").replace(/,/g, " · ").replace(/:/g, " ")}
        </p>
      )}
    </>
  );
}

// ---------------------------------------------------------------- bull / bear
export function BullBearView({ s, open }: { s: Section<Any>; open: (c: Citation) => void }) {
  const point = (p: Any, i: number) => (
    <li key={i}>
      <Cited text={typeof p === "string" ? p : p.point} cites={s.citations} open={open} />
      {typeof p !== "string" && <CiteIds ids={p.citation_ids ?? p.citations} cites={s.citations} open={open} />}
    </li>
  );
  return (
    <div className="bb">
      <div><h3 className="up">BULL</h3><ol>{(s.content?.bull ?? []).map(point)}</ol></div>
      <div><h3 className="dn">BEAR</h3><ol>{(s.content?.bear ?? []).map(point)}</ol></div>
      {s.content?.basis && <p className="sub dim" style={{ fontSize: 10.5 }}>{String(s.content.basis)}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- latest metrics (fallback)
export function MetricRow({ m }: { m: Metric }) {
  return <span>{m.name} {crore(m.value)} ({pct(m.yoy_pct)} YoY)</span>;
}

export function useCiteSheet() {
  const [c, setC] = useState<Citation | null>(null);
  return { open: setC, sheet: <CiteSheet c={c} onClose={() => setC(null)} /> };
}
