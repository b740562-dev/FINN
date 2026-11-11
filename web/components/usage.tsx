"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Row = Record<string, unknown>;

function n(v: unknown): number {
  return typeof v === "number" ? v : Number(v ?? 0) || 0;
}

/** "How FINN thinks": which models did what, tokens, cache hits. Shape-tolerant
 *  so it works with the /usage payload as implemented server-side. */
export function UsagePanel() {
  const [data, setData] = useState<Row | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Row>("/usage").then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <p className="sub">Usage stats unavailable ({err}).</p>;
  if (!data) return <div className="skel sm" style={{ margin: 0 }} />;

  const totals = (data.totals ?? data.total ?? data) as Row;
  const rows = ((data.by_task ?? data.tasks ?? []) as Row[]).slice(0, 8);
  const calls = n(totals.calls ?? totals.count);
  const cached = n(totals.cache_hits ?? totals.cached);
  const tin = n(totals.tokens_in);
  const tout = n(totals.tokens_out);
  // `calls` = model calls actually made; `cached` = requests answered from cache.
  const hitRate = calls + cached ? Math.round((cached / (calls + cached)) * 100) : 0;

  const cost = data.cost_usd === null || data.cost_usd === undefined ? null : n(data.cost_usd);
  const usd = (v: number) => (v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`);

  return (
    <>
      <div className="stat">
        <div><b>{calls.toLocaleString("en-IN")}</b><span>model calls · {n(data.days) || 7}d</span></div>
        <div><b>{Math.round(hitRate)}%</b><span>served from cache</span></div>
        <div><b>{cost === null ? "–" : usd(cost)}</b><span>at paid rates</span></div>
      </div>
      <p className="sub" style={{ marginTop: 8, marginBottom: 0 }}>
        Billed: <b className="up">₹0</b>, since FINN runs on Gemini&apos;s free tier. The figure above is what the same
        {" "}{((tin + tout) / 1000).toFixed(1)}K tokens would cost on the paid tier (Google list prices, Nov 2026).
      </p>
      {rows.length > 0 && (
        <table className="t" style={{ marginTop: 10 }}>
          <thead><tr><th>Task</th><th>Model</th><th>Calls</th><th>Cost</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="lbl">{String(r.task ?? "").replace(/_/g, " ")}</td>
                <td className="dim">{String(r.model ?? "").replace("gemini-", "")}</td>
                <td>{n(r.calls ?? r.count)}{n(r.cache_hits) ? <span className="dim"> +{n(r.cache_hits)}c</span> : null}</td>
                <td>{r.cost_usd === null || r.cost_usd === undefined ? "–" : usd(n(r.cost_usd))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="sub" style={{ marginTop: 10, marginBottom: 0 }}>
        Routing: rules first (most filings never reach a model) → flash-lite for bulk extraction → a stronger flash model only
        for reasoning (promise vs delivered, bull/bear, Q&amp;A), with automatic fallback when a model is overloaded. Every
        response is cached, so repeat work is free. Numbers on cards are computed, never generated.
      </p>
    </>
  );
}
