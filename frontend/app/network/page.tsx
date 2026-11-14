"use client";
import { useCallback, useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, Level, Spinner } from "@/components/ui";
import { Meter, NetGraph } from "@/components/fiu";

export default function Network() {
  const [cl, setCl] = useState<Json[] | null>(null);
  const [sel, setSel] = useState<Json | null>(null);
  const [net, setNet] = useState<Json | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const focus = useCallback((et: string, id: number) => api(`/network/${et}/${id}`).then(setNet).catch((e) => setErr(e.message)), []);
  useEffect(() => {
    api("/network/clusters").then((r: Json[]) => {
      setCl(r);
      const want = new URLSearchParams(window.location.search).get("cluster");
      const c = r.find((x) => x.id === want) || r[0];
      if (c) { setSel(c); focus(c.members[0].type, c.members[0].id); }
    }).catch((e) => setErr(e.message));
  }, [focus]);
  if (!cl) return err ? <ErrorBox message={err} /> : <Spinner label="Analysing links…" />;
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Network analysis</h1><p className="mt-1 text-sm text-slate-500">Entities linked by shared phone, email, IP, device, wallet, bank account, address, directors and UBOs. Link strength is the sum of the strongest evidence of each kind; weak household-style links are down-weighted.</p></div>
      <ErrorBox message={err} />
      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        <Card title={`${cl.length} clusters`}>
          <div className="space-y-2">{cl.map((c) => (
            <button key={c.id} onClick={() => { setSel(c); focus(c.members[0].type, c.members[0].id); }} className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${sel?.id === c.id ? "border-brand-600 bg-brand-50" : "border-slate-100 hover:bg-slate-50"}`}>
              <div className="flex items-center justify-between"><span className="font-medium">{c.members.length} entities</span><Level value={c.level} /></div>
              <div className="mt-1 truncate text-xs text-slate-500">{c.members.map((m: Json) => m.name).join(", ")}</div>
              <div className="mt-1 flex items-center justify-between text-xs text-slate-400"><span>{c.shared.slice(0, 3).join(" · ")}</span><Meter value={c.score} /></div>
            </button>))}</div>
        </Card>
        <div className="space-y-4">
          {net && <Card title={`${net.subject.name} · network risk ${net.network_risk.score} (${net.network_risk.level})`} right={<span className="text-xs text-slate-400">click a node to re-centre</span>}>
            <NetGraph nodes={net.graph.nodes} edges={net.graph.edges} onSelect={(n) => focus(n.type, n.id)} height={420} />
          </Card>}
          {net && net.hidden_associations.length > 0 && <Card title="Hidden associations"><ul className="space-y-1 text-sm">{net.hidden_associations.map((h: Json, i: number) => <li key={i}>{h.explanation}</li>)}</ul></Card>}
          {net && <Card title="Why this network scores as it does"><ul className="space-y-1 text-sm text-slate-700">{Object.entries(net.network_risk.components).map(([k, v]: [string, any]) => <li key={k}><b>{k.replace(/_/g, " ")}</b> (+{v.points}): {v.why}</li>)}</ul></Card>}
        </div>
      </div>
    </div>
  );
}
