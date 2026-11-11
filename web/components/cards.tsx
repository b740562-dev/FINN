"use client";

import { useState } from "react";
import type { Bio, DigestEvent, Metric, ResultsCard } from "@/lib/types";
import { bp, crore, pct, tone } from "@/lib/format";

function initials(name: string) {
  return name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("");
}

/** ₹ crore, compact: 3,30,601 -> 3.31L cr · 65,436 -> 65.4K cr · 909 -> 909 cr */
export function crShort(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  const a = Math.abs(v);
  if (a >= 100000) return `${(v / 100000).toFixed(2)}L cr`;
  if (a >= 10000) return `${(v / 1000).toFixed(1)}K cr`;
  return `${Math.round(v).toLocaleString("en-IN")} cr`;
}

function Arrow({ v }: { v: number | null | undefined }) {
  if (v === null || v === undefined || v === 0) return null;
  return <span aria-hidden>{v > 0 ? "▲" : "▼"}</span>;
}

/** The interpretation first: big YoY change per headline metric, value small. */
export function KpiTiles({ card }: { card: ResultsCard }) {
  if (card.status !== "ready" || !card.metrics) return null;
  const by = Object.fromEntries(card.metrics.map((m) => [m.key, m]));
  const margin = card.ratios?.find((r) => r.key === "ebitda_margin") ?? card.ratios?.find((r) => r.key === "pat_margin");
  const tiles: Metric[] = [by.revenue, by.ebitda ?? by.nii, by.pat].filter(Boolean) as Metric[];
  return (
    <div className="kpis">
      {tiles.map((m) => (
        <div key={m.key} className="kpi">
          <span className="k">{m.key === "nii" ? "NII" : m.name}</span>
          <b className={tone(m.yoy_pct)}><Arrow v={m.yoy_pct} />{pct(m.yoy_pct, 0).replace("+", "").replace("−", "")}</b>
          <span className="s">{crShort(m.value)}</span>
        </div>
      ))}
      {margin && margin.value !== null && (
        <div className="kpi">
          <span className="k">{margin.key === "ebitda_margin" ? "Margin" : "PAT mgn"}</span>
          <b>{margin.value.toFixed(1)}%</b>
          <span className={`s ${tone(margin.yoy_bp)}`}>{bp(margin.yoy_bp)} YoY</span>
        </div>
      )}
    </div>
  );
}

export function ResultsTable({ card }: { card: ResultsCard }) {
  if (card.status !== "ready" || !card.metrics) {
    return <div className="take">Numbers for this quarter aren&apos;t posted yet.</div>;
  }
  const amount = (m: Metric) => (
    <tr key={m.key}>
      <td className="lbl">{m.name}</td>
      <td>{crore(m.value)}</td>
      <td className={tone(m.qoq_pct)}>{pct(m.qoq_pct)}</td>
      <td className={tone(m.yoy_pct)}>{pct(m.yoy_pct)}</td>
    </tr>
  );
  const ratio = (m: Metric) => {
    const bad = m.key === "gnpa" || m.key === "nnpa";   // a rise in NPAs is bad
    const t = (v: number | null | undefined) => (bad ? (tone(v) === "up" ? "dn" : tone(v) === "dn" ? "up" : "flat") : tone(v));
    return (
      <tr key={m.key}>
        <td className="lbl">{m.name}</td>
        <td>{m.value === null ? "–" : `${m.value.toFixed(1)}%`}</td>
        <td className={t(m.qoq_bp)}>{bp(m.qoq_bp)}</td>
        <td className={t(m.yoy_bp)}>{bp(m.yoy_bp)}</td>
      </tr>
    );
  };
  return (
    <table className="t">
      <thead><tr><th>{card.quarter_label} · ₹ cr</th><th>Actual</th><th>QoQ</th><th>YoY</th></tr></thead>
      <tbody>{card.metrics.map(amount)}{card.ratios?.map(ratio)}</tbody>
    </table>
  );
}

export function BioBlock({ bio, full = false, compact = false }: { bio: Bio; full?: boolean; compact?: boolean }) {
  return (
    <div className="person">
      <div className="av">{initials(bio.name)}</div>
      <div style={{ minWidth: 0, alignSelf: "center" }}>
        {!compact && <div className="pn">{bio.name}</div>}
        {!compact && <div className="pr">{bio.role}</div>}
        {bio.status === "ready" && bio.headline && <div className="cred">{bio.headline}</div>}
        {full && bio.status === "ready" && (
          <>
            {bio.summary && <div className="pb">{bio.summary}</div>}
            {bio.education && bio.education.length > 0 && <div className="chiprow">{bio.education.map((e) => <span key={e} className="pill">{e.split(",")[0]}</span>)}</div>}
          </>
        )}
        {full && bio.sources && bio.sources.length > 0 && (
          <div className="srcs">
            {bio.sources.map((s) => {
              let host = s.url;
              try { host = new URL(s.url).hostname.replace(/^www\./, ""); } catch {}
              return <a key={s.url} href={s.url} target="_blank" rel="noreferrer">{host}</a>;
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Importance tiers inside "routine" (all below the feed's cut-off). */
const TIERS = [
  { key: "look", label: "Worth a look", min: 25 },
  { key: "minor", label: "Minor", min: 15 },
  { key: "paper", label: "Paperwork", min: 0 },
] as const;
type Tier = (typeof TIERS)[number]["key"];

function tierOf(m: number): Tier {
  return (TIERS.find((t) => m >= t.min) ?? TIERS[2]).key;
}

/** Exchange boilerplate off the front of a headline. */
function tidy(h: string) {
  return h
    .replace(/^(Announcement|Disclosure|Intimation)\s+under\s+(Regulation\s+30\s*)?(of\s+)?(SEBI\s*)?\(?LODR\)?(,?\s*Regulations,?\s*2015)?\s*[-–:]?\s*/i, "")
    .replace(/_/g, " ")
    .trim() || h;
}

export function RoutineList({ items, mix }: { items: DigestEvent[]; mix: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  void mix;
  const total = items.reduce((n, e) => n + 1 + e.related, 0);
  if (!total) return null;
  const counts: Record<Tier, number> = { look: 0, minor: 0, paper: 0 };
  for (const e of items) counts[tierOf(e.materiality)] += 1 + e.related;
  const sorted = [...items].sort((a, b) => b.materiality - a.materiality || b.filed_at.localeCompare(a.filed_at));
  return (
    <div className="routine">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="rt-title">{open ? "▾" : "▸"} {total} routine set aside</span>
        <span className="rt-legend">
          {TIERS.map((t) => counts[t.key] > 0 && (
            <span key={t.key} className={`rt-key ${t.key}`}><i />{counts[t.key]} {t.label}</span>
          ))}
        </span>
      </button>
      {open && (
        <ul>
          {sorted.map((e) => {
            const t = tierOf(e.materiality);
            return (
              <li key={e.filing_ids[0]} className={`rt-${t}`}>
                <span className="tk">{e.symbol}</span>
                <span className="rt-cat">{e.label}</span>
                <span className="rt-h">{e.one_liner || tidy(e.headline)}</span>
                {e.related > 0 && <span className="rt-rel">+{e.related}</span>}
                {e.url && <a className="link" href={e.url} target="_blank" rel="noreferrer" aria-label="Open filing">↗</a>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
