"use client";
import { useState } from "react";
import { Json } from "@/lib/api";
import { RISK_COLOR } from "@/components/charts";

export const QUEUE_LABEL: Record<string, string> = { ALERT: "Alert queue", TRIAGE: "Triage", FIU: "FIU", ESCALATION: "Escalation", SAR: "SAR", MLRO: "MLRO", CLOSED: "Closed" };
export const PRIORITY_TONE: Record<string, string> = { CRITICAL: "bg-red-700 text-white", HIGH: "bg-orange-100 text-orange-800", MEDIUM: "bg-amber-100 text-amber-800", LOW: "bg-emerald-100 text-emerald-800" };

export function Prio({ v }: { v?: string | null }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${PRIORITY_TONE[v || ""] || "bg-slate-100 text-slate-700"}`}>{v || "-"}</span>;
}

export function Meter({ value, label }: { value: number; label?: string }) {
  const c = value >= 80 ? "#b91c1c" : value >= 60 ? "#f97316" : value >= 35 ? "#f5b301" : "#16a34a";
  return (
    <div className="flex items-center gap-2" title={label}>
      <div className="h-1.5 w-20 rounded-full bg-slate-100"><div className="h-1.5 rounded-full" style={{ width: `${Math.max(3, value)}%`, background: c }} /></div>
      <span className="text-xs font-semibold tabular-nums text-slate-700">{value}</span>
    </div>
  );
}

/** Relationship graph. Subject in the centre, others on a ring; edge width = link strength; hover an edge for the shared identifiers. */
export function NetGraph({ nodes, edges, onSelect, height = 380 }: { nodes: Json[]; edges: Json[]; onSelect?: (n: Json) => void; height?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  const W = 760, H = height, cx = W / 2, cy = H / 2;
  const subj = nodes.find((n) => n.is_subject) || nodes[0];
  const others = nodes.filter((n) => n !== subj);
  const pos: Record<string, { x: number; y: number }> = {};
  if (subj) pos[subj.key] = { x: cx, y: cy };
  const r1 = Math.min(W, H) * 0.36;
  others.forEach((n, i) => {
    const ring = others.length > 10 && i % 2 ? 0.62 : 1;
    const a0 = others.length <= 3 ? Math.PI : -Math.PI / 2;
    const a = (2 * Math.PI * i) / Math.max(1, others.length) + a0;
    pos[n.key] = { x: cx + Math.cos(a) * r1 * ring * (W / H) * 0.8, y: cy + Math.sin(a) * r1 * ring };
  });
  if (!subj) return <div className="text-sm text-slate-400">No links found.</div>;
  return (
    <div className="relative overflow-hidden rounded-lg border border-slate-100 bg-slate-50/50">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Entity relationship graph">
        {edges.map((e, i) => {
          const a = pos[e.source], b = pos[e.target];
          if (!a || !b) return null;
          const id = `${e.source}|${e.target}`;
          return (
            <g key={i} onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.declared ? "#94a3b8" : "#eb6834"} strokeWidth={1 + e.strength / 25} strokeDasharray={e.declared ? "5 4" : undefined} opacity={hover && hover !== id ? 0.25 : 0.85} />
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={14} />
            </g>
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.key];
          if (!p) return null;
          const col = RISK_COLOR[n.rating] || "#64748b";
          return (
            <g key={n.key} transform={`translate(${p.x},${p.y})`} onClick={() => onSelect?.(n)} className={onSelect ? "cursor-pointer" : ""}>
              {n.type === "corporate" ? <rect x={-14} y={-14} width={28} height={28} rx={5} fill={col} stroke="#fff" strokeWidth={2.5} /> : <circle r={n.is_subject ? 17 : 14} fill={col} stroke="#fff" strokeWidth={2.5} />}
              {n.is_subject && <circle r={23} fill="none" stroke="#0f172a" strokeWidth={1.5} strokeDasharray="3 3" />}
              <text y={30} textAnchor="middle" className="fill-slate-700 text-[11px] font-medium">{n.name.length > 22 ? n.name.slice(0, 21) + "…" : n.name}</text>
              {n.typology_score !== undefined && n.typology_score >= 35 && <text y={4} textAnchor="middle" className="fill-white text-[10px] font-bold">{n.typology_score}</text>}
            </g>
          );
        })}
      </svg>
      {hover && (() => {
        const e = edges.find((x) => `${x.source}|${x.target}` === hover);
        return e ? (
          <div className="pointer-events-none absolute left-3 top-3 max-w-xs rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-card">
            <div className="mb-1 font-semibold">Link strength {e.strength}/100{e.declared ? " · declared" : " · undeclared"}</div>
            {e.reasons.map((r: Json, i: number) => <div key={i} className="text-slate-600"><span className="font-medium">{r.kind.replace("_", " ").toLowerCase()}</span>: {r.detail}</div>)}
          </div>
        ) : null;
      })()}
      <div className="flex flex-wrap gap-4 border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
        <span>● person ■ company</span>
        {Object.entries(RISK_COLOR).map(([k, c]) => <span key={k}><span style={{ color: c }}>●</span> {k.toLowerCase()}</span>)}
        <span><span style={{ color: "#eb6834" }}>━</span> undeclared link</span><span><span style={{ color: "#94a3b8" }}>┅</span> declared link</span>
      </div>
    </div>
  );
}

/** Wallet fund-flow path: upstream on the left, focus wallet, downstream on the right; cross-chain hops are dashed. */
export function PathMap({ nodes, edges }: { nodes: Json[]; edges: Json[] }) {
  const byLevel: Record<number, Json[]> = {};
  nodes.forEach((n) => { (byLevel[n.level ?? 0] ||= []).push(n); });
  const levels = Object.keys(byLevel).map(Number).sort((a, b) => a - b);
  const colW = 150, rowH = 44, W = Math.max(640, levels.length * colW + 60);
  const H = Math.max(160, Math.max(...Object.values(byLevel).map((v) => v.length)) * rowH + 40);
  const pos: Record<string, { x: number; y: number }> = {};
  levels.forEach((l, ci) => byLevel[l].forEach((n, ri) => { pos[n.id] = { x: 40 + ci * colW, y: 30 + ri * rowH + (H - 40 - byLevel[l].length * rowH) / 2 }; }));
  const COL: Record<string, string> = { MIXER: "#b91c1c", SANCTIONED: "#7f1d1d", DARKNET: "#b91c1c", RANSOMWARE: "#7f1d1d", SCAM: "#f97316", UNREGULATED_EXCHANGE: "#f97316", BRIDGE: "#7c3aed", REGULATED_EXCHANGE: "#16a34a", DEFI: "#64748b", GAMBLING: "#f5b301", UNLABELED: "#94a3b8" };
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-100 bg-slate-50/50">
      <svg viewBox={`0 0 ${W} ${H}`} style={{ minWidth: W }} className="w-full" role="img" aria-label="Fund-flow path">
        {edges.map((e, i) => { const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null; return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.cross_chain ? "#7c3aed" : "#94a3b8"} strokeWidth={e.cross_chain ? 2.5 : 1.3} strokeDasharray={e.cross_chain ? "6 4" : undefined} />; })}
        {nodes.map((n) => { const p = pos[n.id]; if (!p) return null; return (
          <g key={n.id} transform={`translate(${p.x},${p.y})`}>
            <circle r={n.focus ? 10 : 7} fill={COL[n.category] || "#94a3b8"} stroke={n.focus ? "#0f172a" : "#fff"} strokeWidth={2} />
            <text x={14} y={4} className="fill-slate-700 text-[10px]">{n.entity ? (n.entity.length > 22 ? n.entity.slice(0, 21) + "…" : n.entity) : n.id.slice(0, 8) + "…"}</text>
          </g>); })}
      </svg>
      <div className="flex flex-wrap gap-3 border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
        {["MIXER", "BRIDGE", "UNREGULATED_EXCHANGE", "REGULATED_EXCHANGE", "UNLABELED"].map((k) => <span key={k}><span style={{ color: COL[k] }}>●</span> {k.replace("_", " ").toLowerCase()}</span>)}<span><span style={{ color: "#7c3aed" }}>┅</span> cross-chain hop</span>
      </div>
    </div>
  );
}
