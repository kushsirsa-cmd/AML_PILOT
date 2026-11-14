"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Json } from "@/lib/api";
import { Card, ErrorBox, fmtDateTime, Spinner, eur } from "@/components/ui";
import { C, Donut, HBars, Legend, LineArea, RISK_COLOR, SEV_COLOR, StackedColumns } from "@/components/charts";

function Kpi({ label, value, sub, href, accent }: { label: string; value: React.ReactNode; sub?: React.ReactNode; href?: string; accent?: string }) {
  const body = (
    <div className="h-full rounded-xl border border-slate-200/80 bg-white p-4 shadow-card transition hover:shadow-md">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{accent && <i className="h-2 w-2 rounded-full" style={{ background: accent }} />}{label}</div>
      <div className="mt-2 text-[28px] font-semibold leading-none tracking-tight text-slate-900 tabular-nums">{value}</div>
      {sub && <div className="mt-1.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function Executive() {
  const [e, setE] = useState<Json>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api("/executive").then(setE).catch((x) => setErr(x.message)); }, []);
  if (err) return <ErrorBox message={`Cannot load dashboard: ${err}`} />;
  if (!e) return <Spinner label="Loading executive dashboard…" />;
  const k = e.kpis, rd = e.risk_distribution;
  const cv = e.case_volume, s = e.sars, t = e.transactions;
  const statusColor: Record<string, string> = { FILED: C.s3, APPROVED: C.s1, PENDING_MLRO: C.s2, DRAFT: "#94a3b8", REJECTED: "#b91c1c" };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Executive dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">Financial crime risk posture · updated {fmtDateTime(e.generated_at)}</p>
        </div>
        <Link href="/work" className="btn">Open work queues →</Link>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Total customers" value={k.total_customers} sub={`${k.total_businesses} business entities`} href="/customers" accent={C.s1} />
        <Kpi label="High-risk customers" value={k.high_risk_customers} sub={`${k.high_risk_businesses} high-risk businesses`} href="/customers" accent={RISK_COLOR.HIGH} />
        <Kpi label="Open alerts" value={k.open_alerts} sub={`${k.critical_alerts} critical · ${k.escalated_to_mlro} with MLRO`} href="/mlro" accent={RISK_COLOR.PROHIBITED} />
        <Kpi label="Pending reviews" value={k.pending_reviews} sub={`${k.overdue_periodic_reviews} periodic overdue`} href="/reviews" accent={C.s2} />
        <Kpi label="Case volume (30d)" value={k.case_volume_30d} sub="alerts + reviews + SARs" accent={C.s3} />
        <Kpi label="SARs filed" value={k.sars_filed} sub={`${k.sars_in_progress} in progress`} href="/sars" accent="#6250d6" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Customer risk distribution" right={<span className="text-xs text-slate-400">{k.total_customers} customers</span>}>
          <Donut data={rd.labels.map((l: string, i: number) => ({ label: l, value: rd.customers[i], color: RISK_COLOR[l] }))} center={k.total_customers} sub="customers" />
          <div className="mt-4 border-t border-slate-100 pt-3"><div className="mb-2 text-xs font-medium text-slate-500">Business entities ({k.total_businesses})</div>
            <div className="flex h-2.5 overflow-hidden rounded-full">{rd.labels.map((l: string, i: number) => <div key={l} style={{ width: `${(100 * rd.businesses[i]) / k.total_businesses}%`, background: RISK_COLOR[l], marginRight: 2 }} title={`${l}: ${rd.businesses[i]}`} />)}</div>
            <div className="mt-2"><Legend items={rd.labels.map((l: string, i: number) => ({ label: l, color: RISK_COLOR[l], value: rd.businesses[i] }))} /></div></div>
        </Card>
        <Card title="Case volume by month" right={<Legend items={[{ label: "Alerts", color: C.s1 }, { label: "Reviews", color: C.s2 }, { label: "SARs", color: C.s3 }]} />}>
          <StackedColumns labels={cv.months} series={[{ name: "Alerts", color: C.s1, values: cv.alerts }, { name: "Reviews", color: C.s2, values: cv.reviews }, { name: "SARs", color: C.s3, values: cv.sars }]} />
        </Card>
        <Card title="SAR statistics" right={<Link href="/sars" className="text-xs text-brand-600 hover:underline">View all</Link>}>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div><div className="text-2xl font-semibold tabular-nums">{s.total}</div><div className="text-[11px] uppercase tracking-wide text-slate-500">Total</div></div>
            <div><div className="text-2xl font-semibold tabular-nums">{s.avg_days_to_file ?? "–"}</div><div className="text-[11px] uppercase tracking-wide text-slate-500">Avg days to file</div></div>
            <div><div className="text-2xl font-semibold tabular-nums">{eur(s.total_value_eur)}</div><div className="text-[11px] uppercase tracking-wide text-slate-500">Filed value</div></div>
          </div>
          <div className="mt-5"><HBars items={Object.entries(s.by_status).map(([k2, v]) => ({ label: k2.replace("_", " "), value: v as number, color: statusColor[k2] }))} /></div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Weekly transactions vs flagged (12 weeks)" className="xl:col-span-2" right={<Legend items={[{ label: "All", color: C.s1 }, { label: "Flagged by monitoring", color: C.s2 }]} />}>
          <LineArea labels={t.weeks} fmt={(n) => String(Math.round(n))} series={[{ name: "All transactions", color: C.s1, values: t.total_count }, { name: "Flagged", color: C.s2, values: t.flagged_count }]} />
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">{Object.entries(t.flags_by_rule).map(([r, n]) => <span key={r} className="rounded-full bg-slate-100 px-2 py-0.5">{r.replace(/_/g, " ").toLowerCase()} <b className="text-slate-800">{n as number}</b></span>)}</div>
        </Card>
        <Card title="Open alert ageing">
          <HBars items={Object.entries(e.alert_ageing).map(([l, v]) => ({ label: l, value: v as number, color: l.startsWith("30") || l.startsWith("15") ? RISK_COLOR.HIGH : C.s1 }))} />
          <div className="mt-4 border-t border-slate-100 pt-3"><div className="mb-2 text-xs font-medium text-slate-500">By severity</div><Legend items={Object.entries(e.alerts_by_severity).map(([l, v]) => ({ label: l, color: SEV_COLOR[l], value: v as number }))} /></div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Alerts by workflow (open / closed)">
          <HBars items={e.alerts_by_source.map((a: Json) => ({ label: a.source.replace(/_/g, " "), value: a.open, sub: `/ ${a.closed} closed` }))} color={C.s2} />
        </Card>
        <Card title="Analyst workload (open alerts)">
          <HBars items={e.workload.map((w: Json) => ({ label: w.assignee, value: w.open_alerts, color: w.assignee === "Unassigned" ? "#94a3b8" : C.s1 }))} />
          <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">QA: {e.qa.completed}/{e.qa.sampled} sampled decisions reviewed · pass rate <b className="text-slate-900">{e.qa.pass_rate_pct ?? "–"}%</b></div>
        </Card>
        <Card title="Recent activity" right={<Link href="/audit" className="text-xs text-brand-600 hover:underline">Audit trail</Link>}>
          <ul className="space-y-2.5">
            {e.recent_activity.slice(0, 7).map((r: Json, i: number) => (
              <li key={i} className="flex items-start justify-between gap-3 text-xs"><span><b className="text-slate-800">{r.action.replace(/_/g, " ").toLowerCase()}</b> <span className="text-slate-500">· {r.actor}</span></span><span className="shrink-0 text-slate-400">{fmtDateTime(r.ts)}</span></li>
            ))}
          </ul>
          <div className="mt-4 border-t border-slate-100 pt-3"><div className="mb-2 text-xs font-medium text-slate-500">High-risk customers by residence</div><HBars items={e.top_risk_countries.map((c: Json) => ({ label: c.country, value: c.customers, color: RISK_COLOR.HIGH }))} /></div>
        </Card>
      </div>
    </div>
  );
}
