"""Settings, SQLite session, password hashing, HMAC-signed JWT (HS256), audit log."""
import base64, hashlib, hmac, json, os, sqlite3, time, secrets
DB_PATH = os.environ.get("TWIN_DB", "demo.db")
SECRET = os.environ.get("TWIN_SECRET", "dev-only-change-me").encode()
ROLES = ("ADMIN", "CLINICIAN", "RESEARCHER", "PATIENT")

def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, pw TEXT, role TEXT, patient_id TEXT);
CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY, mrn TEXT, name TEXT, birth_date TEXT, gender TEXT,
  twin_confidence REAL DEFAULT 0, data_completeness REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS wearable_observations(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT,
  hr REAL, hrv REAL, spo2 REAL, sbp REAL, glucose REAL, raw_json TEXT);
CREATE TABLE IF NOT EXISTS simulations(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, scenario TEXT,
  intervention TEXT, parameters TEXT, baseline TEXT, simulated TEXT, risk_delta REAL, synthetic INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, severity TEXT, message TEXT,
  created TEXT, acknowledged_by TEXT, acknowledged_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, role TEXT, action TEXT,
  resource TEXT, ip TEXT, status INTEGER, ts_utc TEXT);
"""

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${h}"

def check_pw(pw, stored):
    salt, _ = stored.split("$"); return hmac.compare_digest(hash_pw(pw, salt), stored)

def init_db():
    c = db(); c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM users").fetchone():
        for u, r, p in [("admin","ADMIN",None),("clinician","CLINICIAN",None),("researcher","RESEARCHER",None),("patient","PATIENT","P001")]:
            c.execute("INSERT INTO users VALUES(?,?,?,?)", (u, hash_pw("demo123"), r, p))
        c.execute("INSERT INTO patients VALUES('P001','SYN-0001','Synthetic Patient','1965-04-12','F',0,0)")
    c.commit(); c.close()

def _b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def _unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def make_token(sub, role, patient_id=None, ttl=3600):
    h = _b64(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    p = _b64(json.dumps({"sub":sub,"role":role,"pid":patient_id,"exp":int(time.time())+ttl}).encode())
    sig = _b64(hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"

def decode_token(tok):
    try:
        h, p, s = tok.split(".")
        good = _b64(hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(good, s): return None
        d = json.loads(_unb64(p))
        return d if d["exp"] > time.time() else None
    except Exception:
        return None

def audit(user, role, action, resource, ip, status):
    c = db()
    c.execute("INSERT INTO audit_log(username,role,action,resource,ip,status,ts_utc) VALUES(?,?,?,?,?,?,datetime('now'))",
              (user, role, action, resource, ip, status))
    c.commit(); c.close()
