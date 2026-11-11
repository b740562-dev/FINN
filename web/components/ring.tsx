/** Small progress ring with the percentage inside (profile completeness). */
export function Ring({ pct, size = 34, stroke = 3.5 }: { pct: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, pct));
  const done = v >= 100;
  return (
    <span className="ring" style={{ width: size, height: size }} aria-label={`Profile ${v}% complete`} title={`Profile ${v}% complete`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={done ? "#5be38f" : "#c6f45e"} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dasharray 0.35s ease" }} />
      </svg>
      <b style={{ fontSize: Math.max(9, size * 0.27) }}>{done ? "✓" : `${v}%`}</b>
    </span>
  );
}
