AK LOGISTIC & TRANSPORT — PRODUCTION-READY FINAL PACKAGE
Telegram integration intentionally postponed.

WHAT IS INCLUDED
- Flask backend + SQLite persistent database
- Public customer tracking page
- Admin session login
- Receive/search/filter parcels
- Confirm pickup
- Automatic Unclaimed status after 7 days
- Activity/history database
- Dashboard totals and fee summary
- CSV export + print
- Responsive iPad/iPhone/Desktop interface
- Dockerfile + Docker Compose
- Persistent Docker data volume
- Health endpoint: /health
- Environment-variable configuration
- Gunicorn production server

QUICK LOCAL TEST
pip install -r requirements.txt
python app.py
Open: http://localhost:5000

DEMO LOGIN
admin / AK2026
Change this before any public deployment.

DOCKER DEPLOYMENT
1. Copy .env.example to .env
2. Replace SECRET_KEY and ADMIN_PASS
3. Run: docker compose up -d --build
4. Open: http://SERVER-IP:8080

PUBLIC DEPLOYMENT
Point your domain/reverse proxy to port 8080 and enable HTTPS.
Set COOKIE_SECURE=1 when HTTPS is enabled.

IMPORTANT
This package is deployable, but this chat does not itself provision a hosting account,
domain/DNS, TLS certificate, or managed cloud database. SQLite is suitable for a
single-server deployment. For larger multi-server use, migrate the database to a
managed PostgreSQL service.

TELEGRAM
Not included yet, by request.
