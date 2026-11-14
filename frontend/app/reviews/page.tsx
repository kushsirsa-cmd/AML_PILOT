"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Pill, RiskBadge, Spinner } from "@/components/ui";

export default function Reviews() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api(`/reviews${status ? `?status=${status}` : ""}`).then(setRows).catch((e) => setErr(e.message)); }, [status]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Periodic & event-driven reviews</h1>
        <select className="input max-w-[180px]" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option><option>PENDING</option><option>ESCALATED</option><option>COMPLETED</option>
        </select>
      </div>
      <p className="text-sm text-slate-500">Trigger reviews from a customer&apos;s <b>Reviews</b> tab. Decide them there too.</p>
      <ErrorBox message={err} />
      <Card>
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Created</th><th className="th">Customer</th><th className="th">Type</th><th className="th">Trigger</th><th className="th">Recommendation</th><th className="th">Priority</th><th className="th">Status</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="td text-slate-500">{fmtDateTime(r.created_at)}</td>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${r.customer.id}`}>{r.customer.full_name}</Link> <RiskBadge rating={r.customer.risk_rating} /></td>
                  <td className="td">{r.review_type.replace("_", " ")}</td>
                  <td className="td">{r.trigger}</td>
                  <td className="td text-xs">{r.recommendation}</td>
                  <td className="td">{r.outcome?.priority ? <Pill tone={r.outcome.priority === "CRITICAL" ? "red" : r.outcome.priority === "HIGH" ? "amber" : "slate"}>{r.outcome.priority}</Pill> : "-"}</td>
                  <td className="td"><Pill tone={r.status === "PENDING" ? "amber" : r.status === "ESCALATED" ? "red" : "green"}>{r.status}</Pill></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="td text-slate-400" colSpan={7}>No reviews yet.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
