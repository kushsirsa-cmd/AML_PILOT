"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, post, Json } from "@/lib/api";
import { Card, ErrorBox, eur, fmtDateTime, Level, Pill, Spinner } from "@/components/ui";

export default function Transactions() {
  const [d, setD] = useState<Json>(null);
  const [flagged, setFlagged] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api(`/transactions/fiat?limit=500&flagged=${flagged}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [flagged]);
  async function rerun() { try { await post("/transactions/monitor"); load(); } catch (e) { setErr((e as Error).message); } }
  if (!d) return err ? <ErrorBox message={err} /> : <Spinner label="Loading…" />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Transaction monitoring</h1><p className="mt-1 text-sm text-slate-500">Rule-based monitoring of account activity. Crypto transfers are analysed on the <Link className="text-brand-600 hover:underline" href="/crypto">Crypto</Link> page.</p></div>
        <div className="flex gap-2"><button className="btn-secondary" onClick={() => setFlagged(!flagged)}>{flagged ? "Show all transactions" : "Show flagged only"}</button><button className="btn" onClick={rerun}>Re-run monitoring</button></div>
      </div>
      <ErrorBox message={err} />
      <Card title="Monitoring rules">
        <div className="grid gap-3 md:grid-cols-3">{Object.entries(d.rules).map(([k, v]: [string, Json]) => <div key={k} className="rounded-lg border border-slate-200 p-3"><div className="flex items-center gap-2 text-sm font-semibold">{k.replace(/_/g, " ")} <Level value={v.severity} /></div><p className="mt-1 text-xs text-slate-500">{v.description}</p></div>)}</div>
      </Card>
      <Card title={`${flagged ? "Flagged transactions" : "Transactions"} · ${d.transactions.length}`}>
        <table>
          <thead><tr><th className="th">Ref</th><th className="th">When</th><th className="th">Holder</th><th className="th">Dir</th><th className="th text-right">Amount</th><th className="th">Channel</th><th className="th">Counterparty</th><th className="th">Rules</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {d.transactions.map((t: Json) => (
              <tr key={t.txn_ref}>
                <td className="td font-mono text-xs text-slate-500">{t.txn_ref}</td><td className="td text-xs text-slate-500">{fmtDateTime(t.ts)}</td>
                <td className="td"><Link className="font-medium text-brand-700 hover:underline" href={t.holder_type === "customer" ? `/customers/${t.customer_id}` : `/kyb/${t.corporate_id}`}>{t.holder}</Link></td>
                <td className="td"><Pill tone={t.direction === "IN" ? "green" : "slate"}>{t.direction}</Pill></td><td className="td text-right tabular-nums">{eur(t.amount_eur)}</td>
                <td className="td text-xs">{t.channel.replace("_", " ")}</td><td className="td text-xs">{t.counterparty}<div className="text-slate-400">{t.counterparty_country}</div></td>
                <td className="td"><div className="flex flex-wrap gap-1">{t.flags.map((f: string) => <Pill key={f} tone="amber">{f.replace(/_/g, " ").toLowerCase()}</Pill>)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
