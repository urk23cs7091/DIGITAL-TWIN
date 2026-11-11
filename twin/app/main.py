import json, os
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from . import core, services as sv

app = FastAPI(title="Digital Twin Prototype (synthetic data only)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
core.init_db()

class Login(BaseModel): username: str; password: str
class Telemetry(BaseModel):
    patient_id: str; timestamp: Optional[str] = None
    hr: Optional[float]=None; hrv: Optional[float]=None; spo2: Optional[float]=None; resp: Optional[float]=None
    sbp: Optional[float]=None; dbp: Optional[float]=None; temp: Optional[float]=None; glucose: Optional[float]=None
class Sim(BaseModel):
    patient_id: str; intervention: str = "beta_blocker_25pct"; params: Optional[dict] = None

def user(request: Request, authorization: str = Header(None)):
    d = core.decode_token((authorization or "").removeprefix("Bearer "))
    if not d: raise HTTPException(401, "invalid or missing token")
    d["ip"] = request.client.host if request.client else "?"; return d

def need(*roles):
    def dep(u=Depends(user)):
        if u["role"] not in roles:
            core.audit(u["sub"], u["role"], "DENIED", "rbac", u["ip"], 403); raise HTTPException(403, "role not permitted")
        return u
    return dep

def own(u, pid):
    if u["role"] == "PATIENT" and u["pid"] != pid: raise HTTPException(403, "own record only")

def latest(pid):
    c = core.db(); r = c.execute("SELECT raw_json FROM wearable_observations WHERE patient_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "no telemetry yet")
    return json.loads(r["raw_json"])["clean"]

@app.post("/auth/login")
def login(b: Login, request: Request):
    c = core.db(); r = c.execute("SELECT * FROM users WHERE username=?", (b.username,)).fetchone(); c.close()
    ip = request.client.host if request.client else "?"
    if not r or not core.check_pw(b.password, r["pw"]):
        core.audit(b.username, "-", "LOGIN", "auth", ip, 401); raise HTTPException(401, "bad credentials")
    core.audit(r["username"], r["role"], "LOGIN", "auth", ip, 200)
    return {"token": core.make_token(r["username"], r["role"], r["patient_id"]), "role": r["role"], "patient_id": r["patient_id"]}

@app.get("/patients")
def patients(u=Depends(user)):
    c = core.db(); rows = [dict(r) for r in c.execute("SELECT * FROM patients")]; c.close()
    return [r for r in rows if u["role"] != "PATIENT" or r["id"] == u["pid"]]

@app.get("/demo/packet")
def demo_packet(stress: bool = False, u=Depends(need("ADMIN","CLINICIAN"))):
    return {"patient_id": "P001", **sv.synthetic_packet(stress), "_label": "synthetic"}

@app.post("/telemetry")
async def telemetry(t: Telemetry, u=Depends(need("ADMIN","CLINICIAN"))):
    raw = t.model_dump(); clean, clamped, missing = sv.validate(raw)
    q = sv.quality_score(clamped, missing); state = sv.build_state(clean); rk = sv.risk(clean)
    c = core.db()
    c.execute("INSERT INTO wearable_observations(patient_id,ts,hr,hrv,spo2,sbp,glucose,raw_json) VALUES(?,?,?,?,?,?,?,?)",
              (t.patient_id, t.timestamp, clean["hr"], clean["hrv"], clean["spo2"], clean["sbp"], clean["glucose"],
               json.dumps({"raw": raw, "clean": clean})))
    c.execute("UPDATE patients SET data_completeness=?, twin_confidence=? WHERE id=?", (1-len(missing)/8, q, t.patient_id))
    exceeded = sv.check_exceeded_targets(clean)
    alert = None
    if exceeded or rk["3h"]["p50"] >= 0.5 or clamped:
        is_high = rk["3h"]["p50"] >= 0.5 or bool(clamped) or any(
            (e["key"] == "hr" and (e["value"] > 130 or e["value"] < 45)) or
            (e["key"] == "spo2" and e["value"] < 90) or
            (e["key"] == "sbp" and (e["value"] > 160 or e["value"] < 85)) or
            (e["key"] == "temp" and e["value"] > 39.0) or
            (e["key"] == "glucose" and (e["value"] > 250 or e["value"] < 60))
            for e in exceeded
        )
        sev = "HIGH" if is_high else "MEDIUM"
        reasons = []
        if exceeded:
            detail_strs = [f"{e['key'].upper()}={e['value']} ({e['direction']} vs target {e['target_min']}-{e['target_max']})" for e in exceeded]
            reasons.append("Abnormal reading: " + ", ".join(detail_strs))
        if clamped:
            reasons.append(f"Clamped: {clamped}")
        if rk["3h"]["p50"] >= 0.5:
            reasons.append(f"3h risk elevated ({rk['3h']['p50']})")
        msg = "; ".join(reasons)
        # Deduplication: check if an identical unacknowledged alert was logged in the last 10 minutes
        recent = c.execute(
            """SELECT id, severity, message, created FROM alerts 
               WHERE patient_id=? AND message=? AND acknowledged_at IS NULL
               AND datetime(created) >= datetime('now', '-10 minutes')
               ORDER BY id DESC LIMIT 1""",
            (t.patient_id, msg)
        ).fetchone()

        if recent:
            alert = {"id": recent["id"], "severity": recent["severity"], "message": recent["message"], "exceeded": exceeded, "is_repeat": True}
        else:
            cur = c.execute("INSERT INTO alerts(patient_id,severity,message,created) VALUES(?,?,?,datetime('now'))", (t.patient_id, sev, msg))
            alert = {"id": cur.lastrowid, "severity": sev, "message": msg, "exceeded": exceeded, "is_repeat": False}
    c.commit(); c.close()
    core.audit(u["sub"], u["role"], "INGEST", f"patient/{t.patient_id}", u["ip"], 200)
    out = {"clean": clean, "clamped": clamped, "missing": missing, "quality_score": q, "state": state, "risk": rk, "alert": alert, "exceeded": exceeded}
    for ws in list(clients.get(t.patient_id, [])):
        try: await ws.send_json({"clean": clean, "risk": rk, "quality_score": q, "alert": alert, "exceeded": exceeded})
        except Exception: clients[t.patient_id].discard(ws)
    return out

@app.get("/patients/{pid}/state")
def state(pid: str, u=Depends(user)):
    own(u, pid); o = latest(pid); core.audit(u["sub"], u["role"], "READ", f"state/{pid}", u["ip"], 200)
    s = sv.build_state(o); return {"dim": len(s), "state": s}

@app.get("/patients/{pid}/risk")
def get_risk(pid: str, u=Depends(user)):
    own(u, pid); core.audit(u["sub"], u["role"], "READ", f"risk/{pid}", u["ip"], 200); return sv.risk(latest(pid))

@app.post("/simulations")
def simulate(s: Sim, u=Depends(need("ADMIN","CLINICIAN","RESEARCHER"))):
    r = sv.what_if(latest(s.patient_id), s.intervention, s.params)
    c = core.db()
    c.execute("INSERT INTO simulations(patient_id,scenario,intervention,parameters,baseline,simulated,risk_delta) VALUES(?,?,?,?,?,?,?)",
              (s.patient_id, "what-if", s.intervention, json.dumps(r["params"]), json.dumps(r["baseline"]), json.dumps(r["simulated"]), r["risk_delta"]))
    c.commit(); c.close(); core.audit(u["sub"], u["role"], "SIMULATE", f"patient/{s.patient_id}", u["ip"], 200); return r

@app.get("/alerts")
def alerts(u=Depends(user)):
    c = core.db()
    rows = [dict(r) for r in c.execute("""
        SELECT a.*, p.name as patient_name, p.mrn, p.birth_date, p.gender, p.twin_confidence, p.data_completeness 
        FROM alerts a
        LEFT JOIN patients p ON a.patient_id = p.id
        ORDER BY a.id DESC LIMIT 100
    """)]
    c.close()
    return [r for r in rows if u["role"] != "PATIENT" or r["patient_id"] == u["pid"]]

@app.post("/alerts/{aid}/ack")
def ack(aid: int, u=Depends(need("ADMIN","CLINICIAN"))):
    c = core.db(); c.execute("UPDATE alerts SET acknowledged_by=?, acknowledged_at=datetime('now') WHERE id=?", (u["sub"], aid)); c.commit(); c.close()
    core.audit(u["sub"], u["role"], "ACK_ALERT", f"alert/{aid}", u["ip"], 200); return {"ok": True}

@app.get("/audit")
def audit_log(u=Depends(need("ADMIN"))):
    c = core.db(); rows = [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 50")]; c.close(); return rows

clients: dict = {}
@app.websocket("/ws/telemetry/{pid}")
async def ws(w: WebSocket, pid: str, token: str = ""):
    d = core.decode_token(token)
    if not d or (d["role"] == "PATIENT" and d["pid"] != pid): await w.close(code=4401); return
    await w.accept(); clients.setdefault(pid, set()).add(w)
    try:
        while True: await w.receive_text()
    except WebSocketDisconnect: clients[pid].discard(w)

@app.get("/")
def index(): return FileResponse(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"))

from . import services_ext as ext
@app.get("/fhir/{pid}/bundle")
def fhir_bundle(pid: str, u=Depends(user)):
    own(u, pid); core.audit(u["sub"], u["role"], "FHIR_EXPORT", f"patient/{pid}", u["ip"], 200); return ext.to_fhir(pid, latest(pid))
@app.get("/patients/{pid}/explain")
def explain(pid: str, u=Depends(user)):
    own(u, pid); return ext.explain(latest(pid))
@app.get("/graph/{pid}")
def graph(pid: str, u=Depends(need("ADMIN","CLINICIAN","RESEARCHER"))): return ext.graph(latest(pid))
@app.post("/rollout/{pid}")
def rollout(pid: str, u=Depends(need("ADMIN","CLINICIAN","RESEARCHER"))):
    core.audit(u["sub"], u["role"], "ROLLOUT", f"patient/{pid}", u["ip"], 200); return ext.rollout(latest(pid))
