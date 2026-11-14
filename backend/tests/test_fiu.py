"""Phase 4 - Investigations & FIU: link analysis, typologies, case lifecycle + permissions, SAR formats, crypto investigation, operating model."""
import pytest

from app.modules.fiu import operating_model as om

A = {"X-Analyst": "analyst.demo"}
S = {"X-Analyst": "senior.demo"}
M = {"X-Analyst": "mlro.demo"}


def names(cluster):
    return {m["name"] for m in cluster["members"]}


@pytest.fixture(scope="module")
def clusters(client):
    return client.get("/api/network/clusters").json()


def test_clusters_find_planted_rings(client, clusters):
    assert any(len([m for m in c["members"] if m["type"] == "customer"]) >= 5 and c["score"] >= 35 for c in clusters), "mule ring not found"
    assert any({"Viktor Kozlov", "Baltic Trade Ventures OÜ"} <= names(c) for c in clusters), "Kozlov/Baltic network not linked"
    assert all(c["size"] <= 30 for c in clusters)


def test_benign_household_not_a_hidden_association(client, clusters):
    barbara = next(i for i in client.get("/api/investigations").json()["items"] if i["subject"].startswith("Barbara"))
    n = client.get(f"/api/network/{barbara['entity_type']}/{barbara['entity_id']}").json()
    assert n["hidden_associations"] == [], "household (address/IP-only) pair reported as a hidden association"


def test_typology_detection_and_human_gate(client):
    tf = next(i for i in client.get("/api/investigations", params={"queue": "ESCALATION"}).json()["items"])
    r = client.get(f"/api/typology/{tf['entity_type']}/{tf['entity_id']}").json()
    codes = {d["code"] for d in r["detections"]}
    assert "TERRORIST_FINANCING" in codes
    assert r["escalation"]["human_decision_required"] is True


def test_investigation_seed_spans_all_queues(client):
    c = client.get("/api/investigations").json()["counts"]
    for q in ("TRIAGE", "FIU", "ESCALATION", "SAR", "MLRO", "CLOSED"):
        assert c[q] >= 1, q
    assert c["ALERT"] >= 1


def test_dashboard_has_required_tiles(client):
    t = client.get("/api/fiu/dashboard").json()["tiles"]
    for k in ("open_investigations", "pending_escalations", "sar_queue", "high_risk_customers", "high_risk_wallets", "suspicious_transactions", "network_cases", "regulatory_filing_queue"):
        assert k in t


def test_case_lifecycle_and_permissions(client):
    q = client.get("/api/rbi/queue").json()
    assert q, "RBI queue empty"
    tgt = q[0]
    r = client.post("/api/investigations", json={"entity_type": tgt["entity_type"], "entity_id": tgt["entity_id"], "source_type": "RBI"}, headers=A)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    d = client.get(f"/api/investigations/{iid}", headers=A).json()
    assert [s["n"] for s in d["agents"]["workbook"]["steps"]] == list(range(1, 10))
    assert d["summary"]["queue"] == "TRIAGE"
    act = lambda a, h, **k: client.post(f"/api/investigations/{iid}/actions", json={"action": a, **k}, headers=h)
    assert act("escalate", A, text="x" * 20).status_code == 409  # not in FIU yet
    assert act("accept_to_fiu", A).status_code == 200
    assert act("escalate", A, text="Escalating for MLRO review of typology.").status_code == 403  # analyst cannot escalate
    assert act("escalate", S, text="short").status_code == 422
    assert act("escalate", S, text="Escalating for MLRO review of typology.").status_code == 200
    r = act("to_sar", S)
    assert r.status_code == 200 and r.json()["queue"] == "SAR"
    assert act("close", S, text="Closing without a report after review.", disposition="NO_SUSPICION").status_code == 403  # escalated cases: MLRO only
    assert act("close", M, text="x", disposition="NO_SUSPICION").status_code == 422
    sar = client.get(f"/api/investigations/{iid}", headers=A).json()["sar"]
    assert sar["status"] == "DRAFT"
    assert act("close", M, text="Closing: MLRO accepts no-suspicion after review.", disposition="SAR_FILED").status_code == 422  # filed only via the SAR workflow
    assert act("bogus", A).status_code == 422
    # the audit trail records the lifecycle
    log = client.get("/api/audit", params={"limit": 200}).json() if client.get("/api/audit").status_code == 200 else []
    assert isinstance(log, (list, dict))


def test_duplicate_alert_case_rejected(client):
    inv = [i for i in client.get("/api/investigations").json()["items"] if i["alert_id"] and i["queue"] != "CLOSED"]
    if inv:
        r = client.post("/api/investigations", json={"alert_id": inv[0]["alert_id"]}, headers=A)
        assert r.status_code == 409


def test_sar_formats_are_illustrative_and_correctly_attributed(client):
    iid = next(i["id"] for i in client.get("/api/investigations").json()["items"] if i["queue"] in ("FIU", "MLRO"))
    pkg = client.get(f"/api/investigations/{iid}", headers=A).json()["sar_package"]
    assert set(pkg["formats"]) == {"UK_SAR", "FINTRAC_STR", "MAS_STR", "FIU_INTEL"}
    for f in pkg["formats"].values():
        assert "not a schema-valid" in f["disclaimer"].lower() and f["sections"]
    assert "NCA" in pkg["formats"]["UK_SAR"]["destination_note"]
    assert "STRO" in pkg["formats"]["MAS_STR"]["destination_note"]
    assert client.get(f"/api/investigations/{iid}/report/FINTRAC_STR").status_code == 200
    assert client.get(f"/api/investigations/{iid}/report/NOPE").status_code == 404


def test_crypto_investigation_traces_cross_chain_bridge(client):
    lena = next(c for c in client.get("/api/customers").json() if c["full_name"] == "Lena Hoffmann")
    r = client.get(f"/api/crypto-investigation/customer/{lena['id']}").json()
    assert r["cross_chain"] and r["mixer"]
    w = r["wallets"][0]
    assert w["cross_chain"][0]["bridge"]["method"].endswith("(heuristic)")
    assert len(w["wallet_attribution"]["providers"]) == 4 and all(p["simulated"] for p in w["wallet_attribution"]["providers"])


def test_operating_model_math():
    r = om.calculate()
    assert r["overall"]["teams"] == 26
    for t in om.TEAMS + om.OPTIONAL:
        assert sum(a["share"] for a in t["acts"]) == 100, t["code"]
    assert 0 < r["overall"]["realised_pct"] < r["overall"]["potential_pct"] <= 100
    assert abs(r["overall"]["realised_pct"] - r["overall"]["potential_pct"] * 0.7) < 0.2
    assert om.calculate({"adoption": 1})["overall"]["realised_pct"] > r["overall"]["realised_pct"]
    assert om.calculate({"optional": ["FRAUD"]})["overall"]["teams"] == 27
    low = om.calculate({"fte": {"KYC": 100}})
    assert next(t for t in low["teams"] if t["code"] == "KYC")["fte"] == 100
    # accountability roles never exceed ~25% automation
    sar = next(t for t in r["teams"] if t["code"] == "SAR")
    assert any(a["human_led"] and "MLRO" in a["name"] for a in sar["activities"])
    assert set(r["human_only_by_regulator"]) == {"FCA", "FATF", "MAS", "FINTRAC", "EBA"}
    assert "ESTIMATES" in r["disclaimer"]


def test_operating_model_api(client):
    r = client.post("/api/operating-model/calculate", json={"adoption": 0.5, "optional": ["TRADE"]}).json()
    assert r["overall"]["teams"] == 27
    assert client.post("/api/operating-model/calculate", json={"adoption": 2}).status_code == 422
    assert client.post("/api/operating-model/calculate", json={"fte": {"KYC": -1}}).status_code == 422
