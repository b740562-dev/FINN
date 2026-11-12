"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Citation } from "@/lib/types";
import { useAuth } from "@/components/auth";
import { Cited, useCiteSheet } from "@/components/research";
import { DocUploadForm, type Uploaded } from "@/components/my-docs";
import { MAX_SECONDS, type Recording, startRecording, voiceSupported } from "@/lib/voice";

const GREETING = "Hello, I’m Surya, your investment guide. What decision can I help you with today?";
const STARTERS = [
  "How do I judge if a company has too much debt?",
  "Did Titan hit its revenue guidance?",
  "What is BEL's order book?",
  "When should I rebalance my portfolio?",
];
const STORE = "finn.surya.v1";
const STAGE: Record<string, string> = { queued: "Queued", reading: "Reading the PDF", indexing: "Indexing passages", analysing: "Analysing" };

type Co = { symbol: string; name: string; documents: string[] };
type Msg = {
  id: string;
  role: "user" | "assistant" | "note";
  text: string;
  kind?: "general" | "company_data" | "missing";
  citations?: Citation[];
  companies?: Co[];
  job?: { symbol: string; id: number; done?: boolean };
};
type Reply = { answer: string; kind: Msg["kind"]; citations: Citation[]; companies: Co[] };

const uid = () => Math.random().toString(36).slice(2, 10);

function SunMark({ size = 34 }: { size?: number }) {
  return (
    <span className="surya-mark" style={{ width: size, height: size }} aria-hidden>
      <svg viewBox="0 0 24 24" width={size * 0.58} height={size * 0.58} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
      </svg>
    </span>
  );
}

function sourceLabel(c: Citation) {
  const label = c.doc_label === "screener financials" ? "Reported financials" : c.doc_label;
  return c.page ? `${label} · p.${c.page}` : label;
}

/** Surya: a chat window for decisions. General guidance is free; anything about
 *  a company's data comes only from its verified documents, cited inline. */
export default function Surya() {
  const router = useRouter();
  const { session } = useAuth();
  const guest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const [upload, setUpload] = useState<{ symbol: string; name: string } | null | false>(false); // false = closed
  const cite = useCiteSheet();
  const endRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const [hydrated, setHydrated] = useState(false);
  // Voice: idle -> recording -> transcribing -> idle (transcript lands in the box)
  const [voice, setVoice] = useState<"idle" | "recording" | "transcribing">("idle");
  const [secs, setSecs] = useState(0);
  const [canVoice, setCanVoice] = useState(false);
  const recRef = useRef<Recording | null>(null);

  useEffect(() => setCanVoice(voiceSupported()), []);
  useEffect(() => {
    if (voice !== "recording") return;
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [voice]);
  useEffect(() => () => recRef.current?.cancel(), []);   // leaving the page releases the mic

  // Conversation survives a reload on this device (convenience only).
  useEffect(() => {
    try { const raw = localStorage.getItem(STORE); if (raw) setMsgs(JSON.parse(raw)); } catch {}
    setHydrated(true);
  }, []);
  useEffect(() => {
    if (!hydrated) return;      // never overwrite the saved chat before it has been read
    try { localStorage.setItem(STORE, JSON.stringify(msgs.slice(-40))); } catch {}
  }, [msgs, hydrated]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, thinking]);

  // Follow any document that is still being read.
  const pendingJob = msgs.find((m) => m.job && !m.job.done)?.job;
  const pendingKey = pendingJob ? pendingJob.symbol + ":" + pendingJob.id : "";
  useEffect(() => {
    if (!pendingJob) return;
    const t = setInterval(async () => {
      try {
        const j = await api<{ status: string; error?: string; result?: { label?: string; chunks?: number } }>(
          `/research/${pendingJob.symbol}/jobs/${pendingJob.id}`);
        const done = ["done", "duplicate", "failed"].includes(j.status);
        const line = j.status === "done"
          ? `Done. ${pendingJob.symbol} ${j.result?.label ?? "document"} is indexed (${j.result?.chunks ?? "?"} passages). Ask me about it.`
          : j.status === "duplicate" ? `${pendingJob.symbol}: that document is already in the library. Ask away.`
          : j.status === "failed" ? `I couldn’t read that PDF: ${j.error ?? "unknown error"}.`
          : `${STAGE[j.status] ?? j.status} ${pendingJob.symbol}’s document…`;
        setMsgs((ms) => ms.map((m) => (m.job?.id === pendingJob.id ? { ...m, text: line, job: { ...m.job!, done } } : m)));
      } catch {}
    }, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingKey]);

  const send = useCallback(async (raw: string) => {
    const q = raw.trim();
    if (!q || thinking) return;
    const history = msgs.filter((m) => m.role !== "note").slice(-6).map((m) => ({ role: m.role, content: m.text }));
    setMsgs((ms) => [...ms, { id: uid(), role: "user", text: q }]);
    setText("");
    setThinking(true);
    try {
      const r = await api<Reply>("/chat", { method: "POST", body: JSON.stringify({ message: q, history }) });
      setMsgs((ms) => [...ms, { id: uid(), role: "assistant", text: r.answer, kind: r.kind, citations: r.citations, companies: r.companies }]);
    } catch (e) {
      setMsgs((ms) => [...ms, { id: uid(), role: "note", text: (e as Error).message }]);
    } finally {
      setThinking(false);
      boxRef.current?.focus();
    }
  }, [msgs, thinking]);

  function note(t: string) {
    setMsgs((ms) => [...ms, { id: uid(), role: "note", text: t }]);
  }

  const stopVoice = useCallback(async () => {
    const rec = recRef.current;
    if (!rec) return;
    recRef.current = null;
    setVoice("transcribing");
    try {
      const wav = await rec.stop();
      const fd = new FormData();
      fd.set("audio", wav, "voice.wav");
      const r = await api<{ text: string }>("/chat/transcribe", { method: "POST", body: fd });
      setText((t) => (t.trim() ? `${t.trim()} ${r.text}` : r.text));
      requestAnimationFrame(() => {
        const box = boxRef.current;
        if (!box) return;
        box.focus();
        box.style.height = "auto";
        box.style.height = `${Math.min(box.scrollHeight, 120)}px`;
      });
    } catch (e) {
      note((e as Error).message);
    } finally {
      setVoice("idle");
    }
  }, []);

  async function toggleVoice() {
    if (voice === "recording") return stopVoice();
    if (voice !== "idle") return;
    try {
      recRef.current = await startRecording();
      setSecs(0);
      setVoice("recording");
    } catch (e) {
      const name = (e as Error).name;
      note(name === "NotAllowedError" ? "Microphone access was blocked. Allow it in the browser to talk to Surya."
        : "Couldn't start the microphone on this device.");
    }
  }

  // Auto-stop at the limit.
  useEffect(() => { if (voice === "recording" && secs >= MAX_SECONDS) stopVoice(); }, [voice, secs, stopVoice]);

  function uploaded(r: Uploaded) {
    setUpload(false);
    if (r.status === "duplicate" || !r.job_id) {
      setMsgs((ms) => [...ms, { id: uid(), role: "note", text: `${r.symbol}: that document is already in the library. Ask away.` }]);
      return;
    }
    setMsgs((ms) => [...ms, { id: uid(), role: "note", text: `Reading ${r.symbol}’s document…`, job: { symbol: r.symbol, id: r.job_id! } }]);
  }

  return (
    <div className="surya">
      <header className="sy-head">
        <button className="sy-back" onClick={() => router.back()} aria-label="Back">‹</button>
        <SunMark />
        <div className="sy-title">
          <b>Surya</b>
          <small>Investment guide · facts only from verified documents</small>
        </div>
        {msgs.length > 0 && (
          <button className="sy-new" onClick={() => setMsgs([])} aria-label="New chat" title="New chat">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        )}
      </header>

      <div className="sy-body">
        <div className="sy-row bot">
          <SunMark size={28} />
          <div className="sy-bubble">{GREETING}</div>
        </div>
        {msgs.length === 0 && (
          <div className="sy-starters">
            {STARTERS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
          </div>
        )}

        {msgs.map((m) => m.role === "user" ? (
          <div key={m.id} className="sy-row me"><div className="sy-bubble">{m.text}</div></div>
        ) : m.role === "note" ? (
          <div key={m.id} className={`sy-note ${m.job && !m.job.done ? "run" : ""}`}>
            {m.job && !m.job.done && <span className="md-spin" />}{m.text}
          </div>
        ) : (
          <div key={m.id} className="sy-row bot">
            <SunMark size={28} />
            <div className={`sy-bubble ${m.kind === "missing" ? "missing" : ""}`}>
              <div className="sy-text"><Cited text={m.text} cites={m.citations ?? []} open={cite.open} /></div>
              {m.citations && m.citations.length > 0 && (
                <div className="sy-srcs">
                  {[...new Map(m.citations.map((c) => [sourceLabel(c), c])).entries()].map(([label, c]) => (
                    <button key={label} onClick={() => cite.open(c)}>{label}</button>
                  ))}
                </div>
              )}
              {m.kind === "missing" && (
                <button className="sy-add" onClick={() => setUpload(m.companies?.[0] ? { symbol: m.companies[0].symbol, name: m.companies[0].name } : null)}>
                  📎 Add {m.companies?.[0]?.symbol ?? "a"} report
                </button>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="sy-row bot">
            <SunMark size={28} />
            <div className="sy-bubble sy-typing"><i /><i /><i /><span>Reading the documents</span></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form className="sy-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <button type="button" className="sy-clip" onClick={() => setUpload(null)} aria-label="Add a document">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m21 11.5-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9" />
          </svg>
        </button>
        {voice === "recording" ? (
          <div className="sy-rec" aria-live="polite">
            <i className="sy-recdot" />Listening… <b>{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}</b>
            <span>tap ■ to finish</span>
          </div>
        ) : (
        <textarea ref={boxRef} rows={1} value={text} placeholder={voice === "transcribing" ? "Transcribing…" : "Message Surya…"} maxLength={800}
          onChange={(e) => { setText(e.target.value); e.currentTarget.style.height = "auto"; e.currentTarget.style.height = `${Math.min(e.currentTarget.scrollHeight, 120)}px`; }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
          aria-label="Message Surya" disabled={voice === "transcribing"} />
        )}
        {canVoice && (
          <button type="button" className={`sy-mic ${voice}`} onClick={toggleVoice} disabled={voice === "transcribing" || thinking}
            aria-label={voice === "recording" ? "Stop and transcribe" : "Speak your question"} title={voice === "recording" ? "Stop" : "Speak"}>
            {voice === "recording" ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="3" /></svg>
            ) : voice === "transcribing" ? (
              <span className="md-spin" style={{ margin: 0 }} />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </svg>
            )}
          </button>
        )}
        <button className="sy-send" disabled={!text.trim() || thinking || voice !== "idle"} aria-label="Send">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </form>
      <div className="sy-fine">General guidance, not investment advice. Company facts come only from verified documents.</div>

      {upload !== false && (
        <div className="sheet-bg" onClick={() => setUpload(false)} role="dialog" aria-modal aria-label="Add a document">
          <div className="sheet sy-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="grab" />
            <b className="sy-sheet-t">Add a report for Surya to read</b>
            <DocUploadForm guest={guest} initial={upload} onCancel={() => setUpload(false)} onUploaded={uploaded} />
          </div>
        </div>
      )}
      {cite.sheet}
    </div>
  );
}
