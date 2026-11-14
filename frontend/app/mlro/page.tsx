"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, Level, Spinner, Stat, fmtDateTime } from "@/components/ui";

export default function Mlro() {
  const [d, setD] = useState<Json>(null);
  const [alerts, setAlerts] = useState<Json[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("open");
  const load = () => {
    api("/mlro/dashboard").then(setD).catch((e) => setErr(e.message));
    api("/alerts").then(setAlerts).catch((e) => setErr(e.message));
  };
  useEffect(load, []);

  async function act(id: number, action: string) {
    const note = action === "START_REVIEW" || action === "ASSIGN" ? undefined : window.prompt(`Rationale for ${action} (min 10 chars)`) || "";
    if (note !== undefined && note.length < 10) return;
    setErr(null);
    try { await post(`/alerts/${id}/action`, { action, note }); load(); } catch (e) { setErr((e as Error).message); }
  }
  async function decide(id: number, decision: string) {
    const rationale = window.prompt(`MLRO rationale for ${decision} (min 10 chars)`) || "";
    if (rationale.length < 10) return;
    setErr(null);
    try { const r = await post(`/mlro/alerts/${id}/decision`, { decision, rationale }); if (r.sar_id) window.location.href = `/sars/${r.sar_id}`; else load(); } catch (e) { setErr((e as Error).message); }
  }
  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading..." />;
  const k = d.kpis;
  const shown = alerts.filter((a) => (filter === "open" ? a.status !== "CLOSED" : filter === "all" ? true : a.status === filter));
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">MLRO dashboard</h1>
      <p className="text-sm text-slate-500">Escalations are decided and SARs approved by the <b>MLRO</b> persona (sign out and choose Maria Wiśniewska). Preparers cannot approve their own work.</p>
      <ErrorBox message={err} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
        <Stat label="Open alerts" value={k.open_alerts} /><Stat label="Critical" value={k.critical_open} tone="border-red-300" /><Stat label="Escalated" value={k.escalated_to_mlro} tone="border-orange-300" />
        <Stat label="SARs to approve" value={k.sars_pending_approval} href="/sars" /><Stat label="SARs filed" value={k.sars_filed} /><Stat label="TR holds" value={k.travel_rule_holds} href="/travel-rule" />
        <Stat label="High-risk custs" value={k.high_risk_customers} href="/customers" /><Stat label="Oldest open (d)" value={d.oldest_open_alert_days} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Escalation queue (decision required)">
          {d.escalation_queue.length === 0 && <span className="text-sm text-slate-400">Nothing waiting for the MLRO.</span>}
          {d.escalation_queue.map((a: Json) => (
            <div key={a.id} className="mb-3 rounded border border-slate-200 p-3 text-sm">
              <div className="flex items-center gap-2"><Level value={a.severity} /><b>{a.title}</b><span className="text-xs text-slate-400">{a.age_days}d</span></div>
              <p className="mt-1 text-xs text-slate-600">{a.description}</p>
              {a.resolution && <p className="mt-1 text-xs italic text-slate-500">Analyst: {a.resolution}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {[["FILE_SAR", "File SAR"], ["REQUEST_MORE_INFO", "More info"], ["CLOSE_NO_SAR", "Close – no SAR"], ["EXIT_RELATIONSHIP", "Exit"]].map(([x, l]) => (
                  <button key={x} className={x === "EXIT_RELATIONSHIP" ? "btn-danger !px-2 !py-1 text-xs" : "btn-secondary !px-2 !py-1 text-xs"} onClick={() => decide(a.id, x)}>{l}</button>
                ))}
              </div>
            </div>
          ))}
        </Card>
        <Card title="SAR approval queue">
          {d.sar_approval_queue.length === 0 && <span className="text-sm text-slate-400">No SARs pending.</span>}
          {d.sar_approval_queue.map((s: Json) => (
            <div key={s.id} className="mb-2 flex items-center justify-between text-sm"><div><Link className="font-medium text-indigo-700 hover:underline" href={`/sars/${s.id}`}>{s.reference}</Link> – {s.subject_name}<div className="text-xs text-slate-500">{eur(s.total_amount_eur)} · {s.typologies.join(", ")} · prepared by {s.prepared_by}</div></div><Level value="PENDING_MLRO" /></div>
          ))}
          <div className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><b>By source</b>{Object.entries(d.alerts_by_source).map(([s, n]) => <div key={s}>{s}: {n as number}</div>)}</div><div><b>By severity</b>{Object.entries(d.alerts_by_severity).map(([s, n]) => <div key={s}>{s}: {n as number}</div>)}</div></div>
        </Card>
      </div>
      <Card title="Alert inbox" right={<select className="input w-44" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="open">Not closed</option><option value="all">All</option>{["OPEN", "IN_REVIEW", "ESCALATED_MLRO", "SAR_DRAFTED", "CLOSED"].map((s) => <option key={s}>{s}</option>)}</select>}>
        <table className="w-full">
          <thead><tr><th className="th">Raised</th><th className="th">Sev</th><th className="th">Source</th><th className="th">Alert</th><th className="th">Status</th><th className="th">Assigned</th><th className="th"></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((a) => (
              <tr key={a.id}>
                <td className="td text-xs text-slate-500">{fmtDateTime(a.created_at)}</td><td className="td"><Level value={a.severity} /></td><td className="td text-xs">{a.source}</td>
                <td className="td"><div className="font-medium">{a.title}</div><div className="text-xs text-slate-500">{a.description.slice(0, 140)}</div></td>
                <td className="td"><Level value={a.status} /></td><td className="td text-xs">{a.assigned_to || "-"}</td>
                <td className="td whitespace-nowrap">{["OPEN", "IN_REVIEW"].includes(a.status) && <>
                  {a.status === "OPEN" && <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => act(a.id, "START_REVIEW")}>Start</button>}
                  <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => act(a.id, "CLOSE")}>Close</button>
                  <button className="btn-danger !px-2 !py-1 text-xs" onClick={() => act(a.id, "ESCALATE")}>Escalate</button></>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
