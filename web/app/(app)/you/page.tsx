"use client";

import { useEffect, useState } from "react";
import { api, post, put } from "@/lib/api";
import type { Holding, Rules } from "@/lib/types";
import { inr } from "@/lib/format";
import { useAuth } from "@/components/auth";
import { useData } from "@/components/data";
import { UsagePanel } from "@/components/usage";
import { ProfileButton } from "@/components/profile-menu";

const CAT_LABEL: Record<string, string> = {
  results: "Results", "M&A": "M&A", fund_raise: "Fund raise", management_change: "Mgmt change", litigation: "Legal",
  insider_trading: "Insider", earnings_call: "Concall", investor_meetings: "Investor meet", credit_rating: "Rating",
  dividend: "Dividend", bonus_split: "Bonus/split", capex: "Capex", press_release: "Updates", postal_ballot: "Postal ballot",
  agm_egm: "AGM/EGM", pledging: "Pledge", unclassified: "Routine",
};

export default function You() {
  const { session, signOut, saveAccountEmail } = useAuth();
  const { me, refreshMe, setUnread } = useData();
  const [rules, setRules] = useState<Rules | null>(null);
  const [savingRules, setSavingRules] = useState(false);
  const [rulesMsg, setRulesMsg] = useState<string | null>(null);
  const [rows, setRows] = useState<{ symbol: string; quantity: number; name?: string }[]>([]);
  const [holdMsg, setHoldMsg] = useState<string | null>(null);
  const [addQ, setAddQ] = useState("");
  const [addSugg, setAddSugg] = useState<{ symbol: string; name: string }[]>([]);
  const [email, setEmail] = useState("");
  const [acctMsg, setAcctMsg] = useState<string | null>(null);
  const isGuest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);

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
          <span className="when">{isGuest ? "guest account" : session?.user.email}</span>
        </div>
      </header>

      <div className="sec"><span>── What counts as unusual</span></div>
      <section className="panel" id="rules">
        <h3>Price &amp; volume alerts</h3>
        
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
            <h3 style={{ marginTop: 14 }}>Filing types that alert you</h3>
            
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
              <button className="btn primary" onClick={saveRules} disabled={savingRules}>{savingRules ? "REBUILDING…" : "SAVE RULES"}</button>
            </div>
            {rulesMsg && <div className="ok">{rulesMsg}</div>}
          </>
        ) : <div className="skel sm" style={{ margin: 0 }} />}
      </section>

      <div className="sec"><span>── Portfolio</span>{me && <span>{inr(me.totals.value, { compact: true })}</span>}</div>
      <section className="panel" id="portfolio">
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
          <button className="btn primary" onClick={saveHoldings}>SAVE HOLDINGS</button>
          <button className="btn ghost" onClick={resetDemo}>RESET TO DEMO</button>
        </div>
        {holdMsg && <div className="ok">{holdMsg}</div>}
      </section>

      {me?.user.is_admin && (
        <>
          <div className="sec"><span>── How FINN thinks</span><span>admin</span></div>
          <section className="panel" id="usage"><UsagePanel /></section>
        </>
      )}

      <div className="sec"><span>── Account</span></div>
      <section className="panel" id="account">
        {isGuest ? (
          <>
            <h3>You&apos;re using a guest account</h3>
            <p className="sub">Add an email to keep this portfolio.</p>
            <form style={{ display: "flex", gap: 8 }} onSubmit={async (e) => {
              e.preventDefault();
              try { await saveAccountEmail(email); setAcctMsg(`Check ${email} to confirm.`); } catch (er) { setAcctMsg((er as Error).message); }
            }}>
              <input className="txt" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <button className="btn" disabled={!email}>SAVE</button>
            </form>
            {acctMsg && <div className="ok">{acctMsg}</div>}
          </>
        ) : (
          <p className="sub" style={{ margin: 0 }}>Signed in as {session?.user.email}.</p>
        )}
        <div style={{ marginTop: 12 }}><button className="btn ghost" onClick={signOut}>SIGN OUT</button></div>
      </section>

      <div className="sec"><span>── Sources</span></div>
      <section className="panel" id="sources">
        <div className="chiprow" style={{ margin: 0 }}>
          <span className="pill">EOD prices · Yahoo</span><span className="pill">Filings · NSE/BSE via screener</span>
          <span className="pill">Research · company documents only</span><span className="pill">Not investment advice</span>
        </div>
      </section>
    </>
  );
}
