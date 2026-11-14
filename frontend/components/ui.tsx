import Link from "next/link";
import { ReactNode } from "react";

const RATING_STYLES: Record<string, string> = {
  LOW: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  MEDIUM: "bg-amber-100 text-amber-800 ring-amber-200",
  HIGH: "bg-orange-100 text-orange-800 ring-orange-300",
  PROHIBITED: "bg-red-700 text-white ring-red-800",
  UNRATED: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function RiskBadge({ rating }: { rating?: string | null }) {
  const r = rating || "UNRATED";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${RATING_STYLES[r] || RATING_STYLES.UNRATED}`}>
      {r}
    </span>
  );
}

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "indigo" | "red" | "amber" | "green" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    indigo: "bg-indigo-100 text-indigo-700",
    red: "bg-red-100 text-red-700",
    amber: "bg-amber-100 text-amber-800",
    green: "bg-emerald-100 text-emerald-700",
  };
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200/80 bg-white shadow-card ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, href, tone }: { label: string; value: ReactNode; sub?: ReactNode; href?: string; tone?: string }) {
  const body = (
    <div className={`rounded-xl border bg-white p-4 shadow-card ${tone || "border-slate-200/80"}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-semibold text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-90">{body}</Link> : body;
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{message}</div>;
}

export function Spinner({ label = "Working..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      {label}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "-");
export const fmtDateTime = (s?: string | null) => (s ? new Date(s).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");

const LEVEL_STYLES: Record<string, string> = {
  LOW: "bg-emerald-100 text-emerald-800", ACCEPT: "bg-emerald-100 text-emerald-800", PASS: "bg-emerald-100 text-emerald-800", VERIFIED: "bg-emerald-100 text-emerald-800",
  APPROVED: "bg-emerald-100 text-emerald-800", FILED: "bg-emerald-100 text-emerald-800", SUBMITTED: "bg-emerald-100 text-emerald-800", CLOSED: "bg-slate-100 text-slate-600",
  MEDIUM: "bg-amber-100 text-amber-800", ACCEPT_WITH_REVIEW: "bg-amber-100 text-amber-800", PASS_WITH_FINDINGS: "bg-amber-100 text-amber-800", INCOMPLETE: "bg-amber-100 text-amber-800",
  PENDING: "bg-amber-100 text-amber-800", DRAFT: "bg-slate-100 text-slate-700", OPEN: "bg-amber-100 text-amber-800", IN_REVIEW: "bg-indigo-100 text-indigo-700",
  HIGH: "bg-orange-100 text-orange-800", HOLD_REQUEST_INFO: "bg-orange-100 text-orange-800", PENDING_MLRO: "bg-orange-100 text-orange-800", ESCALATED_MLRO: "bg-red-100 text-red-700",
  SAR_DRAFTED: "bg-orange-100 text-orange-800", UNVERIFIED: "bg-orange-100 text-orange-800",
  SEVERE: "bg-red-700 text-white", CRITICAL: "bg-red-700 text-white", PROHIBITED: "bg-red-700 text-white", REJECT: "bg-red-700 text-white", REJECTED: "bg-red-700 text-white",
  FAIL: "bg-red-700 text-white", SANCTIONS_ALERT: "bg-red-700 text-white",
};

/** Generic coloured badge for risk levels, workflow statuses and outcomes. */
export function Level({ value }: { value?: string | null }) {
  const v = value || "-";
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${LEVEL_STYLES[v] || "bg-slate-100 text-slate-700"}`}>{v.replace(/_/g, " ")}</span>;
}

export const eur = (n?: number | null) => (n === null || n === undefined ? "-" : "EUR " + Math.round(n).toLocaleString("en-GB"));
