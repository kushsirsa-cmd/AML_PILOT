"use client";
import { ReactNode, useState } from "react";

// Categorical slots 1-3 of the validated default palette (blue / orange / aqua); risk levels use status colours.
export const C = { s1: "#2a78d6", s2: "#eb6834", s3: "#1baf7a", grid: "#e2e8f0", muted: "#64748b" };
export const RISK_COLOR: Record<string, string> = { LOW: "#16a34a", MEDIUM: "#f5b301", HIGH: "#f97316", PROHIBITED: "#b91c1c" };
const SEV_COLOR: Record<string, string> = { LOW: "#16a34a", MEDIUM: "#f5b301", HIGH: "#f97316", CRITICAL: "#b91c1c" };
export { SEV_COLOR };

export function Legend({ items }: { items: { label: string; color: string; value?: ReactNode }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: i.color }} />{i.label}{i.value !== undefined && <b className="font-semibold text-slate-900">{i.value}</b>}</span>
      ))}
    </div>
  );
}

export function Donut({ data, center, sub }: { data: { label: string; value: number; color: string }[]; center: ReactNode; sub?: string }) {
  const total = data.reduce((a, d) => a + d.value, 0) || 1;
  const [hover, setHover] = useState<number | null>(null);
  const R = 52, r = 36, cx = 70, cy = 70;
  let acc = 0;
  const arcs = data.map((d, i) => {
    const a0 = (acc / total) * 2 * Math.PI - Math.PI / 2;
    acc += d.value;
    const a1 = (acc / total) * 2 * Math.PI - Math.PI / 2 - (d.value === total ? 0.0001 : 0);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (rad: number, a: number) => `${cx + rad * Math.cos(a)} ${cy + rad * Math.sin(a)}`;
    return { d, i, path: d.value ? `M ${p(R, a0)} A ${R} ${R} 0 ${large} 1 ${p(R, a1)} L ${p(r, a1)} A ${r} ${r} 0 ${large} 0 ${p(r, a0)} Z` : "" };
  });
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 140 140" className="h-36 w-36 shrink-0" role="img" aria-label="Distribution">
        {arcs.map(({ d, i, path }) => path && <path key={i} d={path} fill={d.color} stroke="#fff" strokeWidth={2} opacity={hover === null || hover === i ? 1 : 0.35} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />)}
        <text x={cx} y={cy + 2} textAnchor="middle" fontSize="22" fontWeight="600" fill="#0f172a">{hover !== null ? data[hover].value : center}</text>
        <text x={cx} y={cy + 17} textAnchor="middle" fontSize="8" fill="#64748b">{hover !== null ? data[hover].label : sub}</text>
      </svg>
      <div className="space-y-1.5 text-sm">
        {data.map((d, i) => (
          <div key={d.label} className="flex items-center gap-2" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <i className="h-2.5 w-2.5 rounded-[3px]" style={{ background: d.color }} /><span className="w-24 text-slate-600">{d.label}</span><b className="tabular-nums text-slate-900">{d.value}</b>
            <span className="text-xs text-slate-400">{Math.round((100 * d.value) / total)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StackedColumns({ labels, series, height = 250 }: { labels: string[]; series: { name: string; color: string; values: number[] }[]; height?: number }) {
  const W = 340, padL = 28, padB = 22, padT = 8;
  const totals = labels.map((_, i) => series.reduce((a, s) => a + (s.values[i] || 0), 0));
  const max = Math.max(4, ...totals);
  const bw = Math.min(46, ((W - padL) / labels.length) * 0.58);
  const step = (W - padL) / labels.length;
  const H = height - padB - padT;
  const [hover, setHover] = useState<number | null>(null);
  const nice = Math.ceil(max / 4) * 4;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label="Stacked columns">
        {[0, 1, 2, 3, 4].map((t) => { const y = padT + H - (H * t) / 4; return <g key={t}><line x1={padL} x2={W} y1={y} y2={y} stroke={C.grid} strokeWidth={t === 0 ? 1 : 0.6} /><text x={padL - 5} y={y + 3} textAnchor="end" fontSize="11" fill={C.muted}>{Math.round((nice * t) / 4)}</text></g>; })}
        {labels.map((l, i) => {
          let y = padT + H;
          const x = padL + step * i + (step - bw) / 2;
          return (
            <g key={l} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={padL + step * i} y={padT} width={step} height={H + padB} fill="transparent" />
              {series.map((s, si) => { const h = (H * (s.values[i] || 0)) / nice; y -= h; return h > 0 ? <rect key={s.name} x={x} y={y} width={bw} height={Math.max(0, h - 1.5)} rx={si === series.length - 1 ? 3 : 0} fill={s.color} opacity={hover === null || hover === i ? 1 : 0.5} /> : null; })}
              <text x={x + bw / 2} y={height - 6} textAnchor="middle" fontSize="9.5" fill={C.muted}>{l.slice(5) ? new Date(l + "-01").toLocaleDateString("en-GB", { month: "short" }) : l}</text>
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg">
          <div className="mb-0.5 font-semibold">{new Date(labels[hover] + "-01").toLocaleDateString("en-GB", { month: "long", year: "numeric" })}</div>
          {series.map((s) => <div key={s.name} className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.name}: <b>{s.values[hover]}</b></div>)}
        </div>
      )}
    </div>
  );
}

export function LineArea({ labels, series, height = 190, fmt = (n: number) => String(n) }: { labels: string[]; series: { name: string; color: string; values: number[] }[]; height?: number; fmt?: (n: number) => string }) {
  const W = 520, padL = 40, padB = 22, padT = 8, H = height - padB - padT;
  const max = Math.max(1, ...series.flatMap((s) => s.values)) * 1.08;
  const x = (i: number) => padL + ((W - padL - 22) * i) / Math.max(1, labels.length - 1);
  const y = (v: number) => padT + H - (H * v) / max;
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label="Line chart" onMouseLeave={() => setHover(null)}>
        {[0, 1, 2, 3].map((t) => { const yy = padT + H - (H * t) / 3; return <g key={t}><line x1={padL} x2={W} y1={yy} y2={yy} stroke={C.grid} strokeWidth={t === 0 ? 1 : 0.6} /><text x={padL - 5} y={yy + 3} textAnchor="end" fontSize="9" fill={C.muted}>{fmt((max * t) / 3)}</text></g>; })}
        {series.map((s, si) => {
          const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
          return <g key={s.name}>{si === 0 && <polygon points={`${x(0)},${y(0)} ${pts} ${x(labels.length - 1)},${y(0)}`} fill={s.color} opacity={0.08} />}<polyline points={pts} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" /></g>;
        })}
        {labels.map((l, i) => (i % 2 === 0 || i === labels.length - 1) && <text key={l} x={x(i)} y={height - 6} textAnchor="middle" fontSize="9" fill={C.muted}>{l}</text>)}
        {hover !== null && <g><line x1={x(hover)} x2={x(hover)} y1={padT} y2={padT + H} stroke="#94a3b8" strokeDasharray="3 3" />{series.map((s) => <circle key={s.name} cx={x(hover)} cy={y(s.values[hover])} r={4} fill={s.color} stroke="#fff" strokeWidth={2} />)}</g>}
        {labels.map((_, i) => <rect key={i} x={x(i) - (W - padL) / labels.length / 2} y={padT} width={(W - padL) / labels.length} height={H} fill="transparent" onMouseEnter={() => setHover(i)} />)}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-0 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg">
          <div className="mb-0.5 font-semibold">Week of {labels[hover]}</div>
          {series.map((s) => <div key={s.name} className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.name}: <b>{fmt(s.values[hover])}</b></div>)}
        </div>
      )}
    </div>
  );
}

export function HBars({ items, color = C.s1, max, suffix = "" }: { items: { label: string; value: number; color?: string; sub?: string }[]; color?: string; max?: number; suffix?: string }) {
  const m = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="space-y-2.5">
      {items.map((i) => (
        <div key={i.label} className="text-xs">
          <div className="mb-1 flex justify-between"><span className="text-slate-600">{i.label}</span><span className="font-semibold tabular-nums text-slate-900">{i.value}{suffix}{i.sub && <span className="ml-1 font-normal text-slate-400">{i.sub}</span>}</span></div>
          <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full" style={{ width: `${Math.max(2, (100 * i.value) / m)}%`, background: i.color || color }} /></div>
        </div>
      ))}
      {items.length === 0 && <div className="text-xs text-slate-400">No data</div>}
    </div>
  );
}
