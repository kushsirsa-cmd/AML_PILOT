"use client";
import { useEffect, useState } from "react";
import { api, Json, post, setSession } from "@/lib/api";

const BLURB: Record<string, string> = {
  ANALYST: "Works the queues: KYC/CDD, screening and transaction alerts, drafts SARs.",
  SENIOR_ANALYST: "Approves HIGH-risk customers, completes QA reviews.",
  MLRO: "Decides escalations, approves & files SARs, approves reports.",
  COMPLIANCE_MANAGER: "Oversight: QA, regulatory reports, executive MI.",
  ADMIN: "Manages users and resets the demo dataset.",
};

export default function Login() {
  const [users, setUsers] = useState<Json[]>([]);
  const [pw, setPw] = useState("demo1234");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { api("/auth/users").then((r) => { setUsers(r.users); setPw(r.demo_password); }).catch(() => setErr("Cannot reach the API. If you just started the stack, wait ~20 seconds for the demo data to load, then refresh.")); }, []);

  async function login(username: string) {
    setBusy(username); setErr(null);
    try { const r = await post("/auth/login", { username, password: pw }); setSession(r); window.location.href = r.user.role === "ADMIN" ? "/admin" : "/"; } catch (e) { setErr((e as Error).message); setBusy(null); }
  }
  return (
    <div className="min-h-screen bg-gradient-to-br from-ink-950 via-ink-900 to-[#1e1b4b] px-4 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-10 flex items-center gap-3 text-white">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 text-lg font-bold">A</span>
          <div><div className="text-xl font-semibold">AML Copilot</div><div className="text-sm text-slate-400">AI-assisted financial crime compliance · investor demo</div></div>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight !text-white">Choose a persona to explore the platform</h1>
        <p className="mt-2 max-w-2xl text-slate-400">Every persona sees the same pre-loaded data (100 customers, 50 businesses, 500 transactions) but is permitted different actions — try approving a HIGH-risk customer as an Analyst, then as a Senior Analyst.</p>
        {err && <div className="mt-6 rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{err}</div>}
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {users.map((u) => (
            <button key={u.username} onClick={() => login(u.username)} disabled={!!busy} className="group rounded-2xl border border-white/10 bg-white/5 p-5 text-left transition hover:border-brand-500/60 hover:bg-white/10 disabled:opacity-60">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-500/20 text-sm font-semibold text-brand-100">{u.full_name.split(" ").map((p: string) => p[0]).slice(0, 2).join("")}</span>
                <div><div className="font-medium text-white">{u.full_name}</div><div className="text-xs font-semibold uppercase tracking-wider text-brand-100/80">{u.role_label}</div></div>
              </div>
              <p className="mt-3 text-sm text-slate-400">{BLURB[u.role]}</p>
              <div className="mt-3 text-xs text-slate-500 group-hover:text-slate-300">{busy === u.username ? "Signing in…" : `Sign in as ${u.username} →`}</div>
            </button>
          ))}
        </div>
        <p className="mt-8 text-xs text-slate-500">Demo authentication: one shared password (<code className="text-slate-300">{pw}</code>) for all personas. All data is synthetic; sanctions/PEP lists, blockchain attribution and regulator filings are simulated.</p>
      </div>
    </div>
  );
}
