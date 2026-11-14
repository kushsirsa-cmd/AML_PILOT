"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDate, Pill, RiskBadge, Spinner } from "@/components/ui";

export default function Customers() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [q, setQ] = useState("");
  const [risk, setRisk] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams();
      if (q) p.set("q", q);
      if (risk) p.set("risk", risk);
      api(`/customers?${p}`).then(setRows).catch((e) => setErr(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q, risk]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Customers</h1>
        <Link href="/customers/new" className="btn">+ New customer</Link>
      </div>
      <Card>
        <div className="mb-4 flex gap-3">
          <input className="input max-w-xs" placeholder="Search name or reference..." value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input max-w-[180px]" value={risk} onChange={(e) => setRisk(e.target.value)}>
            <option value="">All ratings</option>
            {["LOW", "MEDIUM", "HIGH", "PROHIBITED", "UNRATED"].map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
        <ErrorBox message={err} />
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Ref</th><th className="th">Name</th><th className="th">Nationality / Residence</th><th className="th">Occupation</th><th className="th">Rating</th><th className="th">Status</th><th className="th">Next review</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="td text-slate-500">{c.customer_ref}</td>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${c.id}`}>{c.full_name}</Link></td>
                  <td className="td">{c.nationality} / {c.country_of_residence}</td>
                  <td className="td">{c.occupation}</td>
                  <td className="td"><div className="flex items-center gap-2"><RiskBadge rating={c.risk_rating} />{c.risk_score != null && <span className="text-xs text-slate-400">{c.risk_score}</span>}</div></td>
                  <td className="td"><Pill>{c.status}</Pill></td>
                  <td className="td text-slate-500">{fmtDate(c.next_review_due)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="td text-slate-400" colSpan={7}>No customers match.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
