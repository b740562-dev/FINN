"use client";

/** Export a Surya conversation: Markdown download, or a print-ready page the
 *  browser saves as PDF. Sources keep their links to the original documents. */

export type ExportCite = { id: string; doc_label: string; page: number | null; quote: string; url?: string };
export type ExportMsg = {
  role: "user" | "assistant" | "note";
  text: string;
  kind?: string;
  verified?: boolean;
  citations?: ExportCite[];
};

const label = (c: ExportCite) =>
  `${c.doc_label === "screener financials" ? "Reported financials" : c.doc_label}${c.page ? `, p.${c.page}` : ""}`;

function stamp() {
  return new Date().toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function sources(m: ExportMsg): ExportCite[] {
  return [...new Map((m.citations ?? []).map((c) => [label(c), c])).values()];
}

/** In-app markers ([c2], [n1], [g3]) become numbers matching the source list: [1], [2]… */
function numbered(m: ExportMsg): string {
  const order = sources(m).map(label);
  const byId = new Map((m.citations ?? []).map((c) => [c.id, order.indexOf(label(c)) + 1]));
  return m.text.replace(/\s?\[([a-z]\d+)\]/gi, (_, id: string) => (byId.get(id) ? ` [${byId.get(id)}]` : ""))
    .replace(/(\[\d+\])(?:\s?\1)+/g, "$1");
}

export function toMarkdown(msgs: ExportMsg[], greeting: string): string {
  const out = [`# Conversation with Surya`, ``, `_FINN · exported ${stamp()} · general guidance, not investment advice_`, ``,
    `**Surya:** ${greeting}`, ``];
  for (const m of msgs) {
    if (m.role === "note") { out.push(`> ${m.text}`, ``); continue; }
    if (m.role === "user") { out.push(`**You:** ${m.text}`, ``); continue; }
    out.push(`**Surya:** ${numbered(m)}`, ``);
    const src = sources(m);
    if (src.length) {
      out.push(m.verified ? `✓ **Verified**: every figure checked against the original` : `Sources:`);
      src.forEach((c, i) => {
        out.push(`${i + 1}. ${c.url ? `[${label(c)}](${c.url})` : label(c)}${c.quote ? ` — “${c.quote.trim()}”` : ""}`);
      });
      out.push(``);
    }
  }
  return out.join("\n");
}

export function downloadMarkdown(msgs: ExportMsg[], greeting: string) {
  const blob = new Blob([toMarkdown(msgs, greeting)], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `surya-chat-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** A clean light print layout in a hidden frame; the print dialog offers "Save as PDF". */
export function printPdf(msgs: ExportMsg[], greeting: string) {
  const turns = msgs.map((m) => {
    if (m.role === "note") return `<p class="note">${esc(m.text)}</p>`;
    const who = m.role === "user" ? "You" : "Surya";
    const src = m.role === "assistant" ? sources(m) : [];
    const srcHtml = src.length ? `<div class="src ${m.verified ? "ok" : ""}">${m.verified ? "<b>✓ Verified</b> · every figure checked against the original" : "<b>Sources</b>"}<ol>${
      src.map((c) => `<li>${c.url ? `<a href="${esc(c.url)}">${esc(label(c))}</a>` : esc(label(c))}${c.quote ? ` — “${esc(c.quote.trim())}”` : ""}</li>`).join("")
    }</ol></div>` : "";
    return `<div class="turn ${m.role}"><div class="who">${who}</div><div class="txt">${esc(m.role === "assistant" ? numbered(m) : m.text).replace(/\n/g, "<br>")}</div>${srcHtml}</div>`;
  }).join("");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Conversation with Surya</title><style>
    body{font:13px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;color:#14211a;margin:32px}
    h1{font-size:20px;margin:0 0 2px} .meta{color:#5d6f64;font-size:11px;margin-bottom:20px}
    .turn{margin:0 0 14px;padding:10px 12px;border-radius:10px;border:1px solid #dfe8e2;page-break-inside:avoid}
    .turn.user{background:#f2f9e4;border-color:#d6ecb0} .who{font-weight:700;font-size:11px;color:#3d6b1f;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
    .src{margin-top:8px;font-size:11.5px;color:#41544a} .src.ok b{color:#17803d} .src ol{margin:4px 0 0 18px;padding:0}
    a{color:#0b6b8a} .note{color:#5d6f64;font-style:italic;font-size:12px}
    </style></head><body><h1>Conversation with Surya</h1><div class="meta">FINN · exported ${esc(stamp())} · general guidance, not investment advice</div>
    <div class="turn assistant"><div class="who">Surya</div><div class="txt">${esc(greeting)}</div></div>${turns}</body></html>`;
  const frame = document.createElement("iframe");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  document.body.appendChild(frame);
  const doc = frame.contentDocument!;
  doc.open();
  doc.write(html);
  doc.close();
  setTimeout(() => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    setTimeout(() => frame.remove(), 60_000);
  }, 250);
}
