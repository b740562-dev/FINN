// Indian number formatting: ₹1,23,456 / ₹48.6L / ₹1.2Cr

export function inr(n: number | null | undefined, opts: { compact?: boolean; sign?: boolean } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const sign = opts.sign ? (n > 0 ? "+" : n < 0 ? "−" : "") : n < 0 ? "−" : "";
  const a = Math.abs(n);
  if (opts.compact) {
    if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)}Cr`;
    if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)}L`;
    if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)}K`;
  }
  return `${sign}₹${Math.round(a).toLocaleString("en-IN")}`;
}

export function crore(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return Math.round(n).toLocaleString("en-IN");
}

export function pct(n: number | null | undefined, digits = 1, sign = true): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const s = sign && n > 0 ? "+" : n < 0 ? "−" : "";
  const v = Math.abs(n);
  return `${s}${v >= 100 ? v.toFixed(0) : v.toFixed(digits)}%`;
}

export function bp(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}bp`;
}

export function tone(n: number | null | undefined): "up" | "dn" | "flat" {
  if (n === null || n === undefined || n === 0) return "flat";
  return n > 0 ? "up" : "dn";
}

export function ago(iso: string): string {
  const d = new Date(iso);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.round(h / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function istTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
}
