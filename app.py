"""
SignalNova website — FastAPI backend.

Serves the one-page site and the whitepaper flow:

    POST /api/send-code     {name, email, consent}  -> e-mails a 6-digit code
    POST /api/verify-code   {email, code}           -> {ok, download_url}; also e-mails the link
    GET  /download/{token}                          -> the PDF, while the link is valid

Every request is recorded in PostgreSQL (see init_db.sql). The PDF lives
outside the web root (WHITEPAPER_PATH) and is only reachable through a
download link, which is handed out after the e-mail address is verified.

Usage:
    pip install -r requirements.txt
    python3 app.py                       # development, http://localhost:8001
    uvicorn app:app --host 127.0.0.1 --port 8001   # production (systemd)
"""

import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import mailer

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("signalnova")

ROOT = Path(__file__).parent

DB_DSN = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME", "signalnova"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Public address of the site, used in e-mailed links. No trailing slash.
SITE_URL = os.getenv("SITE_URL", "http://localhost:8001").rstrip("/")

# Signs the verification codes (HMAC). The app refuses to start without it.
APP_SECRET = os.getenv("APP_SECRET", "")
if len(APP_SECRET) < 32:
    raise RuntimeError("APP_SECRET missing or shorter than 32 characters — see .env.example")

WHITEPAPER_PATH = Path(os.getenv("WHITEPAPER_PATH", "private/whitepaper.pdf"))
if not WHITEPAPER_PATH.is_absolute():
    WHITEPAPER_PATH = ROOT / WHITEPAPER_PATH
WHITEPAPER_FILENAME = os.getenv("WHITEPAPER_FILENAME", "SignalNova-whitepaper.pdf")

CODE_MINUTES = int(os.getenv("CODE_MINUTES", "15"))           # code validity
CODE_MAX_ATTEMPTS = int(os.getenv("CODE_MAX_ATTEMPTS", "5"))   # wrong guesses per code
RESEND_COOLDOWN_S = int(os.getenv("RESEND_COOLDOWN_SECONDS", "30"))
CODES_PER_EMAIL_HOUR = int(os.getenv("CODES_PER_EMAIL_HOUR", "5"))
CODES_PER_IP_HOUR = int(os.getenv("CODES_PER_IP_HOUR", "10"))
# Stay under the mail provider's daily cap (Gmail ≈ 500/day, Brevo free 300/day).
# Each verified request costs two mails (code + link).
MAIL_DAILY_LIMIT = int(os.getenv("MAIL_DAILY_LIMIT", "200"))
LINK_HOURS = int(os.getenv("DOWNLOAD_LINK_HOURS", "72"))
LINK_MAX_USES = int(os.getenv("DOWNLOAD_LINK_MAX_USES", "10"))

# Behind the Cloudflare Tunnel the real visitor IP is in CF-Connecting-IP.
# Only trust it when uvicorn listens on 127.0.0.1 (so only cloudflared can reach it).
TRUST_CF_HEADER = os.getenv("TRUST_CF_HEADER", "true").lower() == "true"

# What the visitor agrees to. Must match the checkbox text in index.html —
# it is stored with every lead as proof of consent.
CONSENT_TEXT = ("I agree that SignalNova may e-mail me the whitepaper and contact me about it, "
                "as described in the privacy notice.")

EMAIL_RE = re.compile(r"^[^\s@<>,;:\"()\[\]\\]+@[^\s@<>,;:\"()\[\]\\]+\.[A-Za-z]{2,}$")

app = FastAPI(title="SignalNova website", docs_url=None, redoc_url=None, openapi_url=None)


# ── Helpers ──────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)


def client_ip(request: Request):
    raw = request.headers.get("cf-connecting-ip") if TRUST_CF_HEADER else None
    raw = raw or (request.client.host if request.client else None)
    try:
        return str(ipaddress.ip_address((raw or "").strip()))
    except ValueError:
        return None


def code_hash(lead_id: int, code: str) -> str:
    return hmac.new(APP_SECRET.encode(), f"{lead_id}:{code}".encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def fail(status: int, message: str, **extra):
    """Errors the page shows to the visitor as-is."""
    return JSONResponse({"ok": False, "message": message, **extra}, status_code=status)


# ── Security headers ─────────────────────────────────────────────────────

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    resp.headers["X-Frame-Options"] = "DENY"
    if SITE_URL.startswith("https://"):
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    path = request.url.path
    if path.startswith(("/api/", "/download/")):
        resp.headers["Cache-Control"] = "no-store"
    elif path.endswith(".html") or "." not in path.rsplit("/", 1)[-1]:
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


# ── Pages and static files ───────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    return FileResponse(ROOT / "index.html")


@app.api_route("/privacy", methods=["GET", "HEAD"], include_in_schema=False)
def privacy():
    return FileResponse(ROOT / "privacy.html")


@app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
def robots():
    return PlainTextResponse(f"User-agent: *\nDisallow: /api/\nDisallow: /download/\n"
                             f"Sitemap: {SITE_URL}/sitemap.xml\n")


@app.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap():
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{SITE_URL}/</loc></url><url><loc>{SITE_URL}/privacy</loc></url></urlset>\n")
    return PlainTextResponse(body, media_type="application/xml")


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon():
    return FileResponse(ROOT / "img" / "icon-32.png", media_type="image/png")


for _d in ("css", "js", "img", "fonts"):
    app.mount(f"/{_d}", StaticFiles(directory=str(ROOT / _d)), name=_d)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
        db = "ok"
    except Exception as e:
        log.error("health: database unreachable: %s", e)
        db = "error"
    return {
        "status": "ok" if db == "ok" else "degraded",
        "database": db,
        "mail": mailer.mail_mode(),
        "whitepaper": "ok" if WHITEPAPER_PATH.is_file() else "missing",
    }


# ── Whitepaper flow ──────────────────────────────────────────────────────

class SendCodeIn(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    consent: bool = False
    website: str = Field(default="", max_length=200)   # honeypot: real visitors leave it empty


class VerifyIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)


@app.post("/api/send-code")
def send_code(body: SendCodeIn, request: Request):
    name = " ".join(body.name.split())
    email = body.email.strip().lower()
    if body.website:                       # bot filled the hidden field: pretend success
        log.info("honeypot hit from %s", client_ip(request))
        return {"ok": True, "cooldown": RESEND_COOLDOWN_S}
    if not name or len(name) > 120:
        return fail(400, "Enter your name.")
    if not EMAIL_RE.match(email):
        return fail(400, "Enter a valid e-mail address.")
    if not body.consent:
        return fail(400, "Tick the box to continue.")

    ip = client_ip(request)
    ua = (request.headers.get("user-agent") or "")[:400]
    code = f"{secrets.randbelow(1_000_000):06d}"

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # Serialise concurrent requests for the same address.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (email,))

            cur.execute("SELECT count(*) AS n FROM verification_codes "
                        "WHERE created_at > now() - interval '24 hours'")
            if cur.fetchone()["n"] >= MAIL_DAILY_LIMIT:
                log.warning("daily mail limit (%s) reached", MAIL_DAILY_LIMIT)
                return fail(503, "We are receiving a lot of requests. Please try again tomorrow, "
                                 "or contact us directly.")
            if ip:
                cur.execute("SELECT count(*) AS n FROM verification_codes "
                            "WHERE ip = %s AND created_at > now() - interval '1 hour'", (ip,))
                if cur.fetchone()["n"] >= CODES_PER_IP_HOUR:
                    return fail(429, "Too many requests from your network. Try again in an hour.")

            cur.execute("""SELECT
                               count(*) AS n,
                               extract(epoch FROM now() - max(vc.created_at)) AS since
                           FROM verification_codes vc JOIN leads l ON l.id = vc.lead_id
                           WHERE l.email = %s AND vc.created_at > now() - interval '1 hour'""", (email,))
            row = cur.fetchone()
            if row["n"] and row["since"] is not None and row["since"] < RESEND_COOLDOWN_S:
                wait = int(RESEND_COOLDOWN_S - row["since"]) + 1
                return fail(429, f"Please wait {wait} seconds before asking for a new code.", retry_after=wait)
            if row["n"] >= CODES_PER_EMAIL_HOUR:
                return fail(429, "Too many codes for this address. Try again in an hour.")

            cur.execute("""INSERT INTO leads (email, name, consent_text, consent_at, first_ip, last_ip, user_agent)
                           VALUES (%s, %s, %s, now(), %s, %s, %s)
                           ON CONFLICT (email) DO UPDATE SET
                               name = EXCLUDED.name, consent_text = EXCLUDED.consent_text,
                               consent_at = now(), last_ip = EXCLUDED.last_ip,
                               user_agent = EXCLUDED.user_agent, updated_at = now()
                           RETURNING id""", (email, name, CONSENT_TEXT, ip, ip, ua))
            lead_id = cur.fetchone()["id"]

            # Only the newest code works.
            cur.execute("UPDATE verification_codes SET expires_at = now() "
                        "WHERE lead_id = %s AND used_at IS NULL AND expires_at > now()", (lead_id,))
            cur.execute("""INSERT INTO verification_codes (lead_id, code_hash, expires_at, ip)
                           VALUES (%s, %s, now() + %s * interval '1 minute', %s) RETURNING id""",
                        (lead_id, code_hash(lead_id, code), CODE_MINUTES, ip))
            code_id = cur.fetchone()["id"]
    finally:
        conn.close()

    try:
        mailer.send_email(email, *mailer.code_email(name, code, CODE_MINUTES))
    except Exception as e:
        log.error("sending code to lead %s failed: %s", lead_id, e)
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("UPDATE verification_codes SET mail_error = %s, expires_at = now() WHERE id = %s",
                            (str(e)[:500], code_id))
        finally:
            conn.close()
        return fail(502, "The code could not be sent. Check the address and try again.")

    log.info("code sent to lead %s", lead_id)
    return {"ok": True, "cooldown": RESEND_COOLDOWN_S}


@app.post("/api/verify-code")
def verify_code(body: VerifyIn, request: Request):
    email = body.email.strip().lower()
    code = body.code.strip()
    if not re.fullmatch(r"\d{6}", code):
        return fail(400, "Enter the 6-digit code.")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""SELECT vc.id, vc.attempts, vc.code_hash, l.id AS lead_id, l.name
                           FROM verification_codes vc JOIN leads l ON l.id = vc.lead_id
                           WHERE l.email = %s AND vc.used_at IS NULL AND vc.expires_at > now()
                           ORDER BY vc.created_at DESC LIMIT 1
                           FOR UPDATE OF vc""", (email,))
            row = cur.fetchone()
            if not row:
                return fail(400, "This code has expired. Ask for a new code.", expired=True)
            if row["attempts"] >= CODE_MAX_ATTEMPTS:
                return fail(400, "Too many wrong attempts. Ask for a new code.", expired=True)

            if not hmac.compare_digest(row["code_hash"], code_hash(row["lead_id"], code)):
                cur.execute("UPDATE verification_codes SET attempts = attempts + 1 WHERE id = %s", (row["id"],))
                left = CODE_MAX_ATTEMPTS - row["attempts"] - 1
                if left <= 0:
                    return fail(400, "Too many wrong attempts. Ask for a new code.", expired=True)
                return fail(400, f"That code is not correct. {left} attempt{'s' if left != 1 else ''} left.")

            token = secrets.token_urlsafe(32)
            cur.execute("UPDATE verification_codes SET used_at = now() WHERE id = %s", (row["id"],))
            cur.execute("UPDATE leads SET verified_at = COALESCE(verified_at, now()), updated_at = now(), "
                        "last_ip = %s WHERE id = %s", (client_ip(request), row["lead_id"]))
            cur.execute("""INSERT INTO download_tokens (token_hash, lead_id, expires_at)
                           VALUES (%s, %s, now() + %s * interval '1 hour')""",
                        (token_hash(token), row["lead_id"], LINK_HOURS))
            lead_id, name = row["lead_id"], row["name"]
    finally:
        conn.close()

    path = f"/download/{token}"
    # The link also goes out by e-mail so the visitor can come back to it.
    # Best effort: the page already shows the download button.
    try:
        mailer.send_email(email, *mailer.link_email(name, SITE_URL + path, LINK_HOURS))
    except Exception as e:
        log.error("sending download link to lead %s failed: %s", lead_id, e)

    log.info("lead %s verified", lead_id)
    return {"ok": True, "download_url": path, "link_hours": LINK_HOURS}


EXPIRED_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Link expired – SignalNova</title>
<link rel="icon" href="/img/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/css/site.css?v=3">
<script src="/js/theme.js?v=3"></script></head><body><main class="page">
<a class="brand" href="/"><img class="logo-light" src="/img/logo.png" alt="SignalNova" width="113" height="26">
<img class="logo-dark" src="/img/logo-dark.png" alt="SignalNova" width="113" height="26"></a>
<h1>This link has expired.</h1>
<p class="lead">Download links work for a limited time. Request the whitepaper again and we will send you a new one.</p>
<p><a class="btn" href="/#whitepaper">Request the whitepaper</a></p></main></body></html>"""


@app.get("/download/{token}", include_in_schema=False)
def download(token: str, request: Request):
    if len(token) > 100:
        return HTMLResponse(EXPIRED_PAGE, status_code=404)
    if not WHITEPAPER_PATH.is_file():
        log.error("whitepaper file missing: %s", WHITEPAPER_PATH)
        raise HTTPException(503, "The whitepaper is temporarily unavailable. Please try again later.")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""UPDATE download_tokens SET uses = uses + 1
                           WHERE token_hash = %s AND expires_at > now() AND uses < %s
                           RETURNING lead_id""", (token_hash(token), LINK_MAX_USES))
            row = cur.fetchone()
            if not row:
                return HTMLResponse(EXPIRED_PAGE, status_code=410)
            cur.execute("INSERT INTO downloads (lead_id, ip, user_agent) VALUES (%s, %s, %s)",
                        (row["lead_id"], client_ip(request), (request.headers.get("user-agent") or "")[:400]))
            cur.execute("UPDATE leads SET download_count = download_count + 1, last_download_at = now() "
                        "WHERE id = %s", (row["lead_id"],))
    finally:
        conn.close()

    return FileResponse(WHITEPAPER_PATH, media_type="application/pdf", filename=WHITEPAPER_FILENAME,
                        headers={"X-Robots-Tag": "noindex"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("PORT", "8001")), reload=True)
