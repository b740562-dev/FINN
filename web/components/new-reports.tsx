"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "./auth";
import { DocUploadForm, type Preset } from "./my-docs";

export type Report = {
  id: number; symbol: string; name: string; kind: "transcript" | "presentation" | "annual_report";
  period: string; label: string; url: string; host: string; status: "needs_upload" | "ingested";
  via: string | null; fetched_url: string | null; updated_at: string;
};

const TAG: Record<Report["kind"], string> = { transcript: "CC", presentation: "IP", annual_report: "AR" };

function when(period: string, kind: Report["kind"]) {
  const d = new Date(period + "T00:00:00");
  return kind === "annual_report" ? `FY${String(d.getFullYear()).slice(-2)}` : d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

/** Reports published for your holdings and the research picks: ones FINN read on
 *  its own, and ones whose host blocks automated downloads, offered as a
 *  one-tap upload with everything pre-filled. */
export function NewReports() {
  const { session } = useAuth();
  const guest = Boolean((session?.user as { is_anonymous?: boolean } | undefined)?.is_anonymous);
  const [items, setItems] = useState<Report[] | null>(null);
  const [adding, setAdding] = useState<Preset | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  const load = useCallback(() => {
    api<{ items: Report[] }>("/reports").then((r) => setItems(r.items)).catch(() => setItems([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const need = (items ?? []).filter((x) => x.status === "needs_upload");
  if (need.length === 0) return null;
  const shown = all ? need : need.slice(0, 4);

  return (
    <section className="nr">
      <div className="nr-head">
        <div>
          <h2>New reports</h2>
          <p>Published lately for your companies. Add one in a tap to update its research.</p>
        </div>
        <span className="nr-counts"><span className="todo">{need.length} to add</span></span>
      </div>

      {shown.map((x) => (
        <div key={x.id} className="nr-row">
          <span className="nr-tag">{TAG[x.kind]}</span>
          <span className="nr-info"><b>{x.symbol} <span>{x.label}</span></b><small>Published {when(x.period, x.kind)} · on {x.host}</small></span>
          <span className="nr-acts">
            <a className="nr-open" href={x.url} target="_blank" rel="noreferrer" title="Open the original to download it">Open ↗</a>
            <button className="nr-add" onClick={() => { setNote(null); setAdding({ symbol: x.symbol, name: x.name, kind: x.kind, period: x.period, url: x.url }); }}>Add</button>
          </span>
        </div>
      ))}
      {need.length > 4 && (
        <button className="nr-more" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${need.length}`}</button>
      )}
      {note && <div className="ok" style={{ margin: "8px 12px 0" }}>{note}</div>}

      {adding && (
        <div className="sheet-bg" onClick={() => setAdding(null)} role="dialog" aria-modal aria-label="Add report">
          <div className="sheet sy-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="grab" />
            <b className="sy-sheet-t">Add {adding.symbol} {need.find((i) => i.url === adding.url)?.label}</b>
            <p className="nr-steps">1. <a href={adding.url} target="_blank" rel="noreferrer">Open the original ↗</a> and save the PDF. 2. Pick it below. Everything else is filled in.</p>
            <DocUploadForm guest={guest} initial={adding} onCancel={() => setAdding(null)}
              onUploaded={(r) => {
                setAdding(null);
                setNote(r.status === "duplicate" ? `${r.symbol}: already in the library.` : `Reading ${r.symbol}'s report. Its research updates when done.`);
                setTimeout(load, 4000);
              }} />
          </div>
        </div>
      )}
    </section>
  );
}
