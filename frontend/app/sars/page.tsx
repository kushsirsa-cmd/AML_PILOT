"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, fmtDateTime, Level, Spinner } from "@/components/ui";

export default function Sars() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [customers, setCustomers] = useState<Json[]>([]);
  const [corps, setCorps] = useState<Json[]>([]);
  const [sel, setSel] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api("/sars").then(setRows).catch((e) => setErr(e.message));
    api("/customers").then(setCustomers).catch(() => {});
    api("/kyb/corporates").then(setCorps).catch(() => {});
  }, []);
  async function gen() {
    const [t, id] = sel.split(":");
    try { const s = await post("/sars/generate", { subject_type: t, subject_id: +id }); window.location.href = `/sars/${s.id}`; } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Suspicious Activity Reports</h1>
      <ErrorBox message={err} />
      <Card title="Generate a SAR draft from case evidence">
        <div className="flex gap-2">
          <select className="input" value={sel} onChange={(e) => setSel(e.target.value)}>
            <option value="">Select subject…</option>
            <optgroup label="Customers">{customers.map((c) => <option key={c.id} value={`customer:${c.id}`}>{c.full_name} ({c.risk_rating})</option>)}</optgroup>
            <optgroup label="Corporates">{corps.map((c) => <option key={c.id} value={`corporate:${c.id}`}>{c.legal_name} ({c.risk_rating})</option>)}</optgroup>
          </select>
          <button className="btn" disabled={!sel} onClick={gen}>Generate draft</button>
        </div>
      </Card>
      <Card>
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Reference</th><th className="th">Subject</th><th className="th">Typologies</th><th className="th">Amount</th><th className="th">Prepared</th><th className="th">Status</th><th className="th">Filing ref</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/sars/${s.id}`}>{s.reference}</Link></td>
                  <td className="td">{s.subject_name}</td><td className="td text-xs">{s.typologies.join(", ")}</td><td className="td">{eur(s.total_amount_eur)}</td>
                  <td className="td text-xs">{s.prepared_by}<div className="text-slate-400">{fmtDateTime(s.created_at)}</div></td><td className="td"><Level value={s.status} /></td><td className="td text-xs">{s.filing_reference || "-"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="td text-slate-400" colSpan={7}>No SARs yet.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
