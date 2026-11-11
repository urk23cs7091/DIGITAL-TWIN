"""FHIR R4 export, occlusion-style explainability, untrained relational graph, greedy 24h rollout. All SYNTHETIC/ILLUSTRATIVE."""
import math, random
from . import services as sv
LOINC = {"hr":("8867-4","Heart rate","/min"),"spo2":("59408-5","Oxygen saturation","%"),"resp":("9279-1","Respiratory rate","/min"),
         "sbp":("8480-6","Systolic BP","mm[Hg]"),"dbp":("8462-4","Diastolic BP","mm[Hg]"),"temp":("8310-5","Body temperature","Cel"),
         "glucose":("2339-0","Glucose","mg/dL")}

def to_fhir(pid, o, ts=None):
    ents = [{"resource":{"resourceType":"Observation","status":"final","subject":{"reference":f"Patient/{pid}"},
             "effectiveDateTime":ts or "1970-01-01T00:00:00Z",
             "code":{"coding":[{"system":"http://loinc.org","code":c,"display":d}]},
             "valueQuantity":{"value":o[k],"unit":u,"system":"http://unitsofmeasure.org"}}} for k,(c,d,u) in LOINC.items()]
    return {"resourceType":"Bundle","type":"collection","entry":ents,"meta":{"tag":[{"code":"SYNTHETIC"}]}}

def explain(o):
    base = sv.risk(o)["24h"]["p50"]; rows = []
    for k in sv.KEYS:
        x = dict(o); x[k] = sv.NOMINAL[k]; rows.append({"feature":k,"value":o[k],"contribution":round(base-sv.risk(x)["24h"]["p50"],4)})
    return {"method":"occlusion vs nominal (illustrative)","baseline_risk":base,"features":sorted(rows,key=lambda r:-r["contribution"])}

EDGES = [("metoprolol","CYP2D6","metabolized_by"),("metoprolol","hr","lowers"),("metoprolol","sbp","lowers"),
         ("CYP2D6_poor_metabolizer","CYP2D6","reduces"),("hypertension","sbp","raises"),("diabetes","glucose","raises")]
REL_W = {"metabolized_by":0.5,"lowers":-0.8,"raises":0.8,"reduces":-0.6}
def graph(o, dim=16, seed=7):
    r = random.Random(seed); nodes = sorted({n for e in EDGES for n in e[:2]})
    h = {n:[r.gauss(0,.1) for _ in range(dim)] for n in nodes}   # random, untrained embeddings
    act = {n:0.0 for n in nodes}
    for k in sv.KEYS:
        if k in act: act[k] = sv._dev({**sv.NOMINAL,k:o[k]})
    for _ in range(2):                                          # 2 rounds of typed message passing
        new = dict(act)
        for s,t,rel in EDGES: new[t] += REL_W[rel]*act[s]; new[s] += 0.3*REL_W[rel]*act[t]
        act = new
    return {"embedding_dim":dim,"note":"untrained RGCN-style propagation; not clinical","edges":EDGES,
            "node_activation":{n:round(a,4) for n,a in act.items()},"sample_embedding":{n:[round(v,3) for v in h[n][:4]] for n in nodes[:3]}}

ACTIONS = {"no_change":{}, "beta_blocker":dict(hr=-.10,sbp=-.05), "fluids":dict(sbp=.06,hr=-.04), "oxygen":dict(spo2=.03), "glucose_control":dict(glucose=-.12)}
def rollout(o, hours=24):
    cur, traj, acts = dict(o), [], []
    for _ in range(hours):
        best = None
        for a,d in ACTIONS.items():
            x = {k:min(max(cur[k]*(1+d.get(k,0)), sv.BOUNDS[k][0]), sv.BOUNDS[k][1]) for k in cur}
            rr = sv.risk(x)["3h"]["p50"]
            if best is None or rr < best[0]-1e-9: best = (rr,a,x)
        traj.append(best[0]); acts.append(best[1]); cur = best[2]
    return {"policy":"greedy one-step planner (NOT trained PPO)","actions":acts,"risk_trajectory":traj,"label":"SYNTHETIC"}
