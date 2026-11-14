def test_admin_reset_rebuilds_the_same_dataset(client):
    assert client.post("/api/admin/demo/reset", headers={"X-Analyst": "analyst.demo"}).status_code == 403
    r = client.post("/api/admin/demo/reset", headers={"X-Analyst": "admin.demo"})
    assert r.status_code == 200 and r.json()["customers"] == 100 and r.json()["corporates"] == 50 and r.json()["transactions"] == 500
    assert client.get("/api/executive").json()["kpis"]["total_customers"] == 100
    assert len(client.get("/api/auth/users").json()["users"]) == 5
