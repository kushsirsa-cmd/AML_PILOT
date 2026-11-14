"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, getSession, Json, SessionUser, setSession } from "@/lib/api";

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);
const I = {
  dash: "M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zM13 3v6h8V3h-8z",
  ops: "M4 19V5m0 14h16M8 15l3-4 3 2 4-6",
  work: "M9 11l3 3 8-8M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-5",
  users: "M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2m18 0v-2a4 4 0 00-3-3.9M16 4.1a4 4 0 010 7.8M10 10a4 4 0 100-8 4 4 0 000 8z",
  add: "M12 5v14M5 12h14",
  biz: "M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6M9 10h.01M15 10h.01",
  scan: "M21 21l-4.3-4.3M11 18a7 7 0 100-14 7 7 0 000 14z",
  tx: "M7 7h13l-3-3m3 3l-3 3M17 17H4l3-3m-3 3l3 3",
  coin: "M12 6v12m-3-2.8c.6.9 1.7 1.3 3 1.3 1.7 0 3-.8 3-2s-1.3-1.7-3-2-3-.8-3-2 1.3-2 3-2c1.3 0 2.4.4 3 1.3M12 21a9 9 0 100-18 9 9 0 000 18z",
  globe: "M12 21a9 9 0 100-18 9 9 0 000 18zM3.6 9h16.8M3.6 15h16.8M12 3a14 14 0 010 18M12 3a14 14 0 000 18",
  cal: "M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z",
  shield: "M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6l8-3z",
  doc: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zM14 3v5h5M9 13h6M9 17h6",
  check: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  report: "M9 17v-6m4 6V7m4 10v-3M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z",
  log: "M12 8v4l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z",
  fiu: "M3 7l9-4 9 4-9 4-9-4zM3 12l9 4 9-4M3 17l9 4 9-4",
  net: "M5 7a2 2 0 100-4 2 2 0 000 4zm14 0a2 2 0 100-4 2 2 0 000 4zM12 21a2 2 0 100-4 2 2 0 000 4zM6.5 6.5l4.5 11m6.5-11L13 17.5M7 5h10",
  model: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  cog: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
};

const SECTIONS: { title: string; items: { href: string; label: string; icon: string; admin?: boolean }[] }[] = [
  { title: "Overview", items: [{ href: "/", label: "Executive dashboard", icon: I.dash }, { href: "/operations", label: "Operations", icon: I.ops }, { href: "/work", label: "Work queues", icon: I.work }] },
  { title: "Onboarding & KYC", items: [{ href: "/customers", label: "Customers", icon: I.users }, { href: "/customers/new", label: "New customer", icon: I.add }, { href: "/kyb", label: "Businesses (KYB/UBO)", icon: I.biz }, { href: "/reviews", label: "Periodic & event reviews", icon: I.cal }] },
  { title: "Monitoring", items: [{ href: "/screening", label: "Screening", icon: I.scan }, { href: "/transactions", label: "Transactions", icon: I.tx }, { href: "/crypto", label: "Crypto & blockchain", icon: I.coin }, { href: "/travel-rule", label: "Travel Rule", icon: I.globe }] },
  { title: "Investigations & FIU", items: [{ href: "/fiu", label: "FIU dashboard", icon: I.fiu }, { href: "/cases", label: "Case queues", icon: I.work }, { href: "/network", label: "Network analysis", icon: I.net }, { href: "/operating-model", label: "Operating model", icon: I.model }] },
  { title: "Cases & governance", items: [{ href: "/mlro", label: "MLRO & alerts", icon: I.shield }, { href: "/sars", label: "SARs", icon: I.doc }, { href: "/qa", label: "QA reviews", icon: I.check }, { href: "/reports", label: "Regulatory reports", icon: I.report }, { href: "/audit", label: "Audit trail", icon: I.log }] },
  { title: "Administration", items: [{ href: "/admin", label: "Users & demo data", icon: I.cog, admin: true }] },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [meta, setMeta] = useState<Json>(null);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    const s = getSession();
    setUser(s?.user ?? null);
    setReady(true);
    if (!s && path !== "/login") router.replace("/login");
    if (s) api("/meta").then(setMeta).catch(() => setMeta({ error: true }));
  }, [path, router]);

  if (path === "/login") return <>{children}</>;
  if (!ready || !user) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">Loading…</div>;

  const active = (href: string) => (href === "/" ? path === "/" : path === href || (path.startsWith(href + "/") && !(href === "/customers" && path.startsWith("/customers/new"))));
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto bg-ink-900 text-slate-300 lg:flex">
        <Link href="/" className="flex items-center gap-2.5 px-5 py-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">A</span>
          <span><span className="block text-[15px] font-semibold leading-tight text-white">AML Copilot</span><span className="block text-[11px] text-slate-400">Financial crime platform</span></span>
        </Link>
        <nav className="flex-1 space-y-5 px-3 pb-6">
          {SECTIONS.map((sec) => (
            <div key={sec.title}>
              <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">{sec.title}</div>
              {sec.items.filter((i) => !i.admin || user.role === "ADMIN").map((i) => (
                <Link key={i.href} href={i.href} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition ${active(i.href) ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}>
                  <Icon d={i.icon} />{i.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 p-4 text-[11px] text-slate-500">Demo environment · simulated data only</div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
          <div className="text-sm text-slate-500">{SECTIONS.flatMap((s) => s.items).find((i) => active(i.href))?.label ?? "AML Copilot"}</div>
          <div className="flex items-center gap-3">
            {meta?.error ? <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs text-red-700">API unreachable</span> : meta && (
              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${meta.llm_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`} title={meta.llm_active ? meta.model : "Set ANTHROPIC_API_KEY to switch case summaries from rules to Claude"}>
                {meta.llm_active ? "● Claude AI on" : "○ AI: rules engine"}
              </span>
            )}
            <div className="relative">
              <button onClick={() => setMenu(!menu)} className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left hover:bg-slate-50">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">{user.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span>
                <span className="hidden sm:block"><span className="block text-[13px] font-medium leading-tight text-slate-800">{user.full_name}</span><span className="block text-[11px] leading-tight text-slate-500">{user.role_label}</span></span>
              </button>
              {menu && (
                <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
                  <div className="px-3 py-2 text-xs text-slate-500">{user.email}</div>
                  <button className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { setSession(null); window.location.href = "/login"; }}>Switch user / sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
