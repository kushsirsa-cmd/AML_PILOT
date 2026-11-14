"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, fmtDateTime, Level, Pill, Spinner } from "@/components/ui";

const CAT_COLOR: Record<string, string> = {
  SANCTIONED: "#b91c1c", RANSOMWARE: "#b91c1c", DARKNET: "#c2410c", MIXER: "#c2410c", SCAM: "#c2410c", UNREGULATED_EXCHANGE: "#d97706",
  GAMBLING: "#d97706", REGULATED_EXCHANGE: "#059669", DEFI: "#6366f1", UNLABELED: "#94a3b8",
};

function Graph({ g }: { g: Json }) {
  const cols = useMemo(() => {
    const m: Record<number, Json[]> = {};
    g.nodes.forEach((n: Json) => { (m[n.level] ||= []).push(n); });
    return m;
  }, [g]);
  const levels = Object.keys(cols).map(Number).sort((a, b) => a - b);
  const W = 900, rowH = 46, H = Math.max(...Object.values(cols).map((c) => c.length)) * rowH + 40;
  const pos: Record<string, { x: number; y: number }> = {};
  levels.forEach((lv, i) => cols[lv].forEach((n: Json, j: number) => {
    const x = 70 + (levels.length === 1 ? 0 : (i * (W - 220)) / (levels.length - 1));
    pos[n.id] = { x, y: 30 + j * rowH + (H - 40 - cols[lv].length * rowH) / 2 + rowH / 2 };
  }));
  const maxAmt = Math.max(...g.edges.map((e: Json) => e.amount_eur), 1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded border border-slate-200 bg-slate-50">
      <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" /></marker></defs>
      {g.edges.map((e: Json, i: number) => pos[e.source] && pos[e.target] && (
        <line key={i} x1={pos[e.source].x + 55} y1={pos[e.source].y} x2={pos[e.target].x - 55} y2={pos[e.target].y} stroke="#94a3b8" strokeWidth={1 + (4 * e.amount_eur) / maxAmt} markerEnd="url(#arr)" opacity={0.7}>
          <title>{eur(e.amount_eur)} in {e.tx_count} tx</title>
        </line>
      ))}
      {g.nodes.map((n: Json) => pos[n.id] && (
        <g key={n.id} transform={`translate(${pos[n.id].x - 55},${pos[n.id].y - 16})`}>
          <rect width={110} height={32} rx={6} fill="white" stroke={CAT_COLOR[n.category] || "#94a3b8"} strokeWidth={n.focus ? 3 : 1.5} />
          <text x={55} y={13} textAnchor="middle" fontSize={9} fontWeight={600} fill={CAT_COLOR[n.category] || "#475569"}>{n.focus ? "THIS WALLET" : n.category.replace(/_/g, " ")}</text>
          <text x={55} y={25} textAnchor="middle" fontSize={8} fill="#64748b">{n.entity ? n.entity.slice(0, 22) : n.id.slice(0, 8) + "…" + n.id.slice(-4)}</text>
          <title>{n.id}</title>
        </g>
      ))}
    </svg>
  );
}

function Mix({ title, mix }: { title: string; mix: Record<string, number> }) {
  const entries = Object.entries(mix || {});
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</h3>
      {entries.length === 0 && <span className="text-xs text-slate-400">None</span>}
      {entries.map(([k, v]) => (
        <div key={k} className="mb-1 text-xs"><div className="flex justify-between"><span>{k.replace(/_/g, " ")}</span><span>{v}%</span></div>
          <div className="h-2 rounded bg-slate-100"><div className="h-2 rounded" style={{ width: `${Math.min(v, 100)}%`, background: CAT_COLOR[k] || "#94a3b8" }} /></div></div>
      ))}
    </div>
  );
}

export default function WalletDetail() {
  const { id } = useParams<{ id: string }>();
  const [a, setA] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hops, setHops] = useState(2);
  const load = () => api(`/crypto/wallets/${id}/analysis?hops=${hops}`).then(setA).catch((e) => setErr(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id, hops]);

  async function rescreen() {
    setBusy(true);
    try { await post(`/crypto/wallets/${id}/screen`); await load(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  async function sar() {
    const o = a.wallet.owner;
    if (!o) return;
    try { const s = await post("/sars/generate", { subject_type: "wallet", subject_id: a.wallet.id }); window.location.href = `/sars/${s.id}`; } catch (e) { setErr((e as Error).message); }
  }
  if (!a) return err ? <ErrorBox message={err} /> : <Spinner label="Tracing…" />;
  const w = a.wallet;
  return (
    <div className="space-y-4">
      <Link href="/crypto" className="text-xs text-indigo-700 hover:underline">← Wallets</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Wallet {w.owner ? `· ${w.owner.name}` : ""}</h1>
          <div className="break-all font-mono text-xs text-slate-500">{w.address}</div>
          <div className="mt-1 flex items-center gap-2 text-sm"><Level value={a.risk.level} /> <b>{a.risk.score}</b>/100 {a.risk.overrides?.map((o: string) => <Pill key={o} tone="red">{o}</Pill>)}</div>
        </div>
        <div className="flex gap-2"><button className="btn-secondary" onClick={sar}>Draft SAR</button><button className="btn" disabled={busy} onClick={rescreen}>{busy ? "Screening…" : "Re-screen"}</button></div>
      </div>
      <ErrorBox message={err} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Risk score breakdown">
          {Object.entries(a.risk.components).map(([k, v]: [string, Json]) => (
            <div key={k} className="mb-2 text-sm"><div className="flex justify-between"><span className="font-medium">{k.replace(/_/g, " ")}</span><b>{v.points}</b></div><div className="text-xs text-slate-500">{v.reason}</div></div>
          ))}
        </Card>
        <Card title="Exposure (haircut method, 3 hops)">
          <div className="grid gap-3"><Mix title="Source of funds – direct" mix={a.exposure.sources_direct_pct} /><Mix title="Source of funds – indirect" mix={a.exposure.sources_indirect_pct} /><Mix title="Destination of funds" mix={a.exposure.destinations_total_pct} /></div>
        </Card>
        <Card title="Behavioural patterns">
          {a.patterns.length === 0 && <span className="text-sm text-slate-400">No patterns detected.</span>}
          {a.patterns.map((p: Json) => (<div key={p.pattern} className="mb-2 text-sm"><Level value={p.severity} /> <b>{p.pattern.replace(/_/g, " ")}</b><div className="text-xs text-slate-500">{p.detail}</div></div>))}
          <div className="mt-2 text-xs text-slate-400">{a.summary.tx_count} tx · in {eur(a.summary.total_received_eur)} · out {eur(a.summary.total_sent_eur)}</div>
        </Card>
      </div>
      <Card title="Transaction graph" right={<select className="input w-28" value={hops} onChange={(e) => setHops(+e.target.value)}><option value={1}>1 hop</option><option value={2}>2 hops</option><option value={3}>3 hops</option></select>}>
        <Graph g={a.graph} />
        <div className="mt-2 flex flex-wrap gap-3 text-xs">{Object.entries(CAT_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c }} />{k.replace(/_/g, " ")}</span>)}</div>
      </Card>
      {a.risky_traces.length > 0 && (
        <Card title="Traces to risky entities">
          {a.risky_traces.map((t: Json, i: number) => (
            <div key={i} className="mb-3 text-sm"><Level value={t.direction} /> <b>{t.category.replace(/_/g, " ")}</b> – {t.entity} <span className="text-xs text-slate-400">({t.hops} hop{t.hops > 1 ? "s" : ""})</span>
              <ol className="mt-1 list-decimal pl-6 text-xs text-slate-600">{t.path.map((s: Json, j: number) => <li key={j}><span className="font-mono">{s.from_address.slice(0, 8)}…</span> → <span className="font-mono">{s.to_address.slice(0, 8)}…</span> {eur(s.amount_eur)} · {fmtDateTime(s.ts)}</li>)}</ol></div>
          ))}
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Counterparties">
          <table className="w-full text-sm"><thead><tr><th className="th">Counterparty</th><th className="th">Received</th><th className="th">Sent</th></tr></thead><tbody className="divide-y divide-slate-100">
            {a.counterparties.map((c: Json) => <tr key={c.address}><td className="td"><div>{c.entity || <span className="font-mono text-xs">{c.address.slice(0, 12)}…</span>}</div><div className="text-xs text-slate-400">{c.category.replace(/_/g, " ")}</div></td><td className="td">{eur(c.received_from_eur)}</td><td className="td">{eur(c.sent_to_eur)}</td></tr>)}
          </tbody></table>
        </Card>
        <Card title="Transactions">
          <div className="max-h-96 overflow-auto"><table className="w-full text-sm"><thead><tr><th className="th">When</th><th className="th">Dir</th><th className="th">Counterparty</th><th className="th">EUR</th></tr></thead><tbody className="divide-y divide-slate-100">
            {[...a.transactions].reverse().map((t: Json) => <tr key={t.tx_hash}><td className="td text-xs text-slate-500">{fmtDateTime(t.ts)}</td><td className="td"><Pill tone={t.direction === "IN" ? "green" : "slate"}>{t.direction}</Pill></td><td className="td text-xs">{t.counterparty_entity || t.counterparty_category.replace(/_/g, " ")}</td><td className="td">{Math.round(t.amount_eur).toLocaleString("en-GB")}</td></tr>)}
          </tbody></table></div>
        </Card>
      </div>
    </div>
  );
}
