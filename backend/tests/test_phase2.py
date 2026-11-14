import pytest

MLRO = {"X-Analyst": "mlro.demo"}
QA = {"X-Analyst": "senior.demo"}
ANALYST = {"X-Analyst": "analyst.demo"}


def corp(client, name):
    return next(c for c in client.get("/api/kyb/corporates").json() if c["legal_name"] == name)


def review(client, name):
    return client.get(f"/api/kyb/corporates/{corp(client, name)['id']}").json()["review"]


# ---------------------------------------------------------------- KYB / UBO / ownership
def test_kyb_ratings(client):
    assert corp(client, "Nordic Software AB")["risk_rating"] == "LOW"
    assert corp(client, "Baltic Trade Ventures OÜ")["risk_rating"] == "PROHIBITED"
    assert corp(client, "Helix Digital Assets Ltd")["risk_rating"] in ("HIGH", "PROHIBITED")
    assert corp(client, "Alpine Consulting GmbH")["risk_rating"] in ("MEDIUM", "HIGH")


def test_effective_ownership_through_layers(client):
    r = review(client, "Baltic Trade Ventures OÜ")
    ubos = {u["name"]: u for u in r["ubo_verification"]}
    assert ubos["Viktor Kozlov"]["effective_pct"] == pytest.approx(30.0)
    flags = {f["code"] if isinstance(f, dict) else f for f in r["structure"]["red_flags"]}
    assert {"SECRECY_JURISDICTION", "TRUST_IN_CHAIN", "NOMINEES", "BEARER_SHARES"} <= flags
    assert r["ubo_status"] != "VERIFIED"


def test_circular_and_unaccounted_ownership_detected(client):
    flags = {f["code"] if isinstance(f, dict) else f for f in review(client, "Helix Digital Assets Ltd")["structure"]["red_flags"]}
    assert "CIRCULAR_OWNERSHIP" in flags
    flags = {f["code"] if isinstance(f, dict) else f for f in review(client, "Alpine Consulting GmbH")["structure"]["red_flags"]}
    assert "UNACCOUNTED_OWNERSHIP" in flags


def test_cannot_approve_prohibited_or_unverified(client):
    for name in ("Baltic Trade Ventures OÜ", "Alpine Consulting GmbH"):
        r = client.post(f"/api/kyb/corporates/{corp(client, name)['id']}/decision", json={"decision": "APPROVE", "note": "looks fine"})
        assert r.status_code == 409


def test_structure_validation(client):
    cid = corp(client, "Nordic Software AB")["id"]
    bad = {"nodes": [{"key": "a", "name": "A", "node_type": "PERSON"}], "edges": [{"owner": "zzz", "owned": "ROOT", "percentage": 10}]}
    assert client.put(f"/api/kyb/corporates/{cid}/structure", json=bad).status_code == 422


def test_new_corporate_end_to_end(client):
    body = dict(legal_name="Test Widgets Ltd", country_of_incorporation="Ireland", industry="Retail", operating_countries="Ireland",
                structure=dict(nodes=[dict(key="p", name="Jane Doe", node_type="PERSON", country="Ireland", dob="1980-01-01", id_verified=True)],
                               edges=[dict(owner="p", owned="ROOT", percentage=100)]))
    r = client.post("/api/kyb/corporates", json=body)
    assert r.status_code == 201
    d = r.json()
    assert d["review"]["ubo_status"] == "VERIFIED"
    ok = client.post(f"/api/kyb/corporates/{d['corporate']['id']}/decision", json={"decision": "APPROVE", "note": "UBO verified, low risk"})
    assert ok.status_code == 200 and ok.json()["corporate"]["status"] == "ACTIVE"


# ---------------------------------------------------------------- crypto
def wallet_of(client, name):
    return next(w for w in client.get("/api/crypto/wallets").json() if w["owner"] and w["owner"]["name"] == name)


def test_wallet_risk_levels(client):
    assert wallet_of(client, "Katarzyna Nowak")["risk_level"] == "LOW"
    assert wallet_of(client, "Viktor Kozlov")["risk_level"] == "SEVERE"  # direct sanctioned receipt forces SEVERE
    assert wallet_of(client, "Marek Zielinski")["risk_level"] in ("MEDIUM", "HIGH", "SEVERE")


def test_analysis_view_has_graph_patterns_and_traces(client):
    w = wallet_of(client, "Marek Zielinski")
    a = client.get(f"/api/crypto/wallets/{w['id']}/analysis").json()
    assert any(p["pattern"] == "STRUCTURING" for p in a["patterns"])
    assert a["graph"]["nodes"] and a["graph"]["edges"] and a["counterparties"]
    v = client.get(f"/api/crypto/wallets/{wallet_of(client, 'Viktor Kozlov')['id']}/analysis").json()
    assert v["exposure"]["sources_direct_pct"].get("SANCTIONED", 0) > 0 or v["overrides"]


def test_adhoc_screen_and_unknown_address(client):
    labels = client.get("/api/crypto/labels").json()
    mixer = next(l for l in labels if l["category"] == "MIXER")
    assert client.post("/api/crypto/screen", json={"address": mixer["address"]}).status_code == 200
    assert client.post("/api/crypto/screen", json={"address": "0x" + "ab" * 20}).status_code == 404


def test_wallet_screening_raised_alert_and_audit(client):
    alerts = client.get("/api/alerts").json()
    assert any(a["source"] == "CRYPTO" and a["severity"] in ("HIGH", "CRITICAL") for a in alerts)
    audit_rows = client.get("/api/audit?action=WALLET_SCREENED").json()
    assert any(r["action"] == "WALLET_SCREENED" for r in (audit_rows["items"] if isinstance(audit_rows, dict) else audit_rows))


def test_customer_rating_reflects_crypto(client):
    c = next(x for x in client.get("/api/customers").json() if x["full_name"] == "Viktor Kozlov")
    assert c["risk_rating"] == "PROHIBITED"


# ---------------------------------------------------------------- travel rule
def base(**kw):
    d = dict(direction="OUT", amount_eur=5000, asset="USDT", counterparty_vasp="NordEx",
             originator=dict(name="Jane Roe", account="0xabc0000000", address="1 Main St, Berlin", dob="1985-01-01"),
             beneficiary=dict(name="John Poe", account="0xdef0000000"))
    d.update(kw)
    return d


def test_travel_rule_accepts_complete_transfer(client):
    r = client.post("/api/travel-rule/evaluate", json=base()).json()
    assert r["status"] in ("ACCEPT", "ACCEPT_WITH_REVIEW")


def test_travel_rule_below_threshold_not_blocked(client):
    r = client.post("/api/travel-rule/evaluate", json=base(amount_eur=500, originator=dict(name="Jane Roe", account="0xabc0000000"), beneficiary=dict(name="John Poe", account="0xdef0000000"))).json()
    assert r["status"] in ("ACCEPT", "ACCEPT_WITH_REVIEW")  # no address/DOB needed below the threshold


def test_travel_rule_missing_data_holds(client):
    r = client.post("/api/travel-rule/evaluate", json=base(beneficiary=dict(account="0xdef0000000"))).json()
    assert r["status"] == "HOLD_REQUEST_INFO"


def test_travel_rule_unlicensed_vasp_and_sanctions_reject(client):
    assert client.post("/api/travel-rule/evaluate", json=base(counterparty_vasp="OffshoreFX")).json()["status"] == "REJECT"
    assert client.post("/api/travel-rule/evaluate", json=base(counterparty_vasp="OldCoin Exchange")).json()["status"] == "REJECT"
    r = client.post("/api/travel-rule/evaluate", json=base(direction="IN", originator=dict(name="Viktor Kozlov", account="0x1", address="Cyprus", dob="1968-03-14"))).json()
    assert r["status"] == "REJECT"


def test_travel_rule_self_hosted_needs_proof_and_resolution_flow(client):
    r = client.post("/api/travel-rule/check", json=base(self_hosted=True, counterparty_vasp=None, ownership_proof=False,
                                                         beneficiary=dict(name="John Poe", account="0xdef0000000")))
    assert r.status_code == 201 and r.json()["status"] == "HOLD_REQUEST_INFO"
    tid = r.json()["id"]
    assert client.post(f"/api/travel-rule/transfers/{tid}/resolve", json={"action": "RELEASE", "note": "still missing proof"}).status_code == 409
    ok = client.post(f"/api/travel-rule/transfers/{tid}/resolve", json={"action": "RELEASE", "note": "proof received via signed message", "ownership_proof": True})
    assert ok.status_code == 200


# ---------------------------------------------------------------- alerts, MLRO, SAR
def test_alert_close_requires_rationale(client):
    a = next(x for x in client.get("/api/alerts").json() if x["status"] == "OPEN")
    assert client.post(f"/api/alerts/{a['id']}/action", json={"action": "CLOSE", "note": "no"}).status_code == 422
    assert client.post(f"/api/alerts/{a['id']}/action", json={"action": "START_REVIEW"}).json()["status"] == "IN_REVIEW"


def test_mlro_decision_requires_role_and_escalated_state(client):
    open_alert = next(x for x in client.get("/api/alerts").json() if x["status"] in ("OPEN", "IN_REVIEW"))
    body = {"decision": "CLOSE_NO_SAR", "rationale": "reviewed, not suspicious"}
    assert client.post(f"/api/mlro/alerts/{open_alert['id']}/decision", json=body).status_code == 403
    assert client.post(f"/api/mlro/alerts/{open_alert['id']}/decision", json=body, headers=MLRO).status_code == 409


def test_sar_lifecycle_four_eyes_and_xml(client):
    sar = next(s for s in client.get("/api/sars?status=PENDING_MLRO").json() if s["subject_name"] == "Viktor Kozlov")
    assert sar["prepared_by"] == "analyst.demo"
    d = {"decision": "APPROVE", "note": "grounds are clear"}
    assert client.post(f"/api/sars/{sar['id']}/decision", json=d, headers=ANALYST).status_code == 403  # role
    assert client.post(f"/api/sars/{sar['id']}/decision", json=d, headers={"X-Analyst": "manager.demo"}).status_code == 403  # only the MLRO decides SARs
    assert client.post(f"/api/sars/{sar['id']}/file", headers=MLRO).status_code == 409  # not yet approved
    assert client.post(f"/api/sars/{sar['id']}/decision", json=d, headers=MLRO).json()["status"] == "APPROVED"
    f = client.post(f"/api/sars/{sar['id']}/file", headers=MLRO).json()
    assert f["status"] == "FILED" and f["filing_reference"].startswith("FIU-SIM-")
    xml = client.get(f"/api/sars/{sar['id']}/xml")
    assert xml.status_code == 200 and "<report>" in xml.text and sar["reference"] in xml.text
    assert client.put(f"/api/sars/{sar['id']}/narrative", json={"narrative": "x" * 80}).status_code == 409


def test_sar_four_eyes_preparer_cannot_approve_own(client):
    c = next(x for x in client.get("/api/customers").json() if x["full_name"] == "Ivan Petrov")
    s = client.post("/api/sars/generate", json={"subject_type": "customer", "subject_id": c["id"]}, headers=MLRO).json()
    assert s["prepared_by"] == "mlro.demo"
    assert client.post(f"/api/sars/{s['id']}/submit", headers=MLRO).status_code == 200
    r = client.post(f"/api/sars/{s['id']}/decision", json={"decision": "APPROVE", "note": "self approval"}, headers=MLRO)
    assert r.status_code == 403 and "Four-eyes" in r.json()["detail"]


def test_sar_generate_and_submit_validation(client):
    c = next(x for x in client.get("/api/customers").json() if x["full_name"] == "Marek Zielinski")
    s = client.post("/api/sars/generate", json={"subject_type": "customer", "subject_id": c["id"]}).json()
    assert s["status"] == "DRAFT" and not s["narrative_gaps"] and "STRUCTURING" in " ".join(s["typologies"]).upper()
    sid = s["id"]
    assert client.put(f"/api/sars/{sid}/narrative", json={"narrative": "Too vague. " * 10}).status_code == 200
    assert client.post(f"/api/sars/{sid}/submit").status_code == 422  # missing sections
    assert client.put(f"/api/sars/{sid}/narrative", json={"narrative": s["narrative"]}).status_code == 200
    assert client.post(f"/api/sars/{sid}/submit").json()["status"] == "PENDING_MLRO"
    assert client.post("/api/sars/generate", json={"subject_type": "customer", "subject_id": 99999}).status_code == 404


def test_mlro_dashboard(client):
    k = client.get("/api/mlro/dashboard").json()["kpis"]
    assert k["open_alerts"] >= 1 and "sars_filed" in k


# ---------------------------------------------------------------- QA
def test_qa_prechecks_flag_weak_decisions(client):
    items = client.get("/api/qa/reviews").json()
    weak = [q for q in items if q["precheck"]]
    assert weak, "seeded weak decisions should be auto-flagged"


def test_qa_four_eyes_and_scoring(client):
    pending = client.get("/api/qa/reviews?status=PENDING").json()
    q = next(x for x in pending if x["decision_maker"] == "analyst.demo")
    crit = client.get("/api/qa/checklist").json()["criteria"]
    ok = {k: "PASS" for k in crit}
    assert client.post(f"/api/qa/reviews/{q['id']}/complete", json={"checklist": ok}, headers=ANALYST).status_code == 403  # analysts cannot QA
    assert client.post(f"/api/qa/reviews/{q['id']}/complete", json={"checklist": {"decision_supported_by_evidence": "PASS"}}, headers=QA).status_code == 422
    fail = dict(ok, rationale_documented="FAIL")
    assert client.post(f"/api/qa/reviews/{q['id']}/complete", json={"checklist": fail}, headers=QA).status_code == 422  # findings required
    r = client.post(f"/api/qa/reviews/{q['id']}/complete", json={"checklist": fail, "findings": "Rationale is one word."}, headers=QA).json()
    assert r["outcome"] == "FAIL" and r["reviewer"] == "senior.demo"
    assert client.post(f"/api/qa/reviews/{q['id']}/complete", json={"checklist": ok}, headers=QA).status_code == 409
    dash = client.get("/api/qa/dashboard").json()
    assert dash["completed"] >= 1 and any(a["analyst"] == "analyst.demo" for a in dash["by_analyst"])


def test_qa_reviewer_cannot_review_own_decision(client):
    pending = client.get("/api/qa/reviews?status=PENDING").json()
    own = next(x for x in pending if x["decision_maker"] == "senior.demo")
    ok = {k: "PASS" for k in client.get("/api/qa/checklist").json()["criteria"]}
    r = client.post(f"/api/qa/reviews/{own['id']}/complete", json={"checklist": ok}, headers=QA)
    assert r.status_code == 403 and "four-eyes" in r.json()["detail"].lower()


def test_qa_sampling_is_idempotent(client):
    client.post("/api/qa/sample", json={"days": 30, "low_risk_rate": 1.0})
    again = client.post("/api/qa/sample", json={"days": 30, "low_risk_rate": 1.0}).json()
    assert again["created"] == 0


# ---------------------------------------------------------------- reporting
def test_report_lifecycle(client):
    types = client.get("/api/reports/types").json()
    assert len(types) == 6
    for t in types:
        r = client.post("/api/reports/generate", json={"report_type": t})
        assert r.status_code == 201, t
    rid = client.post("/api/reports/generate", json={"report_type": "SAR_STATISTICS"}, headers={"X-Analyst": "analyst.demo"}).json()["id"]
    assert client.post(f"/api/reports/{rid}/submit", headers=MLRO).status_code == 409  # not approved
    own = client.post("/api/reports/generate", json={"report_type": "KYB_UBO"}, headers=MLRO).json()["id"]
    r = client.post(f"/api/reports/{own}/approve", headers=MLRO)
    assert r.status_code == 403 and "Four-eyes" in r.json()["detail"]  # generator cannot approve own report
    assert client.post(f"/api/reports/{rid}/approve", headers=ANALYST).status_code == 403  # role
    assert client.post(f"/api/reports/{own}/approve", headers={"X-Analyst": "manager.demo"}).json()["status"] == "APPROVED"  # compliance manager may approve
    assert client.post(f"/api/reports/{rid}/approve", headers=MLRO).json()["status"] == "APPROVED"
    s = client.post(f"/api/reports/{rid}/submit", headers=MLRO).json()
    assert s["status"] == "SUBMITTED" and s["submission_reference"].startswith("REG-SIM-")
    assert client.get(f"/api/reports/{rid}/csv").status_code == 200
    assert client.post("/api/reports/generate", json={"report_type": "NOPE"}).status_code == 422
    assert client.post("/api/reports/generate", json={"report_type": "KYB_UBO", "period_start": "2026-02-01", "period_end": "2026-01-01"}).status_code == 422
