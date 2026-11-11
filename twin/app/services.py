"""Validation, quality score, 64-value state, SYNTHETIC risk heuristic, What-If. No trained models."""
import math, random
NOMINAL = dict(hr=72, hrv=50, spo2=97, resp=14, sbp=120, dbp=80, temp=36.8, glucose=100)
# hr/spo2/hrv/resp/sbp/glucose bounds are from the report; dbp/temp bounds are ASSUMED (not in report).
BOUNDS = dict(hr=(40,180), spo2=(80,100), hrv=(5,150), resp=(8,35), sbp=(80,220), glucose=(50,400), dbp=(40,130), temp=(34,41))
TARGETS = dict(hr=(60,100), spo2=(95,100), hrv=(20,100), resp=(12,20), sbp=(90,140), glucose=(70,180), dbp=(60,90), temp=(36.1,37.8))
KEYS = list(NOMINAL)
HORIZONS = {"3h":1.0, "12h":1.3, "24h":1.5, "7d":2.0}

def validate(obs):
    clean, clamped, missing = {}, [], []
    for k in KEYS:
        v = obs.get(k)
        if v is None: missing.append(k); clean[k] = NOMINAL[k]; continue
        lo, hi = BOUNDS[k]; c = min(max(v, lo), hi)
        if c != v: clamped.append(k)
        clean[k] = c
    return clean, clamped, missing

def quality_score(clamped, missing):
    # Simplified: completeness minus 0.15 per clamped outlier. Report's exact formula is unspecified.
    return round(max(0.0, (len(KEYS)-len(missing))/len(KEYS) - 0.15*len(clamped)), 3)

def check_exceeded_targets(obs):
    exceeded = []
    for k, (lo, hi) in TARGETS.items():
        v = obs.get(k)
        if v is not None:
            if v < lo:
                exceeded.append({"key": k, "value": v, "target_min": lo, "target_max": hi, "direction": "LOW", "diff": round(lo - v, 2)})
            elif v > hi:
                exceeded.append({"key": k, "value": v, "target_min": lo, "target_max": hi, "direction": "HIGH", "diff": round(v - hi, 2)})
    return exceeded

def _n(k, v): lo, hi = BOUNDS[k]; return (v-lo)/(hi-lo)

def build_state(o):
    s = [_n(k, o[k]) for k in ["hr","hrv","spo2","resp","sbp","dbp","temp","glucose"]]   # 0-7
    pp, mapp = o["sbp"]-o["dbp"], (o["sbp"]+2*o["dbp"])/3
    s += [pp/120, mapp/150, o["hr"]/max(o["sbp"],1), o["hrv"]/max(o["hr"],1),             # 8-15: ILLUSTRATIVE derived
          (100-o["spo2"])/20, abs(o["glucose"]-100)/300, abs(o["temp"]-36.8)/5, abs(o["resp"]-16)/20]
    s += [0.5*math.sin(0.35*i + 1.5*s[i % 16]) for i in range(16, 64)]                     # 16-63 per report pseudocode
    return [round(x, 4) for x in s]

def _dev(o):
    tot = 0.0
    for k in KEYS:
        lo, hi = TARGETS[k]; b = BOUNDS[k]
        tot += max(0, lo-o[k], o[k]-hi) / (b[1]-b[0])
    return tot

def risk(o):
    d = _dev(o); out = {}
    for h, m in HORIZONS.items():
        p50 = 1-math.exp(-1.5*d*m); w = 0.04*m
        out[h] = {"p05": round(max(0,p50-w),3), "p50": round(p50,3), "p95": round(min(1,p50+w),3)}
    out["_note"] = "SYNTHETIC heuristic, not a trained TFT; intervals are illustrative."
    return out

PRESETS = {"beta_blocker_25pct": dict(hr=-0.15, sbp=-0.08)}  # illustrative deltas, not drug-efficacy evidence

def what_if(o, intervention="beta_blocker_25pct", params=None):
    p = params or PRESETS.get(intervention, {})
    base, sim = [], []
    for t in range(25):
        f = 1-math.exp(-t/6); x = dict(o)
        for k, dl in p.items(): x[k] = min(max(o[k]*(1+dl*f), BOUNDS[k][0]), BOUNDS[k][1])
        base.append(risk(o)["24h"]["p50"]); sim.append(risk(x)["24h"]["p50"])
    return {"baseline": base, "simulated": sim, "risk_delta": round(sim[-1]-base[-1], 4), "params": p,
            "label": "SYNTHETIC / ILLUSTRATIVE simulation output"}

def synthetic_packet(stress=False):
    r = random.Random()
    p = {k: round(NOMINAL[k]*r.uniform(0.95,1.08), 1) for k in KEYS}
    if stress: p.update(hr=r.uniform(130,200), spo2=r.uniform(78,90), sbp=r.uniform(150,230))
    return p
