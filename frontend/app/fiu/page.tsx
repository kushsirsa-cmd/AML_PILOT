"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, Spinner, Stat } from "@/components/ui";
import { C, Donut, HBars } from "@/components/charts";
import { Level } from "@/components/ui";
import { Meter, Prio, QUEUE_LABEL } from "@/components/fiu";

export default function Fiu() {
  const [d, setD] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api("/fiu/dashboard").then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function open(r: Json) {
    try { const c = await post("/investigations", { entity_type: r.entity_type, entity_id: r.entity_id, source_type: "RBI" }); window.location.href = `/cases/${c.id}`; } catch (e) { setErr((e as Error).message); }
  }
  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading FIU dashboard…" />;
  const t = d.tiles;
  const qcol: Record<string, string> = { TRIAGE: C.s1, FIU: C.s2, ESCALATION: "#7c3aed", SAR: "#f97316", MLRO: "#b91c1c", CLOSED: "#94a3b8" };
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Investigations &amp; FIU</h1><p className="mt-1 text-sm text-slate-500">Risk Based Investigation, FIU, link analysis, typologies, crypto tracing and SAR/STR preparation. Agents prepare — people decide.</p></div>
      <ErrorBox message={err} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Open investigations" value={t.open_investigations} href="/cases" />
        <Stat label="Pending escalations" value={t.pending_escalations} href="/cases?queue=ESCALATION" tone={t.pending_escalations ? "border-orange-300" : undefined} />
        <Stat label="SAR queue" value={t.sar_queue} sub="drafts + with MLRO" href="/cases?queue=SAR" />
        <Stat label="Regulatory filing queue" value={t.regulatory_filing_queue} sub="awaiting MLRO / filing" href="/sars" />
        <Stat label="High-risk customers" value={t.high_risk_customers} sub="individuals + businesses" href="/customers" />
        <Stat label="High-risk wallets" value={t.high_risk_wallets} href="/crypto" />
        <Stat label="Suspicious transactions" value={t.suspicious_transactions} sub={eur(t.suspicious_transactions_eur) + " flagged"} href="/transactions" />
        <Stat label="Network analysis cases" value={t.network_cases} sub="clusters ≥ medium risk" href="/network" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Case queues"><HBars items={["TRIAGE", "FIU", "ESCALATION", "SAR", "MLRO", "CLOSED"].map((k) => ({ label: QUEUE_LABEL[k], value: d.queues[k] || 0, color: qcol[k] }))} /></Card>
        <Card title="Open cases by priority">
          <Donut center={t.open_investigations} sub="open" data={["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((k) => ({ label: k, value: d.priority[k] || 0, color: { CRITICAL: "#b91c1c", HIGH: "#f97316", MEDIUM: "#f5b301", LOW: "#16a34a" }[k] as string }))} />
        </Card>
        <Card title="Typologies in open cases">
          <HBars color={C.s2} items={d.typologies.slice(0, 7).map((x: Json) => ({ label: x.label, value: x.count }))} />
          <div className="mt-3 text-xs text-slate-400">Ageing: {Object.entries(d.ageing).map(([k, v]) => `${k}: ${v}`).join(" · ") || "no open cases"}</div>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="RBI priority queue" right={<span className="text-xs text-slate-400">high-risk subjects without a case, ranked by investigation priority</span>}>
          <table><thead><tr><th className="th">Subject</th><th className="th">Priority</th><th className="th">Typologies</th><th className="th"></th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {d.rbi_queue.map((r: Json) => (
                <tr key={r.entity_type + r.entity_id}>
                  <td className="td"><Link href={`/customers/${r.entity_id}`} className="font-medium text-brand-700 hover:underline">{r.name}</Link><div className="text-xs text-slate-400">{r.ref} · {r.rating}</div></td>
                  <td className="td"><Meter value={r.priority_score} /></td>
                  <td className="td text-xs text-slate-600">{(r.typologies || []).slice(0, 2).join(", ").replace(/_/g, " ").toLowerCase() || "—"}</td>
                  <td className="td text-right"><button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => open(r)}>Open case</button></td>
                </tr>))}
              {d.rbi_queue.length === 0 && <tr><td className="td text-slate-400" colSpan={4}>Nothing waiting.</td></tr>}
            </tbody></table>
        </Card>
        <Card title="Network clusters" right={<Link href="/network" className="text-xs text-brand-700 hover:underline">All clusters →</Link>}>
          <div className="space-y-2">
            {d.top_clusters.map((c: Json) => (
              <Link key={c.id} href={`/network?cluster=${encodeURIComponent(c.id)}`} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm hover:bg-slate-50">
                <span><span className="font-medium">{c.names.join(", ")}</span>{c.size > 3 && <span className="text-slate-400"> +{c.size - 3}</span>}</span>
                <span className="flex items-center gap-2"><Meter value={c.score} /><Level value={c.level} /></span>
              </Link>))}
            {d.top_clusters.length === 0 && <div className="text-sm text-slate-400">No medium-or-higher clusters.</div>}
          </div>
          <div className="mt-4 grid grid-cols-4 gap-2 text-center text-xs">
            {[["Draft", d.filing.draft], ["With MLRO", d.filing.pending_mlro], ["Approved", d.filing.approved], ["Filed", d.filing.filed]].map(([k, v]) => <div key={k as string} className="rounded-lg bg-slate-50 p-2"><div className="text-lg font-semibold">{v}</div><div className="text-slate-500">{k}</div></div>)}
          </div>
          <div className="mt-1 text-center text-[11px] text-slate-400">SAR / STR filing pipeline</div>
        </Card>
      </div>
    </div>
  );
}
