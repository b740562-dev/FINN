"use client";

import { useEffect, useState } from "react";
import type { Digest, Me } from "@/lib/types";

function spokenNumber(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e7) return `${(a / 1e7).toFixed(1)} crore`;
  if (a >= 1e5) return `${(a / 1e5).toFixed(1)} lakh`;
  return `${Math.round(a).toLocaleString("en-IN")}`;
}

function spokenPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  return `${n >= 0 ? "up" : "down"} ${Math.abs(n).toFixed(Math.abs(n) >= 10 ? 0 : 1)} percent`;
}

/** Builds the ~60-second spoken brief from the digest. Deterministic text. */
export function briefScript(me: Me | null, d: Digest | null, windowLabel: string): string {
  const parts: string[] = [];
  const hr = new Date().getHours();
  parts.push(hr < 12 ? "Good morning." : hr < 17 ? "Good afternoon." : "Good evening.");
  if (me) {
    parts.push(`Your portfolio is worth ${spokenNumber(me.totals.value)} rupees, ${spokenPct(me.totals.day_pct)} on the day.`);
  }
  if (!d || d.matters.length === 0) {
    parts.push(`Nothing material across your holdings in the ${windowLabel}.`);
    return parts.join(" ");
  }
  parts.push(`${d.matters.length} thing${d.matters.length === 1 ? "" : "s"} matter in the ${windowLabel}.`);
  d.matters.slice(0, 4).forEach((e, i) => {
    const lead = ["First", "Next", "Then", "Also"][i];
    const card = e.enrichment?.results_card;
    if (e.category === "results" && card?.status === "ready" && card.metrics) {
      const rev = card.metrics.find((m) => m.key === "revenue");
      const pat = card.metrics.find((m) => m.key === "pat");
      parts.push(`${lead}, ${e.company} results for ${card.quarter_label?.replace("FY", "F Y ")}: revenue ${spokenPct(rev?.yoy_pct)}, profit ${spokenPct(pat?.yoy_pct)} year on year.`);
      if (card.flags?.length) parts.push(`Note: ${card.flags[0]}.`);
    } else if (e.category === "management_change" && e.enrichment?.bios?.[0]?.status === "ready") {
      const b = e.enrichment.bios[0];
      parts.push(`${lead}, at ${e.company}, ${b.name} takes over as ${b.role}. ${b.headline ?? ""}`);
    } else {
      parts.push(`${lead}, ${e.company}: ${(e.one_liner || e.headline).replace(/₹/g, "rupees ")}`);
    }
  });
  const rest = d.matters.length - 4;
  if (rest > 0) parts.push(`${rest} more on your screen.`);
  if (d.counts.routine_filings) parts.push(`${d.counts.routine_filings} routine filings were set aside.`);
  return parts.join(" ");
}

export function BriefButton({ script }: { script: string }) {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    return () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); };
  }, []);

  if (!supported) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(script);
    const voices = synth.getVoices();
    u.voice = voices.find((v) => v.lang === "en-IN") || voices.find((v) => v.lang.startsWith("en-GB")) || voices.find((v) => v.lang.startsWith("en")) || null;
    u.rate = 1.04;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  }

  return (
    <button className={`play ${speaking ? "on" : ""}`} onClick={toggle} aria-label="Play audio brief">
      {speaking ? "■ STOP" : "▶ 60s BRIEF"}
    </button>
  );
}
