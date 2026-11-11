"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type Doc = {
  id: number; symbol: string; company: string | null; kind: string; period: string | null; label: string | null;
  filename: string | null; source: string | null; source_label: string | null; source_url: string | null;
  pages: number | null; pages_kept: number | null; chunks: number | null; added_at: string;
};
type Job = { id: number; symbol: string; filename: string | null; kind: string; period: string; status: string; error: string | null };
type Mine = { documents: Doc[]; jobs: Job[] };

const KINDS: [string, string, string][] = [
  ["annual_report", "Annual report", "AR"],
  ["transcript", "Concall transcript", "CC"],
  ["presentation", "Investor presentation", "IP"],
];
const SOURCES: [string, string][] = [
  ["company_website", "Company website"], ["bse", "BSE"], ["nse", "NSE"],
  ["investor_relations", "Investor relations"], ["other", "Other"],
];
const STAGE: Record<string, string> = { queued: "Queued", reading: "Reading", indexing: "Indexing", analysing: "Analysing" };
const MAX_MB = 40;

function fyOptions() {
  const now = new Date();
  const last = now.getMonth() >= 3 ? now.getFullYear() + 1 : now.getFullYear(); // current FY ends next March
  return Array.from({ length: 6 }, (_, i) => last - 1 - i);                      // latest complete FY first
}

/** "Your documents": add an annual report / transcript / presentation for any
 *  company (with where it came from), watch it being read, remove it later. */
export function MyDocuments({ guest }: { guest: boolean }) {
  const [mine, setMine] = useState<Mine | null>(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sugg, setSugg] = useState<{ symbol: string; name: string }[]>([]);
  const [co, setCo] = useState<{ symbol: string; name: string } | null>(null);
  const [kind, setKind] = useState("transcript");
  const [fy, setFy] = useState(String(fyOptions()[0]));
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [source, setSource] = useState("company_website");
  const [link, setLink] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try { setMine(await api<Mine>("/documents/mine")); } catch { setMine({ documents: [], jobs: [] }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Poll while anything is still being read.
  const pending = (mine?.jobs ?? []).some((j) => j.status !== "failed");
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [pending, load]);

  useEffect(() => {
    if (co || q.trim().length < 2) { setSugg([]); return; }
    const t = setTimeout(() => api<{ symbol: string; name: string }[]>(`/companies?q=${encodeURIComponent(q.trim())}`)
      .then((r) => setSugg(r.slice(0, 5))).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [q, co]);

  function pickFile(f: File | null) {
    setMsg(null);
    if (f && f.size > MAX_MB * 1024 * 1024) { setMsg({ ok: false, text: `That PDF is over ${MAX_MB} MB.` }); return; }
    setFile(f);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!co || !file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.set("file", file);
    fd.set("kind", kind);
    fd.set("period", kind === "annual_report" ? `${fy}-03-31` : `${month}-01`);
    fd.set("source", source);
    if (link.trim()) fd.set("source_url", link.trim());
    try {
      const r = await api<{ status: string; label?: string }>(`/research/${co.symbol}/documents`, { method: "POST", body: fd });
      setMsg(r.status === "duplicate"
        ? { ok: true, text: `Already in FINN's library${r.label ? ` (${co.symbol} ${r.label})` : ""}. Nothing new to read.` }
        : { ok: true, text: `Reading ${co.symbol}'s document. Its research updates when it's done.` });
      setFile(null); setLink(""); if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (er) {
      setMsg({ ok: false, text: (er as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setConfirm(null);
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      await load();
    } catch (er) {
      setMsg({ ok: false, text: (er as Error).message });
    }
  }

  async function dismiss(id: number) {
    try { await api(`/documents/jobs/${id}`, { method: "DELETE" }); } catch {}
    load();
  }

  const docs = mine?.documents ?? [];
  const jobs = mine?.jobs ?? [];
  const kindLabel = (k: string) => KINDS.find((x) => x[0] === k)?.[1] ?? k;
  const kindTag = (k: string) => KINDS.find((x) => x[0] === k)?.[2] ?? "DOC";
  const ready = Boolean(co && file);

  return (
    <div className="md" id="my-docs">
      <div className="md-head">
        <div>
          <b>Your documents</b>
          <small>{docs.length ? `${docs.length} added` : "Annual reports, concalls, presentations"}</small>
        </div>
        {!open && <button className="btn primary sm" onClick={() => setOpen(true)}>＋ Add</button>}
      </div>

      {open && (
        <form className="md-form" onSubmit={submit}>
          <div className="md-step"><i>1</i><span>Company</span></div>
          {co ? (
            <button type="button" className="md-co" onClick={() => { setCo(null); setQ(""); }}>
              <b>{co.symbol}</b><span>{co.name}</span><em aria-label="Change company">✕</em>
            </button>
          ) : (
            <div style={{ position: "relative" }}>
              <input className="txt" placeholder="Search symbol or name" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
              {sugg.length > 0 && (
                <div className="md-sugg">
                  {sugg.map((c) => (
                    <button type="button" key={c.symbol} onClick={() => { setCo(c); setSugg([]); }}>
                      <b>{c.symbol}</b><span>{c.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="md-step"><i>2</i><span>What it is</span></div>
          <div className="md-kinds">
            {KINDS.map(([k, l, t]) => (
              <button type="button" key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>
                <em>{t}</em><span>{l}</span>
              </button>
            ))}
          </div>
          {kind === "annual_report" ? (
            <div className="chips">
              {fyOptions().map((y) => (
                <button type="button" key={y} className={`chip ${fy === String(y) ? "on" : ""}`} onClick={() => setFy(String(y))}>
                  FY{String(y).slice(-2)}
                </button>
              ))}
            </div>
          ) : (
            <label className="md-month">
              <span>{kind === "transcript" ? "Call month" : "Month"}</span>
              <input className="txt" type="month" value={month} max={new Date().toISOString().slice(0, 7)}
                onChange={(e) => setMonth(e.target.value)} style={{ colorScheme: "dark" }} required />
            </label>
          )}

          <div className="md-step"><i>3</i><span>Source</span></div>
          <div className="chips">
            {SOURCES.map(([k, l]) => (
              <button type="button" key={k} className={`chip ${source === k ? "on" : ""}`} onClick={() => setSource(k)}>{l}</button>
            ))}
          </div>
          <input className="txt" type="url" placeholder="Link to the original (optional)" value={link}
            onChange={(e) => setLink(e.target.value)} maxLength={500} />

          <div className="md-step"><i>4</i><span>PDF</span></div>
          <label className={`md-file ${file ? "has" : ""}`}>
            <input ref={fileRef} type="file" accept="application/pdf" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
            <span className="md-pdf">PDF</span>
            <span className="md-fn">{file ? file.name : "Choose a file"}</span>
            <span className="md-sz">{file ? `${(file.size / 1048576).toFixed(1)} MB` : `up to ${MAX_MB} MB`}</span>
          </label>

          <div className="md-actions">
            <button type="button" className="btn ghost" onClick={() => { setOpen(false); setMsg(null); }}>Cancel</button>
            {guest ? (
              <Link className="btn primary" href="/profile">Save your account to add</Link>
            ) : (
              <button className="btn primary" disabled={!ready || busy}>{busy ? "Uploading…" : "Add document"}</button>
            )}
          </div>
          {guest && <p className="md-note">Added documents feed the company&apos;s research for everyone, so they need a saved account.</p>}
        </form>
      )}

      {msg && <div className={msg.ok ? "ok" : "err"} style={{ margin: "8px 0 0" }}>{msg.text}</div>}

      {(jobs.length > 0 || docs.length > 0) && (
        <ul className="md-list">
          {jobs.map((j) => (
            <li key={`j${j.id}`} className={j.status === "failed" ? "bad" : "run"}>
              <span className="md-tag">{kindTag(j.kind)}</span>
              <div className="md-info">
                <b>{j.symbol}</b>
                <small>{j.status === "failed" ? (j.error ?? "Couldn't read it") : `${STAGE[j.status] ?? j.status}…`}</small>
              </div>
              {j.status === "failed"
                ? <button className="md-x" onClick={() => dismiss(j.id)} aria-label="Dismiss">✕</button>
                : <span className="md-spin" aria-label="Processing" />}
            </li>
          ))}
          {docs.map((d) => (
            <li key={d.id}>
              <span className="md-tag">{kindTag(d.kind)}</span>
              <div className="md-info">
                <b><Link href={`/research/${d.symbol}`}>{d.symbol}</Link> <span>{d.label ?? kindLabel(d.kind)}</span></b>
                <small>
                  {d.source_url ? <a href={d.source_url} target="_blank" rel="noreferrer">{d.source_label ?? "Source"} ↗</a> : (d.source_label ?? "Source not given")}
                  {d.pages_kept ? ` · ${d.pages_kept} pages` : ""}{d.chunks ? ` · ${d.chunks} passages` : ""}
                </small>
              </div>
              {confirm === d.id ? (
                <span className="md-confirm">
                  <button onClick={() => setConfirm(null)}>Keep</button>
                  <button className="yes" onClick={() => remove(d.id)}>Remove</button>
                </span>
              ) : (
                <button className="md-x" onClick={() => setConfirm(d.id)} aria-label={`Remove ${d.symbol} ${d.label ?? ""}`}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
