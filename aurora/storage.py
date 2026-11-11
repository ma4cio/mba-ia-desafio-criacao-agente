"""SQLite persistence and atomic condominium rules."""
import json
import sqlite3
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "runtime" / "aurora.sqlite3"

def connect():
    DB.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def reset():
    DB.parent.mkdir(exist_ok=True)
    if DB.exists():
        DB.unlink()
    with connect() as db:
        db.executescript("""
        CREATE TABLE sessions(id TEXT PRIMARY KEY, apartment TEXT NOT NULL);
        CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE reservations(code TEXT PRIMARY KEY, apartment TEXT NOT NULL, area TEXT NOT NULL, date TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE UNIQUE INDEX unique_active_area_date ON reservations(area,date) WHERE active=1;
        CREATE TABLE visitors(id INTEGER PRIMARY KEY AUTOINCREMENT, apartment TEXT NOT NULL, name TEXT NOT NULL, date TEXT NOT NULL);
        CREATE TABLE confirmations(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL, pending INTEGER NOT NULL DEFAULT 1);
        """)
        for item in load("reservas.json"):
            db.execute("INSERT INTO reservations(code,apartment,area,date) VALUES(?,?,?,?)",(item["codigo"],item["apartamento"],item["area"],item["data"]))
        for item in load("visitantes.json"):
            db.execute("INSERT INTO visitors(apartment,name,date) VALUES(?,?,?)",(item["apartamento"],item["nome"],item["data"]))

def ensure():
    if not DB.exists():
        reset()

def load(filename):
    return json.loads((ROOT / "dados" / filename).read_text(encoding="utf-8"))

def session(session_id):
    with connect() as db:
        row=db.execute("SELECT apartment FROM sessions WHERE id=?",(session_id,)).fetchone()
        return row["apartment"] if row else None

def create_session(apartment):
    identifier=uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO sessions VALUES (?,?)",(identifier,apartment))
    return identifier

def log(session_id, payload):
    with connect() as db:
        db.execute("INSERT INTO events(session_id,payload) VALUES(?,?)",(session_id,json.dumps(payload,ensure_ascii=False)))

def events(session_id):
    with connect() as db:
        return [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM events WHERE session_id=? ORDER BY id",(session_id,))]

def reservations(apartment):
    with connect() as db:
        return [{"codigo":r["code"],"area":r["area"],"data":r["date"]} for r in db.execute("SELECT code,area,date FROM reservations WHERE apartment=? AND active=1",(apartment,))]

def visitors(apartment):
    with connect() as db:
        return [{"nome":r["name"],"data":r["date"]} for r in db.execute("SELECT name,date FROM visitors WHERE apartment=?",(apartment,))]

def available(area,date):
    with connect() as db:
        return db.execute("SELECT 1 FROM reservations WHERE area=? AND date=? AND active=1",(area,date)).fetchone() is None

def reserve(apartment,area,date):
    code="RSV-"+uuid.uuid4().hex.upper()
    try:
        with connect() as db:
            db.execute("INSERT INTO reservations(code,apartment,area,date) VALUES(?,?,?,?)",(code,apartment,area,date))
        return {"ok":True,"codigo":code}
    except sqlite3.IntegrityError:
        return {"ok":False,"mensagem":"A área está ocupada nessa data."}

def cancel(apartment,area,date):
    with connect() as db:
        cur=db.execute("UPDATE reservations SET active=0 WHERE apartment=? AND area=? AND date=? AND active=1",(apartment,area,date))
        return cur.rowcount>0

def authorize(apartment,name,date):
    with connect() as db:
        db.execute("INSERT INTO visitors(apartment,name,date) VALUES(?,?,?)",(apartment,name,date))

def pending(session_id):
    with connect() as db:
        return [{"id":r["id"],"acao":r["action"],"detalhes":json.loads(r["details"])} for r in db.execute("SELECT * FROM confirmations WHERE session_id=? AND pending=1",(session_id,))]

def request_confirmation(session_id,action,details):
    identifier=uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO confirmations(id,session_id,action,details) VALUES(?,?,?,?)",(identifier,session_id,action,json.dumps(details,ensure_ascii=False)))
    return identifier

def resolve(session_id,identifier,approved):
    """Claim pending action transactionally. A duplicate id cannot execute twice."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT action,details FROM confirmations WHERE id=? AND session_id=? AND pending=1",(identifier,session_id)).fetchone()
        if not row:
            return None
        db.execute("UPDATE confirmations SET pending=0 WHERE id=?",(identifier,))
        if not approved:
            return {"ok":True,"mensagem":"Solicitação recusada."}
        details=json.loads(row["details"])
        apartment=db.execute("SELECT apartment FROM sessions WHERE id=?",(session_id,)).fetchone()["apartment"]
        if row["action"]=="reserve":
            code="RSV-"+uuid.uuid4().hex.upper()
            try:
                db.execute("INSERT INTO reservations(code,apartment,area,date) VALUES(?,?,?,?)",(code,apartment,details["area"],details["data"]))
                return {"ok":True,"mensagem":"Reserva realizada.","codigo":code}
            except sqlite3.IntegrityError:
                return {"ok":False,"mensagem":"A área está ocupada nessa data."}
        if row["action"]=="visitor":
            db.execute("INSERT INTO visitors(apartment,name,date) VALUES(?,?,?)",(apartment,details["nome"],details["data"]))
            return {"ok":True,"mensagem":"Visitante autorizado."}
        return {"ok":False,"mensagem":"Ação desconhecida."}
