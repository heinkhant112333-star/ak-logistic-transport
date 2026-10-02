from flask import Flask, request, jsonify, send_from_directory, session
import sqlite3, os
from datetime import datetime, date

app = Flask(__name__, static_folder="public", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY","CHANGE-ME-IN-PRODUCTION")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE","0")=="1",
)
DB=os.environ.get("DATABASE_PATH","ak_logistic.db")
ADMIN_USER=os.environ.get("ADMIN_USER","admin")
ADMIN_PASS=os.environ.get("ADMIN_PASS","AK2026")

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS parcels(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tracking TEXT UNIQUE NOT NULL, customer TEXT NOT NULL,
      phone TEXT DEFAULT '', fee REAL DEFAULT 0,
      arrival TEXT NOT NULL, pickup TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'Waiting Pickup',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS history(
      id INTEGER PRIMARY KEY AUTOINCREMENT, tracking TEXT NOT NULL,
      action TEXT NOT NULL, created_at TEXT NOT NULL)""")
    for col, typ in [
    ("recipient", "TEXT DEFAULT ''"),
    ("weight_kg", "REAL DEFAULT 0")
]:
    try:    
        c.execute(f"ALTER TABLE parcels ADD COLUMN {col} {typ}")
    except sqlite3.OperationalError:
        pass
        c.commit(); c.close()
init()

def auth():
    return bool(session.get("admin"))

def normalize_unclaimed(c):
    today=date.today()
    rows=c.execute("SELECT tracking,arrival,status FROM parcels WHERE status='Waiting Pickup'").fetchall()
    for r in rows:
        try:
            if (today-datetime.strptime(r["arrival"],"%Y-%m-%d").date()).days>=7:
                now=datetime.now().isoformat(timespec="seconds")
                c.execute("UPDATE parcels SET status='Unclaimed',updated_at=? WHERE tracking=?",(now,r["tracking"]))
                c.execute("INSERT INTO history(tracking,action,created_at) VALUES(?,?,?)",(r["tracking"],"Auto status → Unclaimed",now))
        except: pass
    c.commit()

@app.get("/")
def home(): return send_from_directory("public","index.html")

@app.get("/health")
def health(): return jsonify(ok=True, service="AK Logistic & Transport")

@app.post("/api/login")
def login():
    d=request.get_json(force=True)
    if d.get("username")==ADMIN_USER and d.get("password")==ADMIN_PASS:
        session["admin"]=True; return jsonify(ok=True)
    return jsonify(ok=False,error="Invalid login"),401

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/public/track/<tracking>")
def public_track(tracking):
    c=db(); normalize_unclaimed(c)
    r=c.execute("SELECT tracking,customer,fee,arrival,pickup,status FROM parcels WHERE tracking=?",(tracking,)).fetchone(); c.close()
    return (jsonify(dict(r)) if r else (jsonify(error="Parcel not found"),404))

@app.get("/api/parcels")
def parcels():
    if not auth(): return jsonify(error="Unauthorized"),401
    c=db(); normalize_unclaimed(c)
    q=request.args.get("q","").strip(); status=request.args.get("status","").strip()
    sql="SELECT * FROM parcels WHERE 1=1"; args=[]
    if q: sql+=" AND (tracking LIKE ? OR customer LIKE ?)"; args += [f"%{q}%",f"%{q}%"]
    if status: sql+=" AND status=?"; args.append(status)
    rows=[dict(x) for x in c.execute(sql+" ORDER BY id DESC",args).fetchall()]; c.close()
    return jsonify(rows)

@app.post("/api/parcels")
def add():
    if not auth(): return jsonify(error="Unauthorized"),401
    d=request.get_json(force=True)
t=d.get("tracking","").strip()
customer=d.get("customer","").strip()
recipient=d.get("recipient","").strip()
weight_kg=float(d.get("weight_kg") or 0)
    if not t or not customer: return jsonify(error="Tracking and customer are required"),400
    now=datetime.now().isoformat(timespec="seconds"); arrival=d.get("arrival") or date.today().isoformat()
    c=db()
    try:
        c.execute("INSERT INTO parcels(tracking,customer,recipient,weight_kg,phone,fee,arrival,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
(t,customer,recipient,weight_kg,d.get("phone",""),float(d.get("fee") or 0),arrival,"Waiting Pickup",now,now))
    except sqlite3.IntegrityError:
        c.close(); return jsonify(error="Tracking already exists"),409
    c.close(); return jsonify(ok=True)

@app.post("/api/parcels/<tracking>/pickup")
def pickup(tracking):
    if not auth(): return jsonify(error="Unauthorized"),401
    now=datetime.now().isoformat(timespec="seconds"); d=date.today().isoformat(); c=db()
    c.execute("UPDATE parcels SET status='Picked Up',pickup=?,updated_at=? WHERE tracking=?",(d,now,tracking))
    c.execute("INSERT INTO history(tracking,action,created_at) VALUES(?,?,?)",(tracking,"Pickup confirmed",now)); c.commit(); c.close()
    return jsonify(ok=True)

@app.delete("/api/parcels/<tracking>")
def delete(tracking):
    if not auth(): return jsonify(error="Unauthorized"),401
    c=db(); c.execute("DELETE FROM parcels WHERE tracking=?",(tracking,)); c.commit(); c.close(); return jsonify(ok=True)

@app.get("/api/history/<tracking>")
def history(tracking):
    if not auth(): return jsonify(error="Unauthorized"),401
    c=db(); rows=[dict(x) for x in c.execute("SELECT * FROM history WHERE tracking=? ORDER BY id DESC",(tracking,)).fetchall()]; c.close()
    return jsonify(rows)

@app.get("/api/stats")
def stats():
    if not auth(): return jsonify(error="Unauthorized"),401
    c=db(); normalize_unclaimed(c)
    rows=c.execute("SELECT status,COUNT(*) n FROM parcels GROUP BY status").fetchall()
    m={r["status"]:r["n"] for r in rows}; total=sum(m.values())
    fees=c.execute("SELECT COALESCE(SUM(fee),0) x FROM parcels").fetchone()["x"]; c.close()
    return jsonify(total=total,waiting=m.get("Waiting Pickup",0),picked=m.get("Picked Up",0),unclaimed=m.get("Unclaimed",0),fees=fees)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
