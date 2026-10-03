from flask import Flask, request, jsonify, send_from_directory, session
import os
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from datetime import datetime, date

app = Flask(__name__, static_folder="public", static_url_path="")

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE-ME-IN-PRODUCTION"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)

DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "AK2026")


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


def init():
    with db() as c:
        with c.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS parcels(
                    id BIGSERIAL PRIMARY KEY,
                    tracking TEXT UNIQUE NOT NULL,
                    customer TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    fee DOUBLE PRECISION DEFAULT 0,
                    arrival TEXT NOT NULL,
                    pickup TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Waiting Pickup',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    recipient TEXT DEFAULT '',
                    weight_kg DOUBLE PRECISION DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS history(
                    id BIGSERIAL PRIMARY KEY,
                    tracking TEXT NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                ALTER TABLE parcels
                ADD COLUMN IF NOT EXISTS recipient TEXT DEFAULT ''
            """)

            cur.execute("""
                ALTER TABLE parcels
                ADD COLUMN IF NOT EXISTS weight_kg
                DOUBLE PRECISION DEFAULT 0
            """)


init()


def auth():
    return bool(session.get("admin"))


def normalize_unclaimed(c):
    today = date.today()

    with c.cursor() as cur:
        cur.execute("""
            SELECT tracking, arrival, status
            FROM parcels
            WHERE status=%s
        """, ("Waiting Pickup",))

        rows = cur.fetchall()

        for r in rows:
            try:
                arrival_date = datetime.strptime(
                    r["arrival"],
                    "%Y-%m-%d"
                ).date()

                if (today - arrival_date).days >= 7:

                    now = datetime.now().isoformat(
                        timespec="seconds"
                    )

                    cur.execute("""
                        UPDATE parcels
                        SET status=%s, updated_at=%s
                        WHERE tracking=%s
                    """, (
                        "Unclaimed",
                        now,
                        r["tracking"]
                    ))

                    cur.execute("""
                        INSERT INTO history(
                            tracking,
                            action,
                            created_at
                        )
                        VALUES(%s,%s,%s)
                    """, (
                        r["tracking"],
                        "Auto status → Unclaimed",
                        now
                    ))

            except (ValueError, TypeError):
                pass

    c.commit()


@app.get("/")
def home():
    return send_from_directory(
        "public",
        "index.html"
    )


@app.get("/health")
def health():
    return jsonify(
        ok=True,
        service="AK Logistic & Transport"
    )


@app.post("/api/login")
def login():
    d = request.get_json(force=True)

    if (
        d.get("username") == ADMIN_USER
        and d.get("password") == ADMIN_PASS
    ):
        session["admin"] = True
        return jsonify(ok=True)

    return jsonify(
        ok=False,
        error="Invalid login"
    ), 401


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/public/track/<tracking>")
def public_track(tracking):

    with db() as c:
        normalize_unclaimed(c)

        with c.cursor() as cur:
            cur.execute("""
                SELECT
                    tracking,
                    customer,
                    fee,
                    arrival,
                    pickup,
                    status
                FROM parcels
                WHERE tracking=%s
            """, (tracking,))

            r = cur.fetchone()

    if r:
        return jsonify(r)

    return jsonify(
        error="Parcel not found"
    ), 404


@app.get("/api/parcels")
def parcels():

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    q = request.args.get(
        "q",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    with db() as c:
        normalize_unclaimed(c)

        sql = """
            SELECT *
            FROM parcels
            WHERE 1=1
        """

        args = []

        if q:
            sql += """
                AND (
                    tracking ILIKE %s
                    OR customer ILIKE %s
                    OR recipient ILIKE %s
                )
            """

            search = f"%{q}%"

            args.extend([
                search,
                search,
                search
            ])

        if status:
            sql += " AND status=%s"
            args.append(status)

        sql += " ORDER BY id DESC"

        with c.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()

    return jsonify(rows)


@app.post("/api/parcels")
def add():

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    d = request.get_json(force=True)

    t = str(
        d.get("tracking", "")
    ).strip()

    customer = str(
        d.get("customer", "")
    ).strip()

    recipient = str(
        d.get("recipient", "")
    ).strip()

    try:
        weight_kg = float(
            d.get("weight_kg") or 0
        )

        fee = float(
            d.get("fee") or 0
        )

    except (TypeError, ValueError):
        return jsonify(
            error="Invalid weight or fee"
        ), 400

    if not t or not customer:
        return jsonify(
            error="Tracking and customer are required"
        ), 400

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    arrival = (
        d.get("arrival")
        or date.today().isoformat()
    )

    try:
        with db() as c:
            with c.cursor() as cur:

                cur.execute("""
                    INSERT INTO parcels(
                        tracking,
                        customer,
                        recipient,
                        weight_kg,
                        phone,
                        fee,
                        arrival,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s
                    )
                """, (
                    t,
                    customer,
                    recipient,
                    weight_kg,
                    d.get("phone", ""),
                    fee,
                    arrival,
                    "Waiting Pickup",
                    now,
                    now
                ))

    except UniqueViolation:
        return jsonify(
            error="Tracking already exists"
        ), 409

    return jsonify(ok=True)


@app.post("/api/parcels/<tracking>/pickup")
def pickup(tracking):

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    pickup_date = date.today().isoformat()

    with db() as c:
        with c.cursor() as cur:

            cur.execute("""
                UPDATE parcels
                SET
                    status=%s,
                    pickup=%s,
                    updated_at=%s
                WHERE tracking=%s
            """, (
                "Picked Up",
                pickup_date,
                now,
                tracking
            ))

            cur.execute("""
                INSERT INTO history(
                    tracking,
                    action,
                    created_at
                )
                VALUES(%s,%s,%s)
            """, (
                tracking,
                "Pickup confirmed",
                now
            ))

    return jsonify(ok=True)


@app.delete("/api/parcels/<tracking>")
def delete(tracking):

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    with db() as c:
        with c.cursor() as cur:
            cur.execute("""
                DELETE FROM parcels
                WHERE tracking=%s
            """, (tracking,))

    return jsonify(ok=True)


@app.get("/api/history/<tracking>")
def history(tracking):

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    with db() as c:
        with c.cursor() as cur:

            cur.execute("""
                SELECT *
                FROM history
                WHERE tracking=%s
                ORDER BY id DESC
            """, (tracking,))

            rows = cur.fetchall()

    return jsonify(rows)


@app.get("/api/stats")
def stats():

    if not auth():
        return jsonify(
            error="Unauthorized"
        ), 401

    with db() as c:
        normalize_unclaimed(c)

        with c.cursor() as cur:

            cur.execute("""
                SELECT
                    status,
                    COUNT(*) AS n
                FROM parcels
                GROUP BY status
            """)

            rows = cur.fetchall()

            m = {
                r["status"]: r["n"]
                for r in rows
            }

            total = sum(m.values())

            cur.execute("""
                SELECT
                    COALESCE(SUM(fee),0) AS x
                FROM parcels
            """)

            fees = cur.fetchone()["x"]

    return jsonify(
        total=total,
        waiting=m.get(
            "Waiting Pickup",
            0
        ),
        picked=m.get(
            "Picked Up",
            0
        ),
        unclaimed=m.get(
            "Unclaimed",
            0
        ),
        fees=fees
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
