# 15-minute stakeholder demo

Before you start: Admin → **Reset demo data** (restores the exact dataset below). Use two browser windows (normal + private) to hold two personas side by side.

## 1. The 30-second pitch — *Compliance Manager* (`manager.demo`)
**Executive dashboard.** 100 customers, 26 high-risk, 40 open alerts, 5 critical, 10 SARs. "This is the whole financial-crime posture on one screen; every number drills into a queue."
Point at: alert ageing, transaction trend with flagged line, analyst workload (18 unassigned — a staffing story).

## 2. An analyst's day — *Analyst* (`analyst.demo`)
**Work queues.** Pick **EDD review** → open **Layla Haddad** (Lebanon + adverse media). Show the *AI agents* tab: each agent's finding and score, and the plain-English "why". Show the *Screening* tab: confirm or dismiss a hit with a mandatory rationale.
**PEP alerts** → **Rashid Bin Saeed Al-Falasi**: the profile says "Teacher", declared PEP = No, yet screening returns a 100% match to a sovereign-wealth-fund director — an *undeclared PEP* whose stated occupation doesn't fit. The EDD agent triggers on PEP status and requires senior-management approval; the SoF agent notes no source-of-funds evidence is on file and lists the documents to request. The AI recommendation: escalate, complete EDD, get senior approval.
Try to **approve** him as Analyst → blocked: HIGH risk needs a senior role.

## 3. Four-eyes — *Senior Analyst* (`senior.demo`, private window)
Open the same customer → the decision box now works. Record a decision with rationale. Then **Audit trail** — every step by user/AI/system is there, with before/after.

## 4. Sanctions & crypto story — *Analyst* → *MLRO* (`mlro.demo`)
Analyst: **Crypto** → wallet `0xed42…f5ed` (Viktor Kozlov) severity SEVERE: first activity 15 days ago, EUR 87k moved, **1 hop from a sanctioned entity**. Open it for the exposure graph.
MLRO: **MLRO & alerts** → escalation queue → *File SAR* / *More info* / *Close – no SAR* / *Exit relationship*. **SARs** → SAR-2026-0001 (prepared by analyst.demo): narrative, indicators, EUR 45,000 — approve. Show that the preparer *cannot* approve their own SAR (try as analyst).

## 5. Corporates — *Analyst*
**Businesses (KYB/UBO)** → a HIGH one (e.g. Wieczorek Logistics OÜ): layered ownership, UBO resolution, shell indicators.

## 6. Governance — *Compliance Manager*
**QA reviews**: risk-weighted sampling, pass rate. **Regulatory reports**: generate → approve (cannot approve your own).

## 6b. Investigations & FIU — *Senior Analyst* → *MLRO*
**FIU dashboard** → RBI queue → *Open case* on a high-risk subject. Walk the **Workbook** (nine steps), **RBI** hypotheses, **Typologies** (point-by-point indicators), **Network** (mule ring / Kozlov–Baltic; hover an edge for shared identifiers), **Crypto** (Lena Hoffmann: ETH → bridge → BTC → mixer / unlicensed OTC), **SAR / STR** formats (point out they are illustrative). Show permissions: an analyst cannot escalate; escalated cases close by MLRO only. **Operating model**: drag adoption, tick optional modules, expand a team, read the human-led list.

## 7. Close — *Admin* (`admin.demo`)
Users & roles (change a role live), **Reset demo data**. Mention what's real vs simulated (README) and the production checklist.

### Likely questions
* *Is the AI making decisions?* No — transparent rules decide; the LLM only drafts narratives and is optional.
* *Real data?* All synthetic; lists and chain data are simulated, integration points are isolated in `modules/`.
* *Auth?* Demo-grade; SSO/MFA is on the hardening checklist.
