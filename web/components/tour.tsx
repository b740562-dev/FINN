"use client";

import { useEffect, useRef, useState } from "react";
import { LogoMark } from "./logo";

const KEY = "finn.tour.v1";

const STEPS: { icon: React.ReactNode; tone: string; title: string; body: string; points: string[] }[] = [
  {
    tone: "lime",
    title: "Today",
    body: "What changed for the stocks you own, ranked by how much it matters to your money.",
    points: ["Results, CEO changes, deals, ratings", "Numbers first. Tap any story for detail", "Paperwork folded away"],
    icon: <path d="M3 3v18h18M7 15l4-4 3 3 5-6" />,
  },
  {
    tone: "amber",
    title: "Alerts",
    body: "FINN watches prices, volumes and filings against your own rules, with the ₹ impact on your position.",
    points: ["You decide what counts as unusual", "Colour-coded by kind and importance", "Search any company before you buy"],
    icon: <><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>,
  },
  {
    tone: "blue",
    title: "Research",
    body: "Is the company actually doing well? Answers come only from its own reports and reported numbers.",
    points: ["Promise vs delivered on guidance", "Health check, bull vs bear", "Every claim links to its source"],
    icon: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  },
  {
    tone: "green",
    title: "Ask me",
    body: "Surya, your investment guide. Type or speak a question; company facts are verified against the original.",
    points: ["✓ Verified answers with source links", "Says so when it doesn’t know", "Never gives buy or sell calls"],
    icon: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" /></>,
  },
];

/** A four-card introduction shown once per browser, on the first visit to Today. */
export function Tour() {
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const touch = useRef<number | null>(null);

  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setOpen(true); } catch {}
  }, []);

  function done() {
    setOpen(false);
    try { localStorage.setItem(KEY, "1"); } catch {}
  }

  if (!open) return null;
  const s = STEPS[i];
  const last = i === STEPS.length - 1;

  return (
    <div className="tour-bg" role="dialog" aria-modal aria-label="How FINN works">
      <div className="tour"
        onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => {
          if (touch.current === null) return;
          const dx = e.changedTouches[0].clientX - touch.current;
          if (dx < -40 && !last) setI(i + 1);
          if (dx > 40 && i > 0) setI(i - 1);
          touch.current = null;
        }}>
        <button className="tour-skip" onClick={done}>Skip</button>
        <div className="tour-kicker"><LogoMark size={18} /> How FINN works · {i + 1}/{STEPS.length}</div>
        <span className={`tour-ic ${s.tone}`}>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{s.icon}</svg>
        </span>
        <h2>{s.title}</h2>
        <p>{s.body}</p>
        <ul>{s.points.map((p) => <li key={p}>{p}</li>)}</ul>
        <div className="tour-dots">
          {STEPS.map((_, k) => <button key={k} className={k === i ? "on" : ""} onClick={() => setI(k)} aria-label={`Step ${k + 1}`} />)}
        </div>
        <div className="tour-acts">
          {i > 0 && <button className="btn ghost" onClick={() => setI(i - 1)}>Back</button>}
          <button className="btn primary" onClick={() => (last ? done() : setI(i + 1))}>{last ? "Start exploring" : "Next"}</button>
        </div>
      </div>
    </div>
  );
}
