"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, Json, post } from "@/lib/api";
import { Card, ErrorBox, Pill, Spinner } from "@/components/ui";

export default function Screening() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [disp, setDisp] = useState("OPEN");
  const [err, setErr] = useState<string | null>(null);
  const [adhoc, setAdhoc] = useState({ name: "", date_of_birth: "", nationality: "" });
  const [res, setRes] = useState<Json>(null);

  useEffect(() => { api(`/screening/hits${disp ? `?disposition=${disp}` : ""}`).then(setRows).catch((e) => setErr(e.message)); }, [disp]);

  async function run(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      setRes(await post("/screening/adhoc", { name: adhoc.name, date_of_birth: adhoc.date_of_birth || null, nationality: adhoc.nationality || null }));
    } catch (ex) { setErr((ex as Error).message); }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Screening</h1>
      <ErrorBox message={err} />
      <Card title="Ad-hoc name screening (not saved to any customer)">
        <form onSubmit={run} className="flex flex-wrap items-end gap-3">
          <div><span className="mb-1 block text-xs text-slate-600">Name</span><input required className="input" value={adhoc.name} onChange={(e) => setAdhoc({ ...adhoc, name: e.target.value })} placeholder="Viktor Kozlov" /></div>
          <div><span className="mb-1 block text-xs text-slate-600">DOB</span><input type="date" className="input" value={adhoc.date_of_birth} onChange={(e) => setAdhoc({ ...adhoc, date_of_birth: e.target.value })} /></div>
          <div><span className="mb-1 block text-xs text-slate-600">Nationality</span><input className="input" value={adhoc.nationality} onChange={(e) => setAdhoc({ ...adhoc, nationality: e.target.value })} /></div>
          <button className="btn">Screen</button>
        </form>
        {res && (
          <div className="mt-4 space-y-2 text-sm">
            {Object.entries(res).map(([list, hits]) => (
              <div key={list}>
                <div className="font-medium">{list.replace("_", " ")} ({(hits as Json[]).length})</div>
                {(hits as Json[]).map((h) => (
                  <div key={h.entity_id} className="ml-4 text-slate-600">{h.matched_name} - <b>{h.confidence}%</b> ({h.strength}) - name {h.matched_on.name_similarity}%, DOB {h.matched_on.date_of_birth}, nationality {h.matched_on.nationality}</div>
                ))}
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Customer hits" right={<select className="input w-40" value={disp} onChange={(e) => setDisp(e.target.value)}><option value="">All</option><option>OPEN</option><option>CONFIRMED</option><option>FALSE_POSITIVE</option></select>}>
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Customer</th><th className="th">List</th><th className="th">Matched</th><th className="th">Confidence</th><th className="th">Disposition</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((h) => (
                <tr key={h.id}>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/customers/${h.customer.id}`}>{h.customer.full_name}</Link></td>
                  <td className="td">{h.list_type.replace("_", " ")}</td>
                  <td className="td">{h.matched_name}</td>
                  <td className="td"><Pill tone={h.confidence >= 90 ? "red" : h.confidence >= 75 ? "amber" : "slate"}>{Math.round(h.confidence)}%</Pill></td>
                  <td className="td"><Pill>{h.disposition}</Pill></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="td text-slate-400" colSpan={5}>No hits.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
