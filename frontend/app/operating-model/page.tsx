"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, Pill, Spinner, Stat } from "@/components/ui";
import { C, HBars } from "@/components/charts";

const REGS = ["FCA", "FATF", "MAS", "FINTRAC", "EBA"];
const TIER_COL = [C.s1, C.s2, C.s3];

export default function OperatingModel() {
  const [r, setR] = useState<Json>(null);
  const [adoption, setAdoption] = useState(70);
  const [optional, setOptional] = useState<string[]>([]);
  const [regs, setRegs] = useState<string[]>(REGS);
  const [fte, setFte] = useState<Record<string, number>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [tier, setTier] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => post("/operating-model/calculate", { adoption: adoption / 100, optional, regulators: regs, fte }).then(setR).catch((e) => setErr(e.message)), 150);
    return () => clearTimeout(timer.current);
  }, [adoption, optional, regs, fte]);

  if (!r) return err ? <ErrorBox message={err} /> : <Spinner label="Calculating operating model…" />;
  const o = r.overall;
  const teams: Json[] = r.teams.filter((t: Json) => !tier || t.tier === tier);
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">AML operating model</h1>
        <p className="mt-1 max-w-4xl text-sm text-slate-500">How much of each team&apos;s effort agentic AI can prepare or perform, and which activities must stay human-led to meet FCA, FATF, MAS, FINTRAC and EBA expectations. Change the assumptions — everything recalculates.</p></div>
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">{r.disclaimer}</div>
      <ErrorBox message={err} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Realised automation" value={o.realised_pct + "%"} sub={`technical potential ${o.potential_pct}%`} />
        <Stat label="Stays human-led" value={o.human_pct + "%"} sub="of weighted effort" />
        <Stat label="Capacity released" value={o.releasable_fte + " FTE"} sub={`of ${o.fte} FTE · capacity, not a headcount target`} />
        <Stat label="Teams modelled" value={o.teams} sub="25 teams + SoF/SoW line (+ optional)" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Assumptions">
          <label className="text-sm font-medium">Adoption of technical potential: <b>{adoption}%</b></label>
          <input type="range" min={30} max={100} value={adoption} onChange={(e) => setAdoption(+e.target.value)} className="mt-2 w-full" aria-label="Adoption" />
          <p className="mt-1 text-xs text-slate-400">What share of the potential is realistically achieved after change effort, controls and exceptions.</p>
          <div className="mt-4 text-sm font-medium">Optional modules</div>
          <div className="mt-1 space-y-1">{r.optional_available.map((m: Json) => <label key={m.code} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={optional.includes(m.code)} onChange={() => setOptional(toggle(optional, m.code))} />{m.name} <span className="text-xs text-slate-400">{m.fte} FTE</span></label>)}</div>
        </Card>
        <Card title="Regulators in scope">
          <div className="flex flex-wrap gap-2">{REGS.map((g) => <button key={g} onClick={() => setRegs(toggle(regs, g))} className={`rounded-lg px-3 py-1.5 text-sm font-medium ${regs.includes(g) ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500"}`}>{g}</button>)}</div>
          <p className="mt-3 text-xs text-slate-500">Filters which regulator expectations are shown against each human-led activity below. It does not change the automation estimates.</p>
        </Card>
        <Card title="Automation by tier"><HBars suffix="%" items={r.tiers.map((t: Json, i: number) => ({ label: t.label, value: t.realised_pct, color: TIER_COL[i], sub: `${t.teams} teams · ${t.releasable_fte} FTE` }))} max={100} />
          <div className="mt-4 text-xs text-slate-500">Sensitivity: {r.sensitivity.map((s: Json) => `${Math.round(s.adoption * 100)}% → ${s.realised_pct}%`).join(" · ")}</div></Card>
      </div>

      <Card title="Teams" right={<div className="flex gap-1">{[0, 1, 2, 3].map((n) => <button key={n} onClick={() => setTier(n)} className={`rounded-md px-2.5 py-1 text-xs font-medium ${tier === n ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>{n ? r.tiers[n - 1].label : "All"}</button>)}</div>}>
        <table>
          <thead><tr><th className="th">Team</th><th className="th">FTE (editable)</th><th className="th">Potential</th><th className="th">Realised</th><th className="th w-48">Human-led share</th><th className="th">Released FTE</th><th className="th">Must stay human-led</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {teams.map((t) => (
              <Fragment key={t.code}>
                <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(open === t.code ? null : t.code)}>
                  <td className="td font-medium">{t.name}{t.optional && <span className="ml-2"><Pill tone="amber">optional</Pill></span>}<div className="text-xs font-normal text-slate-400">{r.tiers[t.tier - 1].label}</div></td>
                  <td className="td" onClick={(e) => e.stopPropagation()}><input type="number" min={0} max={5000} className="input !w-20 !py-1 text-sm" value={fte[t.code] ?? t.fte} onChange={(e) => setFte({ ...fte, [t.code]: Math.max(0, +e.target.value || 0) })} aria-label={`FTE ${t.name}`} /></td>
                  <td className="td tabular-nums">{t.potential_pct}%</td>
                  <td className="td font-semibold tabular-nums">{t.realised_pct}%</td>
                  <td className="td"><div className="flex h-2 overflow-hidden rounded-full bg-slate-100"><div style={{ width: `${t.realised_pct}%`, background: TIER_COL[t.tier - 1] }} /></div><div className="mt-0.5 text-[11px] text-slate-400">{t.human_pct}% human</div></td>
                  <td className="td tabular-nums">{t.releasable_fte}</td>
                  <td className="td max-w-xs text-xs text-slate-600">{t.human_led.length ? t.human_led.join("; ") : "—"}</td>
                </tr>
                {open === t.code && (
                  <tr><td colSpan={7} className="bg-slate-50 px-6 py-3">
                    <table><thead><tr><th className="th">Activity</th><th className="th">Share of effort</th><th className="th">Automatable</th><th className="th">Constrained by</th><th className="th">Why it stays (partly) human</th></tr></thead>
                      <tbody className="divide-y divide-slate-100">{t.activities.map((a: Json) => (
                        <tr key={a.name}><td className="td text-sm">{a.name}{a.human_led && <span className="ml-2"><Pill tone="red">human-led</Pill></span>}</td><td className="td tabular-nums">{a.share}%</td><td className="td tabular-nums">{a.auto}%</td><td className="td text-xs">{a.constrained_by.join(", ") || "—"}</td><td className="td text-xs text-slate-600">{a.why || "—"}</td></tr>))}</tbody></table>
                  </td></tr>)}
              </Fragment>))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What each regulator expects to stay with people (indicative)">
          <div className="space-y-4">{Object.entries(r.human_only_by_regulator).map(([k, v]) => <div key={k}><div className="mb-1 text-sm font-semibold">{k}</div><ul className="space-y-1 text-sm text-slate-700">{(v as string[]).map((x, i) => <li key={i} className="flex gap-2"><span className="text-slate-300">•</span>{x}</li>)}</ul></div>)}</div>
        </Card>
        <Card title={`Human-led activities (${r.human_led_activities.length})`} right={<span className="text-xs text-slate-400">automation ≤ 25% of the activity</span>}>
          <div className="max-h-[34rem] space-y-2 overflow-y-auto pr-1">{r.human_led_activities.map((a: Json, i: number) => <div key={i} className="rounded-lg border border-slate-100 p-2.5 text-sm"><div className="flex justify-between gap-2"><b>{a.activity}</b><span className="text-xs text-slate-400">{a.auto}% auto</span></div><div className="text-xs text-slate-500">{a.team}{a.regs.length ? " · " + a.regs.join(", ") : ""}</div>{a.why && <div className="mt-0.5 text-xs text-slate-600">{a.why}</div>}</div>)}</div>
        </Card>
      </div>
    </div>
  );
}
