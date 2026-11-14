"use client";
import { useEffect, useState } from "react";
import { api, download, post, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Level } from "@/components/ui";
import { Output } from "@/components/Output";

export default function Reports() {
  const [types, setTypes] = useState<Record<string, string>>({});
  const [rows, setRows] = useState<Json[]>([]);
  const [sel, setSel] = useState("SAR_STATISTICS");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [detail, setDetail] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api("/reports").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); api("/reports/types").then(setTypes).catch(() => {}); }, []);
  const run = async (fn: () => Promise<Json>) => { setErr(null); try { await fn(); load(); } catch (e) { setErr((e as Error).message); } };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Regulatory reporting</h1>
      <p className="text-sm text-slate-500">Lifecycle: DRAFT → APPROVED (MLRO, different person from the generator) → SUBMITTED. Formats are illustrative, not official regulator templates.</p>
      <ErrorBox message={err} />
      <Card title="Generate a report">
        <div className="grid gap-3 md:grid-cols-4">
          <select className="input md:col-span-2" value={sel} onChange={(e) => setSel(e.target.value)}>{Object.entries(types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} title="Period start (default: 90 days ago)" />
          <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} title="Period end (default: today)" />
        </div>
        <button className="btn mt-3" onClick={() => run(async () => { const r = await post("/reports/generate", { report_type: sel, period_start: start || undefined, period_end: end || undefined }); setDetail(r); })}>Generate</button>
      </Card>
      <Card title="Reports">
        <table className="w-full"><thead><tr><th className="th">Created</th><th className="th">Report</th><th className="th">Period</th><th className="th">Rows</th><th className="th">By</th><th className="th">Status</th><th className="th"></th></tr></thead><tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id}><td className="td text-xs text-slate-500">{fmtDateTime(r.created_at)}</td><td className="td"><div className="font-medium">{r.title}</div><div className="text-xs text-slate-400">{r.report_type}</div></td>
              <td className="td text-xs">{r.period_start} → {r.period_end}</td><td className="td">{r.row_count}</td><td className="td text-xs">{r.generated_by}{r.approved_by && <div className="text-slate-400">approved: {r.approved_by}</div>}{r.submission_reference && <div className="text-slate-400">{r.submission_reference}</div>}</td>
              <td className="td"><Level value={r.status} /></td>
              <td className="td whitespace-nowrap">
                <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => run(async () => setDetail(await api(`/reports/${r.id}`)))}>View</button>
                <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => download(`/reports/${r.id}/csv`, `${r.report_type}.csv`).catch((e) => setErr(e.message))}>CSV</button>
                {r.status === "DRAFT" && <button className="btn !px-2 !py-1 text-xs" onClick={() => run(() => post(`/reports/${r.id}/approve`))}>Approve</button>}
                {r.status === "APPROVED" && <button className="btn !px-2 !py-1 text-xs" onClick={() => run(() => post(`/reports/${r.id}/submit`))}>Submit</button>}</td></tr>
          ))}
        </tbody></table>
      </Card>
      {detail && (
        <Card title={`${detail.title} · ${detail.period_start} → ${detail.period_end}`} right={<button className="btn-secondary" onClick={() => setDetail(null)}>Close</button>}>
          <Output data={detail.metrics} />
          {detail.rows?.length > 0 && (
            <div className="mt-4 max-h-96 overflow-auto"><table className="w-full text-xs"><thead><tr>{Object.keys(detail.rows[0]).map((k) => <th key={k} className="th">{k.replace(/_/g, " ")}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
              {detail.rows.map((row: Json, i: number) => <tr key={i}>{Object.values(row).map((v, j) => <td key={j} className="td">{String(v ?? "")}</td>)}</tr>)}
            </tbody></table></div>
          )}
          <p className="mt-2 text-xs text-slate-400">{detail.disclaimer}</p>
        </Card>
      )}
    </div>
  );
}
