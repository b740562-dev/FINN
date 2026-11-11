"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Co = { symbol: string; name: string; sector: string | null };

// Minimal typing for the browser speech API (not in TS's DOM lib everywhere).
type SpeechRec = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};

const STOP = new Set(["did", "does", "do", "is", "are", "was", "what", "how", "why", "the", "a", "an", "of", "on", "in",
  "for", "and", "to", "hit", "its", "it", "has", "have", "vs", "with", "about", "tell", "me", "show", "research"]);

/** Words that might name a company: drop question words, keep 2+ letter tokens. */
function candidates(text: string): string[] {
  return text.replace(/[?.,!']/g, " ").split(/\s+/).filter((w) => w.length >= 2 && !STOP.has(w.toLowerCase()));
}

export function AskBar() {
  const [q, setQ] = useState("");
  const [sugg, setSugg] = useState<Co[]>([]);
  const [focus, setFocus] = useState(false);
  const [listening, setListening] = useState(false);
  const [canListen, setCanListen] = useState(false);
  const recRef = useRef<SpeechRec | null>(null);
  const router = useRouter();
  const path = usePathname() || "/";
  const onResearch = /^\/research\/[^/]+/.test(path);

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
    setCanListen(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  useEffect(() => {
    const words = candidates(q);
    if (!words.length) return setSugg([]);
    const t = setTimeout(async () => {
      try {
        const seen = new Map<string, Co>();
        for (const w of words.slice(0, 3)) {
          for (const c of await api<Co[]>(`/companies?q=${encodeURIComponent(w)}`)) seen.set(c.symbol, c);
          if (seen.size >= 5) break;
        }
        setSugg([...seen.values()].slice(0, 5));
      } catch {
        setSugg([]);
      }
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  function go(symbol: string, question?: string) {
    setQ("");
    setSugg([]);
    (document.activeElement as HTMLElement | null)?.blur();
    const qs = question ? `?q=${encodeURIComponent(question)}` : "";
    router.push(`/research/${encodeURIComponent(symbol.toUpperCase())}${qs}`);
  }

  function submit(text: string) {
    const t = text.trim();
    if (!t) return;
    const words = candidates(t).map((w) => w.toLowerCase());
    const match = sugg.find((c) =>
      words.some((w) => c.symbol.toLowerCase() === w || c.name.toLowerCase().split(/\s+/)[0] === w));
    const isQuestion = t.split(/\s+/).length > 2 || t.includes("?");
    if (match) return go(match.symbol, isQuestion ? t : undefined);
    if (onResearch && isQuestion) {
      window.dispatchEvent(new CustomEvent("finn:ask", { detail: t }));
      setQ("");
      return;
    }
    // Single token we don't track yet: treat it as an NSE ticker (any-ticker research).
    if (/^[A-Za-z&-]{2,20}$/.test(t)) return go(t);
    if (sugg[0]) return go(sugg[0].symbol, isQuestion ? t : undefined);
    router.push(`/research?q=${encodeURIComponent(t)}`);
    setQ("");
  }

  function mic() {
    const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
    const R = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!R) return;
    if (listening) return recRef.current?.stop();
    const rec = new R();
    rec.lang = "en-IN";
    rec.interimResults = true;
    let finalText = "";
    rec.onresult = (e) => {
      finalText = Array.from(e.results).map((r) => r[0].transcript).join(" ");
      setQ(finalText);
    };
    rec.onend = () => {
      setListening(false);
      if (finalText.trim()) setTimeout(() => submit(finalText), 250);
    };
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  }

  const placeholder = onResearch ? "Ask a follow-up about this company…" : "Ask FINN: “Did Titan hit FY27 guidance?”";

  return (
    <>
      {focus && sugg.length > 0 && (
        <div className="suggest" onMouseDown={(e) => e.preventDefault()}>
          <div className="hint">RESEARCH</div>
          {sugg.map((c) => (
            <button key={c.symbol} onClick={() => go(c.symbol, candidates(q).length > 1 ? q : undefined)}>
              <span><span className="tk">{c.symbol}</span> <span className="muted">{c.name}</span></span>
              <span className="dim mono" style={{ fontSize: 10 }}>{c.sector ?? ""}</span>
            </button>
          ))}
        </div>
      )}
      <form className="ask" onSubmit={(e) => { e.preventDefault(); submit(q); }}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 120)}
          placeholder={listening ? "Listening…" : placeholder}
          aria-label="Ask FINN"
          enterKeyHint="go"
        />
        {canListen && (
          <button type="button" className={`icon ${listening ? "live" : ""}`} onClick={mic} aria-label="Speak">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          </button>
        )}
        <button type="submit" className="icon" aria-label="Go">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </form>
    </>
  );
}
