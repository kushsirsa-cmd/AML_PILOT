"use client";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Level, Pill, Spinner, Stat } from "@/components/ui";

export default function Qa() {
  const [dash, setDash] = useState<Json>(null);
  const [items, setItems] = useState<Json[]>([]);
  const [criteria, setCriteria] = useState<Json>(null);
  const [active, setActive] = useState<Json>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [findings, setFindings] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    api("/qa/dashboard").then(setDash).catch((e) => setErr(e.message));
    api("/qa/reviews").then(setItems).catch((e) => setErr(e.message));
  };
  useEffect(() => { load(); api("/qa/checklist").then(setCriteria).catch(() => {}); }, []);

  async function open(id: number) {
    const q = await api(`/qa/reviews/${id}`);
    setActive(q); setFindings(q.findings || "");
    setAnswers(q.status === "COMPLETED" ? q.checklist : Object.fromEntries(Object.keys(criteria.criteria).map((k) => [k, "PASS"])));
  }
  async function submit() {
    setErr(null);
    try { await post(`/qa/reviews/${active.id}/complete`, { checklist: answers, findings: findings || null }); setActive(null); load(); } catch (e) { setErr((e as Error).message); }
  }
  async function sample() { setErr(null); try { await post("/qa/sample", { days: 30, low_risk_rate: 0.25 }); load(); } catch (e) { setErr((e as Error).message); } }
  if (!dash) return err ? <ErrorBox message={err} /> : <Spinner label="Loading..." />;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">QA review dashboard</h1><button className="btn" onClick={sample}>Draw sample (last 30 days)</button></div>
      <p className="text-sm text-slate-500">Risk-weighted sampling: 100% of HIGH-risk and MLRO/SAR decisions, 25% of the rest, plus anything the automated pre-checks flag. Reviewers cannot review their own decisions (four-eyes control, enforced by the API).</p>
      <ErrorBox message={err} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Sampled" value={dash.sampled} /><Stat label="Pending" value={dash.pending} tone="border-amber-300" /><Stat label="Completed" value={dash.completed} />
        <Stat label="Pass rate" value={dash.pass_rate_pct === null ? "-" : `${dash.pass_rate_pct}%`} /><Stat label="Auto-flagged" value={dash.auto_flagged} tone="border-orange-300" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Error rate by analyst">
          <table className="w-full text-sm"><thead><tr><th className="th">Analyst</th><th className="th">Sampled</th><th className="th">Done</th><th className="th">Fail</th><th className="th">Findings</th><th className="th">Error %</th></tr></thead><tbody className="divide-y divide-slate-100">
            {dash.by_analyst.map((a: Json) => <tr key={a.analyst}><td className="td">{a.analyst}</td><td className="td">{a.sampled}</td><td className="td">{a.completed}</td><td className="td">{a.failed}</td><td className="td">{a.with_findings}</td><td className="td">{a.error_rate_pct ?? "-"}</td></tr>)}
          </tbody></table>
        </Card>
        <Card title="Where decisions go wrong">
          <div className="grid grid-cols-2 gap-3 text-xs"><div><b>Automated pre-check findings</b>{Object.entries(dash.auto_findings_by_category).map(([k, v]) => <div key={k}>{k}: {v as number}</div>)}{Object.keys(dash.auto_findings_by_category).length === 0 && <div className="text-slate-400">none</div>}</div>
            <div><b>Failed checklist criteria</b>{Object.entries(dash.failed_criteria).map(([k, v]) => <div key={k}>{k.replace(/_/g, " ")}: {v as number}</div>)}{Object.keys(dash.failed_criteria).length === 0 && <div className="text-slate-400">none</div>}</div></div>
          <div className="mt-3 text-xs"><b>Weekly pass rate</b> {dash.weekly_trend.map((w: Json) => <span key={w.week} className="ml-2">{w.week}: {w.pass_rate_pct}%</span>)}</div>
        </Card>
      </div>
      {active && (
        <Card title={`Review #${active.id} – ${active.summary}`} right={<button className="btn-secondary" onClick={() => setActive(null)}>Close</button>}>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="text-sm">
              <div>Decision by <b>{active.decision_maker}</b> · {active.decision_action} · risk {active.risk_rating || "-"}</div>
              <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(active.decision?.details, null, 2)}</pre>
              {active.precheck.map((f: Json, i: number) => <div key={i} className="mt-2 rounded bg-orange-50 p-2 text-xs text-orange-800"><b>{f.category}</b>: {f.message}</div>)}
            </div>
            <div>
              {criteria && Object.entries(criteria.criteria).map(([k, label]) => (
                <div key={k} className="mb-2 flex items-center justify-between gap-2 text-sm"><span>{label as string} {criteria.critical.includes(k) && <Pill tone="red">critical</Pill>}</span>
                  <select className="input w-24" disabled={active.status === "COMPLETED"} value={answers[k] || "PASS"} onChange={(e) => setAnswers({ ...answers, [k]: e.target.value })}><option>PASS</option><option>FAIL</option><option>NA</option></select></div>
              ))}
              <textarea className="input mt-2 h-20" placeholder="Findings (required when any criterion fails)" readOnly={active.status === "COMPLETED"} value={findings} onChange={(e) => setFindings(e.target.value)} />
              {active.status !== "COMPLETED" ? <button className="btn mt-2" onClick={submit}>Complete review</button> : <div className="mt-2 text-sm">Outcome: <Level value={active.outcome} /> score {active.score} · by {active.reviewer}</div>}
            </div>
          </div>
        </Card>
      )}
      <Card title="Sampled decisions">
        <table className="w-full"><thead><tr><th className="th">Sampled</th><th className="th">Decision</th><th className="th">Maker</th><th className="th">Risk</th><th className="th">Auto flags</th><th className="th">Status</th><th className="th">Outcome</th><th className="th"></th></tr></thead><tbody className="divide-y divide-slate-100">
          {items.map((q) => (
            <tr key={q.id}><td className="td text-xs text-slate-500">{fmtDateTime(q.created_at)}</td><td className="td text-xs">{q.summary}</td><td className="td">{q.decision_maker}</td><td className="td">{q.risk_rating ? <Level value={q.risk_rating} /> : "-"}</td>
              <td className="td">{q.precheck.length ? <Pill tone="amber">{q.precheck.length}</Pill> : "-"}</td><td className="td"><Level value={q.status} /></td><td className="td">{q.outcome ? <Level value={q.outcome} /> : "-"}</td>
              <td className="td"><button className="btn-secondary !px-2 !py-1 text-xs" onClick={() => open(q.id)}>{q.status === "PENDING" ? "Review" : "View"}</button></td></tr>
          ))}
        </tbody></table>
      </Card>
    </div>
  );
}
