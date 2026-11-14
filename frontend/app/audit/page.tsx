"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Pill, Spinner } from "@/components/ui";

const ACTIONS = ["", "CUSTOMER_CREATED", "AGENT_RUN", "RISK_RATING_ASSIGNED", "RISK_RATING_CHANGED", "CASE_DECISION", "REVIEW_DECISION",
  "SCREENING_HIT_DISPOSITION", "EVENT_RECEIVED", "EVENT_REVIEW_COMPLETED", "PERIODIC_REVIEW_COMPLETED", "DOCUMENT_ADDED", "CUSTOMER_UPDATED"];

export default function AuditPage() {
  const [data, setData] = useState<Json>(null);
  const [actorType, setActorType] = useState("");
  const [action, setAction] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ limit: "300" });
    if (actorType) p.set("actor_type", actorType);
    if (action) p.set("action", action);
    api(`/audit?${p}`).then(setData).catch((e) => setErr(e.message));
  }, [actorType, action]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Audit log</h1>
      <ErrorBox message={err} />
      <Card>
        <div className="mb-4 flex gap-3">
          <select className="input max-w-[160px]" value={actorType} onChange={(e) => setActorType(e.target.value)}>
            <option value="">All actors</option><option>USER</option><option>AI</option><option>SYSTEM</option>
          </select>
          <select className="input max-w-[260px]" value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.map((a) => <option key={a} value={a}>{a || "All actions"}</option>)}
          </select>
          {data && <span className="self-center text-sm text-slate-500">{data.total} entries</span>}
        </div>
        {!data ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Time</th><th className="th">Type</th><th className="th">Actor</th><th className="th">Action</th><th className="th">Customer</th><th className="th">Details</th></tr></thead>
            <tbody className="divide-y divide-slate-100 align-top">
              {data.items.map((a: Json) => (
                <tr key={a.id}>
                  <td className="td whitespace-nowrap text-slate-500">{fmtDateTime(a.ts)}</td>
                  <td className="td"><Pill tone={a.actor_type === "AI" ? "indigo" : a.actor_type === "USER" ? "green" : "slate"}>{a.actor_type}</Pill></td>
                  <td className="td">{a.actor}</td>
                  <td className="td font-medium">{a.action}</td>
                  <td className="td">{a.customer_id ? <Link className="text-indigo-700 hover:underline" href={`/customers/${a.customer_id}`}>#{a.customer_id}</Link> : "-"}</td>
                  <td className="td"><details><summary className="cursor-pointer text-xs text-slate-500">view</summary><pre className="mt-1 max-w-md overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(a.details, null, 2)}</pre></details></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
