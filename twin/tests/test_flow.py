import os, tempfile
os.environ["TWIN_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
def tok(u):
    r = c.post("/auth/login", json={"username": u, "password": "demo123"}); assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_full_flow():
    h = tok("clinician")
    r = c.post("/telemetry", headers=h, json={"patient_id": "P001", "hr": 250, "spo2": 90, "sbp": 150}).json()
    assert "hr" in r["clamped"] and "spo2" not in r["clamped"] and len(r["state"]) == 64 and r["quality_score"] < 1
    assert set(["3h","12h","24h","7d"]) <= set(r["risk"]) and r["alert"]
    s = c.post("/simulations", headers=h, json={"patient_id": "P001"}).json()
    assert len(s["baseline"]) == len(s["simulated"]) == 25 and s["risk_delta"] < 0
    assert c.post(f"/alerts/{r['alert']['id']}/ack", headers=h).status_code == 200
    log = c.get("/audit", headers=tok("admin")).json()
    assert any(x["action"] == "ACK_ALERT" for x in log)

def test_rbac():
    assert c.post("/telemetry", headers=tok("patient"), json={"patient_id": "P001"}).status_code == 403
    assert c.get("/audit", headers=tok("clinician")).status_code == 403
    assert c.get("/alerts").status_code == 401

def test_extensions():
    h = tok("clinician"); c.post("/telemetry", headers=h, json={"patient_id": "P001", "hr": 130, "sbp": 160})
    b = c.get("/fhir/P001/bundle", headers=h).json(); assert b["resourceType"] == "Bundle" and len(b["entry"]) == 7
    assert c.get("/patients/P001/explain", headers=h).json()["features"][0]["contribution"] >= 0
    assert "node_activation" in c.get("/graph/P001", headers=h).json()
    r = c.post("/rollout/P001", headers=h).json(); assert len(r["actions"]) == 24
    assert c.get("/graph/P001", headers=tok("patient")).status_code == 403
