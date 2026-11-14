"use client";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, fmtDateTime, Level } from "@/components/ui";

const EMPTY = { direction: "OUT", amount_eur: 5000, asset: "USDT", counterparty_vasp: "NordEx", self_hosted: false, ownership_proof: false,
  originator: { name: "", account: "", address: "", dob: "" }, beneficiary: { name: "", account: "" } };

export default function TravelRule() {
  const [f, setF] = useState<Json>(EMPTY);
  const [vasps, setVasps] = useState<Json>(null);
  const [rows, setRows] = useState<Json[]>([]);
  const [res, setRes] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = () => api("/travel-rule/transfers").then(setRows).catch((e) => setErr(e.message));
  useEffect(() => { load(); api("/travel-rule/vasps").then(setVasps).catch(() => {}); }, []);
  const set = (path: string, v: unknown) => { const [a, b] = path.split("."); setF(b ? { ...f, [a]: { ...f[a], [b]: v } } : { ...f, [a]: v }); };
  const clean = () => ({ ...f, amount_eur: +f.amount_eur, counterparty_vasp: f.self_hosted ? null : f.counterparty_vasp || null });

  async function run(store: boolean) {
    setErr(null);
    try { const r = await post(store ? "/travel-rule/check" : "/travel-rule/evaluate", clean()); setRes(r); if (store) load(); } catch (e) { setErr((e as Error).message); }
  }
  async function resolve(id: number, action: string) {
    const note = window.prompt(`Note for ${action} (min 3 chars)`) || "";
    if (note.length < 3) return;
    try { await post(`/travel-rule/transfers/${id}/resolve`, { action, note, ownership_proof: action === "RELEASE" ? window.confirm("Is wallet ownership proof now on file?") : undefined }); load(); } catch (e) { setErr((e as Error).message); }
  }
  const inp = (label: string, path: string, type = "text") => (
    <label className="block"><span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      <input className="input" type={type} value={path.includes(".") ? f[path.split(".")[0]][path.split(".")[1]] : f[path]} onChange={(e) => set(path, e.target.value)} /></label>
  );
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Travel Rule checks (FATF R.16 / EU TFR)</h1>
      <ErrorBox message={err} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Check a transfer">
          <div className="grid grid-cols-2 gap-3">
            <label className="block"><span className="mb-1 block text-xs font-medium text-slate-600">Direction</span><select className="input" value={f.direction} onChange={(e) => set("direction", e.target.value)}><option>OUT</option><option>IN</option></select></label>
            {inp("Amount (EUR)", "amount_eur", "number")}
            <label className="block"><span className="mb-1 block text-xs font-medium text-slate-600">Counterparty VASP</span>
              <select className="input" disabled={f.self_hosted} value={f.counterparty_vasp} onChange={(e) => set("counterparty_vasp", e.target.value)}><option value="">(none)</option>{vasps?.vasps?.map((v: Json) => <option key={v.name}>{v.name}</option>)}</select></label>
            <div className="flex flex-col justify-end gap-1 text-sm"><label><input type="checkbox" checked={f.self_hosted} onChange={(e) => set("self_hosted", e.target.checked)} /> Self-hosted (unhosted) wallet</label><label><input type="checkbox" checked={f.ownership_proof} onChange={(e) => set("ownership_proof", e.target.checked)} /> Ownership proof on file</label></div>
            {inp("Originator name", "originator.name")}{inp("Originator wallet", "originator.account")}{inp("Originator address", "originator.address")}{inp("Originator DOB", "originator.dob")}
            {inp("Beneficiary name", "beneficiary.name")}{inp("Beneficiary wallet", "beneficiary.account")}
          </div>
          <div className="mt-3 flex gap-2"><button className="btn-secondary" onClick={() => run(false)}>Dry run</button><button className="btn" onClick={() => run(true)}>Check &amp; record</button></div>
        </Card>
        <Card title={res ? <span className="flex items-center gap-2">Result <Level value={res.status} /></span> : "Result"}>
          {!res ? <span className="text-sm text-slate-400">Run a check to see the rule-by-rule outcome. Threshold: {eur(vasps?.threshold_eur)}.</span> : (
            <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
              {res.checks.map((c: Json, i: number) => (
                <tr key={i}><td className="py-1.5"><Level value={c.result === "PASS" ? "PASS" : c.result === "FAIL" ? (c.severity === "CRITICAL" ? "REJECT" : "HIGH") : c.result === "WARN" ? "MEDIUM" : "DRAFT"} /></td><td className="py-1.5 pl-2"><div className="text-xs font-semibold">{c.check.replace(/_/g, " ")}</div><div className="text-xs text-slate-500">{c.detail}</div></td></tr>
              ))}
            </tbody></table>
          )}
        </Card>
      </div>
      <Card title="Recorded transfers">
        <table className="w-full">
          <thead><tr><th className="th">When</th><th className="th">Dir</th><th className="th">Amount</th><th className="th">VASP</th><th className="th">Status</th><th className="th">Reasons</th><th className="th"></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((t) => (
              <tr key={t.id}>
                <td className="td text-xs text-slate-500">{fmtDateTime(t.created_at)}</td><td className="td">{t.direction}</td><td className="td">{eur(t.amount_eur)} <span className="text-xs text-slate-400">{t.asset}</span></td>
                <td className="td text-xs">{t.self_hosted ? "self-hosted" : t.counterparty_vasp || "-"}</td><td className="td"><Level value={t.status} /></td>
                <td className="td text-xs text-slate-600">{open === t.id ? t.reasons.join(" | ") : (t.reasons[0] || "-")} {t.reasons.length > 1 && <button className="text-indigo-700" onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? "less" : `+${t.reasons.length - 1}`}</button>}</td>
                <td className="td whitespace-nowrap">{["HOLD_REQUEST_INFO", "REJECT", "ACCEPT_WITH_REVIEW"].includes(t.status) && <>
                  <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => resolve(t.id, "RELEASE")}>Release</button>
                  <button className="btn-secondary mr-1 !px-2 !py-1 text-xs" onClick={() => resolve(t.id, "RETURN_FUNDS")}>Return</button>
                  <button className="btn-danger !px-2 !py-1 text-xs" onClick={() => resolve(t.id, "REPORT_TO_MLRO")}>MLRO</button></>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
