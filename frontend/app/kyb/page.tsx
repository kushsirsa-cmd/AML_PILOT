"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Spinner, fmtDate } from "@/components/ui";

const SAMPLE = JSON.stringify(
  {
    nodes: [
      { key: "hold", name: "Example Holdings Ltd", node_type: "ENTITY", country: "Cyprus" },
      { key: "jd", name: "Jane Doe", node_type: "PERSON", country: "Ireland", dob: "1980-01-01", id_verified: true },
    ],
    edges: [
      { owner: "hold", owned: "ROOT", percentage: 100 },
      { owner: "jd", owned: "hold", percentage: 60 },
    ],
  },
  null,
  2,
);

export default function Kyb() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState<Json>({ legal_name: "", country_of_incorporation: "", industry: "", operating_countries: "", expected_activity: "", has_bearer_shares: false, nominee_directors: false });
  const [structure, setStructure] = useState(SAMPLE);

  const load = () => api("/kyb/corporates").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function create() {
    setBusy(true); setErr(null);
    try {
      const r = await post("/kyb/corporates", { ...f, structure: JSON.parse(structure) });
      window.location.href = `/kyb/${r.corporate.id}`;
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">KYB reviews &amp; UBO verification</h1>
        <button className="btn" onClick={() => setOpen(!open)}>{open ? "Close" : "New corporate"}</button>
      </div>
      <ErrorBox message={err} />
      {open && (
        <Card title="Onboard a corporate (runs the KYB review immediately)">
          <div className="grid gap-3 md:grid-cols-3">
            {[["legal_name", "Legal name"], ["country_of_incorporation", "Country of incorporation"], ["industry", "Industry"], ["operating_countries", "Operating countries"]].map(([k, l]) => (
              <label key={k} className="block"><span className="mb-1 block text-xs font-medium text-slate-600">{l}</span><input className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
            ))}
            <label className="block md:col-span-2"><span className="mb-1 block text-xs font-medium text-slate-600">Expected activity</span><input className="input" value={f.expected_activity} onChange={(e) => setF({ ...f, expected_activity: e.target.value })} /></label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.has_bearer_shares} onChange={(e) => setF({ ...f, has_bearer_shares: e.target.checked })} /> Bearer shares</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.nominee_directors} onChange={(e) => setF({ ...f, nominee_directors: e.target.checked })} /> Nominee directors</label>
          </div>
          <label className="mt-3 block"><span className="mb-1 block text-xs font-medium text-slate-600">Ownership structure (JSON: nodes + edges; use <code>ROOT</code> for the company itself)</span>
            <textarea className="input h-56 font-mono text-xs" value={structure} onChange={(e) => setStructure(e.target.value)} /></label>
          <div className="mt-3"><button className="btn" disabled={busy || !f.legal_name || !f.country_of_incorporation || !f.industry} onClick={create}>{busy ? "Reviewing..." : "Create & run KYB"}</button></div>
        </Card>
      )}
      <Card>
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Ref</th><th className="th">Company</th><th className="th">Incorporated</th><th className="th">Industry</th><th className="th">Status</th><th className="th">Rating</th><th className="th">Score</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((c) => (
                <tr key={c.id}>
                  <td className="td text-slate-500">{c.corp_ref}</td>
                  <td className="td"><Link className="font-medium text-indigo-700 hover:underline" href={`/kyb/${c.id}`}>{c.legal_name}</Link></td>
                  <td className="td">{c.country_of_incorporation} <span className="text-xs text-slate-400">{fmtDate(c.incorporation_date)}</span></td>
                  <td className="td">{c.industry}</td>
                  <td className="td"><Level value={c.status} /></td>
                  <td className="td"><Level value={c.risk_rating} /></td>
                  <td className="td">{c.risk_score ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
