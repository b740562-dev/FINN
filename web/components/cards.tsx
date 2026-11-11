"use client";

import { useState } from "react";
import Link from "next/link";
import type { Bio, DigestEvent, Metric, ResultsCard } from "@/lib/types";
import { bp, crore, pct, shortDate, tone } from "@/lib/format";

const VARIANT: Record<string, string> = {
  results: "results",
  management_change: "mgmt",
  "M&A": "deal",
  fund_raise: "deal",
  capex: "deal",
};

function initials(name: string) {
  return name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("");
}

export function ResultsTable({ card }: { card: ResultsCard }) {
  if (card.status !== "ready" || !card.metrics) {
    return <div className="take">Numbers for this quarter aren&apos;t posted yet. FINN will fill them in on the next refresh.</div>;
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
    // For NPA ratios a rise is bad: invert the colour.
    const bad = m.key === "gnpa" || m.key === "nnpa";
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
    <>
      <table className="t">
        <thead>
          <tr><th>{card.quarter_label} · ₹ cr</th><th>Actual</th><th>QoQ</th><th>YoY</th></tr>
        </thead>
        <tbody>
          {card.metrics.map(amount)}
          {card.ratios?.map(ratio)}
        </tbody>
      </table>
      {card.flags?.map((f) => <div key={f} className="flag red">⚑ {f}</div>)}
      {card.cross_check?.filter((x) => !x.consistent).map((x) => (
        <div key={x.filing_text} className="flag">
          Filing text says “{x.filing_text}”, but the reported table shows {pct(x.card_yoy_pct)} YoY. Check the filing.
        </div>
      ))}
    </>
  );
}

export function BioBlock({ bio }: { bio: Bio }) {
  return (
    <div className="person">
      <div className="av">{initials(bio.name)}</div>
      <div style={{ minWidth: 0 }}>
        <div className="pn">{bio.name}</div>
        <div className="pr">{bio.role}</div>
        {bio.status === "ready" ? (
          <>
            {bio.headline && <div className="pb" style={{ color: "var(--ink-2)" }}>{bio.headline}</div>}
            {bio.summary && <div className="pb">{bio.summary}</div>}
            {bio.education && bio.education.length > 0 && <div className="pb dim">{bio.education.join(" · ")}</div>}
          </>
        ) : (
          <div className="pb dim">Couldn&apos;t confirm a public profile for this person yet.</div>
        )}
        {bio.sources && bio.sources.length > 0 && (
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

export function EventCard({ e }: { e: DigestEvent }) {
  const [open, setOpen] = useState(false);
  const variant = VARIANT[e.category] ?? "other";
  const card = e.enrichment?.results_card;
  const bios = (e.enrichment?.bios ?? []).filter((b) => b.status !== "not_found");
  const leaving = (e.enrichment?.people ?? []).filter((p) => p.change === "leaving");
  const text = e.one_liner || e.headline;

  return (
    <article className={`card ${variant}`}>
      <div className="ch">
        <span>
          <Link href={`/research/${e.symbol}`} className="tk">{e.symbol}</Link>
          <span className="tag">{e.label}</span>
          {e.related > 0 && <span className="related">+{e.related} related</span>}
        </span>
        <span className="src">{shortDate(e.filed_at)}</span>
      </div>

      {e.category === "results" && card?.status === "ready" ? (
        <>
          <div className="head">{card.headline}</div>
          <ResultsTable card={card} />
        </>
      ) : (
        <div className="head">{text}</div>
      )}

      {e.category === "management_change" && (
        <>
          {bios.map((b) => <BioBlock key={b.name} bio={b} />)}
          {!bios.length && leaving.length > 0 && (
            <div className="take">Outgoing: {leaving.map((p) => `${p.name} (${p.role})`).join(", ")}</div>
          )}
        </>
      )}

      <div className="foot">
        <span className="why">{e.why}</span>
        <button className="link" onClick={() => setOpen(!open)}>{open ? "LESS" : "DETAILS"}</button>
      </div>

      {open && (
        <div className="take" style={{ marginTop: 10 }}>
          <div className="dim mono" style={{ fontSize: 10, marginBottom: 4 }}>FILING SUBJECT</div>
          <div>{e.headline}</div>
          {e.factors.length > 0 && <div style={{ marginTop: 6 }}>Sized: {e.factors.join(" · ")}</div>}
          <div style={{ marginTop: 6 }} className="dim">
            Materiality {e.materiality}/100 · {e.company}
            {card?.source ? ` · ${card.source}` : ""}
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 14 }}>
            {e.url && <a className="link" href={e.url} target="_blank" rel="noreferrer">OPEN FILING ↗</a>}
            <Link className="link" href={`/research/${e.symbol}`}>RESEARCH {e.symbol} →</Link>
          </div>
        </div>
      )}
    </article>
  );
}

export function RoutineList({ items, mix }: { items: DigestEvent[]; mix: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  const total = items.reduce((n, e) => n + 1 + e.related, 0);
  if (!total) return null;
  const summary = Object.entries(mix).slice(0, 3).map(([k, v]) => `${k.toLowerCase()} ${v}`).join(" · ");
  return (
    <div className="routine">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{open ? "▾" : "▸"} {total} routine filing{total === 1 ? "" : "s"}</span>
        <span>{summary}</span>
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
