"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, download, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, fmtDate, fmtDateTime, Level, Pill, Spinner } from "@/components/ui";
import { Meter, NetGraph, PathMap, Prio, QUEUE_LABEL } from "@/components/fiu";

const TABS = ["Workbook", "RBI", "FIU", "Typologies", "Network", "Crypto", "SAR / STR", "Notes"];
const FLOW = ["TRIAGE", "FIU", "ESCALATION", "SAR", "MLRO", "CLOSED"];

const Bullets = ({ items }: { items: string[] }) => <ul className="space-y-1 text-sm text-slate-700">{items.filter(Boolean).map((x, i) => <li key={i} className="flex gap-2"><span className="text-slate-300">•</span><span>{x}</span></li>)}</ul>;

export default function CaseDetail() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Json>(null);
  const [tab, setTab] = useState("Workbook");
  const [text, setText] = useState("");
  const [disp, setDisp] = useState("");
  const [fmt, setFmt] = useState("UK_SAR");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api(`/investigations/${id}`).then(setD).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function act(action: string, extra: Json = {}) {
    setErr(null); setBusy(true);
    try { await post(`/investigations/${id}/actions`, { action, text: text || undefined, ...extra }); setText(""); await load(); } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }
  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading case…" />;
  const s = d.summary, ag = d.agents, wb = ag.workbook, rbi = ag.rbi, fiu = ag.fiu, can = d.can;
  const closed = s.queue === "CLOSED";
  const idx = FLOW.indexOf(s.queue);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-400"><Link href="/cases" className="hover:underline">Case queues</Link> / {s.reference}</div>
          <h1 className="text-2xl font-semibold">{s.subject} <span className="text-base font-normal text-slate-400">{s.subject_ref}</span></h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">{s.title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2"><Prio v={s.priority} /><Level value={s.rating} /><Pill tone="indigo">{QUEUE_LABEL[s.queue]}</Pill>
          <Link href={s.entity_type === "customer" ? `/customers/${s.entity_id}` : `/kyb`} className="btn-secondary !py-1 text-xs">Customer file</Link></div>
      </div>
      <ErrorBox message={err} />

      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-slate-200/80 bg-white p-3 shadow-card" aria-label="Case progress">
        {FLOW.map((q, i) => (
          <div key={q} className="flex items-center gap-1">
            <div className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${i < idx || closed ? "bg-emerald-100 text-emerald-800" : i === idx ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"}`}>{QUEUE_LABEL[q]}</div>{i < FLOW.length - 1 && <span className="text-slate-300">›</span>}
          </div>))}
        <div className="ml-auto whitespace-nowrap pl-4 text-xs text-slate-500">Step {s.step}/9 · risk <b>{s.risk_score ?? "–"}</b> · confidence <b>{s.confidence ?? "–"}</b>/100</div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">{TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-brand-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>{t}</button>)}</div>

          {tab === "Workbook" && (
            <div className="space-y-3">
              <Card title="Disposition recommended by the AML Investigations agent">
                <div className="flex flex-wrap items-center gap-3"><Level value={wb.disposition.recommended} /><span className="text-sm text-slate-700">{wb.disposition.rationale}</span></div>
                <p className="mt-2 text-xs text-slate-400">Decision support only — a person chooses the disposition (step 9).</p>
              </Card>
              {wb.steps.map((st: Json) => (
                <Card key={st.n} title={<span className="flex items-center gap-2"><span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${st.status === "DONE" ? "bg-emerald-100 text-emerald-800" : st.status === "CURRENT" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"}`}>{st.n}</span>{st.title}</span>} right={<Pill tone={st.status === "DONE" ? "green" : st.status === "CURRENT" ? "indigo" : "slate"}>{st.status.toLowerCase()}</Pill>}>
                  <p className="mb-2 text-sm font-medium text-slate-800">{st.summary}</p><Bullets items={st.findings.slice(0, 8)} />
                </Card>))}
              <Card title="Case notes (draft)"><pre className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">{wb.case_notes}</pre></Card>
            </div>)}

          {tab === "RBI" && (
            <div className="space-y-3">
              <Card title="Risk narrative" right={<span className="text-xs text-slate-400">engine: {rbi.engine}</span>}><pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{rbi.narrative}</pre></Card>
              <div className="grid gap-3 md:grid-cols-2">
                <Card title={`Case confidence ${rbi.confidence.score}/100`}><Bullets items={Object.entries(rbi.confidence.components).map(([k, v]) => `${k.replace(/_/g, " ")}: ${(v as number) > 0 ? "+" : ""}${v}`)} /></Card>
                <Card title={`Priority ${rbi.priority.level} (${rbi.priority.score})`}><Bullets items={Object.entries(rbi.priority.components).map(([k, v]) => `${k}: ${v}`)} /></Card>
              </div>
              <Card title="Hypotheses and next steps">
                <div className="space-y-3">{rbi.hypotheses.map((h: Json) => (
                  <div key={h.id} className="rounded-lg border border-slate-100 p-3"><div className="flex items-center justify-between"><b className="text-sm">{h.title}</b><span className="flex items-center gap-2"><Level value={h.likelihood} /><Meter value={h.score} /></span></div>
                    <p className="mt-1 text-xs text-slate-500">{h.statement}</p>{h.supporting?.length > 0 && <div className="mt-2"><Bullets items={h.supporting.slice(0, 4)} /></div>}
                    {h.tests?.length > 0 && <div className="mt-2 text-xs text-slate-500"><b>To test:</b> {h.tests.join(" · ")}</div>}</div>))}</div>
              </Card>
              <div className="grid gap-3 md:grid-cols-2">
                <Card title="Risk factors"><Bullets items={rbi.risk_factors.map((f: Json) => `${f.factor.replace(/_/g, " ")} (+${f.points}): ${f.reason}`)} /></Card>
                <Card title="Mitigating facts"><Bullets items={rbi.mitigating_facts.length ? rbi.mitigating_facts : ["None identified"]} /></Card>
              </div>
              <Card title="Behavioural profile"><div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">{[["90-day inflow", eur(rbi.behaviour.inflow_90d)], ["90-day outflow", eur(rbi.behaviour.outflow_90d)], ["Cash share", rbi.behaviour.cash_share_pct + "%"], ["High-risk geography", rbi.behaviour.high_risk_geography_pct + "%"]].map(([k, v]) => <div key={k as string} className="rounded-lg bg-slate-50 p-2.5"><div className="text-xs text-slate-500">{k}</div><div className="font-semibold">{v}</div></div>)}</div></Card>
              <Card title="Timeline"><div className="space-y-2">{rbi.timeline.slice(-14).map((e: Json, i: number) => <div key={i} className="flex gap-3 text-sm"><span className="w-28 shrink-0 text-xs text-slate-400">{fmtDate(e.ts)}</span><Pill tone={e.severity === "HIGH" || e.severity === "CRITICAL" ? "red" : e.severity === "MEDIUM" ? "amber" : "slate"}>{e.kind}</Pill><span><b>{e.title}</b> <span className="text-slate-500">{e.detail}</span></span></div>)}</div></Card>
            </div>)}

          {tab === "FIU" && (
            <div className="space-y-3">
              <Card title={`Suspicion assessment — ${fiu.suspicion.level.replace(/_/g, " ")} (${fiu.suspicion.score})`}>
                <div className="grid gap-4 md:grid-cols-2"><div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Factors for</div><Bullets items={fiu.suspicion.factors_for} /></div><div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Factors against</div><Bullets items={fiu.suspicion.factors_against.length ? fiu.suspicion.factors_against : ["None identified"]} /></div></div>
                <p className="mt-3 text-xs text-slate-400">{fiu.suspicion.legal_note}</p>
              </Card>
              <Card title="SAR recommendation" right={<Pill tone={fiu.sar_recommendation.recommendation === "FILE" ? "red" : "slate"}>{fiu.sar_recommendation.recommendation.replace(/_/g, " ")}</Pill>}>
                <p className="text-sm">{fiu.sar_recommendation.rationale}</p><p className="mt-2 text-xs text-slate-500">{fiu.sar_recommendation.urgency} · {fiu.sar_recommendation.consent_note}</p><p className="mt-1 text-xs font-medium text-red-700">{fiu.sar_recommendation.tipping_off_warning}</p>
              </Card>
              {fiu.mule_network && <Card title="Mule network"><p className="text-sm">{fiu.mule_network.summary}</p></Card>}
              <Card title="Fund flow">
                <div className="grid gap-4 md:grid-cols-2"><div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Sources ({fiu.flow_chains.distinct_sources})</div><Bullets items={fiu.flow_chains.sources.slice(0, 6).map((x: Json) => `${x.name}: ${eur(x.eur)} (${x.count})`)} /></div>
                  <div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Destinations</div><Bullets items={fiu.flow_chains.destinations.slice(0, 6).map((x: Json) => `${x.name}${x.country ? " (" + x.country + ")" : ""}: ${eur(x.eur)} — ${x.share_of_inflow_pct}% of inflow, median ${x.median_hours_after_credit}h after credit`)} /></div></div>
              </Card>
              <Card title="Entity resolution candidates"><Bullets items={fiu.entity_resolution.length ? fiu.entity_resolution.map((r: Json) => `${r.name} (${r.ref}) — ${r.reason ?? r.basis ?? "possible same person"}`) : ["No duplicate-identity candidates."]} /></Card>
              <Card title="Intelligence package" right={<span className="text-xs text-slate-400">{fiu.intelligence_package.package_id} · {fiu.intelligence_package.classification}</span>}>
                <div className="grid gap-3 text-sm md:grid-cols-3">{[["Associates", fiu.intelligence_package.associates.length], ["Identifiers", fiu.intelligence_package.identifiers.length], ["Key transactions", fiu.intelligence_package.key_transactions.length]].map(([k, v]) => <div key={k as string} className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-500">{k}</div><div className="text-xl font-semibold">{v}</div></div>)}</div>
                <p className="mt-3 text-xs text-slate-500">{fiu.intelligence_package.grading.assessment}</p>
              </Card>
            </div>)}

          {tab === "Typologies" && (
            <div className="space-y-3">
              <Card title={`Advanced typology engine — overall ${fiu.typology.risk_score} (${fiu.typology.severity})`} right={<Pill tone="amber">{fiu.typology.escalation.recommendation.replace(/_/g, " ")}</Pill>}>
                <p className="text-sm text-slate-600">{fiu.typology.escalation.rationale}</p>
              </Card>
              {fiu.typology.detections.map((t: Json) => (
                <Card key={t.code} title={t.label} right={<span className="flex items-center gap-2"><Level value={t.severity} /><Meter value={t.score} /></span>}>
                  <p className="mb-2 text-xs text-slate-500">{t.description}{t.mlro_required ? " · MLRO judgement required" : ""}</p>
                  <div className="space-y-1">{t.indicators.map((i: Json, n: number) => <div key={n} className="flex gap-2 text-sm"><span className="w-10 shrink-0 text-xs font-semibold text-slate-400">+{i.points}</span><span>{i.text}{i.refs?.length > 0 && <span className="ml-1 text-xs text-slate-400">({i.refs.slice(0, 4).join(", ")})</span>}</span></div>)}</div>
                </Card>))}
              {fiu.typology.detections.length === 0 && <Card><p className="text-sm text-slate-500">No typology reached the detection threshold.</p></Card>}
              {fiu.network_typologies.length > 0 && <Card title="Across the linked network"><Bullets items={fiu.network_typologies.map((r: Json) => `${r.label}: ${r.members.join(", ")} (max ${r.max_score})`)} /></Card>}
            </div>)}

          {tab === "Network" && (
            <div className="space-y-3">
              <Card title={fiu.network.linked ? `Network risk ${fiu.network.network_risk.score} (${fiu.network.network_risk.level}) · ${fiu.network.cluster_size} entities` : "No linked entities"}>
                {fiu.network.linked ? <NetGraph nodes={fiu.network.graph.nodes} edges={fiu.network.graph.edges} onSelect={(n) => { window.location.href = n.type === "customer" ? `/customers/${n.id}` : "/kyb"; }} /> : <p className="text-sm text-slate-500">No shared identifiers, wallets, accounts, directors or UBOs with other customers.</p>}
              </Card>
              {fiu.network.hidden_associations.length > 0 && <Card title="Hidden associations (undeclared)"><Bullets items={fiu.network.hidden_associations.map((h: Json) => h.explanation)} /></Card>}
              {fiu.network.linked && <Card title="Network risk breakdown"><Bullets items={Object.entries(fiu.network.network_risk.components).map(([k, v]: [string, any]) => `${k.replace(/_/g, " ")} (+${v.points}): ${v.why}`)} /></Card>}
            </div>)}

          {tab === "Crypto" && (
            <div className="space-y-3">
              {ag.crypto.count === 0 && <Card><p className="text-sm text-slate-500">No wallets are registered to this subject.</p></Card>}
              {ag.crypto.wallets.map((w: Json) => (
                <Card key={w.wallet.id} title={`${w.wallet.chain} wallet ${w.wallet.address.slice(0, 12)}…`} right={<Level value={w.exposure_analysis.level} />}>
                  <p className="mb-3 text-sm text-slate-700">{w.findings.join(" ")}</p>
                  <PathMap nodes={w.path.nodes} edges={w.path.edges} />
                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Provider triangulation (simulated)</div>
                      <table><tbody className="divide-y divide-slate-100">{w.wallet_attribution.providers.map((p: Json) => <tr key={p.provider}><td className="td text-xs">{p.name}</td><td className="td text-right"><Meter value={p.risk_score} /></td></tr>)}</tbody></table>
                      <p className="mt-1 text-[11px] text-slate-400">{w.wallet_attribution.disclaimer}</p></div>
                    <div><div className="mb-1 text-xs font-semibold uppercase text-slate-500">Cross-chain &amp; mixer</div>
                      <Bullets items={[...w.cross_chain.map((c: Json) => `Via ${c.bridge.bridge}: ${eur(c.bridge.deposit.eur)} ${c.bridge.source_chain} → ${c.bridge.dest_chain} in ${c.bridge.delay_hours}h (match ${c.bridge.match_confidence})`), w.mixer.used ? "Mixer interaction detected" : "No mixer interaction", ...w.clusters.map((c: Json) => `Cluster (${c.basis}): ${c.size} addresses`)]} />
                      <p className="mt-1 text-[11px] text-slate-400">{w.mixer.note}</p></div>
                  </div>
                </Card>))}
            </div>)}

          {tab === "SAR / STR" && d.sar_package && (
            <div className="space-y-3">
              <Card title="Report content" right={d.sar ? <Link href={`/sars/${d.sar.id}`} className="text-xs text-brand-700 hover:underline">Open SAR {d.sar.reference} · {d.sar.status.replace(/_/g, " ")} →</Link> : <span className="text-xs text-slate-400">No SAR drafted yet</span>}>
                <p className="mb-2 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900">{d.sar_package.disclaimer}</p>
                <div className="mb-3 flex flex-wrap gap-1.5">{Object.entries(d.sar_package.formats).map(([k, v]: [string, any]) => <button key={k} onClick={() => setFmt(k)} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${fmt === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700"}`}>{v.label}</button>)}</div>
                <p className="mb-3 text-xs text-slate-500">{d.sar_package.formats[fmt].destination_note}</p>
                <div className="space-y-3">{d.sar_package.formats[fmt].sections.map(([k, v]: [string, string]) => <div key={k}><div className="text-xs font-semibold uppercase text-slate-500">{k}</div><pre className="whitespace-pre-wrap text-sm text-slate-800">{v}</pre></div>)}</div>
                <button className="btn-secondary mt-4 text-xs" onClick={() => download(`/investigations/${id}/report/${fmt}`, `${s.reference}-${fmt}.txt`)}>Download this format (.txt)</button>
              </Card>
            </div>)}

          {tab === "Notes" && (
            <Card title="Case notes and decisions">
              <div className="space-y-3">{d.notes.slice().reverse().map((n: Json, i: number) => <div key={i} className="rounded-lg border border-slate-100 p-3"><div className="mb-1 flex items-center gap-2 text-xs text-slate-400"><Pill tone={n.kind === "DECISION" ? "indigo" : n.kind === "AGENT" ? "amber" : "slate"}>{n.kind.toLowerCase()}</Pill><b className="text-slate-600">{n.author}</b>{fmtDateTime(n.ts)}</div><p className="text-sm text-slate-800">{n.text}</p></div>)}</div>
            </Card>)}
        </div>

        <aside className="space-y-4">
          <Card title="Actions">
            {closed ? (
              <div className="space-y-2 text-sm"><div><Level value={s.disposition} /></div><p className="text-slate-600">{d.closure_rationale}</p>
                {can.mlro && s.disposition !== "SAR_FILED" && <button className="btn-secondary w-full" disabled={busy} onClick={() => act("reopen")}>Reopen (MLRO)</button>}</div>
            ) : (
              <div className="space-y-3">
                <textarea className="input min-h-[84px] w-full text-sm" placeholder="Rationale / note (required for escalation and closure)" value={text} onChange={(e) => setText(e.target.value)} />
                {s.queue === "TRIAGE" && <button className="btn w-full" disabled={busy} onClick={() => act("accept_to_fiu")}>Accept to FIU investigation</button>}
                {s.queue === "FIU" && <button className="btn w-full" disabled={busy || !can.escalate} title={can.escalate ? "" : "Senior analyst, MLRO or compliance manager only"} onClick={() => act("escalate")}>Escalate{!can.escalate && " (senior only)"}</button>}
                {s.queue === "ESCALATION" && <button className="btn w-full" disabled={busy || !can.to_sar} onClick={() => act("to_sar")}>Draft SAR / STR{!can.to_sar && " (senior only)"}</button>}
                {(s.queue === "SAR" || s.queue === "MLRO") && d.sar && <Link href={`/sars/${d.sar.id}`} className="btn w-full text-center">Go to SAR {d.sar.reference} →</Link>}
                {(s.queue === "FIU" || s.queue === "ESCALATION") && <button className="btn-secondary w-full" disabled={busy} onClick={() => act("return_to_triage")}>Return to triage</button>}
                <div className="border-t border-slate-100 pt-3">
                  <select className="input w-full text-sm" value={disp} onChange={(e) => setDisp(e.target.value)}><option value="">Close with disposition…</option>{Object.entries(d.dispositions).filter(([k]) => k !== "SAR_FILED").map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select>
                  <button className="btn-danger mt-2 w-full" disabled={busy || !disp} onClick={() => act("close", { disposition: disp })}>Close case</button>
                  <p className="mt-1 text-[11px] text-slate-400">Escalated cases close by MLRO only; HIGH/CRITICAL cases need a different reviewer from the investigator (four-eyes). A SAR is filed only through the MLRO.</p>
                </div>
                <div className="flex gap-2"><button className="btn-secondary flex-1 text-xs" disabled={busy || !text} onClick={() => act("note")}>Add note</button><button className="btn-secondary flex-1 text-xs" disabled={busy} onClick={() => act("refresh")}>Re-run agents</button></div>
              </div>)}
          </Card>
          <Card title="Case facts"><dl className="space-y-1.5 text-sm">{[["Opened", fmtDate(s.created_at) + " by " + s.opened_by], ["Assigned", s.assigned_to || "–"], ["Source", s.source_type], ["Age", s.age_days + " days"], ["Typologies", (s.typologies || []).join(", ").replace(/_/g, " ").toLowerCase() || "–"]].map(([k, v]) => <div key={k} className="flex justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{v}</dd></div>)}</dl></Card>
        </aside>
      </div>
    </div>
  );
}
