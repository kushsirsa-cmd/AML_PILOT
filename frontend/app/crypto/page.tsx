"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Spinner, fmtDateTime } from "@/components/ui";

export default function Crypto() {
  const [rows, setRows] = useState<Json[] | null>(null);
  const [labels, setLabels] = useState<Json[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [addr, setAddr] = useState("");
  const [res, setRes] = useState<Json>(null);
  const load = () => api("/crypto/wallets").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); api("/crypto/labels").then(setLabels).catch(() => {}); }, []);

  async function adhoc(a: string) {
    setErr(null); setRes(null);
    try { setRes(await post("/crypto/screen", { address: a })); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Crypto wallet screening &amp; blockchain risk</h1>
      <p className="text-sm text-slate-500">Attribution and transactions come from a <b>simulated</b> chain (Chainalysis/TRM-style); replace <code>modules/chain.py</code>&apos;s data source with a real provider API for production.</p>
      <ErrorBox message={err} />
      <Card title="Registered wallets">
        {!rows ? <Spinner label="Loading..." /> : (
          <table className="w-full">
            <thead><tr><th className="th">Address</th><th className="th">Owner</th><th className="th">Type</th><th className="th">Risk</th><th className="th">Score</th><th className="th">Screened</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((w) => (
                <tr key={w.id}>
                  <td className="td font-mono text-xs"><Link className="text-indigo-700 hover:underline" href={`/crypto/${w.id}`}>{w.address.slice(0, 10)}…{w.address.slice(-6)}</Link></td>
                  <td className="td">{w.owner ? <Link className="hover:underline" href={w.owner.type === "customer" ? `/customers/${w.owner.id}` : `/kyb/${w.owner.id}`}>{w.owner.name}</Link> : "-"}</td>
                  <td className="td text-xs">{w.self_hosted ? "Self-hosted" : `Hosted: ${w.hosted_by_vasp}`}</td>
                  <td className="td"><Level value={w.risk_level} /></td>
                  <td className="td">{w.risk_score ?? "-"}</td>
                  <td className="td text-slate-500">{fmtDateTime(w.last_screened_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Screen any address on the simulated chain">
        <div className="flex gap-2"><input className="input font-mono text-xs" placeholder="0x…" value={addr} onChange={(e) => setAddr(e.target.value)} /><button className="btn" disabled={addr.length < 10} onClick={() => adhoc(addr)}>Screen</button></div>
        <div className="mt-2 flex flex-wrap gap-1 text-xs">
          {labels.map((l) => <button key={l.address} className="rounded bg-slate-100 px-2 py-1 hover:bg-indigo-100" onClick={() => { setAddr(l.address); adhoc(l.address); }}>{l.category}: {l.entity}</button>)}
        </div>
        {res && (
          <div className="mt-3 text-sm">
            <div className="flex items-center gap-2"><Level value={res.risk_level} /> score {res.risk_score} {res.attribution?.entity && <span className="text-slate-500">· {res.attribution.category}: {res.attribution.entity}</span>}</div>
            <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{Object.values(res.score_components || {}).map((c: Json, i) => <li key={i}>{c.reason} ({c.points} pts)</li>)}</ul>
          </div>
        )}
      </Card>
    </div>
  );
}
