"use client";
import { useEffect, useState } from "react";
import { api, patch, post, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Spinner } from "@/components/ui";

const ROLES = ["ANALYST", "SENIOR_ANALYST", "MLRO", "COMPLIANCE_MANAGER", "ADMIN"];

export default function Admin() {
  const [users, setUsers] = useState<Json[] | null>(null);
  const [sys, setSys] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => { api("/admin/users").then(setUsers).catch((e) => setErr(e.message)); api("/admin/system").then(setSys).catch(() => {}); };
  useEffect(load, []);
  const update = async (id: number, body: Json) => { setErr(null); try { await patch(`/admin/users/${id}`, body); load(); } catch (e) { setErr((e as Error).message); } };
  async function reset() {
    if (!window.confirm("Wipe ALL data and rebuild the demo dataset? This takes a few seconds.")) return;
    setBusy(true); setErr(null); setMsg(null);
    try { const r = await post("/admin/demo/reset"); setMsg(`Demo data rebuilt: ${r.customers} customers, ${r.corporates} businesses, ${r.transactions} transactions, ${r.alerts} alerts.`); load(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  if (!users) return err ? <ErrorBox message={err} /> : <Spinner label="Loading…" />;
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Administration</h1>
      <ErrorBox message={err} />
      {msg && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{msg}</div>}
      <Card title="Users & roles">
        <table>
          <thead><tr><th className="th">Name</th><th className="th">Username</th><th className="th">Role</th><th className="th">Status</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="td font-medium">{u.full_name}<div className="text-xs font-normal text-slate-400">{u.email}</div></td><td className="td font-mono text-xs">{u.username}</td>
                <td className="td"><select className="input !w-64 !py-1.5" value={u.role} onChange={(e) => update(u.id, { role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></td>
                <td className="td"><button className="btn-secondary !px-2.5 !py-1 text-xs" onClick={() => update(u.id, { active: !u.active })}>{u.active ? <Level value="LOW" /> : <Level value="REJECT" />}<span className="ml-2">{u.active ? "Active – deactivate" : "Inactive – activate"}</span></button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-400">Role changes take effect immediately: permissions are enforced by the API from the users table, never from the browser.</p>
      </Card>
      {sys && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Demo data" right={<button className="btn-danger" disabled={busy} onClick={reset}>{busy ? "Rebuilding…" : "Reset demo data"}</button>}>
            <div className="grid grid-cols-3 gap-3 text-center">{Object.entries(sys.counts).map(([k, v]) => <div key={k} className="rounded-lg bg-slate-50 p-3"><div className="text-xl font-semibold tabular-nums">{v as number}</div><div className="text-[11px] uppercase tracking-wide text-slate-500">{k.replace("_", " ")}</div></div>)}</div>
            <p className="mt-3 text-xs text-slate-400">Reset restores the original deterministic dataset — use it between stakeholder demos.</p>
          </Card>
          <Card title="System">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">AI case summaries</dt><dd>{sys.llm_active ? `Claude (${sys.model})` : "Rules engine (set ANTHROPIC_API_KEY for Claude)"}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Dataset size</dt><dd>{sys.seed_size}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Open demo access (no token needed)</dt><dd>{sys.demo_open_access ? "on" : "off"}</dd></div>
            </dl>
          </Card>
        </div>
      )}
    </div>
  );
}
