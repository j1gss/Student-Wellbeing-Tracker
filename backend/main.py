"""Student Wellbeing API: accounts, private check-ins, productivity estimate, insights.
Run:  uvicorn main:app --reload --port 8000   (from the backend folder), then open http://localhost:8000"""
import hashlib, hmac, re, secrets, sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestRegressor

BASE = Path(__file__).parent
DB_PATH = BASE / "student_wellbeing.db"
FRONTEND = next((p for p in (BASE / "frontend", BASE.parent / "frontend") if p.exists()), None)
DEMO_NOTES = {4: "Deadline week starts", 5: "Slept badly, felt heavy", 7: "Long walk, felt lighter"}

app = FastAPI(title="Student Wellbeing Telemetry Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # token header, no cookies

# ---------- schemas ----------
class CheckinPayload(BaseModel):
    entry_date: str
    mood: int = Field(ge=1, le=5)
    stress: int = Field(ge=1, le=5)
    sleep_hours: float = Field(ge=0, le=24)
    study_hours: float = Field(ge=0, le=24)
    water_liters: float = Field(ge=0, le=10)
    exercise_mins: int = Field(ge=0, le=600)
    note: str = Field(default="", max_length=60)  # optional, shown on the chart

class CheckinRecord(CheckinPayload):
    id: int
    predicted_productivity: float

class Credentials(BaseModel):
    username: str
    password: str

def as_dict(m):
    return m.model_dump() if hasattr(m, "model_dump") else m.dict()

# ---------- database ----------
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()

def now():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    is_new = not DB_PATH.exists()
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, salt TEXT, pw_hash TEXT);
            CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER, expires TEXT);
            CREATE TABLE IF NOT EXISTS checkins (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, entry_date TEXT,
                mood INTEGER, stress INTEGER, sleep_hours REAL, study_hours REAL, water_liters REAL,
                exercise_mins INTEGER, predicted_productivity REAL, note TEXT DEFAULT '');""")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(checkins)")]
        for col, ddl in (("note", "TEXT DEFAULT ''"), ("user_id", "INTEGER")):  # upgrade older databases
            if col not in cols:
                conn.execute(f"ALTER TABLE checkins ADD COLUMN {col} {ddl}")
        demo = conn.execute("SELECT id FROM users WHERE username='demo'").fetchone()
        if demo:
            demo_id = demo["id"]
        else:  # shared demo login: change or delete before a public launch
            salt = secrets.token_bytes(16)
            demo_id = conn.execute("INSERT INTO users (username,salt,pw_hash) VALUES ('demo',?,?)",
                                   (salt.hex(), hash_pw("demo1234", salt))).lastrowid
        conn.execute("UPDATE checkins SET user_id=? WHERE user_id IS NULL", (demo_id,))
        if is_new:
            rng = np.random.default_rng(7)
            base = date.today() - timedelta(days=14)
            for i in range(14):
                sleep = float(rng.choice([5.0, 6.0, 7.5, 8.0]))
                stress = int(rng.choice([2, 3, 4, 5]))
                mood = int(max(1, min(5, 6 - stress + rng.integers(-1, 2))))
                study = round(float(rng.uniform(2.5, 6.5)), 1)
                water = round(float(rng.uniform(1.4, 2.8)), 1)
                ex = int(rng.choice([0, 20, 30, 45]))
                prod = max(25.0, min(95.0, sleep*6.5 + mood*7.5 - stress*7.5 + study*3.5 + water*3.0))
                conn.execute("INSERT INTO checkins (user_id,entry_date,mood,stress,sleep_hours,study_hours,water_liters,"
                             "exercise_mins,predicted_productivity,note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (demo_id, (base + timedelta(days=i)).isoformat(), mood, stress, sleep, study, water, ex,
                              round(prod, 1), DEMO_NOTES.get(i, "")))

# ---------- accounts ----------
def new_session(conn, uid):
    tok = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions VALUES (?,?,?)",
                 (hashlib.sha256(tok.encode()).hexdigest(), uid, (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()))
    return tok

def current_user(authorization: str = Header(default="")) -> int:
    tok = authorization.replace("Bearer ", "").strip()
    with db() as conn:
        row = conn.execute("SELECT user_id, expires FROM sessions WHERE token_hash=?",
                           (hashlib.sha256(tok.encode()).hexdigest(),)).fetchone()
    if not row or row["expires"] < now():
        raise HTTPException(401, "Please sign in again.")
    return row["user_id"]

@app.post("/api/register")
def register(c: Credentials):
    u = c.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,20}", u):
        raise HTTPException(400, "Username: 3-20 letters, numbers or underscores.")
    if len(c.password) < 8:
        raise HTTPException(400, "Password needs at least 8 characters.")
    salt = secrets.token_bytes(16)
    with db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            raise HTTPException(400, "That username is taken.")
        uid = conn.execute("INSERT INTO users (username,salt,pw_hash) VALUES (?,?,?)",
                           (u, salt.hex(), hash_pw(c.password, salt))).lastrowid
        tok = new_session(conn, uid)
    return {"token": tok, "username": u}

@app.post("/api/login")
def login(c: Credentials):
    u = c.username.strip().lower()
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if not row or not hmac.compare_digest(row["pw_hash"], hash_pw(c.password, bytes.fromhex(row["salt"]))):
            raise HTTPException(401, "Wrong username or password.")
        tok = new_session(conn, row["id"])
    return {"token": tok, "username": u}

@app.post("/api/logout")
def logout(authorization: str = Header(default="")):
    tok = authorization.replace("Bearer ", "").strip()
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(tok.encode()).hexdigest(),))
    return {"ok": True}

# ---------- model ----------
FEATURES = ["mood", "stress", "sleep_hours", "study_hours", "water_liters", "exercise_mins"]

def train_model():
    # NOTE: trained on synthetic data from a hand-written formula (no real labels yet).
    rng = np.random.default_rng(42)
    n = 1000
    X = pd.DataFrame({
        "mood": rng.integers(1, 6, n), "stress": rng.integers(1, 6, n),
        "sleep_hours": rng.uniform(3, 10, n), "study_hours": rng.uniform(1, 10, n),
        "water_liters": rng.uniform(0.5, 4.0, n), "exercise_mins": rng.choice([0, 15, 30, 60, 90], n)})
    y = np.clip(X.sleep_hours*6.5 + X.mood*7.5 - X.stress*8.0 + X.study_hours*3.5
                + X.water_liters*2.0 + X.exercise_mins*0.1, 15, 98)
    return RandomForestRegressor(n_estimators=50, random_state=42).fit(X[FEATURES], y)

init_db()
model = train_model()

# ---------- private data routes (each user only ever sees their own rows) ----------
@app.get("/api/history", response_model=List[CheckinRecord])
def get_history(uid: int = Depends(current_user)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM checkins WHERE user_id=? ORDER BY entry_date ASC, id ASC", (uid,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/checkin", response_model=CheckinRecord)
def create_checkin(item: CheckinPayload, uid: int = Depends(current_user)):
    try:
        date.fromisoformat(item.entry_date)
    except ValueError:
        raise HTTPException(422, "entry_date must look like 2026-09-30")
    pred = round(float(model.predict(pd.DataFrame([as_dict(item)])[FEATURES])[0]), 1)
    with db() as conn:
        cur = conn.execute("INSERT INTO checkins (user_id,entry_date,mood,stress,sleep_hours,study_hours,water_liters,"
                           "exercise_mins,predicted_productivity,note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (uid, item.entry_date, item.mood, item.stress, item.sleep_hours, item.study_hours,
                            item.water_liters, item.exercise_mins, pred, item.note.strip()))
        new_id = cur.lastrowid
    return {**as_dict(item), "note": item.note.strip(), "id": new_id, "predicted_productivity": pred}

@app.get("/api/insights")
def insights(uid: int = Depends(current_user)):
    """Up to 3 gentle suggestions, each with the reason it was made."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM checkins WHERE user_id=? ORDER BY entry_date DESC, id DESC LIMIT 7", (uid,)).fetchall()
    if not rows:
        return []
    df = pd.DataFrame([dict(r) for r in rows])
    n, out = len(df), []
    if df.sleep_hours.mean() < 6.5:
        out.append({"title": "Aim for an earlier night",
                    "why": f"You've averaged {df.sleep_hours.mean():.1f}h of sleep over your last {n} check-ins."})
    if df.study_hours.mean() >= 6:
        out.append({"title": "Take a proper break, away from screens",
                    "why": f"You've averaged {df.study_hours.mean():.1f}h of study a day recently."})
    if df.stress.mean() >= 4:
        out.append({"title": "Pick just one thing for tomorrow", "why": "Pressure has felt high across your last few check-ins."})
    if df.water_liters.mean() < 1.5:
        out.append({"title": "Keep a glass of water nearby", "why": f"You've averaged {df.water_liters.mean():.1f} L a day."})
    if df.exercise_mins.mean() < 15:
        out.append({"title": "A short walk, if you feel like it", "why": "You've moved very little this week, and even 10 minutes can help."})
    if n >= 5 and df.sleep_hours.std() > 0 and df.mood.std() > 0:
        r = df.sleep_hours.corr(df.mood)
        if r > 0.4:
            out.append({"title": "Sleep seems to lift your mood",
                        "why": f"Longer nights lined up with better moods in your last {n} days (r = {r:.2f}, small sample)."})
    return out[:3] or [{"title": "Keep doing what you're doing", "why": "Your last week looks balanced."}]

@app.delete("/api/data")
def delete_data(uid: int = Depends(current_user)):
    with db() as conn:
        n = conn.execute("DELETE FROM checkins WHERE user_id=?", (uid,)).rowcount
    return {"deleted": n}

@app.get("/api/health")
def health():
    return {"ok": True, "frontend_folder": str(FRONTEND) if FRONTEND else None}

if FRONTEND:  # keep this last so it doesn't shadow /api routes
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
else:
    print("WARNING: no 'frontend' folder found next to or above main.py, so http://localhost:8000/ will 404.")
