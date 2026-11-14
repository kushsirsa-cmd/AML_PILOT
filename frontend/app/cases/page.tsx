"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDate, Level, Spinner } from "@/components/ui";
import { Meter, Prio, QUEUE_LABEL } from "@/components/fiu";

const TABS = ["ALERT", "TRIAGE", "FIU", "ESCALATION", "SAR", "MLRO", "CLOSED"];
const HELP: Record<string, string> = {
  ALERT: "Open alerts with no investigation yet. Open a case to start the nine-step workflow.",
  TRIAGE: "Cases awaiting a triage decision (steps 1–2): proceed, or close as a false positive.",
  FIU: "Active FIU investigation: evidence, transaction analysis, network and typology work (steps 3–6).",
  ESCALATION: "Escalated by a senior analyst; decide whether to draft a SAR/STR (step 7).",
  SAR: "SAR/STR drafted — narrative being completed and submitted to the MLRO (step 8).",
  MLRO: "With the MLRO for the reporting decision. Only the MLRO approves and files.",
  CLOSED: "Closed with a recorded disposition and rationale (step 9).",
};

export default function Cases() {
  const [tab, setTab] = useState("TRIAGE");
  const [data, setData] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback((q: string) => api(`/investigations?queue=${q}`).then(setData).catch((e) => setErr(e.message)), []);
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("queue"); if (q && TABS.includes(q)) setTab(q); }, []);
  useEffect(() => { load(tab); }, [tab, load]);
  async function open(alertId: number) {
    try { const c = await post("/investigations", { alert_id: alertId }); window.location.href = `/cases/${c.id}`; } catch (e) { setErr((e as Error).message); }
  }
  if (!data) return err ? <ErrorBox message={err} /> : <Spinner label="Loading cases…" />;
  const items: Json[] = data.items;
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Case queues</h1><p className="mt-1 text-sm text-slate-500">Alert → Triage → FIU → Escalation → SAR → MLRO. Moves are role-checked on the server and every action is audited.</p></div>
      <ErrorBox message={err} />
      <div className="flex flex-wrap gap-2">
        {TABS.map((k) => (
          <button key={k} onClick={() => { setData(null); setTab(k); }} className={`rounded-lg px-3.5 py-2 text-sm font-medium transition ${tab === k ? "bg-slate-900 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
            {QUEUE_LABEL[k]} <span className={`ml-1.5 rounded-full px-1.5 text-xs ${tab === k ? "bg-white/20" : "bg-slate-100"}`}>{data.counts[k]}</span>
          </button>))}
      </div>
      <Card title={QUEUE_LABEL[tab]} right={<span className="text-xs text-slate-400">{HELP[tab]}</span>}>
        {tab === "ALERT" ? (
          <table><thead><tr><th className="th">Alert</th><th className="th">Source</th><th className="th">Severity</th><th className="th">Raised</th><th className="th"></th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((a) => <tr key={a.id}><td className="td font-medium">{a.title}</td><td className="td text-xs">{a.source.replace(/_/g, " ")}</td><td className="td"><Level value={a.severity} /></td><td className="td text-xs text-slate-500">{fmtDate(a.created_at)}</td>
                <td className="td text-right"><button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => open(a.id)}>Open investigation</button></td></tr>)}
              {items.length === 0 && <tr><td className="td text-slate-400" colSpan={5}>No un-investigated open alerts.</td></tr>}
            </tbody></table>
        ) : (
          <table><thead><tr><th className="th">Case</th><th className="th">Subject</th><th className="th">Priority</th><th className="th">Risk</th><th className="th">Confidence</th><th className="th">Typologies</th><th className="th">Step</th><th className="th">Age</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((c) => (
                <tr key={c.id}>
                  <td className="td"><Link href={`/cases/${c.id}`} className="font-medium text-brand-700 hover:underline">{c.reference}</Link><div className="text-xs text-slate-400">{c.source_type.toLowerCase()} · {c.assigned_to || "unassigned"}</div></td>
                  <td className="td">{c.subject}<div className="text-xs text-slate-400">{c.subject_ref}</div></td>
                  <td className="td"><Prio v={c.priority} /></td>
                  <td className="td"><Meter value={c.risk_score ?? 0} /></td>
                  <td className="td tabular-nums">{c.confidence ?? "–"}<span className="text-xs text-slate-400">/100</span></td>
                  <td className="td max-w-[14rem] text-xs text-slate-600">{(c.typologies || []).slice(0, 2).join(", ").replace(/_/g, " ").toLowerCase() || "—"}</td>
                  <td className="td tabular-nums text-slate-500">{c.step}/9</td>
                  <td className="td tabular-nums text-slate-500">{c.age_days}d</td>
                </tr>))}
              {items.length === 0 && <tr><td className="td text-slate-400" colSpan={8}>Queue is empty.</td></tr>}
            </tbody></table>
        )}
      </Card>
    </div>
  );
}
