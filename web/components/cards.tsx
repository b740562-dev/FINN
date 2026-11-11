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

export function RoutineList({ items, mix }: { items: DigestEvent[]; mix: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  const total = items.reduce((n, e) => n + 1 + e.related, 0);
  if (!total) return null;
  const top = Object.entries(mix).slice(0, 3);
  return (
    <div className="routine">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{open ? "▾" : "▸"} {total} routine</span>
        <span className="chiprow" style={{ margin: 0 }}>{top.map(([k, v]) => <span key={k} className="pill">{k} {v}</span>)}</span>
      </button>
      {open && (
        <ul>
          {items.map((e) => (
            <li key={e.filing_ids[0]}>
              <span className="tk">{e.symbol}</span>
              <span style={{ flex: 1 }}>{e.one_liner || e.headline}</span>
              {e.url && <a className="link" href={e.url} target="_blank" rel="noreferrer">↗</a>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
