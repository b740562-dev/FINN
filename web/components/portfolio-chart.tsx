"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { inr, pct, tone } from "@/lib/format";

type Hist = { days: number; points: { date: string; value: number }[]; change: number | null; change_pct: number | null };

const RANGES = [
  { key: 30, label: "1M" },
  { key: 90, label: "3M" },
  { key: 180, label: "6M" },
];
const W = 340;
const H = 120;
const PAD_T = 14;
const PAD_B = 6;

/** Portfolio value over time: glowing lime line over a soft gradient area,
 *  with a touch/hover readout of any day's value. */
export function PortfolioChart() {
  const [days, setDays] = useState(90);
  const [data, setData] = useState<Hist | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    api<Hist>(`/me/history?days=${days}`).then((d) => alive && setData(d)).catch(() => alive && setData(null));
    return () => { alive = false; };
  }, [days]);

  const geo = useMemo(() => {
    const pts = data?.points ?? [];
    if (pts.length < 2) return null;
    const vals = pts.map((p) => p.value);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;
    const xy = pts.map((p, i) => [(i / (pts.length - 1)) * W, PAD_T + (1 - (p.value - min) / span) * (H - PAD_T - PAD_B)] as const);
    // smooth path (Catmull-Rom -> cubic Bezier)
    let d = `M${xy[0][0]},${xy[0][1]}`;
    for (let i = 0; i < xy.length - 1; i++) {
      const [x0, y0] = xy[Math.max(i - 1, 0)];
      const [x1, y1] = xy[i];
      const [x2, y2] = xy[i + 1];
      const [x3, y3] = xy[Math.min(i + 2, xy.length - 1)];
      d += ` C${x1 + (x2 - x0) / 6},${y1 + (y2 - y0) / 6} ${x2 - (x3 - x1) / 6},${y2 - (y3 - y1) / 6} ${x2},${y2}`;
    }
    return { pts, xy, line: d, area: `${d} L${W},${H} L0,${H} Z` };
  }, [data]);

  function onMove(clientX: number) {
    if (!geo || !boxRef.current) return;
    const r = boxRef.current.getBoundingClientRect();
    const i = Math.round(((clientX - r.left) / r.width) * (geo.pts.length - 1));
    setHover(Math.max(0, Math.min(geo.pts.length - 1, i)));
  }

  const idx = hover ?? (geo ? geo.pts.length - 1 : 0);
  const sel = geo?.pts[idx];
  const selXY = geo?.xy[idx];

  return (
    <div className="pchart">
      <div
        ref={boxRef}
        style={{ position: "relative", touchAction: "pan-y" }}
        onMouseMove={(e) => onMove(e.clientX)}
        onMouseLeave={() => setHover(null)}
        onTouchMove={(e) => onMove(e.touches[0].clientX)}
        onTouchEnd={() => setHover(null)}
      >
        {geo && sel && selXY && (
          <div className="tip" style={{
            left: `${(selXY[0] / W) * 100}%`,
            // keep the label inside the card near either edge
            transform: selXY[0] / W > 0.8 ? "translateX(-100%)" : selXY[0] / W < 0.2 ? "translateX(0)" : "translateX(-50%)",
          }}>
            {inr(sel.value, { compact: true })} · {new Date(sel.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
          </div>
        )}
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-label="Portfolio value chart">
          <defs>
            <linearGradient id="pfill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#c6f45e" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#c6f45e" stopOpacity="0" />
            </linearGradient>
            <filter id="pglow" x="-20%" y="-50%" width="140%" height="200%">
              <feGaussianBlur stdDeviation="3.2" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {geo ? (
            <>
              <path d={geo.area} fill="url(#pfill)" />
              <path d={geo.line} fill="none" stroke="#c6f45e" strokeWidth="2.2" filter="url(#pglow)"
                vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
              {selXY && (
                <>
                  <line x1={selXY[0]} x2={selXY[0]} y1={PAD_T - 4} y2={H} stroke="rgba(198,244,94,0.35)" strokeDasharray="3 4"
                    vectorEffect="non-scaling-stroke" />
                  <circle cx={selXY[0]} cy={selXY[1]} r="7" fill="rgba(198,244,94,0.22)" />
                  <circle cx={selXY[0]} cy={selXY[1]} r="3.4" fill="#c6f45e" />
                </>
              )}
            </>
          ) : (
            <rect x="0" y={H / 2} width={W} height="1" fill="rgba(255,255,255,0.06)" />
          )}
        </svg>
      </div>
      <div className="ranges">
        {data?.change_pct != null && (
          <span className="delta" style={{ marginRight: "auto" }}>
            <b className={tone(data.change)}>{inr(data.change, { sign: true, compact: true })} ({pct(data.change_pct)})</b> over {RANGES.find((r) => r.key === days)?.label}
          </span>
        )}
        {RANGES.map((r) => (
          <button key={r.key} className={days === r.key ? "on" : ""} onClick={() => setDays(r.key)}>{r.label}</button>
        ))}
      </div>
    </div>
  );
}
