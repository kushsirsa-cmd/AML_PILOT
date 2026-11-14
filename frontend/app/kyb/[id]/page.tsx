"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, post, put, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Pill, Spinner } from "@/components/ui";
import { Output } from "@/components/Output";

function Tree({ n, depth = 0 }: { n: Json; depth?: number }) {
  return (
    <div className={depth ? "ml-6 border-l border-slate-200 pl-3" : ""}>
      <div className="my-1 flex flex-wrap items-center gap-2 text-sm">
        {n.pct !== null && n.pct !== undefined && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold">{n.pct}%</span>}
        <span className={n.type === "PERSON" ? "font-medium" : "font-semibold text-indigo-800"}>{n.type === "PERSON" ? "👤" : "🏢"} {n.name}</span>
        <span className="text-xs text-slate-400">{n.country || "unknown"}</span>
        {n.trust && <Pill tone="amber">trust</Pill>}
        {n.nominee && <Pill tone="amber">nominee</Pill>}
        {n.listed && <Pill tone="green">listed</Pill>}
        {n.type === "PERSON" && (n.verified ? <Pill tone="green">ID verified</Pill> : <Pill tone="red">unverified</Pill>)}
        {n.cycle && <Pill tone="red">circular</Pill>}
      </div>
      {(n.children || []).map((c: Json, i: number) => <Tree key={i} n={c} depth={depth + 1} />)}
    </div>
  );
}

export default function KybDetail() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(() => api(`/kyb/corporates/${id}`).then((r) => { setD(r); setEditor(JSON.stringify(r.structure, null, 2)); }).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<Json>) {
    setBusy(true); setErr(null);
    try { const r = await fn(); setD(r); setEditor(JSON.stringify(r.structure, null, 2)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading..." />;
  const c = d.corporate, r = d.review;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/kyb" className="text-xs text-indigo-700 hover:underline">← KYB reviews</Link>
          <h1 className="text-xl font-semibold">{c.legal_name} <span className="text-sm font-normal text-slate-400">{c.corp_ref}</span></h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-slate-600">{c.country_of_incorporation} · {c.industry} · <Level value={c.status} /> <Level value={c.risk_rating} /> {r && <Level value={r.ubo_status} />}</div>
        </div>
        <button className="btn" disabled={busy} onClick={() => act(() => post(`/kyb/corporates/${id}/review`))}>{busy ? "Working..." : "Re-run KYB review"}</button>
      </div>
      <ErrorBox message={err} />
      {!r ? <Card>No review has been run yet.</Card> : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Recommendation" className="lg:col-span-2">
              <div className="mb-2 flex items-center gap-2"><Pill tone={r.recommendation.startsWith("REJECT") ? "red" : r.recommendation.startsWith("APPROVE") ? "green" : "amber"}>{r.recommendation.replace(/_/g, " ")}</Pill><span className="text-xs text-slate-400">engine: {r.engine} · score {r.risk_score}</span></div>
              <p className="whitespace-pre-wrap text-sm">{r.narrative}</p>
              {r.overrides?.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-red-700">{r.overrides.map((o: string) => <li key={o}>{o}</li>)}</ul>}
              <h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Information requests</h3>
              <ul className="list-disc pl-5 text-sm">{r.information_requests.map((x: string, i: number) => <li key={i}>{x}</li>)}{r.information_requests.length === 0 && <li className="text-slate-400">None</li>}</ul>
            </Card>
            <Card title="Risk components">
              <table className="w-full text-sm"><tbody>
                {Object.entries(r.components).map(([k, v]: [string, Json]) => (
                  <tr key={k} className="border-b border-slate-100" title={v.reason}><td className="py-1.5">{k.replace(/_/g, " ")}</td><td className="py-1.5 text-right font-semibold">{v.points}</td></tr>
                ))}
              </tbody></table>
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Ownership structure" right={<span className="text-xs text-slate-400">layers {r.structure.metrics.layers}</span>}>
              <Tree n={r.ownership_tree} />
              <div className="mt-3 flex flex-wrap gap-1">{r.structure.red_flags.map((f: Json) => <Pill key={f.code || f} tone="red">{(f.code || f).replace(/_/g, " ")}</Pill>)}</div>
              <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">{r.structure.red_flags.filter((f: Json) => f.detail).map((f: Json) => <li key={f.code}>{f.detail}</li>)}</ul>
            </Card>
            <Card title={`Beneficial owners (≥25% or control) · verified ${r.ubo_verified_ownership_pct}%`}>
              <table className="w-full text-sm">
                <thead><tr><th className="th">Name</th><th className="th">Effective</th><th className="th">Status</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {r.ubo_verification.map((u: Json) => (
                    <tr key={u.key}><td className="td"><div className="font-medium">{u.name}</div><div className="text-xs text-slate-400">{u.paths?.[0]}</div></td><td className="td">{u.effective_pct}%</td><td className="td"><Level value={u.status} /></td></tr>
                  ))}
                  {r.ubo_verification.length === 0 && <tr><td className="td text-slate-400" colSpan={3}>No UBO identified.</td></tr>}
                </tbody>
              </table>
              {r.fallback_senior_managing_officials?.length > 0 && <p className="mt-2 text-xs text-slate-500">Fallback senior managing officials: {r.fallback_senior_managing_officials.map((o: Json) => o.name).join(", ")}</p>}
              {r.screening_hits.length > 0 && <div className="mt-3"><h3 className="text-xs font-semibold uppercase text-slate-500">Screening hits</h3><Output data={r.screening_hits} /></div>}
            </Card>
          </div>
        </>
      )}
      <Card title="Edit ownership structure (JSON)" right={<button className="btn" disabled={busy} onClick={() => act(() => put(`/kyb/corporates/${id}/structure`, JSON.parse(editor)))}>Save &amp; re-run</button>}>
        <textarea className="input h-64 font-mono text-xs" value={editor} onChange={(e) => setEditor(e.target.value)} />
        <p className="mt-1 text-xs text-slate-400">Tip: set <code>id_verified: true</code> on a person to record UBO verification. Try changing percentages to see the effective ownership recalculate.</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Decision">
          <input className="input mb-2" placeholder="Decision rationale" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            {["APPROVE", "REQUEST_INFO", "ESCALATE", "REJECT"].map((x) => (
              <button key={x} className={x === "REJECT" ? "btn-danger" : "btn-secondary"} disabled={busy || note.length < 3} onClick={() => act(() => post(`/kyb/corporates/${id}/decision`, { decision: x, note }))}>{x.replace("_", " ")}</button>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-400">Approval is blocked while UBOs are unverified or the entity is PROHIBITED.</p>
        </Card>
        <Card title="Linked wallets & alerts">
          {d.wallets.map((w: Json) => <div key={w.id} className="text-sm"><Link className="text-indigo-700 hover:underline" href={`/crypto/${w.id}`}>{w.address.slice(0, 14)}…</Link> <Level value={w.risk_level} /></div>)}
          {d.alerts.map((a: Json) => <div key={a.id} className="mt-1 text-sm"><Level value={a.severity} /> {a.title} <Level value={a.status} /></div>)}
          {d.wallets.length + d.alerts.length === 0 && <span className="text-sm text-slate-400">None</span>}
        </Card>
      </div>
    </div>
  );
}
