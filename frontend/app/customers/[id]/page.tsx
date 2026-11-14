"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, Json, post } from "@/lib/api";
import { Output } from "@/components/Output";
import { Card, ErrorBox, Field, fmtDate, fmtDateTime, Pill, RiskBadge, Spinner } from "@/components/ui";

const TABS = [
  ["overview", "Overview"],
  ["agents", "AI agents"],
  ["screening", "Screening"],
  ["reviews", "Reviews"],
  ["note", "Case note"],
] as const;

const AGENTS: { key: string; title: string; skip?: string[] }[] = [
  { key: "kyc", title: "KYC Agent" },
  { key: "screening", title: "Screening Agent", skip: ["sanctions", "pep", "adverse_media", "hits"] },
  { key: "cdd", title: "CDD Agent" },
  { key: "edd", title: "EDD Agent" },
  { key: "sof", title: "Source of Funds Agent" },
  { key: "sow", title: "Source of Wealth Agent" },
  { key: "risk", title: "Risk Rating Engine" },
  { key: "summary", title: "AI Case Summary Agent", skip: ["case_note"] },
];

export default function CustomerPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<Json>(null);
  const [tab, setTab] = useState<string>("overview");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => api(`/customers/${id}`).then(setD).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function act(label: string, fn: () => Promise<Json>, reload = false) {
    setBusy(label);
    setErr(null);
    try {
      const res = await fn();
      if (reload) await load();
      else setD(res);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading customer..." />;
  const c = d.customer;
  const A = d.assessments as Record<string, Json>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{c.full_name}</h1>
            <RiskBadge rating={c.risk_rating} />
            {c.risk_score != null && <span className="text-sm text-slate-500">score {c.risk_score}/100</span>}
            <Pill>{c.status}</Pill>
          </div>
          <div className="mt-1 text-sm text-slate-500">{c.customer_ref} - {c.nationality} national, resident in {c.country_of_residence} - next review {fmtDate(c.next_review_due)}</div>
        </div>
        <button className="btn" disabled={!!busy} onClick={() => act("Running all AML agents...", () => post(`/customers/${id}/assess`))}>Run full AML assessment</button>
      </div>

      {busy && <Spinner label={busy} />}
      <ErrorBox message={err} />

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {label}
            {k === "screening" && d.hits.filter((h: Json) => h.disposition === "OPEN").length > 0 && <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-xs text-amber-800">{d.hits.filter((h: Json) => h.disposition === "OPEN").length}</span>}
            {k === "reviews" && d.reviews.filter((r: Json) => r.status === "PENDING").length > 0 && <span className="ml-1.5 rounded-full bg-amber-100 px-1.5 text-xs text-amber-800">{d.reviews.filter((r: Json) => r.status === "PENDING").length}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview d={d} id={id} act={act} busy={!!busy} />}
      {tab === "agents" && <Agents A={A} id={id} act={act} busy={!!busy} />}
      {tab === "screening" && <Hits d={d} id={id} act={act} busy={!!busy} />}
      {tab === "reviews" && <Reviews d={d} id={id} act={act} busy={!!busy} />}
      {tab === "note" && <Note d={d} A={A} />}
    </div>
  );
}

type ActFn = (label: string, fn: () => Promise<Json>, reload?: boolean) => Promise<void>;

function Overview({ d, id, act, busy }: { d: Json; id: string; act: ActFn; busy: boolean }) {
  const c = d.customer;
  const [decision, setDecision] = useState("APPROVE");
  const [note, setNote] = useState("");
  const [doc, setDoc] = useState({ doc_type: "ID_DOCUMENT", expiry_date: "" });
  const rec = A_rec(d);

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card title="Customer profile" className="lg:col-span-2">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {([
            ["Date of birth", fmtDate(c.date_of_birth)], ["Nationality", c.nationality], ["Country of residence", c.country_of_residence], ["Address", c.address],
            ["Occupation", c.occupation], ["Industry", c.industry], ["Annual income", c.annual_income != null ? `EUR ${Number(c.annual_income).toLocaleString()}` : null],
            ["Product / channel", `${c.product} / ${c.channel}`], ["PEP declared", c.pep_declared ? "Yes" : "No"], ["Last KYC review", fmtDate(c.last_kyc_review)],
          ] as [string, string | null][]).map(([k, v]) => (
            <div key={k}><dt className="text-xs uppercase tracking-wide text-slate-500">{k}</dt><dd>{v || <span className="text-slate-400">not provided</span>}</dd></div>
          ))}
          <div className="sm:col-span-2"><dt className="text-xs uppercase tracking-wide text-slate-500">Source of funds</dt><dd>{c.source_of_funds || <span className="text-slate-400">not provided</span>}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs uppercase tracking-wide text-slate-500">Source of wealth</dt><dd>{c.source_of_wealth || <span className="text-slate-400">not provided</span>}</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs uppercase tracking-wide text-slate-500">Expected activity</dt><dd>{c.expected_activity || <span className="text-slate-400">not provided</span>}</dd></div>
        </dl>
      </Card>

      <div className="space-y-5">
        <Card title="Case decision">
          {rec && <p className="mb-3 rounded bg-indigo-50 p-2 text-xs text-indigo-800"><b>AI recommendation:</b> {rec}</p>}
          <div className="space-y-3">
            <select className="input" value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="APPROVE">Approve</option><option value="REJECT">Reject</option><option value="ESCALATE">Escalate</option><option value="REQUEST_INFO">Request information</option>
            </select>
            <textarea className="input" rows={3} placeholder="Rationale (required)" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="btn w-full" disabled={busy || note.trim().length < 3} onClick={() => act("Recording decision...", () => post(`/customers/${id}/decision`, { decision, note }))}>Record decision</button>
          </div>
        </Card>

        <Card title="Documents">
          <ul className="mb-3 space-y-1 text-sm">
            {d.documents.map((x: Json) => {
              const expired = x.expiry_date && new Date(x.expiry_date) < new Date();
              return <li key={x.id} className="flex justify-between"><span>{x.doc_type}</span><span className={expired ? "font-medium text-red-600" : "text-slate-500"}>{x.expiry_date ? `exp ${fmtDate(x.expiry_date)}` : "no expiry"}{expired && " (expired)"}</span></li>;
            })}
            {d.documents.length === 0 && <li className="text-slate-400">No documents on file</li>}
          </ul>
          <div className="flex gap-2">
            <select className="input" value={doc.doc_type} onChange={(e) => setDoc({ ...doc, doc_type: e.target.value })}>
              {["ID_DOCUMENT", "PROOF_OF_ADDRESS", "SOF_EVIDENCE", "SOW_EVIDENCE"].map((t) => <option key={t}>{t}</option>)}
            </select>
            <input type="date" className="input" value={doc.expiry_date} onChange={(e) => setDoc({ ...doc, expiry_date: e.target.value })} title="Expiry date" />
          </div>
          <button className="btn-secondary mt-2 w-full" disabled={busy} onClick={() => act("Adding document...", () => post(`/customers/${id}/documents`, { doc_type: doc.doc_type, expiry_date: doc.expiry_date || null }), true)}>Add document</button>
          <p className="mt-2 text-xs text-slate-400">Re-run the assessment after adding evidence.</p>
        </Card>
      </div>
    </div>
  );
}

function A_rec(d: Json): string | null {
  return d.assessments?.summary?.output?.final_recommendation_text ?? null;
}

function Agents({ A, id, act, busy }: { A: Record<string, Json>; id: string; act: ActFn; busy: boolean }) {
  return (
    <div className="space-y-5">
      {AGENTS.map(({ key, title, skip }) => {
        const a = A[key];
        return (
          <Card
            key={key}
            title={<span className="flex items-center gap-2">{title}{a && <Pill tone={a.engine === "rules+claude" ? "indigo" : "slate"}>{a.engine === "rules+claude" ? "rules + Claude" : "rules"}</Pill>}</span>}
            right={<div className="flex items-center gap-3">{a && <span className="text-xs text-slate-400">{fmtDateTime(a.created_at)}</span>}<button className="btn-secondary" disabled={busy} onClick={() => act(`Running ${title}...`, () => post(`/customers/${id}/agents/${key}`))}>Run</button></div>}
          >
            {!a ? <span className="text-sm text-slate-400">Not run yet.</span> : key === "risk" ? <RiskView o={a.output} /> : <Output data={a.output} skip={skip} />}
          </Card>
        );
      })}
    </div>
  );
}

function RiskView({ o }: { o: Json }) {
  const comps = Object.entries(o.components) as [string, Json][];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <RiskBadge rating={o.risk_rating} />
        <span className="text-2xl font-semibold">{o.risk_score}<span className="text-sm text-slate-400">/100</span></span>
        {o.rating_changed && <Pill tone="amber">changed from {o.previous_rating}</Pill>}
      </div>
      <table className="w-full">
        <thead><tr><th className="th">Factor</th><th className="th">Points</th><th className="th">Reasoning</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {comps.map(([k, v]) => (
            <tr key={k} className={v.points ? "" : "text-slate-400"}>
              <td className="td capitalize">{k.replace(/_/g, " ")}</td>
              <td className="td"><div className="flex items-center gap-2"><div className="h-2 w-16 rounded bg-slate-100"><div className="h-2 rounded bg-indigo-500" style={{ width: `${Math.min(100, v.points * 2.5)}%` }} /></div>{v.points}</div></td>
              <td className="td text-xs">{v.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {o.overrides.length > 0 && <div className="rounded border border-red-200 bg-red-50 p-3 text-sm"><b>Overrides:</b><ul className="list-disc pl-5">{o.overrides.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
      <div className="text-xs text-slate-500">Thresholds: LOW &lt;30, MEDIUM 30-59, HIGH &ge;60; PROHIBITED by override only.</div>
    </div>
  );
}

function Hits({ d, id, act, busy }: { d: Json; id: string; act: ActFn; busy: boolean }) {
  const [notes, setNotes] = useState<Record<number, string>>({});
  return (
    <Card title="Screening hits">
      <div className="space-y-3">
        {d.hits.map((h: Json) => {
          const rec = h.details?.record || {};
          const m = h.details?.matched_on || {};
          return (
            <div key={h.id} className="rounded-md border border-slate-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Pill tone={h.list_type === "SANCTIONS" ? "red" : h.list_type === "PEP" ? "amber" : "indigo"}>{h.list_type.replace("_", " ")}</Pill>
                  <span className="font-medium">{h.matched_name}</span>
                  <Pill tone={h.confidence >= 90 ? "red" : h.confidence >= 75 ? "amber" : "slate"}>{Math.round(h.confidence)}% match</Pill>
                </div>
                <Pill tone={h.disposition === "OPEN" ? "amber" : h.disposition === "CONFIRMED" ? "red" : "green"}>{h.disposition}</Pill>
              </div>
              <div className="mt-2 grid gap-1 text-xs text-slate-600 sm:grid-cols-3">
                <div>Name similarity: <b>{m.name_similarity ?? "-"}</b></div><div>DOB: <b>{m.date_of_birth ?? "-"}</b></div><div>Nationality: <b>{m.nationality ?? "-"}</b></div>
              </div>
              <div className="mt-2 text-sm text-slate-700">
                {h.list_type === "SANCTIONS" && <>{rec.list} - {rec.program}. {rec.reason}</>}
                {h.list_type === "PEP" && <>{rec.position} ({rec.pep_type}) - {rec.nationality}</>}
                {h.list_type === "ADVERSE_MEDIA" && <>[{rec.severity}/{rec.category}] {rec.headline} <span className="text-slate-400">({rec.source}, {rec.date})</span></>}
              </div>
              {h.disposition_note && <div className="mt-1 text-xs italic text-slate-500">Analyst note: {h.disposition_note}</div>}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input className="input max-w-sm" placeholder="Rationale (required)" value={notes[h.id] || ""} onChange={(e) => setNotes({ ...notes, [h.id]: e.target.value })} />
                <button className="btn-secondary" disabled={busy || (notes[h.id] || "").trim().length < 3} onClick={() => act("Recording disposition and re-scoring...", () => post(`/screening/hits/${h.id}/disposition`, { disposition: "FALSE_POSITIVE", note: notes[h.id] }))}>False positive</button>
                <button className="btn-danger" disabled={busy || (notes[h.id] || "").trim().length < 3} onClick={() => act("Recording disposition and re-scoring...", () => post(`/screening/hits/${h.id}/disposition`, { disposition: "CONFIRMED", note: notes[h.id] }))}>Confirm match</button>
              </div>
            </div>
          );
        })}
        {d.hits.length === 0 && <p className="text-sm text-slate-400">No sanctions, PEP or adverse-media hits above the reporting threshold (65%).</p>}
      </div>
    </Card>
  );
}

const EVENT_FIELDS: Record<string, { key: string; label: string; type?: string; options?: string[] }[]> = {
  ADDRESS_CHANGE: [{ key: "new_address", label: "New address" }, { key: "new_country", label: "New country of residence" }],
  OCCUPATION_CHANGE: [{ key: "new_occupation", label: "New occupation" }, { key: "new_industry", label: "New industry" }],
  NEW_SANCTIONS_MATCH: [
    { key: "list_entry_id", label: "Sanctions list entry", options: Array.from({ length: 12 }, (_, i) => `SAN-${String(i + 1).padStart(3, "0")}`) },
    { key: "confidence", label: "Match confidence (%)", type: "number" },
  ],
  NEW_ADVERSE_MEDIA: [
    { key: "headline", label: "Headline" },
    { key: "severity", label: "Severity", options: ["HIGH", "MEDIUM", "LOW"] },
    { key: "category", label: "Category", options: ["FRAUD", "CORRUPTION", "MONEY_LAUNDERING", "TAX_EVASION", "ORGANISED_CRIME", "TERRORISM_FINANCING", "SANCTIONS_EVASION"] },
  ],
};

function Reviews({ d, id, act, busy }: { d: Json; id: string; act: ActFn; busy: boolean }) {
  const [evt, setEvt] = useState("ADDRESS_CHANGE");
  const [payload, setPayload] = useState<Json>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [dec, setDec] = useState<Record<number, string>>({});

  const submitEvent = () => {
    const p: Json = {};
    for (const f of EVENT_FIELDS[evt]) {
      const v = payload[f.key] ?? (f.options ? f.options[0] : "");
      if (v !== "") p[f.key] = f.type === "number" ? Number(v) : v;
    }
    return act("Running event-driven review...", () => post(`/customers/${id}/reviews/event`, { event_type: evt, payload: p }));
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Periodic review">
          <p className="mb-3 text-sm text-slate-600">Re-runs every agent on current data, then checks missing / expired documents, overdue KYC refresh and risk-rating drift.</p>
          <button className="btn" disabled={busy} onClick={() => act("Running periodic review...", () => post(`/customers/${id}/reviews/periodic`))}>Run periodic review</button>
        </Card>
        <Card title="Simulate trigger event">
          <div className="space-y-3">
            <select className="input" value={evt} onChange={(e) => { setEvt(e.target.value); setPayload({}); }}>
              {Object.keys(EVENT_FIELDS).map((k) => <option key={k}>{k}</option>)}
            </select>
            {EVENT_FIELDS[evt].map((f) => (
              <Field key={f.key} label={f.label}>
                {f.options ? (
                  <select className="input" value={payload[f.key] ?? f.options[0]} onChange={(e) => setPayload({ ...payload, [f.key]: e.target.value })}>{f.options.map((o) => <option key={o}>{o}</option>)}</select>
                ) : (
                  <input className="input" type={f.type || "text"} value={payload[f.key] ?? ""} onChange={(e) => setPayload({ ...payload, [f.key]: e.target.value })} />
                )}
              </Field>
            ))}
            <button className="btn" disabled={busy} onClick={submitEvent}>Trigger event review</button>
          </div>
        </Card>
      </div>

      {d.reviews.map((r: Json) => {
        const o = r.outcome || {};
        return (
          <Card
            key={r.id}
            title={<span className="flex items-center gap-2">{r.review_type.replace("_", " ")} review - {r.trigger}<Pill tone={r.status === "PENDING" ? "amber" : r.status === "ESCALATED" ? "red" : "green"}>{r.status}</Pill>{o.priority && <Pill tone={o.priority === "CRITICAL" ? "red" : "amber"}>{o.priority}</Pill>}</span>}
            right={<span className="text-xs text-slate-400">{fmtDateTime(r.created_at)}</span>}
          >
            <div className="mb-3 rounded bg-indigo-50 p-2 text-sm text-indigo-900"><b>{r.recommendation?.replace(/_/g, " ")}</b></div>
            <Output data={o} skip={["event_payload", "narrative"]} />
            {o.narrative && <p className="mt-3 rounded bg-slate-50 p-3 text-sm">{o.narrative}</p>}
            {r.status === "PENDING" ? (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                <select className="input max-w-[220px]" value={dec[r.id] || "COMPLETE_NO_CHANGE"} onChange={(e) => setDec({ ...dec, [r.id]: e.target.value })}>
                  <option value="COMPLETE_NO_CHANGE">Complete - no change</option><option value="COMPLETE_WITH_UPDATES">Complete - with updates</option>
                  <option value="ESCALATE">Escalate</option><option value="EXIT_RELATIONSHIP">Exit relationship</option>
                </select>
                <input className="input max-w-sm" placeholder="Rationale (required)" value={notes[r.id] || ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} />
                <button className="btn" disabled={busy || (notes[r.id] || "").trim().length < 3} onClick={() => act("Recording review decision...", () => post(`/reviews/${r.id}/decision`, { decision: dec[r.id] || "COMPLETE_NO_CHANGE", note: notes[r.id] }), true)}>Record decision</button>
              </div>
            ) : (
              r.decision && <p className="mt-3 text-xs text-slate-500">Decision: <b>{r.decision}</b> by {r.decided_by} - {r.decision_note}</p>
            )}
          </Card>
        );
      })}
      {d.reviews.length === 0 && <p className="text-sm text-slate-400">No reviews yet.</p>}
    </div>
  );
}

function Note({ d, A }: { d: Json; A: Record<string, Json> }) {
  const s = A.summary?.output;
  if (!s) return <p className="text-sm text-slate-400">Run the assessment to generate a case note.</p>;
  return (
    <div className="space-y-5">
      <Card
        title={<span className="flex items-center gap-2">Analyst case note<Pill tone={A.summary.engine === "rules+claude" ? "indigo" : "slate"}>{A.summary.engine === "rules+claude" ? "rules + Claude" : "rules"}</Pill></span>}
        right={<button className="btn-secondary" onClick={() => navigator.clipboard.writeText(s.case_note)}>Copy</button>}
      >
        <div className="mb-3 rounded bg-indigo-50 p-2 text-sm text-indigo-900"><b>Recommendation:</b> {s.final_recommendation_text}</div>
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{s.case_note}</pre>
      </Card>
      {d.notes.length > 1 && (
        <Card title="Previous versions">
          <div className="space-y-3">{d.notes.slice(1).map((n: Json) => <details key={n.id}><summary className="cursor-pointer text-sm text-slate-600">{fmtDateTime(n.created_at)} ({n.engine})</summary><pre className="mt-2 whitespace-pre-wrap font-sans text-xs">{n.content}</pre></details>)}</div>
        </Card>
      )}
    </div>
  );
}
