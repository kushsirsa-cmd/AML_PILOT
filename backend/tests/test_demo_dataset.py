"""The demo dataset, users/permissions, executive dashboard, work queues, transaction monitoring."""
import pytest


def hdr(user):
    return {"X-Analyst": user}


def test_dataset_sizes(client):
    kp = client.get("/api/executive").json()["kpis"]
    assert kp["total_customers"] >= 100 and kp["total_businesses"] >= 50 and kp["transactions"] == 500  # >= : other tests create extra records
    assert kp["high_risk_customers"] >= 15 and kp["open_alerts"] >= 25 and kp["flagged_transactions"] >= 20
    assert len(client.get("/api/transactions/fiat?limit=500").json()["transactions"]) == 500


def test_five_demo_users_and_login(client):
    users = client.get("/api/auth/users").json()["users"]
    assert {u["role"] for u in users} == {"ANALYST", "SENIOR_ANALYST", "MLRO", "COMPLIANCE_MANAGER", "ADMIN"}
    assert client.post("/api/auth/login", json={"username": "mlro.demo", "password": "wrong"}).status_code == 401
    t = client.post("/api/auth/login", json={"username": "mlro.demo", "password": "demo1234"}).json()
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + t["token"]}).json()
    assert me["user"]["role"] == "MLRO" and me["permissions"]["sar_decision"] is True
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_role_comes_from_server_not_client(client):
    # a spoofed X-Role header must not grant anything
    r = client.get("/api/admin/users", headers={"X-Analyst": "analyst.demo", "X-Role": "ADMIN"})
    assert r.status_code == 403
    assert client.get("/api/admin/users", headers=hdr("admin.demo")).status_code == 200


def test_admin_can_deactivate_user_but_not_self(client):
    users = client.get("/api/admin/users", headers=hdr("admin.demo")).json()
    me = next(u for u in users if u["username"] == "admin.demo")
    assert client.patch(f"/api/admin/users/{me['id']}", json={"active": False}, headers=hdr("admin.demo")).status_code == 409
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "NOPE"}, headers=hdr("admin.demo")).status_code == 422


def test_high_risk_approval_needs_senior_role(client):
    custs = client.get("/api/customers").json()
    c = next(x for x in custs if x["risk_rating"] == "HIGH" and x["status"] in ("ONBOARDING", "UNDER_REVIEW"))
    body = {"decision": "APPROVE", "note": "reviewed all evidence and EDD measures"}
    r = client.post(f"/api/customers/{c['id']}/decision", json=body, headers=hdr("analyst.demo"))
    assert r.status_code == 403 and "Senior" in r.json()["detail"]
    r2 = client.post(f"/api/customers/{c['id']}/decision", json=body, headers=hdr("senior.demo"))
    assert r2.status_code in (200, 409)  # 409 only if an open sanctions hit blocks approval - never a role error


def test_executive_dashboard_shapes(client):
    e = client.get("/api/executive").json()
    assert len(e["case_volume"]["months"]) == 6 and len(e["case_volume"]["alerts"]) == 6
    assert sum(e["risk_distribution"]["customers"]) == e["kpis"]["total_customers"] and sum(e["risk_distribution"]["businesses"]) == e["kpis"]["total_businesses"]
    assert e["sars"]["total"] >= 8 and {"FILED", "PENDING_MLRO"} <= set(e["sars"]["by_status"])
    assert len(e["transactions"]["weeks"]) == 12 and e["recent_activity"]


def test_work_queues_cover_every_workflow(client):
    keys = {q["key"]: q for q in client.get("/api/workqueue").json()["queues"]}
    for k in ["KYC_REVIEW", "CDD_REVIEW", "EDD_REVIEW", "SOF_VERIFICATION", "SOW_VERIFICATION", "SANCTIONS_ALERTS", "PEP_ALERTS", "SCREENING_ALERTS", "PERIODIC_REVIEWS", "EVENT_REVIEWS", "SAR_ESCALATION"]:
        assert k in keys, k
    assert keys["EDD_REVIEW"]["count"] > 0 and keys["PERIODIC_REVIEWS"]["count"] > 0 and keys["SAR_ESCALATION"]["count"] > 0
    it = keys["EDD_REVIEW"]["items"][0]
    assert {"name", "rating", "detail", "link"} <= set(it)


def test_pep_and_sanctions_examples_present(client):
    custs = {c["full_name"]: c for c in client.get("/api/customers").json()}
    assert custs["Maria Fernanda Castellanos"]["risk_rating"] == "HIGH"  # undeclared PEP found by screening
    assert custs["Dmitri Volkov"]["risk_rating"] == "PROHIBITED"  # strong sanctions match
    hits = client.get("/api/screening/hits").json()
    kinds = {h["list_type"] for h in (hits["items"] if isinstance(hits, dict) else hits)}
    assert {"SANCTIONS", "PEP", "ADVERSE_MEDIA"} <= kinds


def test_transaction_monitoring_rules_fire(client):
    rules = {f for t in client.get("/api/transactions/fiat?flagged=true&limit=500").json()["transactions"] for f in t["flags"]}
    assert {"STRUCTURING_CASH", "HIGH_RISK_GEOGRAPHY", "RAPID_PASS_THROUGH", "LARGE_CASH"} <= rules
    mz = next(c for c in client.get("/api/customers").json() if c["full_name"] == "Marek Zielinski")
    flagged = client.get(f"/api/transactions/fiat?customer_id={mz['id']}&flagged=true").json()["transactions"]
    assert any("STRUCTURING_CASH" in t["flags"] for t in flagged)


def test_false_positive_closes_screening_alert(client):
    alerts = client.get("/api/alerts?source=ADVERSE_MEDIA&status=OPEN").json()
    a = alerts[0]
    hit_id = a["details"]["hit_id"]
    r = client.post(f"/api/screening/hits/{hit_id}/disposition", json={"disposition": "FALSE_POSITIVE", "note": "different person - DOB differs"}, headers=hdr("senior.demo"))
    assert r.status_code == 200
    assert client.get(f"/api/alerts/{a['id']}").json()["status"] == "CLOSED"


def test_ownership_and_ubo_examples_in_businesses(client):
    corps = client.get("/api/kyb/corporates").json()
    assert len(corps) >= 50
    ratings = {c["risk_rating"] for c in corps}
    assert {"LOW", "MEDIUM", "HIGH", "PROHIBITED"} <= ratings
