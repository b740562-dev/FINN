"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, post, put } from "@/lib/api";
import type { Holding, Rules } from "@/lib/types";
import { inr } from "@/lib/format";
import { useAuth } from "@/components/auth";
import { initialsOf, profileCompleteness, useData } from "@/components/data";
import { Ring } from "@/components/ring";
import { MyDocuments } from "@/components/my-docs";
import { UsagePanel } from "@/components/usage";
import { ProfileButton } from "@/components/profile-menu";

const CAT_LABEL: Record<string, string> = {
  results: "Results", "M&A": "M&A", fund_raise: "Fund raise", management_change: "Mgmt change", litigation: "Legal",
  insider_trading: "Insider", earnings_call: "Concall", investor_meetings: "Investor meet", credit_rating: "Rating",
  dividend: "Dividend", bonus_split: "Bonus/split", capex: "Capex", press_release: "Updates", postal_ballot: "Postal ballot",
  agm_egm: "AGM/EGM", pledging: "Pledge", unclassified: "Routine",
};

const SOURCES: [string, string, string][] = [
  ["₹", "Prices", "Yahoo · end of day"],
  ["▤", "Filings", "NSE / BSE via screener"],
  ["❑", "Research", "Company documents only"],
];

export default function You() {
  const { session } = useAuth();
  const { me, refreshMe, setUnread, unread, profile } = useData();
  const [rules, setRules] = useState<Rules | null>(null);
  const [savingRules, setSavingRules] = useState(false);
  const [rulesMsg, setRulesMsg] = useState<string | null>(null);
  const [rows, setRows] = useState<{ symbol: string; quantity: number; name?: string }[]>([]);
  const [holdMsg, setHoldMsg] = useState<string | null>(null);
  const [addQ, setAddQ] = useState("");
  const [addSugg, setAddSugg] = useState<{ symbol: string; name: string }[]>([]);
  const isGuest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);
  const email = (session?.user as { email?: string | null } | undefined)?.email || null;
  const workLine = [profile?.work_role, profile?.work_company].filter(Boolean).join(" · ");
  const pctDone = profileCompleteness(profile, email);

  useEffect(() => {
    api<Rules>("/rules").then(setRules).catch(() => {});
  }, []);
  useEffect(() => {
    if (me) setRows(me.holdings.map((h: Holding) => ({ symbol: h.symbol, quantity: h.quantity, name: h.name })));
  }, [me]);
  useEffect(() => {
    if (addQ.length < 2) return setAddSugg([]);
    const t = setTimeout(() => api<{ symbol: string; name: string }[]>(`/companies?q=${encodeURIComponent(addQ)}`)
      .then((r) => setAddSugg(r.filter((c) => !rows.some((x) => x.symbol === c.symbol)).slice(0, 5))).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [addQ, rows]);

  async function saveRules() {
    if (!rules) return;
    setSavingRules(true);
    setRulesMsg(null);
    try {
      const { all_categories: _ignored, ...body } = rules;
      void _ignored;
      const r = await put<{ alerts: { created: { eod: number; filing: number } } }>("/rules", body);
      const c = r.alerts.created;
      setRulesMsg(`Saved. Inbox rebuilt under your rules: ${c.eod} price/volume + ${c.filing} filing alerts (last 30 days).`);
      setUnread(c.eod + c.filing);
      refreshMe();
    } catch (e) {
      setRulesMsg((e as Error).message);
    } finally {
      setSavingRules(false);
    }
  }

  async function saveHoldings() {
    setHoldMsg(null);
    try {
      await put("/holdings", rows.filter((r) => r.quantity > 0).map(({ symbol, quantity }) => ({ symbol, quantity })));
      setHoldMsg("Holdings saved.");
      refreshMe();
    } catch (e) {
      setHoldMsg((e as Error).message);
    }
  }

  async function resetDemo() {
    await post("/holdings/reset");
    setHoldMsg("Back to the 18-stock demo portfolio.");
    refreshMe();
  }

  return (
    <>
      <header className="topbar">
        <ProfileButton />
        <div className="brand">
          <span className="logo">YOU</span>
        </div>
      </header>

      <section className="yc">
        <div className="yc-top">
          <div className="yc-av">{initialsOf(profile, email, isGuest)}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="yc-name">{profile?.full_name || (isGuest ? "Guest investor" : email || "Your profile")}</div>
            {workLine && <div className="yc-work">{workLine}</div>}
            <Link href="/profile" className="yc-edit">Edit profile <span aria-hidden>▸</span></Link>
          </div>
          <Ring pct={pctDone} size={44} stroke={4} />
        </div>
        <Link href="/profile" className="yc-band">
          <span className="yc-badge">{isGuest ? "☁" : pctDone >= 100 ? "✓" : "★"}</span>
          <span className="yc-bt">{isGuest ? "Save your account" : pctDone >= 100 ? "Profile complete" : "Complete your profile"}</span>
          <span className="yc-chev" aria-hidden>›</span>
        </Link>
      </section>

      <div className="ytiles">
        <Link href="#portfolio" className="ytile">
          <span className="yi">◫</span>
          <span><small>Portfolio</small><b>{me ? inr(me.totals.value, { compact: true }) : "–"}</b></span>
        </Link>
        <Link href="/alerts" className="ytile">
          <span className="yi">◉</span>
          <span><small>Alerts</small><b className={unread ? "hot" : ""}>{unread} unread</b></span>
        </Link>
      </div>

      <section className="panel ysec" id="rules">
        <h2>Alert sensitivity</h2>
        <h3>Price &amp; volume</h3>
        {rules ? (
          <>
            <div className="field">
              <label htmlFor="mv">Day move beyond</label><span className="val">±{rules.move_pct}%</span>
            </div>
            <input id="mv" type="range" min={1} max={15} step={0.5} value={rules.move_pct}
              onChange={(e) => setRules({ ...rules, move_pct: Number(e.target.value) })} />
            <div className="field">
              <label htmlFor="vm">Volume above</label><span className="val">{rules.volume_multiple}× 20D avg</span>
            </div>
            <input id="vm" type="range" min={1.5} max={6} step={0.25} value={rules.volume_multiple}
              onChange={(e) => setRules({ ...rules, volume_multiple: Number(e.target.value) })} />
            {Object.keys(rules.overrides || {}).length > 0 && (
              <p className="sub" style={{ marginTop: 8 }}>
                Per-stock: {Object.entries(rules.overrides).map(([s, o]) => `${s} ${o.move_pct ? `±${o.move_pct}%` : ""}${o.volume_multiple ? ` ${o.volume_multiple}×` : ""}`).join(" · ")}
              </p>
            )}
            <h3 style={{ marginTop: 14 }}>Filing types</h3>
            <div className="chips">
              {(rules.all_categories ?? Object.keys(CAT_LABEL)).filter((c) => c !== "unclassified").map((c) => {
                const on = rules.categories.includes(c);
                return (
                  <button key={c} className={`chip ${on ? "on" : ""}`}
                    onClick={() => setRules({ ...rules, categories: on ? rules.categories.filter((x) => x !== c) : [...rules.categories, c] })}>
                    {CAT_LABEL[c] ?? c}
                  </button>
                );
              })}
            </div>
            <div style={{ marginTop: 12 }}>
              <button className="btn primary" onClick={saveRules} disabled={savingRules}>{savingRules ? "Rebuilding…" : "Save rules"}</button>
            </div>
            {rulesMsg && <div className="ok">{rulesMsg}</div>}
          </>
        ) : <div className="skel sm" style={{ margin: 0 }} />}
      </section>

      <section className="panel ysec" id="portfolio">
        <h2>Portfolio<span>{rows.length} holdings{me ? ` · ${inr(me.totals.value, { compact: true })}` : ""}</span></h2>
        {rows.map((r, i) => (
          <div className="hold" key={r.symbol}>
            <div><div className="tk">{r.symbol}</div><div className="co">{r.name}</div></div>
            <input className="qty" type="number" min={0} value={r.quantity}
              onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, quantity: Number(e.target.value) } : x)))} aria-label={`${r.symbol} quantity`} />
            <button className="x" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={`Remove ${r.symbol}`}>×</button>
          </div>
        ))}
        <div style={{ marginTop: 10, position: "relative" }}>
          <input className="txt" placeholder="Add a holding (symbol or name)" value={addQ} onChange={(e) => setAddQ(e.target.value)} />
          {addSugg.length > 0 && (
            <div style={{ border: "1px solid var(--line-2)", borderRadius: 8, marginTop: 4 }}>
              {addSugg.map((c) => (
                <button key={c.symbol} style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", fontSize: 12.5 }}
                  onClick={() => { setRows([...rows, { symbol: c.symbol, name: c.name, quantity: 1 }]); setAddQ(""); setAddSugg([]); }}>
                  <span className="tk">{c.symbol}</span> <span className="muted">{c.name}</span>
                </button>
              ))}
            </div>
          )}
          
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button className="btn primary" onClick={saveHoldings}>Save holdings</button>
          <button className="btn ghost" onClick={resetDemo}>Reset to demo</button>
        </div>
        {holdMsg && <div className="ok">{holdMsg}</div>}
      </section>

      {me?.user.is_admin && (
        <>
          <section className="panel ysec" id="usage"><h2>How FINN thinks<span>admin</span></h2><UsagePanel /></section>
        </>
      )}

      <section className="panel ysec" id="sources">
        <h2>Data sources</h2>
        {SOURCES.map(([ic, k, v]) => (
          <div className="yrow" key={k}><span className="yi">{ic}</span><span className="yk">{k}</span><span className="yv">{v}</span></div>
        ))}
        <MyDocuments guest={isGuest} />
        <p className="yfoot">Not investment advice.</p>
      </section>
    </>
  );
}
