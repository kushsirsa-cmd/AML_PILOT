"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Pill, RiskBadge, Spinner, Stat } from "@/components/ui";

const BAR: Record<string, string> = { LOW: "bg-emerald-500", MEDIUM: "bg-amber-400", HIGH: "bg-orange-500", PROHIBITED: "bg-red-700", UNRATED: "bg-slate-300" };

export default function Dashboard() {
  const [d, setD] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api("/dashboard").then(setD).catch((e) => setErr(e.message));
  }, []);

  if (err) return <ErrorBox message={`Cannot load dashboard: ${err}. Is the backend running on port 8000?`} />;
  if (!d) return <Spinner label="Loading dashboard..." />;

  const dist: Record<string, number> = d.risk_distribution;
  const max = Math.max(1, ...Object.values(dist));
  const highCount = (dist.HIGH || 0) + (dist.PROHIBITED || 0);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Operations overview</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Total customers" value={d.total_customers} href="/customers" />
        <Stat label="High-risk customers" value={highCount} sub={`${dist.PROHIBITED || 0} prohibited`} tone="border-orange-200" href="/customers" />
        <Stat label="Reviews pending" value={d.reviews_pending.count} sub={`${d.reviews_pending.periodic} periodic / ${d.reviews_pending.event_driven} event`} href="/reviews" />
        <Stat label="Screening matches" value={d.screening_matches.open_total} sub={`open, >=75% (S ${d.screening_matches.by_list.SANCTIONS} / P ${d.screening_matches.by_list.PEP} / AM ${d.screening_matches.by_list.ADVERSE_MEDIA})`} href="/screening" />
        <Stat label="Reviews overdue" value={d.reviews_overdue} sub="next review date passed" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Risk distribution">
          <div className="space-y-3">
            {Object.entries(dist).map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-xs"><span className="font-medium">{k}</span><span>{v}</span></div>
                <div className="h-3 rounded bg-slate-100"><div className={`h-3 rounded ${BAR[k]}`} style={{ width: `${(v / max) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="High-risk customers" className="lg:col-span-2">
          <table className="w-full">
            <thead><tr><th className="th">Customer</th><th className="th">Country</th><th className="th">Score</th><th className="th">Rating</th><th className="th">Status</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {d.high_risk_customers.map((c: Json) => (
                <tr key={c.id}>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${c.id}`}>{c.full_name}</Link><div className="text-xs text-slate-400">{c.customer_ref}</div></td>
                  <td className="td">{c.country_of_residence}</td>
                  <td className="td">{c.risk_score}</td>
                  <td className="td"><RiskBadge rating={c.risk_rating} /></td>
                  <td className="td"><Pill>{c.status}</Pill></td>
                </tr>
              ))}
              {d.high_risk_customers.length === 0 && <tr><td className="td text-slate-400" colSpan={5}>None</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Pending reviews" right={<Link href="/reviews" className="text-xs text-indigo-600">View all</Link>}>
          <ul className="space-y-2 text-sm">
            {d.reviews_pending.items.map((r: Json) => (
              <li key={r.id} className="flex items-start justify-between gap-2">
                <div>
                  <Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${r.customer_id}`}>{r.customer_name}</Link>
                  <div className="text-xs text-slate-500">{r.review_type.replace("_", " ")} - {r.trigger}</div>
                  <div className="text-xs text-slate-400">{r.recommendation}</div>
                </div>
                {r.priority && <Pill tone={r.priority === "CRITICAL" ? "red" : r.priority === "HIGH" ? "amber" : "slate"}>{r.priority}</Pill>}
              </li>
            ))}
            {d.reviews_pending.items.length === 0 && <li className="text-slate-400">No pending reviews</li>}
          </ul>
        </Card>

        <Card title="Open screening matches" right={<Link href="/screening" className="text-xs text-indigo-600">View all</Link>}>
          <ul className="space-y-2 text-sm">
            {d.screening_matches.items.map((h: Json) => (
              <li key={h.id} className="flex items-start justify-between gap-2">
                <div>
                  <Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${h.customer_id}`}>{h.customer_name}</Link>
                  <div className="text-xs text-slate-500">{h.list_type.replace("_", " ")}: {h.matched_name}</div>
                </div>
                <Pill tone={h.confidence >= 90 ? "red" : "amber"}>{Math.round(h.confidence)}%</Pill>
              </li>
            ))}
            {d.screening_matches.items.length === 0 && <li className="text-slate-400">No open matches</li>}
          </ul>
        </Card>

        <Card title="Recent activity" right={<Link href="/audit" className="text-xs text-indigo-600">Audit log</Link>}>
          <ul className="space-y-2 text-sm">
            {d.recent_audit.map((a: Json) => (
              <li key={a.id}>
                <div className="flex items-center gap-2"><Pill tone={a.actor_type === "AI" ? "indigo" : a.actor_type === "USER" ? "green" : "slate"}>{a.actor_type}</Pill><span className="font-medium">{a.action}</span></div>
                <div className="text-xs text-slate-400">{a.actor} - {fmtDateTime(a.ts)}</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
