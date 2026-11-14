from datetime import date

from app.screening_service import screen


def rating(customers, name):
    return customers[name]["risk_rating"]


def test_seed_ratings_cover_all_outcomes(customers):
    assert len(customers) == 100
    assert rating(customers, "Katarzyna Nowak") == "LOW"
    assert rating(customers, "Rahul Verma") == "MEDIUM"
    assert rating(customers, "Aleksandra Nowicka-Wrona") == "HIGH"  # declared PEP floor
    assert rating(customers, "Viktor Kozlov") == "PROHIBITED"  # strong sanctions match
    assert rating(customers, "Farid Karimi") == "PROHIBITED"  # prohibited jurisdiction
    assert rating(customers, "Isabella Marchetti") == "HIGH"  # undeclared PEP found by screening
    assert rating(customers, "Lena Hoffmann") in ("MEDIUM", "HIGH")


def test_screening_dob_and_nationality_suppress_false_positive():
    # exact name, different DOB, different nationality -> below threshold
    res = screen("Ivan Petrov", date(1991, 5, 5), "Bulgaria")
    assert res["SANCTIONS"] == []
    # same name, same nationality, wrong DOB -> only a weak hit
    weak = screen("Ivan Petrov", date(1991, 5, 5), "Russia")["SANCTIONS"]
    assert weak and weak[0]["strength"] == "WEAK"
    # exact alias + DOB + nationality -> strong
    strong = screen("Viktor Kozlov", date(1968, 3, 14), "Russia")["SANCTIONS"][0]
    assert strong["strength"] == "STRONG" and strong["confidence"] >= 90


def test_screening_handles_diacritics_and_word_order():
    assert screen("Joao  Pedro  Carvalho", None, "Portugal")["PEP"]
    assert screen("Carvalho João Pedro", date(1963, 12, 9), "Portugal")["PEP"][0]["confidence"] >= 90
    assert screen("Wiśniewski Piotr", date(1981, 2, 9), "Poland")["SANCTIONS"] == []


def test_expected_activity_annualisation():
    from app.agents.base import annualised_expected_activity as f

    assert f("Salary credits of about EUR 4,200 per month, rent") == 4200 * 12
    assert f("Monthly inflows of EUR 20,000 in advisory fees plus annual dividends of about EUR 150,000.") == 20000 * 12 + 150000
    assert f("Incoming wires of EUR 1.5m per year since 2019") == 1_500_000
    assert f("no figures here") is None


def test_detail_contains_all_agent_outputs(client, customers):
    d = client.get(f"/api/customers/{customers['Katarzyna Nowak']['id']}").json()
    assert set(d["assessments"]) == {"kyc", "screening", "cdd", "edd", "sof", "sow", "risk", "summary"}
    note = d["assessments"]["summary"]["output"]["case_note"]
    for section in ("CUSTOMER PROFILE", "RISKS IDENTIFIED", "SCREENING RESULTS", "FINAL RECOMMENDATION"):
        assert section in note
    assert d["assessments"]["risk"]["output"]["reasoning"]


def test_incomplete_customer_flags_missing_info(client, customers):
    d = client.get(f"/api/customers/{customers['Maria Garcia']['id']}").json()
    kyc = d["assessments"]["kyc"]["output"]
    assert "Residential address" in kyc["missing_information"]
    assert kyc["completeness_pct"] < 80
    assert d["assessments"]["summary"]["output"]["final_recommendation"] == "REQUEST_INFORMATION" or rating(customers, "Maria Garcia") == "LOW"


def test_cannot_approve_prohibited_customer(client, customers):
    r = client.post(f"/api/customers/{customers['Viktor Kozlov']['id']}/decision", json={"decision": "APPROVE", "note": "try"})
    assert r.status_code == 409


def test_disposition_false_positive_reduces_risk_and_is_audited(client, customers):
    cid = customers["Ivan Petrov"]["id"]
    before = client.get(f"/api/customers/{cid}").json()["customer"]
    hits = client.get(f"/api/customers/{cid}").json()["hits"]
    assert hits, "name collision should produce at least one weak hit"
    for h in hits:
        r = client.post(f"/api/screening/hits/{h['id']}/disposition", json={"disposition": "FALSE_POSITIVE", "note": "DOB and place of birth differ"})
        assert r.status_code == 200
    after = client.get(f"/api/customers/{cid}").json()["customer"]
    assert after["risk_score"] <= before["risk_score"]
    audit = client.get("/api/audit", params={"customer_id": cid, "action": "SCREENING_HIT_DISPOSITION"}).json()
    assert audit["total"] >= len(hits)
    assert all(a["actor_type"] == "USER" for a in audit["items"])
    # note is mandatory
    r = client.post(f"/api/screening/hits/{hits[0]['id']}/disposition", json={"disposition": "CONFIRMED"})
    assert r.status_code == 422


def test_event_new_sanctions_match_escalates_to_prohibited(client):
    created = client.post("/api/customers", json={
        "full_name": "Test Person", "date_of_birth": "1985-01-01", "nationality": "Poland", "country_of_residence": "Poland",
        "occupation": "Teacher", "industry": "Education", "source_of_funds": "Monthly teaching salary of EUR 2,000 from a public school.",
        "source_of_wealth": "Savings from employment as a teacher since 2010 totalling about EUR 20,000.",
        "expected_activity": "Salary of EUR 2,000 per month", "annual_income": 30000,
    }).json()
    cid = created["customer"]["id"]
    assert created["customer"]["risk_rating"] in ("LOW", "MEDIUM")
    r = client.post(f"/api/customers/{cid}/reviews/event", json={"event_type": "NEW_SANCTIONS_MATCH", "payload": {"list_entry_id": "SAN-004", "confidence": 95}})
    assert r.status_code == 201
    out = r.json()
    assert out["customer"]["risk_rating"] == "PROHIBITED"
    ev = out["reviews"][0]["outcome"]
    assert ev["escalation_outcome"] == "ESCALATE_MLRO_FREEZE_PENDING_REVIEW" and ev["priority"] == "CRITICAL"
    changes = client.get("/api/audit", params={"customer_id": cid, "action": "RISK_RATING_CHANGED"}).json()
    assert changes["total"] >= 1


def test_event_address_change_to_high_risk_country(client, customers):
    cid = customers["Katarzyna Nowak"]["id"]
    r = client.post(f"/api/customers/{cid}/reviews/event", json={"event_type": "ADDRESS_CHANGE", "payload": {"new_address": "Moscow", "new_country": "Russia"}})
    assert r.status_code == 201
    ev = r.json()["reviews"][0]["outcome"]
    assert ev["escalation_outcome"] == "ESCALATE_FOR_EDD"
    bad = client.post(f"/api/customers/{cid}/reviews/event", json={"event_type": "NEW_SANCTIONS_MATCH", "payload": {"list_entry_id": "NOPE"}})
    assert bad.status_code == 422


def test_periodic_review_detects_expired_docs_and_overdue_kyc(client, customers):
    cid = customers["Piotr Wiśniewski"]["id"]
    d = client.post(f"/api/customers/{cid}/reviews/periodic").json()
    out = d["reviews"][0]["outcome"]
    assert out["expired_documents"] and out["expired_documents"][0]["doc_type"] == "ID_DOCUMENT"
    assert "PROOF_OF_ADDRESS" in out["missing_documents"]
    assert out["kyc_expired"] is True
    assert out["recommendation"] in ("REQUEST_DOCUMENTS_AND_INFORMATION", "ESCALATE_FOR_EDD_REVIEW")
    # decision closes the review
    rid = d["reviews"][0]["id"]
    done = client.post(f"/api/reviews/{rid}/decision", json={"decision": "ESCALATE", "note": "Docs requested"})
    assert done.status_code == 200 and done.json()["review"]["status"] == "ESCALATED"


def test_dashboard_and_audit(client):
    dash = client.get("/api/dashboard").json()
    assert dash["total_customers"] >= 11
    assert sum(dash["risk_distribution"].values()) == dash["total_customers"]
    assert dash["high_risk_customers"]
    assert dash["screening_matches"]["open_total"] >= 1
    audit = client.get("/api/audit", params={"actor_type": "AI"}).json()
    assert audit["total"] > 0
    assert {"USER", "AI", "SYSTEM"} >= {a["actor_type"] for a in audit["items"]}


def test_validation_errors(client):
    r = client.post("/api/customers", json={"full_name": "X"})
    assert r.status_code == 422
    assert client.get("/api/customers/99999").status_code == 404
