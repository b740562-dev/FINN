export function Spark({ values, w = 110, h = 30, color = "var(--amber)" }: { values: (number | null)[]; w?: number; h?: number; color?: string }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] !== null && p[1] !== undefined);
  if (pts.length < 2) return <svg width={w} height={h} />;
  const ys = pts.map((p) => p[1]);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const span = max - min || 1;
  const n = values.length - 1 || 1;
  const xy = pts.map(([i, v]) => [(i / n) * (w - 4) + 2, h - 3 - ((v - min) / span) * (h - 6)] as const);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const zeroY = min < 0 && max > 0 ? h - 3 - ((0 - min) / span) * (h - 6) : null;
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      {zeroY !== null && <line x1="0" x2={w} y1={zeroY} y2={zeroY} stroke="var(--line-2)" strokeDasharray="2 3" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r="2.4" fill={color} />
    </svg>
  );
}
