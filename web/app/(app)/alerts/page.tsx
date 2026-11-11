"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, post } from "@/lib/api";
import type { Alert } from "@/lib/types";
import { inr, pct, tone } from "@/lib/format";
import { useData } from "@/components/data";
import { ProfileButton } from "@/components/profile-menu";
import { NewsSearch } from "@/components/news-search";

const CAT: Record<string, string> = {
  results: "Results", "M&A": "M&A", fund_raise: "Fund raise", management_change: "Management", litigation: "Legal",
  credit_rating: "Rating", pledging: "Pledge", insider_trading: "Insider", capex: "Capex", press_release: "Update",
};

function dayLabel(d: string | null) {
  if (!d) return "Earlier";
  const date = new Date(d + "T00:00:00");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return date.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

function AlertCard({ a }: { a: Alert }) {
  const p = a.payload;
  if (a.kind === "filing") {
    const variant = p.category === "results" ? "results" : p.category === "management_change" ? "mgmt" : ["M&A", "fund_raise"].includes(p.category ?? "") ? "deal" : "other";
    return (
      <article className={`card ${variant} ${a.read ? "" : "unread"}`}>
        <div className="ch">
          <span><Link className="tk" href={`/research/${a.symbol}`}>{a.symbol}</Link><span className="tag">{CAT[p.category ?? ""] ?? p.category}</span></span>
          <span className="src">FILING</span>
        </div>
        <div className="head">{p.headline}</div>
        <div className="foot">
          <span className="why">{a.name} · materiality {p.materiality}</span>
          {p.url && <a className="link" href={p.url} target="_blank" rel="noreferrer">OPEN FILING ↗</a>}
        </div>
      </article>
    );
  }
  const neg = (p.change_pct ?? 0) < 0;
  return (
    <article className={`card alert ${neg ? "neg" : ""} ${a.read ? "" : "unread"}`}>
      <div className="ch">
        <span>
          <Link className="tk" href={`/research/${a.symbol}`}>{a.symbol}</Link>
          <span className="tag">{a.kind === "move" ? (neg ? "Price drop" : "Price jump") : "Vol spike"}</span>
        </span>
        <span className="src">EOD · ₹{p.close?.toLocaleString("en-IN")}</span>
      </div>
      <div className="metrics num">
        <div>MOVE<b className={tone(p.change_pct)}>{pct(p.change_pct, 1)}</b></div>
        <div>VOLUME<b className={(p.volume_ratio ?? 0) >= (p.rule?.volume_multiple ?? 2) ? "amber" : ""}>{p.volume_ratio?.toFixed(1)}×</b></div>
        {p.impact_inr !== null && p.impact_inr !== undefined && (
          <div>YOUR P&amp;L<b className={tone(p.impact_inr)}>{inr(p.impact_inr, { sign: true, compact: true })}</b></div>
        )}
      </div>
      <div className="foot">
        <span className="why">{(p.triggers ?? []).join(" · ")}</span>
      </div>
    </article>
  );
}

export default function Alerts() {
  const { me, setUnread, bootstrapped } = useData();
  const [items, setItems] = useState<Alert[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "price" | "filing">("all");

  useEffect(() => {
    if (!bootstrapped) return;
    api<{ unread: number; items: Alert[] }>("/alerts?limit=150")
      .then((r) => { setItems(r.items); setUnread(r.unread); })
      .catch((e) => setErr(e.message));
  }, [bootstrapped, setUnread]);

  async function markAll() {
    await post("/alerts/read", {});
    setItems((xs) => xs?.map((x) => ({ ...x, read: true })) ?? null);
    setUnread(0);
  }

  const shown = (items ?? []).filter((a) => filter === "all" || (filter === "filing" ? a.kind === "filing" : a.kind !== "filing"));
  const groups = shown.reduce<Record<string, Alert[]>>((g, a) => {
    const k = dayLabel(a.event_date);
    (g[k] ||= []).push(a);
    return g;
  }, {});
  const r = me?.rules;

  return (
    <>
      <header className="topbar">
        <ProfileButton />
        <div className="brand">
          <span className="logo">ALERTS</span>
          {items && items.some((a) => !a.read) && <button className="link" onClick={markAll}>MARK ALL READ</button>}
        </div>
        <div className="seg">
          {(["all", "price", "filing"] as const).map((f) => (
            <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>{f.toUpperCase()}</button>
          ))}
          <span className="spacer" />
          {r && <Link href="/you" className="asof">±{r.move_pct}% · {r.volume_multiple}× vol ✎</Link>}
        </div>
      </header>

      <NewsSearch />

      {err && <div className="err">{err}</div>}
      {!items && !err && (<><div className="skel sm" style={{ marginTop: 12 }} /><div className="skel sm" /><div className="skel sm" /></>)}
      {items && shown.length === 0 && (
        <div className="empty"><b>No alerts.</b>Nothing crossed your thresholds. You decide what counts as unusual in <Link className="amber" href="/you">settings</Link>.</div>
      )}
      {Object.entries(groups).map(([day, xs]) => (
        <section key={day}>
          <div className="sec"><span>── {day}</span><span>{xs.length}</span></div>
          {xs.map((a) => <AlertCard key={a.id} a={a} />)}
        </section>
      ))}
    </>
  );
}
