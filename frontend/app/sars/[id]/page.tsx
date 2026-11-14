"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, download, post, put, Json } from "@/lib/api";
import { Card, ErrorBox, eur, Level, Pill, Spinner } from "@/components/ui";
import { Output } from "@/components/Output";

export default function SarDetail() {
  const { id } = useParams<{ id: string }>();
  const [s, setS] = useState<Json>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => api(`/sars/${id}`).then((r) => { setS(r); setText(r.narrative); }).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<Json>, ok?: string) {
    setErr(null); setMsg(null);
    try { await fn(); if (ok) setMsg(ok); await load(); } catch (e) { setErr((e as Error).message); }
  }
  const decide = (decision: string) => {
    const note = window.prompt(`MLRO note for ${decision}`) || "";
    if (note.length >= 5) run(() => post(`/sars/${id}/decision`, { decision, note }));
  };
  if (!s) return err ? <ErrorBox message={err} /> : <Spinner label="Loading..." />;
  const ev = s.evidence;
  return (
    <div className="space-y-4">
      <Link href="/sars" className="text-xs text-indigo-700 hover:underline">← SARs</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{s.reference} · {s.subject_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm"><Level value={s.status} /> {s.typologies.map((t: string) => <Pill key={t} tone="indigo">{t}</Pill>)} <span className="text-slate-500">{eur(s.total_amount_eur)}</span> <span className="text-xs text-slate-400">engine {s.engine} · prepared by {s.prepared_by}{s.approved_by ? ` · decided by ${s.approved_by}` : ""}</span></div>
          {s.filing_reference && <div className="mt-1 text-sm">Filing reference (simulated): <b>{s.filing_reference}</b></div>}
          {s.mlro_note && <div className="mt-1 text-sm italic text-slate-600">MLRO: {s.mlro_note}</div>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={() => download(`/sars/${id}/xml`, `${s.reference}.xml`)}>Export XML</button>
          {s.status === "DRAFT" && <button className="btn" onClick={() => run(() => post(`/sars/${id}/submit`), "Submitted to MLRO.")}>Submit to MLRO</button>}
          {s.status === "PENDING_MLRO" && <><button className="btn" onClick={() => decide("APPROVE")}>Approve</button><button className="btn-danger" onClick={() => decide("REJECT")}>Reject</button></>}
          {s.status === "APPROVED" && <button className="btn" onClick={() => run(() => post(`/sars/${id}/file`), "Filed (simulated).")}>File with FIU</button>}
        </div>
      </div>
      <ErrorBox message={err} />
      {msg && <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{msg}</div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Narrative" className="lg:col-span-2" right={s.status === "DRAFT" && <button className="btn" onClick={() => run(() => put(`/sars/${id}/narrative`, { narrative: text }), "Narrative saved.")}>Save</button>}>
          {s.narrative_gaps.length > 0 && <div className="mb-2 rounded bg-amber-50 p-2 text-xs text-amber-800">Missing sections: {s.narrative_gaps.join(", ")}</div>}
          <textarea className="input h-[28rem] font-mono text-xs" readOnly={s.status !== "DRAFT"} value={text} onChange={(e) => setText(e.target.value)} />
          <p className="mt-1 text-xs text-slate-400">Draft generated from case evidence. The reporter remains responsible for accuracy; narrative must not tip off the subject.</p>
        </Card>
        <Card title="Evidence"><div className="max-h-[32rem] overflow-auto text-sm"><Output data={ev} skip={["narrative"]} /></div></Card>
      </div>
    </div>
  );
}
