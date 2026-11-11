"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, post } from "@/lib/api";
import type { Citation, Overview, Section } from "@/lib/types";
import { crore } from "@/lib/format";
import { useData } from "@/components/data";
import { useAuth } from "@/components/auth";
import { BullBearView, Cited, HealthView, PromiseView, SectionShell, SnapshotView, useCiteSheet } from "@/components/research";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;
type QA = { q: string; a?: string; citations?: Citation[]; model?: string; err?: string };

const SECTIONS = ["snapshot", "promise_delivered", "health", "bull_bear"] as const;
type SectionKey = (typeof SECTIONS)[number];

function Dossier() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw || "").toUpperCase();
  const params = useSearchParams();
  const { me } = useData();
  const { session } = useAuth();
  const isGuest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);
  const [ov, setOv] = useState<Overview | null>(null);
  const [ovErr, setOvErr] = useState<string | null>(null);
  const [secs, setSecs] = useState<Record<SectionKey, Section<Any> | "loading" | null>>({
    snapshot: "loading", promise_delivered: "loading", health: "loading", bull_bear: "loading",
  });
  const [chat, setChat] = useState<QA[]>([]);
  const [upload, setUpload] = useState<{ busy: boolean; msg: string | null }>({ busy: false, msg: null });
  const askedInitial = useRef(false);
  const { open, sheet } = useCiteSheet();

  const loadSections = useCallback(() => {
    // Fire all four in parallel; each renders as soon as it lands.
    SECTIONS.forEach((k) => {
      setSecs((s) => ({ ...s, [k]: "loading" }));
      api<Section<Any>>(`/research/${symbol}/sections/${k}`)
        .then((r) => setSecs((s) => ({ ...s, [k]: r })))
        .catch((e) => setSecs((s) => ({ ...s, [k]: { section: k, status: "error", model: null, generated_at: "", content: {}, citations: [], error: e.message } })));
    });
  }, [symbol]);

  const loadOverview = useCallback(async () => {
    const o = await api<Overview>(`/research/${symbol}`);
    setOv(o);
    return o;
  }, [symbol]);

  useEffect(() => {
    let alive = true;
    setOv(null);
    setOvErr(null);
    (async () => {
      try {
        await post(`/research/${symbol}/ensure`);   // fetches unseen tickers on demand
        if (!alive) return;
        await loadOverview();
        loadSections();
      } catch (e) {
        if (alive) setOvErr((e as Error).message);
      }
    })();
    return () => { alive = false; };
  }, [symbol, loadOverview, loadSections]);

  const ask = useCallback(async (question: string) => {
    setChat((c) => [...c, { q: question }]);
    try {
      const r = await post<{ answer: string; citations: Citation[]; model: string }>(`/research/${symbol}/ask`, { question });
      setChat((c) => c.map((x, i) => (i === c.length - 1 ? { ...x, a: r.answer, citations: r.citations, model: r.model } : x)));
    } catch (e) {
      setChat((c) => c.map((x, i) => (i === c.length - 1 ? { ...x, err: (e as Error).message } : x)));
    }
  }, [symbol]);

  // Questions typed in the global ask bar while on this page.
  useEffect(() => {
    const h = (e: Event) => ask((e as CustomEvent<string>).detail);
    window.addEventListener("finn:ask", h);
    return () => window.removeEventListener("finn:ask", h);
  }, [ask]);

  // Arrived with a question (e.g. "Did Titan hit FY27 guidance?").
  useEffect(() => {
    const q = params.get("q");
    if (q && ov && !askedInitial.current) {
      askedInitial.current = true;
      ask(q);
    }
  }, [params, ov, ask]);

  async function onUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const file = fd.get("file") as File | null;
    if (!file || !file.size) return;
    setUpload({ busy: true, msg: `Uploading ${file.name}…` });
    try {
      const r = await api<{ status: string; job_id?: number; label?: string }>(
        `/research/${symbol}/documents`, { method: "POST", body: fd });
      if (r.status === "duplicate") {
        setUpload({ busy: false, msg: `Already on file${r.label ? ` (${r.label})` : ""}. Nothing new to read.` });
        return;
      }
      form.reset();
      // Processing runs on the server; poll the job and narrate its stages.
      for (;;) {
        await new Promise((res) => setTimeout(res, 2000));
        const j = await api<{ status: string; result?: Any; error?: string; seconds: number }>(
          `/research/${symbol}/jobs/${r.job_id}`);
        const res = j.result ?? {};
        if (j.status === "failed") return setUpload({ busy: false, msg: `Couldn't add it: ${j.error}` });
        if (j.status === "duplicate") return setUpload({ busy: false, msg: "Already on file. Nothing new to read." });
        if (j.status === "done") {
          setUpload({ busy: false, msg: `Added ${res.label ?? "document"}: ${res.pages_kept ?? res.pages} pages read, ${res.chunks} passages indexed (${Math.round(j.seconds)}s).` });
          await loadOverview();
          loadSections();
          return;
        }
        const stage: Record<string, string> = {
          queued: "Queued…",
          reading: "Reading the PDF…",
          indexing: `Indexing ${res.chunks ?? ""} passages from ${res.pages_kept ?? "?"} pages…`,
          analysing: "Checking guidance against reported numbers…",
        };
        setUpload({ busy: true, msg: `${stage[j.status] ?? j.status} (${Math.round(j.seconds)}s)` });
      }
    } catch (er) {
      setUpload({ busy: false, msg: (er as Error).message });
    }
  }

  const held = me?.holdings.find((h) => h.symbol === symbol);
  const docs = ov?.docs;

  if (ovErr) {
    return (
      <>
        <header className="topbar"><div className="brand"><Link href="/research" className="logo">‹ {symbol}</Link></div></header>
        <div className="empty"><b>Couldn&apos;t open {symbol}.</b>{ovErr}
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            <button className="btn primary" onClick={() => window.location.reload()}>TRY AGAIN</button>
            <Link className="btn" href="/research">BACK</Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <Link href="/research" className="logo" style={{ fontSize: 17 }}>‹ {symbol}</Link>
          <span className="when">{held ? `in your book · ${held.weight}%` : "research"}</span>
        </div>
      </header>

      <div className="rhead">
        <h1>{ov?.name ?? "Loading…"}</h1>
        <div className="meta">
          {ov?.sector && <span>{ov.sector}</span>}
          {ov?.market_cap_cr != null && <span>₹{crore(ov.market_cap_cr)} cr</span>}
          {docs && <span>{docs.transcripts} transcripts · {docs.annual_reports} annual reports</span>}
        </div>
      </div>

      <SectionShell title="Snapshot" s={secs.snapshot}>
        {secs.snapshot && secs.snapshot !== "loading" && <SnapshotView s={secs.snapshot} open={open} />}
      </SectionShell>

      <SectionShell title="Promise vs delivered" s={secs.promise_delivered}>
        {secs.promise_delivered && secs.promise_delivered !== "loading" && <PromiseView s={secs.promise_delivered} open={open} />}
      </SectionShell>

      <SectionShell title="Health check" s={secs.health}>
        {secs.health && secs.health !== "loading" && <HealthView s={secs.health} />}
      </SectionShell>

      <SectionShell title="Bull vs bear" s={secs.bull_bear}>
        {secs.bull_bear && secs.bull_bear !== "loading" && <BullBearView s={secs.bull_bear} open={open} />}
      </SectionShell>

      <section className="rsec">
        <header><h2>Primary documents</h2><span>{docs ? `${(docs.items ?? []).length} on file` : ""}</span></header>
        <div className="body">
          {(docs?.items ?? []).map((d) => (
            <div key={d.id} className="spark" style={{ padding: "6px 0" }}>
              <div className="l">{d.label}<small>{d.kind.replace("_", " ")}{d.pages ? ` · ${d.pages_kept && d.pages_kept < d.pages ? `${d.pages_kept} of ${d.pages}` : d.pages} pages read` : ""}</small></div>
            </div>
          ))}
          {isGuest ? (
            <p className="needs" style={{ marginTop: 8 }}>
              Documents are shared across all FINN users, so adding them needs a saved account. Guests can read every
              pre-loaded document. <Link className="amber" href="/you">Save your account →</Link>
            </p>
          ) : (
          <form onSubmit={onUpload} style={{ display: "grid", gap: 8, marginTop: 8 }}>
            <input className="txt" type="file" name="file" accept="application/pdf" required />
            <div style={{ display: "flex", gap: 8 }}>
              <select className="txt" name="kind" defaultValue="transcript" style={{ flex: 1 }}>
                <option value="transcript">Concall transcript</option>
                <option value="annual_report">Annual report</option>
              </select>
              <input className="txt" type="date" name="period" required style={{ flex: 1, colorScheme: "dark" }} aria-label="Call date or fiscal year end" />
            </div>
            <button className="btn" disabled={upload.busy}>{upload.busy ? "INGESTING…" : "ADD DOCUMENT"}</button>
            {upload.msg && <div className="ok">{upload.msg}</div>}
            <p className="sub dim" style={{ fontSize: 10.5, margin: 0 }}>Download from screener.in → Documents. Date = call date (transcript) or fiscal year end (annual report).</p>
          </form>
          )}
        </div>
      </section>

      <div className="sec"><span>── Ask about {symbol}</span><span>answers cite its own documents</span></div>
      <div className="chat">
        {chat.length === 0 && <p className="sub dim" style={{ fontSize: 11.5, padding: "0 4px 8px" }}>Use the ask bar below: “What did management say about margins?”</p>}
        {chat.map((m, i) => (
          <div className="qa" key={i}>
            <div className="q">› {m.q}</div>
            {m.err ? <div className="err" style={{ margin: 0 }}>{m.err}</div>
              : m.a ? <div className="a"><Cited text={m.a} cites={m.citations ?? []} open={open} /></div>
              : <div className="skel sm" style={{ margin: 0, height: 36 }} />}
            {m.model && <div className="dim mono" style={{ fontSize: 9.5, marginTop: 6 }}>{m.model.replace("gemini-", "")}</div>}
          </div>
        ))}
      </div>
      {sheet}
    </>
  );
}

export default function DossierPage() {
  return <Suspense fallback={<div className="skel" style={{ marginTop: 16 }} />}><Dossier /></Suspense>;
}
