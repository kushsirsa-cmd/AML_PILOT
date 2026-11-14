"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Spinner } from "@/components/ui";

const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Due diligence", keys: ["KYC_REVIEW", "CDD_REVIEW", "EDD_REVIEW", "SOF_VERIFICATION", "SOW_VERIFICATION"] },
  { title: "Alerts", keys: ["SANCTIONS_ALERTS", "PEP_ALERTS", "SCREENING_ALERTS", "TXN_ALERTS", "KYB_ALERTS", "CRYPTO_ALERTS"] },
  { title: "Reviews & escalation", keys: ["PERIODIC_REVIEWS", "EVENT_REVIEWS", "SAR_ESCALATION"] },
];

export default function Work() {
  const [data, setData] = useState<Json[] | null>(null);
  const [active, setActive] = useState("EDD_REVIEW");
  const [err, setErr] = useState<string | null>(null);
  const load = () => api("/workqueue").then((r) => setData(r.queues)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  async function assign(id: number) {
    try { await post(`/alerts/${id}/action`, { action: "START_REVIEW" }); load(); } catch (e) { setErr((e as Error).message); }
  }
  if (!data) return err ? <ErrorBox message={err} /> : <Spinner label="Loading queues…" />;
  const byKey = Object.fromEntries(data.map((q) => [q.key, q]));
  const q = byKey[active];
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Work queues</h1><p className="mt-1 text-sm text-slate-500">Every AML workflow in one place — derived live from agent assessments, alerts, reviews and SARs. Click a row to open the case.</p></div>
      <ErrorBox message={err} />
      <div className="grid gap-4 lg:grid-cols-3">
        {GROUPS.map((g) => (
          <Card key={g.title} title={g.title}>
            <div className="space-y-1">
              {g.keys.map((k) => byKey[k] && (
                <button key={k} onClick={() => setActive(k)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${active === k ? "bg-brand-50 font-medium text-brand-700" : "hover:bg-slate-50"}`}>
                  <span>{byKey[k].label}</span><span className={`rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${byKey[k].count ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"}`}>{byKey[k].count}</span>
                </button>
              ))}
            </div>
          </Card>
        ))}
      </div>
      {q && (
        <Card title={`${q.label} · ${q.count}`} right={<span className="text-xs text-slate-400">{q.description}</span>}>
          <table>
            <thead><tr><th className="th">Subject</th><th className="th">Risk</th><th className="th">Why it&apos;s here</th><th className="th">Age</th><th className="th">Owner</th><th className="th"></th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {q.items.map((i: Json, n: number) => (
                <tr key={n}>
                  <td className="td"><Link href={i.link} className="font-medium text-brand-700 hover:underline">{i.name}</Link><div className="text-xs text-slate-400">{i.ref}</div></td>
                  <td className="td">{i.rating ? <Level value={i.rating} /> : "–"}</td>
                  <td className="td max-w-xl text-slate-600">{i.detail}</td>
                  <td className="td tabular-nums text-slate-500">{i.age_days !== null && i.age_days !== undefined ? `${i.age_days}d` : "–"}</td>
                  <td className="td text-xs">{i.assignee || <span className="text-slate-400">unassigned</span>}</td>
                  <td className="td text-right">{i.alert_id && i.status === "OPEN" ? <button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => assign(i.alert_id)}>Start review</button> : <Level value={i.status} />}</td>
                </tr>
              ))}
              {q.items.length === 0 && <tr><td className="td text-slate-400" colSpan={6}>Queue is empty — nice.</td></tr>}
            </tbody>
          </table>
          {q.count > q.items.length && <p className="mt-3 text-xs text-slate-400">Showing the first {q.items.length} of {q.count}.</p>}
        </Card>
      )}
    </div>
  );
}
