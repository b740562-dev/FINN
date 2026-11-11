"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { DigestEvent, Person } from "@/lib/types";
import { pct, shortDate, tone } from "@/lib/format";
import { BioBlock, crShort, KpiTiles, ResultsTable } from "./cards";

/* ------------------------------------------------------------------ */
/* Category look: a line icon + one colour. No emoji, no prose.        */
/* ------------------------------------------------------------------ */

type Kind = "results" | "mgmt" | "merger" | "fund" | "capex" | "legal" | "rating" | "payout" | "order" | "insider" | "update";

const COLOR: Record<Kind, string> = {
  results: "#c6f45e",
  mgmt: "#7fd8e8",
  merger: "#c3b4ff",
  fund: "#f4c95d",
  capex: "#f59f5b",
  legal: "#ff7a6e",
  rating: "#5ee0c0",
  payout: "#5be38f",
  order: "#f4c95d",
  insider: "#ff9fb2",
  update: "#8ea698",
};

function kindOf(e: DigestEvent): Kind {
  const t = `${e.one_liner ?? ""} ${e.headline}`.toLowerCase();
  switch (e.category) {
    case "results": return "results";
    case "management_change": return "mgmt";
    case "M&A": return "merger";
    case "fund_raise": return "fund";
    case "capex": return "capex";
    case "litigation": return "legal";
    case "credit_rating": return "rating";
    case "dividend": case "bonus_split": return "payout";
    case "insider_trading": case "pledging": return "insider";
    default: return /\border|contract|bagg/.test(t) ? "order" : "update";
  }
}

const PATHS: Record<Kind, React.ReactNode> = {
  results: <><path d="M3 3v18h18" /><path d="M7 16v-4M12 16V8M17 16V6" /></>,
  mgmt: <><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" /></>,
  merger: <><circle cx="9" cy="12" r="6" /><circle cx="15" cy="12" r="6" /></>,
  fund: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></>,
  capex: <><path d="M3 21V10l6 4v-4l6 4V4h6v17Z" /><path d="M7 18h2M13 18h2" /></>,
  legal: <><path d="M12 3v18M6 21h12M4 7h16" /><path d="M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0z" /></>,
  rating: <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" />,
  payout: <><path d="M19 5 5 19" /><circle cx="6.5" cy="6.5" r="2.5" /><circle cx="17.5" cy="17.5" r="2.5" /></>,
  order: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 13h18" /></>,
  insider: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  update: <><path d="M14 3H6v18h12V7z" /><path d="M14 3v4h4M9 13h6M9 17h4" /></>,
};

export function CatIcon({ kind, size = 18 }: { kind: Kind; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>{PATHS[kind]}</svg>
  );
}

/* ------------------------------------------------------------------ */
/* People: monogram "portrait" with a status badge.                    */
/* ------------------------------------------------------------------ */

function hueOf(name: string) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function mono(name: string) {
  const w = name.replace(/[^A-Za-z\s.]/g, "").split(/[\s.]+/).filter((x) => /^[A-Z]/.test(x));
  return ((w[0]?.[0] ?? "") + (w.length > 1 ? w[w.length - 1][0] : "")).toUpperCase() || "?";
}

function shortName(name: string) {
  const w = name.split(/\s+/).filter((x) => !/^[A-Z]\.$/.test(x));
  return w.length > 1 ? `${w[0]} ${w[w.length - 1]}` : name;
}

export function shortRole(role: string) {
  return role
    .replace(/Managing Director (and|&) Chief Executive Officer/i, "MD & CEO")
    .replace(/Chief Executive Officer/i, "CEO")
    .replace(/Chief Financial Officer/i, "CFO")
    .replace(/Chief Operating Officer/i, "COO")
    .replace(/Managing Director/i, "MD")
    .replace(/Independent Director/i, "Ind. Director")
    .replace(/,.*$/, "");
}

type Badge = "in" | "out" | "retire";

function badgeFor(p: Person, e: DigestEvent): Badge {
  if (p.change !== "leaving") return "in";
  return /retire|superannuat/i.test(`${e.one_liner ?? ""} ${e.headline}`) ? "retire" : "out";
}

export function Portrait({ name, badge, size = 44 }: { name: string; badge?: Badge; size?: number }) {
  const h = hueOf(name);
  return (
    <span className={`portrait ${badge ?? ""}`} style={{ width: size, height: size, fontSize: size * 0.36,
      background: `linear-gradient(145deg, hsl(${h} 38% 34%), hsl(${(h + 40) % 360} 34% 20%))` }}
      aria-label={name} title={name}>
      {mono(name)}
      {badge && <i className="pb">{badge === "in" ? "+" : badge === "retire" ? "◷" : "−"}</i>}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Signals: the numbers / facts a row shows instead of a sentence.     */
/* ------------------------------------------------------------------ */

type Sig = { text: string; tone?: "up" | "dn" | "flat"; strong?: boolean };

function compactNum(raw: string, unit: string) {
  const n = Number(raw.replace(/,/g, ""));
  if (!isFinite(n)) return null;
  const u = unit.toLowerCase();
  if (u.startsWith("million")) return `${n}M`;
  const s = n >= 1e5 ? `${(n / 1e5).toFixed(1)}L` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}K` : String(n);
  return s;
}

function signals(e: DigestEvent, kind: Kind): Sig[] {
  const t = `${e.one_liner ?? ""}`;
  const out: Sig[] = [];
  const amt = e.enrichment?.amount_cr;

  if (kind === "rating") {
    const a = e.enrichment?.rating_action ?? "";
    const pos = /positive|upgrad/i.test(t), neg = /negative|downgrad/i.test(t);
    if (a === "upgrade" || (a === "outlook_change" && pos)) out.push({ text: a === "upgrade" ? "▲ Upgrade" : "↗ Outlook +", tone: "up", strong: true });
    else if (a === "downgrade" || (a === "outlook_change" && neg)) out.push({ text: a === "downgrade" ? "▼ Downgrade" : "↘ Outlook −", tone: "dn", strong: true });
    else if (a) out.push({ text: "= Reaffirmed", tone: "flat", strong: true });
    const agency = t.match(/\b(CRISIL|ICRA|CARE|India Ratings|Fitch|Moody's|S&P|Acuite|Brickwork)\b/i);
    if (agency) out.push({ text: agency[1] });
  }

  if (amt && kind !== "results") out.push({ text: `₹${crShort(amt)}`, strong: true });

  for (const f of e.factors) {
    const m = f.match(/([\d.]+)% of (market cap|TTM revenue|revenue|net worth)/i);
    if (m) out.push({ text: `${m[1]}% ${/market/i.test(m[2]) ? "mcap" : /worth/i.test(m[2]) ? "NW" : "rev"}` });
  }

  if (kind === "merger") {
    const stake = t.match(/stake (?:to|of)?\s*([\d.]+)%/i);
    if (stake) out.push({ text: `Stake ${stake[1]}%`, strong: true });
    if (/merger|amalgamat/i.test(t)) out.push({ text: "Merger" });
    else if (/acqui/i.test(t)) out.push({ text: "Acquisition" });
    if (/restructur/i.test(t)) out.push({ text: "Restructure" });
    if (/swap/i.test(t)) out.push({ text: "Share swap" });
    if (/subsidiar/i.test(t)) out.push({ text: "Subsidiary" });
  }

  if (kind === "legal") {
    const court = t.match(/\b(Supreme Court|High Court|NCLAT|NCLT|SEBI|SAT|CCI|Tax|GST|Income Tax)\b/i);
    if (court) out.push({ text: court[1], strong: true });
  }

  if (kind === "fund") {
    if (/\bQIP\b/.test(t)) out.push({ text: "QIP" });
    else if (/\bNCD|debenture/i.test(t)) out.push({ text: "NCDs" });
    else if (/warrant/i.test(t)) out.push({ text: "Warrants" });
    else if (/rights/i.test(t)) out.push({ text: "Rights" });
    else if (/preferential/i.test(t)) out.push({ text: "Preferential" });
  }

  if (kind === "update" || kind === "order" || kind === "capex") {
    const ch = t.match(/\b(up|rose|grew|increased|higher|down|fell|declined|lower)\b[^.%\d]{0,24}([\d.]+)%/i);
    if (ch) {
      const up = /up|rose|grew|increased|higher/i.test(ch[1]);
      out.push({ text: `${up ? "▲" : "▼"} ${ch[2]}%`, tone: up ? "up" : "dn", strong: true });
    }
    const q = t.match(/([\d][\d,]*(?:\.\d+)?)\s*(million\s+sq\.?\s*ft|million\s+(?:units|vehicles|tonnes)|sq\.?\s*ft|million|units|vehicles|BU|MW|GW|km|stations|tonnes|MT)\b/i);
    if (q) {
      const v = compactNum(q[1], q[2]);
      const unit = q[2].replace(/million\s+/i, "").replace(/sq\.?\s*ft/i, "sq ft").replace(/^million$/i, "");
      if (v) out.push({ text: `${v}${unit ? ` ${unit}` : ""}`, strong: !ch });
    }
    if (/highest[- ]ever|record/i.test(t)) out.push({ text: "★ Record", tone: "up" });
    if (kind === "order" && !out.length) out.push({ text: /orders/i.test(t) ? "Orders" : "Order", strong: true });
    if (/\bEV\b|electric/i.test(t)) out.push({ text: "EV" });
  }

  const seen = new Set<string>();
  return out.filter((s) => (seen.has(s.text) ? false : (seen.add(s.text), true))).slice(0, 3);
}

/** Results: YoY of the two lines investors read first. */
function resultSigs(e: DigestEvent): Sig[] {
  const c = e.enrichment?.results_card;
  if (!c || c.status !== "ready" || !c.metrics) return [];
  const by = Object.fromEntries(c.metrics.map((m) => [m.key, m]));
  const pick = [
    ["Rev", by.revenue ?? by.nii],
    ["PAT", by.pat],
  ] as const;
  return pick.filter(([, m]) => m && m.yoy_pct !== null && m.yoy_pct !== undefined).map(([k, m]) => ({
    text: `${k} ${m!.yoy_pct! >= 0 ? "▲" : "▼"}${Math.abs(m!.yoy_pct!).toFixed(0)}%`,
    tone: tone(m!.yoy_pct) as Sig["tone"],
    strong: true,
  }));
}

function flagCount(e: DigestEvent) {
  const c = e.enrichment?.results_card;
  return (c?.flags?.length ?? 0) + (c?.cross_check ?? []).filter((x) => !x.consistent).length;
}

/* ------------------------------------------------------------------ */
/* Top stories rail                                                    */
/* ------------------------------------------------------------------ */

function bubbleStat(e: DigestEvent, kind: Kind): Sig | null {
  if (kind === "results") return resultSigs(e).find((s) => s.text.startsWith("PAT")) ?? resultSigs(e)[0] ?? { text: e.enrichment?.results_card?.quarter_label ?? "Results" };
  if (kind === "mgmt") {
    const p = (e.enrichment?.people ?? [])[0];
    return p ? { text: shortRole(p.role) } : null;
  }
  return signals(e, kind)[0] ?? null;
}

export function StoryRail({ items, onOpen }: { items: DigestEvent[]; onOpen: (e: DigestEvent) => void }) {
  if (!items.length) return null;
  return (
    <div className="rail" role="list">
      {items.map((e) => {
        const kind = kindOf(e);
        const people = e.enrichment?.people ?? [];
        const lead = people.find((p) => p.change !== "leaving") ?? people[0];
        const stat = bubbleStat(e, kind);
        return (
          <button key={`${e.symbol}-${e.filing_ids[0]}`} className="story" role="listitem" onClick={() => onOpen(e)}
            style={{ "--c": COLOR[kind] } as React.CSSProperties} aria-label={`${e.symbol} ${e.label}`}>
            <span className="halo">
              {kind === "mgmt" && lead ? (
                <Portrait name={lead.name} size={52} />
              ) : (
                <span className="glyph"><CatIcon kind={kind} size={24} /></span>
              )}
              <i className="cat"><CatIcon kind={kind} size={10} /></i>
            </span>
            <b className="tkr">{e.symbol}</b>
            {stat && <span className={`st ${stat.tone ?? ""}`}>{stat.text}</span>}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* News row: icon · ticker · visual signal. Tap → detail sheet.        */
/* ------------------------------------------------------------------ */

export function NewsRow({ e, onOpen }: { e: DigestEvent; onOpen: (e: DigestEvent) => void }) {
  const kind = kindOf(e);
  const people = e.enrichment?.people ?? [];
  const leaving = people.filter((p) => p.change === "leaving");
  const joining = people.filter((p) => p.change !== "leaving");
  const sigs = kind === "results" ? resultSigs(e) : kind === "mgmt" ? [] : signals(e, kind);
  const flags = kind === "results" ? flagCount(e) : 0;
  const card = e.enrichment?.results_card;
  const sub = kind === "results" ? card?.quarter_label ?? e.label : e.label;

  return (
    <button className="nrow" onClick={() => onOpen(e)} style={{ "--c": COLOR[kind] } as React.CSSProperties}>
      <span className="ic"><CatIcon kind={kind} size={18} /></span>
      <span className="who">
        <b>{e.symbol}</b>
        <small>{sub}</small>
      </span>

      <span className="vis">
        {kind === "mgmt" && people.length > 0 ? (
          <span className="faces">
            {leaving.slice(0, 1).map((p) => (
              <span key={p.name} className="face"><Portrait name={p.name} badge={badgeFor(p, e)} size={32} /><em>{shortName(p.name)}</em></span>
            ))}
            {leaving.length > 0 && joining.length > 0 && <span className="to">→</span>}
            {joining.slice(0, 1).map((p) => (
              <span key={p.name} className="face"><Portrait name={p.name} badge="in" size={32} /><em>{shortName(p.name)}</em></span>
            ))}
          </span>
        ) : sigs.length > 0 ? (
          <span className="sigs">
            {sigs.map((s) => <span key={s.text} className={`sig ${s.tone ?? ""} ${s.strong ? "strong" : ""}`}>{s.text}</span>)}
            {flags > 0 && <span className="sig dn">⚑{flags > 1 ? flags : ""}</span>}
          </span>
        ) : kind === "results" ? (
          <span className="sig flat">◷ Pending</span>
        ) : (
          <span className="sig flat">Filing</span>
        )}
      </span>

      <span className="meta">
        {e.related > 0 && <span className="rel">+{e.related}</span>}
        <span className="dt">{shortDate(e.filed_at).replace(/,.*$/, "")}</span>
      </span>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Detail sheet: the full story, opened from a bubble or a row.        */
/* ------------------------------------------------------------------ */

export function NewsSheet({ e, onClose }: { e: DigestEvent | null; onClose: () => void }) {
  useEffect(() => {
    if (!e) return;
    const k = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", k); document.body.style.overflow = prev; };
  }, [e, onClose]);

  if (!e) return null;
  const kind = kindOf(e);
  const card = e.enrichment?.results_card;
  const people = e.enrichment?.people ?? [];
  const bios = (e.enrichment?.bios ?? []).filter((b) => b.status !== "not_found");
  const sigs = kind === "results" ? [] : kind === "mgmt" ? [] : signals(e, kind);

  return (
    <div className="sheet-bg" onClick={onClose} role="dialog" aria-modal aria-label={`${e.symbol} ${e.label}`}>
      <div className="sheet news-sheet" onClick={(ev) => ev.stopPropagation()} style={{ "--c": COLOR[kind] } as React.CSSProperties}>
        <div className="grab" />
        <div className="ns-head">
          <span className="ic"><CatIcon kind={kind} size={20} /></span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="ns-t"><b>{e.symbol}</b><span className="tag">{kind === "results" ? card?.quarter_label ?? e.label : e.label}</span></div>
            <div className="ns-s">{e.company} · {shortDate(e.filed_at)}</div>
          </div>
          <button className="ns-x" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {kind === "results" && card?.status === "ready" ? (
          <>
            <KpiTiles card={card} />
            <div style={{ marginTop: 10 }}><ResultsTable card={card} /></div>
            {(card.flags ?? []).map((f) => <span key={f} className="pill red" style={{ marginTop: 8, display: "inline-block" }}>⚑ {f}</span>)}
            {(card.cross_check ?? []).filter((x) => !x.consistent).map((x) => (
              <div key={x.filing_text} className="ns-note">≠ Filing says {pct(x.stated_pct, 0)}; table shows {pct(x.card_yoy_pct, 0)} YoY</div>
            ))}
          </>
        ) : kind === "mgmt" && people.length > 0 ? (
          <div className="ns-people">
            {people.map((p) => {
              const bio = bios.find((b) => b.name === p.name);
              const b = badgeFor(p, e);
              return (
                <div key={p.name} className={`ns-person ${b}`}>
                  <Portrait name={p.name} badge={b} size={48} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="pn">{p.name}</div>
                    <div className="pr"><span className={`st ${b}`}>{b === "in" ? "Joins" : b === "retire" ? "Retires" : "Exits"}</span>{shortRole(p.role)}</div>
                    {bio && <BioBlock bio={bio} full compact />}
                  </div>
                </div>
              );
            })}
          </div>
        ) : sigs.length > 0 ? (
          <div className="sigs big">{sigs.map((s) => <span key={s.text} className={`sig ${s.tone ?? ""} ${s.strong ? "strong" : ""}`}>{s.text}</span>)}</div>
        ) : null}

        {(e.one_liner || e.headline) && <p className="ns-story">{e.one_liner || e.headline}</p>}
        {e.why && <div className="ns-why"><span>Why it ranks</span>{e.why}</div>}
        {e.one_liner && e.headline && <div className="ns-src">{e.headline}</div>}

        <div className="ns-links">
          {e.url && <a className="btn" href={e.url} target="_blank" rel="noreferrer">Filing ↗</a>}
          <Link className="btn primary" href={`/research/${e.symbol}`}>Research →</Link>
        </div>
      </div>
    </div>
  );
}

/** One open story at a time, shared by the rail and the list. */
export function useNewsSheet() {
  const [cur, setCur] = useState<DigestEvent | null>(null);
  const close = useCallback(() => setCur(null), []);
  return { open: setCur, sheet: <NewsSheet e={cur} onClose={close} /> };
}
