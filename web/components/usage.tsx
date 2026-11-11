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
  const hitRate = calls ? Math.round((cached / calls) * 100) : 0;

  return (
    <>
      <div className="stat">
        <div><b>{calls.toLocaleString("en-IN")}</b><span>LLM calls · {n(data.days) || 7}d</span></div>
        <div><b>{Math.round(hitRate)}%</b><span>cache hits</span></div>
        <div><b>{((tin + tout) / 1000).toFixed(1)}K</b><span>tokens</span></div>
      </div>
      {rows.length > 0 && (
        <table className="t" style={{ marginTop: 10 }}>
          <thead><tr><th>Task</th><th>Model</th><th>Calls</th><th>Tokens</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="lbl">{String(r.task ?? "")}</td>
                <td className="dim">{String(r.model ?? "").replace("gemini-", "")}</td>
                <td>{n(r.calls ?? r.count)}</td>
                <td>{((n(r.tokens_in) + n(r.tokens_out)) / 1000).toFixed(1)}K</td>
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
