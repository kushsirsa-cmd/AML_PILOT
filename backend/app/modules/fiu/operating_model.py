"""AML OPERATING MODEL - how much of each financial-crime team's effort can be automated with agentic AI, and what must stay human-led.

HONESTY NOTE: every `auto` figure below is an ESTIMATE by the prototype's author based on typical task structure (data gathering and drafting automate well;
judgement, approval, accountability and regulator dialogue do not). They are NOT benchmarks, vendor claims or regulator statements. Headcounts are
illustrative defaults for a mid-sized firm and are editable in the UI. Regulatory references are indicative - validate with Legal / Compliance.
`auto` already reflects regulatory human-gates: it is the share of the activity's EFFORT an agent can prepare / perform, never the accountability for it."""
from __future__ import annotations

REGS = ["FCA", "FATF", "MAS", "FINTRAC", "EBA"]

# What each regulator / standard expects to remain human-led (indicative). Used for the "must stay human" panel.
HUMAN_ONLY = {
    "FATF": ["Senior-management approval of PEP / high-risk relationships (R.12, R.10 EDD)", "The suspicion determination and STR filing decision (R.20)", "Risk-based approach ownership and risk appetite (R.1)", "Group-wide programme governance (R.18)"],
    "FCA": ["MLRO / nominated officer decisions on internal disclosures and SARs (POCA / MLR 2017 reg 21(5))", "Senior-manager accountability (SM&CR; SMF17) for AML systems and controls (SYSC 6.3)", "Firm-wide risk assessment sign-off (MLR 2017 reg 18)", "Consent (DAML) judgement and regulator engagement"],
    "MAS": ["Senior-management oversight of AML/CFT and approval of high-risk relationships (MAS AML/CFT Notices)", "Suspicion decision and STR filing by an authorised officer", "Model governance and human oversight of AI in decisions (MAS FEAT principles / AI risk management guidance)", "Risk assessment sign-off"],
    "FINTRAC": ["A designated compliance officer for the programme (PCMLTFA / PCMLTFR)", "Reasonable-grounds-to-suspect determination for STRs", "Approval of the risk assessment and written policies", "Two-yearly effectiveness review performed independently"],
    "EBA": ["Management-body accountability and the AML/CFT compliance officer role (EBA internal governance and compliance-officer guidelines)", "Risk-factor weighting and exceptions in the ML/TF risk factors guidelines", "Final EDD and high-risk-third-country relationship approval", "Human accountability where automated decisions affect customers (alongside GDPR Art. 22 safeguards)"],
}

# (activity, share-of-effort %, automatable %, regulators that constrain it, why it stays (partly) human)
def A(n, share, auto, regs=(), why=""):
    return dict(name=n, share=share, auto=auto, regs=list(regs), why=why)


TEAMS = [
    # ---- Tier 1: Onboarding & monitoring --------------------------------------------------------
    dict(code="KYC", name="KYC", tier=1, fte=28, acts=[A("Document capture, OCR and data extraction", 25, 92), A("Identity and liveness verification checks", 20, 85), A("Application completeness chasing", 20, 88), A("Exception handling (mismatches, poor documents)", 20, 55, ["FCA", "EBA"], "Judgement on ambiguous identity evidence"), A("Final approval of non-standard onboarding", 15, 20, ["FATF", "FCA", "MAS"], "Accountable human approval")]),
    dict(code="CDD", name="CDD", tier=1, fte=22, acts=[A("Customer risk-scoring and rating", 25, 85), A("Beneficial ownership structure mapping", 20, 80), A("Registry and public-source checks", 20, 90), A("Risk rating override / exception decisions", 20, 25, ["EBA", "FCA"], "Rating exceptions are a risk-based judgement"), A("Customer outreach and clarification", 15, 60)]),
    dict(code="EDD", name="EDD", tier=1, fte=18, acts=[A("Open-source and adverse media research", 25, 88), A("Evidence collation and dossier drafting", 25, 85), A("Relationship-manager / customer questions", 15, 50), A("Risk assessment of higher-risk customer", 15, 45, ["FATF", "EBA"], "Judgement on residual risk"), A("Senior-management approval (PEPs, high risk)", 20, 8, ["FATF", "FCA", "MAS", "EBA"], "Senior-management approval must be human (R.12 / R.10)")]),
    dict(code="SOF_SOW", name="EDD - SoF/SoW verification", tier=1, fte=10, acts=[A("Collect and classify evidence (payslips, statements, sale deeds)", 30, 85), A("Extract and cross-check amounts against declared wealth", 25, 80), A("Plausibility versus profile and transaction pattern", 20, 60), A("Resolve gaps / red flags with the customer", 15, 40, ["FATF", "EBA"], "Probing explanation is a conversation"), A("Accept or reject SoF/SoW as satisfactory", 10, 12, ["FATF", "FCA"], "Acceptance is a risk decision")]),
    dict(code="SCREENING", name="Screening", tier=1, fte=20, acts=[A("Name screening against lists (batch + real-time)", 20, 98), A("False-positive triage and match resolution", 35, 80), A("PEP / adverse media classification", 20, 70), A("True-match decisions (sanctions / PEP)", 15, 22, ["FCA", "MAS", "FINTRAC"], "A true sanctions match carries legal consequences"), A("List-governance change approval", 10, 30)]),
    dict(code="TM", name="Transaction Monitoring", tier=1, fte=35, acts=[A("Alert generation and enrichment", 20, 98), A("Level-1 alert triage and closing obvious false positives", 35, 75), A("Alert investigation and narrative", 20, 65), A("Escalation judgement", 15, 25, ["FCA", "FATF"], "Escalation is a risk judgement"), A("Scenario sign-off", 10, 20, ["MAS", "EBA"], "Governance of detection logic")]),
    dict(code="PERIODIC", name="Periodic Review", tier=1, fte=16, acts=[A("Scheduling and file refresh requests", 20, 95), A("Data refresh and change detection", 25, 88), A("Re-rating and review summary", 25, 80), A("Customer contact for changes", 15, 50), A("Review sign-off and exit recommendation", 15, 18, ["FCA", "EBA"], "Retain/exit is an accountable decision")]),
    dict(code="EVENT", name="Event-Driven Review", tier=1, fte=12, acts=[A("Trigger detection (adverse media, ownership change, alerts)", 30, 95), A("Assemble case file", 25, 90), A("Impact assessment and re-rating proposal", 25, 70), A("Decision on relationship change", 20, 15, ["FATF", "FCA", "MAS"], "Accountable decision")]),
    dict(code="CRYPTO", name="Crypto Compliance", tier=1, fte=14, acts=[A("Wallet screening and exposure scoring", 25, 95), A("Travel Rule data matching and exceptions", 20, 80), A("Chain tracing and cluster analysis", 20, 75), A("Provider disagreement / attribution review", 15, 40), A("Onboarding / delisting decisions for VASPs and tokens", 20, 15, ["FATF", "MAS", "EBA"], "Business-risk decision; R.15 / R.16 obligations")]),
    # ---- Tier 2: Investigation & intelligence --------------------------------------------------
    dict(code="RBI", name="Risk Based Investigation (RBI)", tier=2, fte=10, acts=[A("Timeline reconstruction", 25, 92), A("Risk-factor correlation and pattern detection", 25, 85), A("Hypothesis testing and next-step design", 20, 55), A("Case prioritisation", 15, 70), A("Escalation recommendation sign-off", 15, 15, ["FCA", "FATF"], "Human accountability for escalation")]),
    dict(code="INVEST", name="Investigations", tier=2, fte=30, acts=[A("Evidence collection across systems", 25, 90), A("Transaction analysis and customer review", 25, 78), A("Case notes and workbook drafting", 20, 85), A("Interviews / customer enquiry (without tipping off)", 10, 20, ["FCA", "FINTRAC"], "Needs trained human judgement; tipping-off risk"), A("Disposition and closure decision", 20, 12, ["FATF", "FCA", "MAS", "FINTRAC"], "Closure with no report is an accountable decision")]),
    dict(code="FIU", name="Financial Intelligence Unit (FIU)", tier=2, fte=15, acts=[A("Intelligence collation and entity resolution", 30, 85), A("Typology and network analysis", 25, 75), A("Intelligence package drafting", 20, 85), A("Suspicion assessment", 15, 25, ["FATF", "FCA", "FINTRAC", "MAS"], "Suspicion is a human legal judgement"), A("Liaison on onward dissemination", 10, 15)]),
    dict(code="LINK", name="Entity Link / Network Analysis", tier=2, fte=6, acts=[A("Shared-identifier graph building", 35, 97), A("Cluster and hidden-association detection", 30, 88), A("Validation of ambiguous links (family / coincidence)", 20, 45), A("Conclusion that parties are connected for reporting", 15, 18, ["FCA", "MAS"], "False links harm customers")]),
    dict(code="SAR", name="SAR / STR", tier=2, fte=12, acts=[A("Fact assembly and evidence extraction", 25, 92), A("Narrative drafting and typology coding", 30, 85), A("Quality check against regulator expectations", 15, 60), A("MLRO review and approval", 15, 5, ["FCA", "FATF", "MAS", "FINTRAC"], "Statutory role - cannot be delegated to a model"), A("Filing, consent handling and follow-up", 15, 45)]),
    dict(code="MLRO", name="MLRO Office", tier=2, fte=6, acts=[A("Queue management, prepared decision packs", 25, 85), A("Review of internal reports and SAR decisions", 25, 8, ["FCA", "FATF", "FINTRAC"], "Statutory personal responsibility"), A("MI, board and regulator reporting drafts", 20, 80), A("Regulator and law-enforcement dialogue", 15, 5, ["FCA", "MAS"], "Personal accountability"), A("Programme oversight and escalation to the board", 15, 10, ["FCA", "EBA", "FINTRAC"], "Governance duty")]),
    dict(code="SANCTIONS", name="Sanctions Compliance", tier=2, fte=12, acts=[A("List ingestion and change impact analysis", 25, 92), A("Payment / customer hit review prep", 30, 75), A("Evasion indicator analysis", 15, 60), A("Licence, block and reject decisions", 20, 8, ["FCA", "FINTRAC", "MAS", "EBA"], "Legal consequences; strict liability regimes"), A("Regulator / OFSI-type reporting", 10, 30)]),
    dict(code="LEA", name="Law Enforcement Liaison", tier=2, fte=5, acts=[A("Production-order / request intake and logging", 30, 85), A("Record retrieval and pack assembly", 30, 85), A("Legal review of the request", 20, 15, ["FCA", "FINTRAC"], "Legal judgement; disclosure limits"), A("Disclosure and relationship with agencies", 20, 8)]),
    # ---- Tier 3: Governance & assurance --------------------------------------------------------
    dict(code="EWRA", name="Financial Crime Risk Assessment (EWRA)", tier=3, fte=7, acts=[A("Data gathering and metric calculation", 30, 88), A("Inherent / residual risk scoring workings", 25, 70), A("Narrative and control-effectiveness drafting", 20, 70), A("Risk appetite and rating sign-off", 25, 8, ["FCA", "FATF", "MAS", "FINTRAC", "EBA"], "Board / senior-management ownership of the risk assessment")]),
    dict(code="TESTING", name="Compliance Testing / Assurance", tier=3, fte=10, acts=[A("Sample selection and data pulls", 25, 92), A("Test execution against procedures", 30, 75), A("Root-cause and thematic analysis", 20, 55), A("Conclusions, ratings and findings sign-off", 15, 12, ["FCA", "EBA", "FINTRAC"], "Independent assurance judgement"), A("Remediation tracking", 10, 80)]),
    dict(code="QA", name="Quality Assurance", tier=3, fte=14, acts=[A("Sample selection and checklist scoring", 40, 85), A("Narrative quality review", 20, 65), A("Calibration and disagreement resolution", 15, 20, ["FCA", "EBA"], "Reviewer judgement"), A("Feedback to teams and trend MI", 15, 70), A("Four-eyes sign-off of high-risk decisions", 10, 5, ["FCA", "FATF", "MAS"], "Four-eyes must be human")]),
    dict(code="MODEL", name="Model Risk & TM Tuning", tier=3, fte=8, acts=[A("Below-the-line testing and data analysis", 30, 85), A("Threshold and scenario optimisation proposals", 25, 70), A("Model documentation and validation packs", 20, 70), A("Independent validation and change approval", 25, 10, ["MAS", "EBA", "FCA"], "Governance of models; AI oversight expectations")]),
    dict(code="REMED", name="Remediation / Offboarding", tier=3, fte=12, acts=[A("Population identification and prioritisation", 20, 92), A("File remediation and refresh", 35, 82), A("Customer communications drafting", 15, 80), A("Exit decisions", 20, 12, ["FCA", "EBA", "FATF"], "Account closure affects customers; fairness"), A("Funds-return handling", 10, 40)]),
    dict(code="WATCHLIST", name="Watchlist & Data Management", tier=3, fte=8, acts=[A("List sourcing, normalisation and loading", 35, 95), A("Data quality monitoring", 25, 90), A("Whitelist / good-guy list management", 20, 55), A("List-selection governance", 20, 20, ["FCA", "MAS"], "Which lists to use is a policy decision")]),
    dict(code="REGREP", name="Regulatory Reporting", tier=3, fte=9, acts=[A("Data extraction and consolidation", 35, 95), A("Report population and reconciliation", 25, 88), A("Narrative commentary", 15, 75), A("Submission attestation", 25, 10, ["FCA", "MAS", "FINTRAC", "EBA"], "Attestation is a named-person accountability")]),
    dict(code="TRAINING", name="Training & Awareness", tier=3, fte=5, acts=[A("Content drafting and personalisation", 40, 80), A("Delivery, tracking and chasing completion", 35, 92), A("Role-specific scenarios and SME input", 15, 45), A("Board / senior-manager sessions", 10, 10, ["FCA", "EBA"], "Credibility with senior audience")]),
    dict(code="POLICY", name="Policy & Regulatory Change", tier=3, fte=7, acts=[A("Horizon scanning and change summaries", 30, 88), A("Gap analysis against policies", 25, 75), A("Policy drafting", 20, 65), A("Interpretation of rules and approval of policy", 25, 8, ["FCA", "FATF", "MAS", "FINTRAC", "EBA"], "Interpretation and adoption are accountable decisions")]),
]

OPTIONAL = [
    dict(code="CORRESPONDENT", name="Correspondent Banking (optional)", tier=2, fte=6, optional=True, acts=[A("Respondent due-diligence collation", 40, 85), A("Wolfsberg-style questionnaire analysis", 25, 75), A("Nested-relationship and risk analysis", 15, 50), A("Approval to open / continue", 20, 8, ["FATF", "EBA", "FCA"], "Senior-management approval (R.13)")]),
    dict(code="TRADE", name="Trade Finance / TBML (optional)", tier=2, fte=6, optional=True, acts=[A("Document extraction (invoices, bills of lading)", 35, 90), A("Price, quantity and route plausibility checks", 30, 75), A("Dual-use and sanctions screening of goods / vessels", 15, 70), A("Transaction approval / rejection", 20, 12, ["FATF", "FCA", "MAS"], "Trade-based risk judgement")]),
    dict(code="FRAUD", name="Fraud (optional)", tier=2, fte=12, optional=True, acts=[A("Real-time scoring and alert enrichment", 40, 95), A("Case triage and linkage to AML", 25, 75), A("Customer contact and recovery", 20, 40), A("Liability and reimbursement decisions", 15, 15)]),
    dict(code="ABC", name="Anti-Bribery & Corruption (optional)", tier=3, fte=4, optional=True, acts=[A("Third-party due diligence collation", 40, 85), A("Gifts / hospitality register analysis", 25, 80), A("Risk assessment of intermediaries", 15, 50), A("Approvals and investigations of allegations", 20, 8)]),
    dict(code="WHISTLE", name="Whistleblowing (optional)", tier=3, fte=3, optional=True, acts=[A("Case intake, logging and routing", 40, 80), A("Evidence organisation", 25, 70), A("Investigation and interviews", 20, 10), A("Outcome decisions and protection of the reporter", 15, 3)]),
]

TIERS = {1: "Onboarding & monitoring", 2: "Investigation & intelligence", 3: "Governance & assurance"}
HUMAN_LED_THRESHOLD = 25  # an activity at or below this automation share is treated as human-led


def default_assumptions() -> dict:
    return dict(adoption=0.7, optional=[], fte={}, regulators=list(REGS),
                notes=["Automation % = share of an activity's effort an agent can prepare or perform (author's estimate - not a benchmark).",
                       "'Adoption' scales technical potential to what is realistically achieved after change, controls and exceptions (default 70%).",
                       "Releasable FTE is capacity, not a headcount recommendation - regulators expect resourcing to stay adequate for the risk."])


def calculate(opts: dict | None = None) -> dict:
    o = {**default_assumptions(), **(opts or {})}
    adoption = max(0.0, min(1.0, float(o["adoption"])))
    regs = set(o.get("regulators") or REGS)
    teams_src = TEAMS + [t for t in OPTIONAL if t["code"] in set(o.get("optional") or [])]
    out = []
    for t in teams_src:
        assert sum(a["share"] for a in t["acts"]) == 100, t["code"]
        fte = float(o["fte"].get(t["code"], t["fte"]))
        potential = sum(a["share"] * a["auto"] for a in t["acts"]) / 100
        realised = potential * adoption
        acts = []
        for a in t["acts"]:
            human_led = a["auto"] <= HUMAN_LED_THRESHOLD
            acts.append(dict(**a, human_led=human_led, effective_auto=round(a["auto"] * adoption, 1), constrained_by=[r for r in a["regs"] if r in regs]))
        out.append(dict(code=t["code"], name=t["name"], tier=t["tier"], optional=bool(t.get("optional")), fte=fte, potential_pct=round(potential, 1), realised_pct=round(realised, 1),
                        human_pct=round(100 - realised, 1), releasable_fte=round(fte * realised / 100, 1), activities=acts,
                        human_led=[a["name"] for a in acts if a["human_led"]], regulated_human_gates=sorted({r for a in acts if a["human_led"] for r in a["constrained_by"]})))
    tot_fte = sum(t["fte"] for t in out) or 1
    tiers = []
    for n, label in TIERS.items():
        ts = [t for t in out if t["tier"] == n]
        f = sum(t["fte"] for t in ts) or 1
        tiers.append(dict(tier=n, label=label, teams=len(ts), fte=round(sum(t["fte"] for t in ts), 1), potential_pct=round(sum(t["potential_pct"] * t["fte"] for t in ts) / f, 1),
                          realised_pct=round(sum(t["realised_pct"] * t["fte"] for t in ts) / f, 1), releasable_fte=round(sum(t["releasable_fte"] for t in ts), 1)))
    overall = dict(teams=len(out), fte=round(tot_fte, 1), potential_pct=round(sum(t["potential_pct"] * t["fte"] for t in out) / tot_fte, 1),
                   realised_pct=round(sum(t["realised_pct"] * t["fte"] for t in out) / tot_fte, 1), releasable_fte=round(sum(t["releasable_fte"] for t in out), 1))
    overall["human_pct"] = round(100 - overall["realised_pct"], 1)
    sens = [dict(adoption=a, realised_pct=round(overall["potential_pct"] * a, 1)) for a in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]
    human_led = sorted([dict(team=t["name"], activity=a["name"], auto=a["auto"], why=a["why"], regs=a["constrained_by"]) for t in out for a in t["activities"] if a["human_led"]], key=lambda r: r["team"])
    by_reg = {r: HUMAN_ONLY[r] for r in REGS if r in regs}
    return dict(overall=overall, tiers=tiers, teams=out, sensitivity=sens, human_led_activities=human_led, human_only_by_regulator=by_reg, assumptions=o,
                optional_available=[dict(code=t["code"], name=t["name"], fte=t["fte"]) for t in OPTIONAL],
                disclaimer=("All automation percentages and headcounts are the prototype author's ESTIMATES with editable defaults - not benchmarks or vendor claims. "
                            "Regulatory expectations are indicative summaries; validate with Legal / Compliance before use in a business case. "
                            "No regulator permits delegating accountability for suspicion, approval of high-risk relationships or SAR/STR decisions to an AI system."))
