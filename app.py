from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, send_file, abort
from pathlib import Path
from io import BytesIO
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from certificate_renderer import draw_certificate
import sqlite3
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None
import hashlib
import secrets
import base64
import re
import os
import csv
import io
import json
import zipfile
import tempfile
import shutil
import smtplib
from email.message import EmailMessage
from werkzeug.wsgi import get_current_url
import qrcode
import urllib.parse
import urllib.request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "srgpc.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
GENERATED_DIR = BASE_DIR / "generated"
SIGNATURE_DIR = DATA_DIR / "signatures"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
LOGO_PATH = BASE_DIR / "static" / "college_logo.png"
for folder in (DATA_DIR, GENERATED_DIR, SIGNATURE_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SRGPC_SESSION_KEY", "srgpc-local-session-key-change-before-public-hosting")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config["STATIC_VERSION"] = "6.3"

ADMIN_USERNAME = os.environ.get("SRGPC_ADMIN_USERNAME", "ADMIN")
ADMIN_PASSWORD = os.environ.get("SRGPC_ADMIN_PASSWORD", "0000")
PUBLIC_BASE_URL = os.environ.get("SRGPC_PUBLIC_BASE_URL", "")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(DATABASE_URL or PUBLIC_BASE_URL.startswith("https://")),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
CERT_TITLE = "CERTIFICATE OF ACHIEVEMENT"

TEMPLATES = {
    "classic": {"name": "Classic Gold", "description": "Traditional academic certificate with gold borders."},
    "modern": {"name": "Modern Blue", "description": "Clean institutional layout with a strong blue header."},
    "emerald": {"name": "Emerald Minimal", "description": "Minimal white space with elegant emerald accents."},
    "midnight": {"name": "Midnight Prestige", "description": "Dark premium certificate with bright accents."},
    "royal": {"name": "Royal Violet", "description": "Formal violet frame with a ceremonial look."},
    "burgundy": {"name": "Burgundy Honor", "description": "Refined wine-and-ivory certificate with restrained gold detailing."},
    "skyline": {"name": "Skyline", "description": "Contemporary geometric blue certificate."},
    "minimal": {"name": "Pure Minimal", "description": "Ultra-clean design for a modern college identity."},
}

FONT_OPTIONS = {
    "Helvetica": {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"},
    "Times": {"regular": "Times-Roman", "bold": "Times-Bold", "italic": "Times-Italic"},
    "Courier": {"regular": "Courier", "bold": "Courier-Bold", "italic": "Courier-Oblique"},
}

REQUEST_TYPES = ["Achievement", "Participation", "Sports", "Cultural", "Technical", "Workshop / Training", "Internship", "Academic", "Other"]
REQUEST_STATUSES = ["Pending", "Under Review", "Generated", "Rejected"]
ADMIN_ROLES = {"superadmin", "manager", "verifier"}
ROLE_PERMISSIONS = {
    "superadmin": {"*"},
    "admin": {"*"},
    "manager": {"dashboard", "generate", "requests", "certificates", "signatures", "templates", "students", "bulk", "analytics"},
    "verifier": {"dashboard", "certificates", "verify", "analytics"},
}


def require_role(role):
    """Require the current session to have the requested top-level role."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") != role:
                if request.method == "GET":
                    return redirect(url_for("login"))
                abort(403)
            if role == "admin" and session.get("admin_source_student_id"):
                with get_db() as db:
                    source = db.execute(
                        "SELECT admin_enabled, admin_role FROM students WHERE id=?",
                        (session["admin_source_student_id"],),
                    ).fetchone()
                if not source or not source["admin_enabled"]:
                    session.clear()
                    flash("Your student admin access has been revoked.", "error")
                    return redirect(url_for("login"))
                session["admin_role"] = source["admin_role"] or "admin"
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_permission(permission):
    """Require an authenticated admin with the requested permission."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") != "admin":
                if request.method == "GET":
                    return redirect(url_for("login"))
                abort(403)
            role = session.get("admin_role", "superadmin")
            allowed = ROLE_PERMISSIONS.get(role, set())
            if "*" not in allowed and permission not in allowed:
                if request.method == "GET":
                    flash("Your admin role does not have permission for this section.", "error")
                    return redirect(url_for("admin_dashboard"))
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _pg_placeholder_sql(sql):
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, url):
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is configured.")
        self.conn = psycopg.connect(url, row_factory=dict_row)

    def execute(self, sql, params=None):
        return self.conn.execute(_pg_placeholder_sql(sql), params or ())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            self.conn.close()


def get_db():
    if DATABASE_URL:
        return PostgresConnection(DATABASE_URL)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def setting(key, default=""):
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        db.commit()


def current_academic_year():
    now = datetime.now()
    start = now.year if now.month >= 4 else now.year - 1
    return f"{start}-{str(start+1)[-2:]}"


def init_db():
    id_pk = "SERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    case_unique = "" if DATABASE_URL else " COLLATE NOCASE"
    with get_db() as db:
        tables = [
            f"""CREATE TABLE IF NOT EXISTS students (
                id {id_pk},
                username TEXT NOT NULL UNIQUE{case_unique},
                password_hash TEXT NOT NULL,
                mobile TEXT NOT NULL,
                roll_number TEXT NOT NULL UNIQUE{case_unique},
                gmail TEXT NOT NULL UNIQUE{case_unique},
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 1,
                google_sub TEXT UNIQUE{case_unique},
                admin_enabled INTEGER NOT NULL DEFAULT 0,
                admin_role TEXT NOT NULL DEFAULT ''
            )""",
            f"""CREATE TABLE IF NOT EXISTS certificates (
                id {id_pk},
                certificate_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                roll_number TEXT NOT NULL,
                activity TEXT NOT NULL,
                position TEXT NOT NULL,
                template TEXT NOT NULL,
                font_family TEXT NOT NULL DEFAULT 'Helvetica',
                filename TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS certificate_requests (
                id {id_pk},
                student_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                roll_number TEXT NOT NULL,
                request_type TEXT NOT NULL,
                activity TEXT NOT NULL,
                position TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                admin_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                processed_at TEXT,
                certificate_id TEXT,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS admin_users (
                id {id_pk},
                username TEXT NOT NULL UNIQUE{case_unique},
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'manager',
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )""",
            f"""CREATE TABLE IF NOT EXISTS audit_logs (
                id {id_pk},
                actor_role TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS notifications (
                id {id_pk},
                student_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            )""",
            f"""CREATE TABLE IF NOT EXISTS email_verifications (
                id {id_pk},
                student_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE{case_unique},
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            )""",
        ]
        for sql in tables:
            db.execute(sql)

        if DATABASE_URL:
            cols = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='certificates'").fetchall()}
            req_cols = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='certificate_requests'").fetchall()}
            stu_cols = {row["column_name"] for row in db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='students'").fetchall()}
        else:
            cols = {row[1] for row in db.execute("PRAGMA table_info(certificates)").fetchall()}
            req_cols = {row[1] for row in db.execute("PRAGMA table_info(certificate_requests)").fetchall()}
            stu_cols = {row[1] for row in db.execute("PRAGMA table_info(students)").fetchall()}

        migrations = {
            "font_family": "ALTER TABLE certificates ADD COLUMN font_family TEXT NOT NULL DEFAULT 'Helvetica'",
            "certificate_type": "ALTER TABLE certificates ADD COLUMN certificate_type TEXT NOT NULL DEFAULT 'Achievement'",
            "academic_year": "ALTER TABLE certificates ADD COLUMN academic_year TEXT NOT NULL DEFAULT '2026-27'",
            "status": "ALTER TABLE certificates ADD COLUMN status TEXT NOT NULL DEFAULT 'Valid'",
            "payload_hash": "ALTER TABLE certificates ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''",
            "pdf_sha256": "ALTER TABLE certificates ADD COLUMN pdf_sha256 TEXT NOT NULL DEFAULT ''",
            "created_by": "ALTER TABLE certificates ADD COLUMN created_by TEXT NOT NULL DEFAULT 'ADMIN'",
            "request_id": "ALTER TABLE certificates ADD COLUMN request_id INTEGER",
            "revoked_at": "ALTER TABLE certificates ADD COLUMN revoked_at TEXT",
            "revoke_reason": "ALTER TABLE certificates ADD COLUMN revoke_reason TEXT NOT NULL DEFAULT ''",
            "reissued_from": "ALTER TABLE certificates ADD COLUMN reissued_from TEXT NOT NULL DEFAULT ''",
        }
        for col, sql in migrations.items():
            if col not in cols:
                db.execute(sql)

        req_migrations = {
            "academic_year": "ALTER TABLE certificate_requests ADD COLUMN academic_year TEXT NOT NULL DEFAULT '2026-27'",
            "processed_by": "ALTER TABLE certificate_requests ADD COLUMN processed_by TEXT NOT NULL DEFAULT ''",
        }
        for col, sql in req_migrations.items():
            if col not in req_cols:
                db.execute(sql)

        if "department" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN department TEXT NOT NULL DEFAULT 'CSE'")
        if "academic_year" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN academic_year TEXT NOT NULL DEFAULT '2026-27'")
        if "email_verified" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")
        if "google_sub" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN google_sub TEXT UNIQUE")
        if "admin_enabled" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN admin_enabled INTEGER NOT NULL DEFAULT 0")
        if "admin_role" not in stu_cols:
            db.execute("ALTER TABLE students ADD COLUMN admin_role TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE students SET admin_role='admin' WHERE admin_enabled=1")
        db.execute("UPDATE students SET admin_role='' WHERE admin_enabled=0")
        # Remove the legacy manager account requested by the administrator.
        db.execute("DELETE FROM admin_users WHERE LOWER(username)=LOWER('MRGARG')")

        defaults = {
            "default_template": "classic",
            "default_font": "Helvetica",
            "show_qr": "1",
            "certificate_title": "CERTIFICATE OF ACHIEVEMENT",
            "default_academic_year": current_academic_year(),
        }
        for key, value in defaults.items():
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING", (key, value))
        db.commit()



# Initialize the database when the app is imported by Gunicorn/Render.
# SQLite remains available for local development when DATABASE_URL is not set.
init_db()


def current_signature_path(kind):
    filename = setting(f"{kind}_signature", "")
    if not filename:
        return None
    path = Path(filename)
    if not path.is_absolute():
        path = BASE_DIR / filename
    return path if path.exists() else None


def clean(value, max_len=140):
    value = re.sub(r"\s+", " ", (value or "").strip())
    return value[:max_len]


def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def make_certificate_id():
    raw = f"{datetime.now().isoformat(timespec='microseconds')}|{secrets.token_hex(24)}|{secrets.token_hex(8)}"
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"SRGPC-{datetime.now():%Y}-{digest[:12]}"


def allowed_template(value):
    return value if value in TEMPLATES else setting("default_template", "classic")


def allowed_font(value):
    return value if value in FONT_OPTIONS else setting("default_font", "Helvetica")



def is_unique_violation(exc):
    return isinstance(exc, sqlite3.IntegrityError) or getattr(exc, "sqlstate", None) == "23505"

def audit(action, entity_type="", entity_id="", details=""):
    actor_role = session.get("admin_role", session.get("role", "system"))
    actor_name = session.get("username", "system")
    with get_db() as db:
        db.execute("INSERT INTO audit_logs(actor_role,actor_name,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?,?)", (actor_role, actor_name, action, entity_type, str(entity_id), clean(details, 500), datetime.now().isoformat(timespec="seconds")))
        db.commit()


def notify_student(student_id, title, body):
    with get_db() as db:
        db.execute("INSERT INTO notifications(student_id,title,body,created_at) VALUES(?,?,?,?)", (student_id, clean(title, 120), clean(body, 500), datetime.now().isoformat(timespec="seconds")))
        db.commit()


def add_request_update(db, request_id, status, message, actor_role=None, actor_name=None):
    db.execute(
        "INSERT INTO request_updates(request_id,status,message,actor_role,actor_name,created_at) VALUES(?,?,?,?,?,?)",
        (
            request_id,
            status,
            clean(message, 500),
            actor_role or session.get("admin_role", session.get("role", "system")),
            actor_name or session.get("username", "system"),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def begin_session(**values):
    session.clear()
    session.permanent = True
    session.update(values)


def cert_payload_hash(info):
    raw = "|".join(str(info.get(k, "")) for k in ("name","roll_number","activity","position","certificate_type","academic_year"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def public_verify_url(certificate_id):
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}{url_for('public_verify', certificate_id=certificate_id)}"
    try:
        return url_for('public_verify', certificate_id=certificate_id, _external=True)
    except RuntimeError:
        return f"/verify/{certificate_id}"



def render_certificate(target, info, verification_url=None):
    draw_certificate(
        target,
        info,
        verification_url=verification_url,
        logo_path=LOGO_PATH,
        teacher_sig=current_signature_path('teacher'),
        principal_sig=current_signature_path('principal'),
        show_qr=setting('show_qr', '1') == '1',
    )


def is_valid_gmail(gmail):
    return bool(re.fullmatch(r"[^@\s]+@gmail\.com", gmail.strip(), re.I))


def google_configured():
    return bool(os.environ.get("GOOGLE_CLIENT_ID", "").strip() and os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())


def google_redirect_uri():
    return url_for("google_callback", _external=True)


def google_authorize_url():
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def google_exchange_code(code):
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "redirect_uri": google_redirect_uri(),
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def google_userinfo(access_token):
    req = urllib.request.Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def google_signin_or_register():
    if not google_configured():
        flash("Google Sign-In is not configured yet. Ask the administrator to add the Google OAuth credentials in Render.", "error")
        return redirect(url_for("login"))
    return redirect(google_authorize_url())


def verification_configured():
    required = ("SRGPC_SMTP_HOST", "SRGPC_SMTP_USER", "SRGPC_SMTP_PASSWORD", "SRGPC_SMTP_FROM")
    return all(os.environ.get(key, "").strip() for key in required)


def verification_url(token):
    return url_for("verify_email", token=token, _external=True)


def send_verification_email(gmail, name, token):
    if not verification_configured():
        raise RuntimeError("Email verification is not configured on the server.")
    host = os.environ["SRGPC_SMTP_HOST"].strip()
    user = os.environ["SRGPC_SMTP_USER"].strip()
    password = os.environ["SRGPC_SMTP_PASSWORD"]
    sender = os.environ["SRGPC_SMTP_FROM"].strip()
    port = int(os.environ.get("SRGPC_SMTP_PORT", "587"))
    use_ssl = os.environ.get("SRGPC_SMTP_SSL", "0").strip().lower() in {"1", "true", "yes"}
    verify_link = verification_url(token)
    msg = EmailMessage()
    msg["Subject"] = "Verify your SRGPC student account"
    msg["From"] = sender
    msg["To"] = gmail
    msg.set_content(
        f"Hello {name},\n\n"
        "You created a student account for the SRGPC Certificate Portal. Confirm that you own this Gmail address by opening the link below:\n\n"
        f"{verify_link}\n\n"
        "This verification link expires in 30 minutes. If you did not create this account, you can ignore this email.\n\n"
        "SRGPC Certificate Portal"
    )
    msg.add_alternative(
        f"""<div style="font-family:Arial,sans-serif;line-height:1.6;color:#172033">
        <h2>Verify your SRGPC account</h2>
        <p>Hello {clean(name, 80)},</p>
        <p>Confirm that you own this Gmail address to activate your student account.</p>
        <p><a href="{verify_link}" style="display:inline-block;padding:12px 18px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px">Verify Email Address</a></p>
        <p style="font-size:13px;color:#64748b">This link expires in 30 minutes.</p>
        </div>""",
        subtype="html",
    )
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)


def create_email_verification(student_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now()
    from datetime import timedelta
    expires = now.replace(microsecond=0) + timedelta(minutes=30)
    with get_db() as db:
        db.execute("UPDATE email_verifications SET used_at=? WHERE student_id=? AND used_at IS NULL", (now.isoformat(timespec="seconds"), student_id))
        db.execute("INSERT INTO email_verifications(student_id,token_hash,expires_at,created_at) VALUES(?,?,?,?)", (student_id, token_hash, expires.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")))
        db.commit()
    return token


def save_signature_upload(kind, file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Choose an image file first.")
    suffix = Path(secure_filename(file_storage.filename)).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Signature must be PNG, JPG or JPEG.")
    filename = f"{kind}_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}{suffix}"
    path = SIGNATURE_DIR / filename
    file_storage.save(path)
    old = current_signature_path(kind)
    if old and old != path:
        try: old.unlink(missing_ok=True)
        except Exception: pass
    set_setting(f"{kind}_signature", str(path.relative_to(BASE_DIR)))


def save_signature_data(kind, data_url):
    if not data_url or "," not in data_url:
        raise ValueError("Draw a signature first.")
    head, encoded = data_url.split(",", 1)
    if "image/png" not in head:
        raise ValueError("Signature drawing must be PNG data.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        raise ValueError("Invalid signature drawing data.")
    filename = f"{kind}_drawn_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}.png"
    path = SIGNATURE_DIR / filename
    path.write_bytes(raw)
    old = current_signature_path(kind)
    if old and old != path:
        try: old.unlink(missing_ok=True)
        except Exception: pass
    set_setting(f"{kind}_signature", str(path.relative_to(BASE_DIR)))


def student_for_session():
    if session.get("role") != "student":
        return None
    with get_db() as db:
        return db.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()


def certificate_for_filename(filename):
    with get_db() as db:
        return db.execute("SELECT * FROM certificates WHERE filename = ?", (filename,)).fetchone()


@app.route("/")
def login():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))
    return render_template("login.html")


@app.get("/auth/google")
def google_login():
    session["google_login_mode"] = "student"
    return google_signin_or_register()


@app.get("/auth/google/admin")
def google_admin_login():
    session["google_login_mode"] = "admin"
    return google_signin_or_register()


@app.get("/auth/google/callback")
def google_callback():
    if not google_configured():
        flash("Google Sign-In is not configured.", "error")
        return redirect(url_for("login"))
    state = request.args.get("state", "")
    if not state or not secrets.compare_digest(state, session.pop("google_oauth_state", "")):
        flash("Google sign-in could not be verified. Please try again.", "error")
        return redirect(url_for("login"))
    if request.args.get("error"):
        flash("Google sign-in was cancelled.", "error")
        return redirect(url_for("login"))
    code = request.args.get("code", "")
    if not code:
        flash("Google did not return an authorization code.", "error")
        return redirect(url_for("login"))
    try:
        tokens = google_exchange_code(code)
        profile = google_userinfo(tokens["access_token"])
    except Exception:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))

    google_sub = clean(profile.get("sub"), 160)
    gmail = clean(profile.get("email"), 120).lower()
    email_verified = str(profile.get("email_verified", "")).lower() == "true"
    name = clean(profile.get("name"), 80)
    if not google_sub or not gmail or not email_verified:
        flash("Google could not confirm this account's email address.", "error")
        return redirect(url_for("login"))
    if not is_valid_gmail(gmail):
        flash("Only Gmail accounts can be used for student access.", "error")
        return redirect(url_for("login"))

    with get_db() as db:
        student = db.execute(
            "SELECT * FROM students WHERE google_sub=? OR LOWER(gmail)=LOWER(?) LIMIT 1",
            (google_sub, gmail),
        ).fetchone()

    login_mode = session.pop("google_login_mode", "student")
    if student:
        if not student["google_sub"]:
            with get_db() as db:
                db.execute("UPDATE students SET google_sub=?, email_verified=1 WHERE id=?", (google_sub, student["id"]))
                db.commit()
            with get_db() as db:
                student = db.execute("SELECT * FROM students WHERE id=?", (student["id"],)).fetchone()
        if login_mode == "admin":
            if not student["admin_enabled"]:
                flash("This student account does not have admin access. Ask the superadmin to grant it first.", "error")
                return redirect(url_for("login"))
            begin_session(role="admin", username=student["username"], admin_role="admin", admin_id=None, admin_source_student_id=student["id"])
            audit("Admin Google login", "admin", student["username"], f"Student admin role: {session['admin_role']}")
            return redirect(url_for("admin_dashboard"))
        begin_session(role="student", student_id=student["id"], username=student["username"])
        return redirect(url_for("student_dashboard"))

    if login_mode == "admin":
        flash("That Google account is not registered as an SRGPC student yet. Sign in as a student first, then ask the superadmin to grant admin access.", "error")
        return redirect(url_for("login"))

    session["pending_google"] = {"sub": google_sub, "gmail": gmail, "name": name}
    return redirect(url_for("register_google"))


@app.route("/register/google", methods=["GET", "POST"])
def register_google():
    pending = session.get("pending_google")
    if not pending:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("register.html", google_pending=pending, form={"name": pending.get("name",""), "gmail": pending["gmail"]})
    fields = {
        "mobile": clean(request.form.get("mobile"), 20),
        "roll_number": clean(request.form.get("roll_number"), 40),
        "gmail": pending["gmail"],
        "name": clean(request.form.get("name"), 80) or pending.get("name",""),
        "department": clean(request.form.get("department"), 60) or "CSE",
    }
    fields["username"] = re.sub(r"[^a-z0-9._-]+", "", fields["roll_number"].strip().lower())[:40]
    fields["password"] = secrets.token_urlsafe(24)
    if not all([fields["username"], fields["mobile"], fields["roll_number"], fields["name"], fields["department"]]):
        flash("Please complete every college profile field.", "error")
        return render_template("register.html", form=fields, google_pending=pending)
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO students(username,password_hash,mobile,roll_number,gmail,name,department,academic_year,created_at,email_verified,google_sub) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (fields["username"], generate_password_hash(fields["password"]), fields["mobile"], fields["roll_number"], fields["gmail"], fields["name"], fields["department"], setting("default_academic_year", current_academic_year()), datetime.now().isoformat(timespec="seconds"), 1, pending["sub"]),
            )
            row = db.execute("SELECT id FROM students WHERE google_sub=?", (pending["sub"],)).fetchone()
            student_id = row["id"] if row else None
            db.commit()
        session.pop("pending_google", None)
        begin_session(role="student", student_id=student_id, username=fields["username"])
        flash("Google account connected. Your SRGPC student account is ready.", "success")
        return redirect(url_for("student_dashboard"))
    except Exception as exc:
        if is_unique_violation(exc):
            flash("That username or roll number is already registered.", "error")
            return render_template("register.html", form=fields, google_pending=pending)
        raise


@app.post("/login")
def do_login():
    role = request.form.get("role", "student")
    username = clean(request.form.get("username"), 80).lower()
    password = request.form.get("password", "")
    if role == "admin":
        if username.casefold() == ADMIN_USERNAME.casefold() and password == ADMIN_PASSWORD:
            begin_session(role="admin", username=ADMIN_USERNAME, admin_role="superadmin")
            audit("Login", "admin", ADMIN_USERNAME, "Master admin login")
            return redirect(url_for("admin_dashboard"))
        with get_db() as db:
            admin = db.execute("SELECT * FROM admin_users WHERE username = ? AND active=1", (username,)).fetchone()
        if not admin or not check_password_hash(admin["password_hash"], password):
            flash("Invalid admin username or password.", "error")
            return redirect(url_for("login"))
        begin_session(role="admin", username=admin["username"], admin_role=admin["role"], admin_id=admin["id"])
        audit("Login", "admin", admin["username"], f"Role: {admin['role']}")
        return redirect(url_for("admin_dashboard"))
    with get_db() as db:
        student = db.execute(
            "SELECT * FROM students WHERE LOWER(username)=LOWER(?) OR LOWER(roll_number)=LOWER(?) OR LOWER(gmail)=LOWER(?) LIMIT 1",
            (username, username, username),
        ).fetchone()
    if not student or not check_password_hash(student["password_hash"], password):
        flash("Invalid student username or password.", "error")
        return redirect(url_for("login"))
    if not student["email_verified"]:
        flash("Please verify your Gmail address before logging in. Check your inbox for the verification link.", "error")
        return redirect(url_for("login"))
    begin_session(role="student", student_id=student["id"], username=student["username"])
    return redirect(url_for("student_dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    return redirect(url_for("google_login"))



@app.route("/verify-email", methods=["GET"])
def verify_email():
    token = clean(request.args.get("token"), 200)
    if not token:
        flash("That verification link is invalid.", "error")
        return redirect(url_for("login"))
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with get_db() as db:
        row = db.execute(
            "SELECT ev.id, ev.student_id, ev.expires_at, ev.used_at FROM email_verifications ev WHERE ev.token_hash=? LIMIT 1",
            (token_hash,),
        ).fetchone()
        if not row or row["used_at"]:
            flash("That verification link is invalid or has already been used.", "error")
            return redirect(url_for("login"))
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            flash("That verification link has expired. Request a new verification email.", "error")
            return redirect(url_for("resend_verification"))
        db.execute("UPDATE students SET email_verified=1 WHERE id=?", (row["student_id"],))
        db.execute("UPDATE email_verifications SET used_at=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), row["id"]))
        db.commit()
    flash("Gmail verified successfully. You can now log in.", "success")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "GET":
        return render_template("resend_verification.html")
    gmail = clean(request.form.get("gmail"), 120).lower()
    if not is_valid_gmail(gmail):
        flash("Enter a valid Gmail address.", "error")
        return render_template("resend_verification.html", gmail=gmail)
    try:
        with get_db() as db:
            student = db.execute("SELECT * FROM students WHERE LOWER(gmail)=LOWER(?) LIMIT 1", (gmail,)).fetchone()
        if student and not student["email_verified"]:
            token = create_email_verification(student["id"])
            send_verification_email(student["gmail"], student["name"], token)
        flash("If that Gmail belongs to an unverified SRGPC account, a new verification link has been sent.", "success")
        return redirect(url_for("login"))
    except Exception:
        flash("We could not send a verification email right now. Please try again later.", "error")
        return render_template("resend_verification.html", gmail=gmail)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------- ADMIN PAGES -------------------------


def admin_base_context(active):
    with get_db() as db:
        total_students = db.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
        total_certs = db.execute("SELECT COUNT(*) c FROM certificates").fetchone()["c"]
        pending = db.execute("SELECT COUNT(*) c FROM certificate_requests WHERE status='Pending'").fetchone()["c"]
        under_review = db.execute("SELECT COUNT(*) c FROM certificate_requests WHERE status='Under Review'").fetchone()["c"]
        attention = pending + under_review
        today_sql = "SELECT COUNT(*) c FROM certificates WHERE DATE(created_at) = CURRENT_DATE" if DATABASE_URL else "SELECT COUNT(*) c FROM certificates WHERE date(created_at)=date('now','localtime')"
        today = db.execute(today_sql).fetchone()["c"]
        valid = db.execute("SELECT COUNT(*) c FROM certificates WHERE status='Valid'").fetchone()["c"]
        revoked = db.execute("SELECT COUNT(*) c FROM certificates WHERE status='Revoked'").fetchone()["c"]
    return dict(active=active, total_students=total_students, total_certs=total_certs, pending=pending, under_review=under_review, attention=attention, today=today, valid=valid, revoked=revoked, admin_username=ADMIN_USERNAME, admin_role=session.get('admin_role','superadmin'))


@app.get("/admin")
@require_role("admin")
def admin_dashboard():
    ctx = admin_base_context("dashboard")
    with get_db() as db:
        certs = db.execute("SELECT * FROM certificates ORDER BY id DESC LIMIT 8").fetchall()
        requests = db.execute(
            """SELECT r.*, s.name student_name, s.roll_number student_roll
               FROM certificate_requests r JOIN students s ON s.id=r.student_id
               ORDER BY r.id DESC LIMIT 8"""
        ).fetchall()
        audit_rows = db.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 8").fetchall()
    return render_template("admin_dashboard.html", **ctx, certs=certs, requests=requests, audit_rows=audit_rows, templates=TEMPLATES)


@app.get("/admin/generate")
@admin_permission("generate")
def admin_generate_page():
    ctx = admin_base_context("generate")
    with get_db() as db:
        order_sql = "SELECT name, roll_number FROM students ORDER BY LOWER(name)" if DATABASE_URL else "SELECT name, roll_number FROM students ORDER BY name COLLATE NOCASE"
        students = db.execute(order_sql).fetchall()
    return render_template(
        "admin_generate.html",
        **ctx,
        templates=TEMPLATES,
        font_options=FONT_OPTIONS,
        request_types=REQUEST_TYPES,
        academic_year=setting("default_academic_year", current_academic_year()),
        default_template=setting("default_template", "classic"),
        default_font=setting("default_font", "Helvetica"),
        teacher_sig=bool(current_signature_path("teacher")),
        principal_sig=bool(current_signature_path("principal")),
        students=students,
    )


@app.post("/admin/generate")
@admin_permission("generate")
def admin_generate():
    info = {
        "name": clean(request.form.get("name"), 80),
        "roll_number": clean(request.form.get("roll_number"), 40),
        "activity": clean(request.form.get("activity"), 140),
        "position": clean(request.form.get("position"), 80),
        "certificate_type": clean(request.form.get("certificate_type"), 60) or "Achievement",
        "academic_year": clean(request.form.get("academic_year"), 20) or setting("default_academic_year", current_academic_year()),
        "template": allowed_template(request.form.get("template")),
        "font_family": allowed_font(request.form.get("font_family")),
    }
    if not all([info["name"], info["roll_number"], info["activity"], info["position"]]):
        flash("Fill in name, roll number, activity and position before generating.", "error")
        return redirect(url_for("admin_generate_page"))
    with get_db() as db:
        duplicate = db.execute("SELECT certificate_id FROM certificates WHERE lower(name)=lower(?) AND lower(roll_number)=lower(?) AND lower(activity)=lower(?) AND lower(position)=lower(?) AND status='Valid'", (info['name'], info['roll_number'], info['activity'], info['position'])).fetchone()
    if duplicate and request.form.get("allow_duplicate") != "1":
        flash(f"A matching valid certificate already exists ({duplicate['certificate_id']}). Enable duplicate issuance if this is an intentional reissue.", "error")
        return redirect(url_for("admin_generate_page"))
    info["certificate_id"] = make_certificate_id()
    info["payload_hash"] = cert_payload_hash(info)
    info["created_at"] = datetime.now().isoformat(timespec="seconds")
    info["created_by"] = session.get("username", ADMIN_USERNAME)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", info["name"]).strip("_").lower() or "student"
    filename = f"{slug}_{info['certificate_id']}.pdf"
    render_certificate(GENERATED_DIR / filename, info, public_verify_url(info["certificate_id"]))
    pdf_hash = file_sha256(GENERATED_DIR / filename)
    with get_db() as db:
        db.execute(
            "INSERT INTO certificates(certificate_id,name,roll_number,activity,position,template,font_family,filename,created_at,certificate_type,academic_year,status,payload_hash,pdf_sha256,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (info["certificate_id"], info["name"], info["roll_number"], info["activity"], info["position"], info["template"], info["font_family"], filename, info["created_at"], info["certificate_type"], info["academic_year"], "Valid", info["payload_hash"], pdf_hash, info["created_by"]),
        )
        db.commit()
    audit("Generate certificate", "certificate", info["certificate_id"], f"{info['name']} · {info['activity']}")
    flash(f"Certificate generated: {info['certificate_id']}", "success")
    return redirect(url_for("admin_certificates"))


@app.get("/admin/certificate-preview")
@admin_permission("generate")
def admin_certificate_preview():
    info = {
        "name": clean(request.args.get("name"), 80) or "Student Name",
        "roll_number": clean(request.args.get("roll_number"), 40) or "CSE24017",
        "activity": clean(request.args.get("activity"), 140) or "Activity / Event",
        "position": clean(request.args.get("position"), 80) or "Position / Achievement",
        "certificate_type": clean(request.args.get("certificate_type"), 60) or "Achievement",
        "academic_year": clean(request.args.get("academic_year"), 20) or setting("default_academic_year", current_academic_year()),
        "template": allowed_template(request.args.get("template")),
        "font_family": allowed_font(request.args.get("font_family")),
        "certificate_id": "SRGPC-PREVIEW",
    }
    buf = BytesIO()
    render_certificate(buf, info, url_for("public_verify", certificate_id=info["certificate_id"], _external=True))
    buf.seek(0)
    response = send_file(buf, mimetype="application/pdf", download_name="SRGPC_Preview.pdf", max_age=0, conditional=False)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/admin/certificate/<certificate_id>")
@admin_permission("certificates")
def admin_certificate_detail(certificate_id):
    ctx = admin_base_context("certificates")
    with get_db() as db:
        cert = db.execute(
            "SELECT * FROM certificates WHERE certificate_id=?",
            (clean(certificate_id,80).upper(),),
        ).fetchone()
    if not cert:
        abort(404)
    return render_template("admin_certificate_detail.html", **ctx, certificate=cert, templates=TEMPLATES)


@app.get("/student/certificate/<certificate_id>")
@require_role("student")
def student_certificate_detail(certificate_id):
    student = student_for_session()
    with get_db() as db:
        cert = db.execute(
            "SELECT * FROM certificates WHERE certificate_id=? AND lower(roll_number)=lower(?)",
            (clean(certificate_id,80).upper(), student["roll_number"]),
        ).fetchone()
    if not cert:
        abort(404)
    return render_template("student_certificate_detail.html", student=student, certificate=cert, active="certificates", templates=TEMPLATES)


@app.get("/admin/certificates")
@admin_permission("certificates")
def admin_certificates():
    ctx = admin_base_context("certificates")
    search = clean(request.args.get("q"), 100)
    with get_db() as db:
        if search:
            like = f"%{search}%"
            certs = db.execute("SELECT * FROM certificates WHERE name LIKE ? OR roll_number LIKE ? OR certificate_id LIKE ? ORDER BY id DESC", (like, like, like)).fetchall()
        else:
            certs = db.execute("SELECT * FROM certificates ORDER BY id DESC").fetchall()
    return render_template("admin_certificates.html", **ctx, certs=certs, templates=TEMPLATES, search=search)


@app.get("/admin/verify")
@admin_permission("verify")
def admin_verify_page():
    ctx = admin_base_context("verify")
    cert = None
    query = clean(request.args.get("certificate_id"), 80).upper()
    if query:
        with get_db() as db:
            cert = db.execute("SELECT * FROM certificates WHERE certificate_id = ?", (query,)).fetchone()
    return render_template("admin_verify.html", **ctx, certificate=cert, query=query, templates=TEMPLATES)


@app.post("/admin/verify")
@admin_permission("verify")
def admin_verify():
    certificate_id = clean(request.form.get("certificate_id"), 80).upper()
    return redirect(url_for("admin_verify_page", certificate_id=certificate_id))


@app.get("/admin/signatures")
@admin_permission("signatures")
def admin_signatures():
    ctx = admin_base_context("signatures")
    return render_template(
        "admin_signatures.html",
        **ctx,
        teacher_sig=bool(current_signature_path("teacher")),
        principal_sig=bool(current_signature_path("principal")),
        teacher_url=url_for("signature_preview", kind="teacher") if current_signature_path("teacher") else "",
        principal_url=url_for("signature_preview", kind="principal") if current_signature_path("principal") else "",
    )


@app.post("/admin/signature/upload")
@admin_permission("signatures")
def signature_upload():
    kind = request.form.get("kind")
    if kind not in {"teacher", "principal"}:
        flash("Unknown signature type.", "error")
        return redirect(url_for("admin_signatures"))
    try:
        save_signature_upload(kind, request.files.get("signature"))
        flash(f"{kind.title()} signature uploaded successfully.", "success")
    except Exception as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_signatures"))


@app.post("/admin/signature/draw")
@admin_permission("signatures")
def signature_draw():
    kind = request.form.get("kind")
    if kind not in {"teacher", "principal"}:
        flash("Unknown signature type.", "error")
        return redirect(url_for("admin_signatures"))
    try:
        save_signature_data(kind, request.form.get("signature_data", ""))
        flash(f"Drawn {kind} signature saved successfully.", "success")
    except Exception as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_signatures"))


@app.post("/admin/signature/remove")
@admin_permission("signatures")
def signature_remove():
    kind = request.form.get("kind")
    if kind in {"teacher", "principal"}:
        old = current_signature_path(kind)
        if old:
            try: old.unlink(missing_ok=True)
            except Exception: pass
        set_setting(f"{kind}_signature", "")
        flash(f"{kind.title()} signature removed.", "success")
    return redirect(url_for("admin_signatures"))


@app.get("/admin/templates")
@admin_permission("templates")
def admin_templates():
    ctx = admin_base_context("templates")
    return render_template(
        "admin_templates.html",
        **ctx,
        templates=TEMPLATES,
        font_options=FONT_OPTIONS,
        default_template=setting("default_template", "classic"),
        default_font=setting("default_font", "Helvetica"),
        show_qr=setting("show_qr", "1"),
        default_academic_year=setting("default_academic_year", current_academic_year()),
    )


@app.post("/admin/templates/save")
@admin_permission("templates")
def admin_templates_save():
    set_setting("default_template", allowed_template(request.form.get("default_template")))
    set_setting("default_font", allowed_font(request.form.get("default_font")))
    set_setting("show_qr", "1" if request.form.get("show_qr")=="1" else "0")
    set_setting("default_academic_year", clean(request.form.get("default_academic_year"), 20) or current_academic_year())
    audit("Update template settings", "settings", "global", f"Template {setting('default_template')} · Font {setting('default_font')} · QR {setting('show_qr')}")
    flash("Template, font, QR and academic-year defaults saved.", "success")
    return redirect(url_for("admin_templates"))


@app.get("/admin/students")
@admin_permission("students")
def admin_students():
    ctx = admin_base_context("students")
    search = clean(request.args.get("q"), 100)
    with get_db() as db:
        if search:
            like = f"%{search}%"
            students = db.execute("SELECT id,username,mobile,roll_number,gmail,name,created_at FROM students WHERE name LIKE ? OR roll_number LIKE ? OR username LIKE ? ORDER BY id DESC", (like, like, like)).fetchall()
        else:
            students = db.execute("SELECT id,username,mobile,roll_number,gmail,name,created_at FROM students ORDER BY id DESC").fetchall()
    return render_template("admin_students.html", **ctx, students=students, search=search)





@app.post("/admin/student/<int:student_id>/reset-password")
@admin_permission("students")
def admin_student_reset_password(student_id):
    new_password = request.form.get("new_password", "")
    if len(new_password) < 4:
        flash("Student password must be at least 4 characters.", "error")
        return redirect(url_for("admin_students"))

    with get_db() as db:
        student = db.execute("SELECT id, username, name FROM students WHERE id = ?", (student_id,)).fetchone()
        if not student:
            flash("Student account not found.", "error")
            return redirect(url_for("admin_students"))

        db.execute(
            "UPDATE students SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), student_id),
        )
        db.commit()

    audit("Reset student password", "student", student_id, f"Username: {student['username']}")
    flash(f"Password reset successfully for {student['name']} ({student['username']}).", "success")
    return redirect(url_for("admin_students"))


@app.post("/admin/student/<int:student_id>/delete")
@admin_permission("students")
def admin_student_delete(student_id):
    confirm = request.form.get("confirm_delete")
    if confirm != "DELETE":
        flash("Delete confirmation was not provided.", "error")
        return redirect(url_for("admin_students"))

    with get_db() as db:
        student = db.execute(
            "SELECT id, username, name, roll_number FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if not student:
            flash("Student account not found.", "error")
            return redirect(url_for("admin_students"))

        # Remove account-owned workflow data. Certificates remain archived by roll number.
        db.execute("DELETE FROM notifications WHERE student_id = ?", (student_id,))
        db.execute("DELETE FROM certificate_requests WHERE student_id = ?", (student_id,))
        db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        db.commit()

    audit(
        "Delete student account",
        "student",
        student_id,
        f"Deleted {student['name']} ({student['username']}, {student['roll_number']})",
    )
    flash(f"Student account deleted: {student['name']} ({student['username']}).", "success")
    return redirect(url_for("admin_students"))


@app.get("/admin/requests")
@admin_permission("requests")
def admin_requests():
    ctx = admin_base_context("requests")
    status = request.args.get("status", "All")
    with get_db() as db:
        if status in {"Pending", "Under Review", "Generated", "Rejected"}:
            rows = db.execute("SELECT r.*, s.username, s.gmail, s.mobile FROM certificate_requests r JOIN students s ON s.id=r.student_id WHERE r.status=? ORDER BY r.id DESC", (status,)).fetchall()
        else:
            rows = db.execute("SELECT r.*, s.username, s.gmail, s.mobile FROM certificate_requests r JOIN students s ON s.id=r.student_id ORDER BY r.id DESC").fetchall()
    return render_template("admin_requests.html", **ctx, requests=rows, status=status, default_template=setting("default_template", "classic"), default_font=setting("default_font", "Helvetica"), templates=TEMPLATES)


@app.get("/admin/request/<int:request_id>")
@admin_permission("requests")
def admin_request_detail(request_id):
    ctx = admin_base_context("requests")
    with get_db() as db:
        req = db.execute(
            """SELECT r.*, s.name student_name, s.roll_number student_roll, s.gmail student_gmail,
                      s.mobile student_mobile, s.department
               FROM certificate_requests r JOIN students s ON s.id=r.student_id
               WHERE r.id=?""",
            (request_id,),
        ).fetchone()
        if not req:
            abort(404)
        updates = db.execute("SELECT * FROM request_updates WHERE request_id=? ORDER BY id ASC", (request_id,)).fetchall()
    return render_template("admin_request_detail.html", **ctx, request=req, updates=updates, templates=TEMPLATES, default_template=setting("default_template","classic"), default_font=setting("default_font","Helvetica"))


@app.post("/admin/request/<int:request_id>/review")
@admin_permission("requests")
def admin_request_review(request_id):
    with get_db() as db:
        req = db.execute("SELECT * FROM certificate_requests WHERE id=?", (request_id,)).fetchone()
        if not req:
            flash("Certificate request not found.", "error")
            return redirect(url_for("admin_requests"))
        if req["status"] != "Pending":
            flash("Only pending requests can be moved to review.", "error")
            return redirect(url_for("admin_requests"))
        now = datetime.now().isoformat(timespec="seconds")
        db.execute(
            "UPDATE certificate_requests SET status='Under Review', processed_at=NULL, processed_by=? WHERE id=?",
            (session.get("username", ADMIN_USERNAME), request_id),
        )
        add_request_update(db, request_id, "Under Review", "Request moved to under review.", session.get("admin_role","admin"), session.get("username", ADMIN_USERNAME))
        db.commit()
    notify_student(req["student_id"], "Request under review", f"Your {req['request_type']} certificate request is now being reviewed by the admin.")
    audit("Review request", "request", request_id, "Moved to Under Review")
    flash("Request moved to review.", "success")
    return redirect(url_for("admin_requests", status="Under Review"))


@app.post("/admin/request/<int:request_id>/generate")
@admin_permission("requests")
def admin_request_generate(request_id):
    with get_db() as db:
        req = db.execute("SELECT * FROM certificate_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        flash("Certificate request not found.", "error")
        return redirect(url_for("admin_requests"))
    if req["status"] not in {"Pending", "Under Review"}:
        flash("This request has already been processed.", "error")
        return redirect(url_for("admin_requests"))
    info = {
        "name": req["name"],
        "roll_number": req["roll_number"],
        "activity": req["activity"],
        "position": req["position"],
        "certificate_type": req["request_type"],
        "academic_year": req["academic_year"] if "academic_year" in req.keys() else setting("default_academic_year", current_academic_year()),
        "template": allowed_template(request.form.get("template") or setting("default_template", "classic")),
        "font_family": allowed_font(request.form.get("font_family") or setting("default_font", "Helvetica")),
        "certificate_id": make_certificate_id(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "created_by": session.get("username", ADMIN_USERNAME),
    }
    info["payload_hash"] = cert_payload_hash(info)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", info["name"]).strip("_").lower() or "student"
    filename = f"{slug}_{info['certificate_id']}.pdf"
    render_certificate(GENERATED_DIR / filename, info, public_verify_url(info["certificate_id"]))
    pdf_hash = file_sha256(GENERATED_DIR / filename)
    with get_db() as db:
        db.execute("INSERT INTO certificates(certificate_id,name,roll_number,activity,position,template,font_family,filename,created_at,certificate_type,academic_year,status,payload_hash,pdf_sha256,created_by,request_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (info["certificate_id"], info["name"], info["roll_number"], info["activity"], info["position"], info["template"], info["font_family"], filename, info["created_at"], info["certificate_type"], info["academic_year"], "Valid", info["payload_hash"], pdf_hash, info["created_by"], request_id))
        db.execute("UPDATE certificate_requests SET status='Generated', processed_at=?, processed_by=?, certificate_id=? WHERE id=?", (info["created_at"], session.get("username", ADMIN_USERNAME), info["certificate_id"], request_id))
        add_request_update(db, request_id, "Generated", f"Certificate generated: {info['certificate_id']}.", session.get("admin_role","admin"), session.get("username", ADMIN_USERNAME))
        db.commit()
    notify_student(req["student_id"], "Certificate generated", f"Your {req['request_type']} certificate is ready: {info['certificate_id']}")
    audit("Fulfil request", "request", request_id, f"Generated {info['certificate_id']}")
    flash(f"Request fulfilled and certificate generated: {info['certificate_id']}", "success")
    return redirect(url_for("admin_requests"))


@app.post("/admin/request/<int:request_id>/reject")
@admin_permission("requests")
def admin_request_reject(request_id):
    note = clean(request.form.get("admin_note"), 240)
    with get_db() as db:
        db.execute("UPDATE certificate_requests SET status='Rejected', admin_note=?, processed_at=?, processed_by=? WHERE id=? AND status='Pending'", (note, datetime.now().isoformat(timespec="seconds"), session.get("username", ADMIN_USERNAME), request_id))
        req = db.execute("SELECT student_id FROM certificate_requests WHERE id=?", (request_id,)).fetchone()
        db.commit()
    if req:
        notify_student(req["student_id"], "Certificate request rejected", note or "Your certificate request was rejected by the admin.")
    audit("Reject request", "request", request_id, note)
    flash("Certificate request rejected.", "success")
    return redirect(url_for("admin_requests"))


# ------------------------- STUDENT PAGES -------------------------

@app.get("/student")
@require_role("student")
def student_dashboard():
    student = student_for_session()
    search_name = clean(request.args.get("name"), 80)
    with get_db() as db:
        certs = db.execute("SELECT * FROM certificates WHERE roll_number = ? ORDER BY id DESC", (student["roll_number"],)).fetchall()
        requests = db.execute("SELECT * FROM certificate_requests WHERE student_id = ? ORDER BY id DESC", (student["id"],)).fetchall()
        notifications = db.execute("SELECT * FROM notifications WHERE student_id=? ORDER BY id DESC LIMIT 8", (student["id"],)).fetchall()
        unread = db.execute("SELECT COUNT(*) c FROM notifications WHERE student_id=? AND is_read=0", (student["id"],)).fetchone()["c"]
    request_counts = {
        "Pending": sum(1 for row in requests if row["status"]=="Pending"),
        "Under Review": sum(1 for row in requests if row["status"]=="Under Review"),
        "Generated": sum(1 for row in requests if row["status"]=="Generated"),
        "Rejected": sum(1 for row in requests if row["status"]=="Rejected"),
    }
    shown = [c for c in certs if not search_name or norm(c["name"]) == norm(search_name)]
    return render_template("student_dashboard.html", student=student, certs=shown, all_count=len(certs), search_name=search_name, requests=requests, request_counts=request_counts, notifications=notifications, unread=unread, templates=TEMPLATES, active="dashboard")


@app.get("/student/certificates")
@require_role("student")
def student_certificates():
    student = student_for_session()
    search_name = clean(request.args.get("name"), 80)
    with get_db() as db:
        certs = db.execute("SELECT * FROM certificates WHERE roll_number = ? ORDER BY id DESC", (student["roll_number"],)).fetchall()
    shown = [c for c in certs if not search_name or norm(c["name"]) == norm(search_name)]
    return render_template("student_certificates.html", student=student, certs=shown, search_name=search_name, templates=TEMPLATES, active="certificates")


@app.get("/student/request")
@require_role("student")
def student_request_page():
    student = student_for_session()
    with get_db() as db:
        requests = db.execute("SELECT * FROM certificate_requests WHERE student_id=? ORDER BY id DESC", (student["id"],)).fetchall()
    request_ids = [row["id"] for row in requests]
    updates = {}
    if request_ids:
        with get_db() as db:
            for rid in request_ids:
                updates[rid] = db.execute("SELECT * FROM request_updates WHERE request_id=? ORDER BY id DESC", (rid,)).fetchall()
    return render_template("student_request.html", student=student, requests=requests, request_types=REQUEST_TYPES, request_updates=updates, active="request")


@app.get("/student/request/<int:request_id>")
@require_role("student")
def student_request_detail(request_id):
    student = student_for_session()
    with get_db() as db:
        req = db.execute(
            "SELECT * FROM certificate_requests WHERE id=? AND student_id=?",
            (request_id, student["id"]),
        ).fetchone()
        if not req:
            abort(404)
        updates = db.execute("SELECT * FROM request_updates WHERE request_id=? ORDER BY id ASC", (request_id,)).fetchall()
    return render_template("student_request_detail.html", student=student, request=req, updates=updates, active="request")


@app.post("/student/request")
@require_role("student")
def student_request_submit():
    student = student_for_session()
    fields = {
        "name": clean(request.form.get("name"), 80),
        "roll_number": clean(request.form.get("roll_number"), 40),
        "request_type": clean(request.form.get("request_type"), 60),
        "activity": clean(request.form.get("activity"), 140),
        "position": clean(request.form.get("position"), 80),
        "note": clean(request.form.get("note"), 240),
    }
    if fields["name"] != student["name"] or fields["roll_number"].casefold() != student["roll_number"].casefold():
        flash("For security, the requested certificate name and roll number must match your registered account.", "error")
        return redirect(url_for("student_request_page"))
    if fields["request_type"] not in REQUEST_TYPES:
        flash("Choose a valid certificate type.", "error")
        return redirect(url_for("student_request_page"))
    if not all([fields["name"], fields["roll_number"], fields["activity"], fields["position"]]):
        flash("Please fill in name, roll number, activity and position.", "error")
        return redirect(url_for("student_request_page"))
    created_at = datetime.now().isoformat(timespec="seconds")
    with get_db() as db:
        db.execute(
            "INSERT INTO certificate_requests(student_id,name,roll_number,request_type,activity,position,note,academic_year,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (student["id"], fields["name"], fields["roll_number"], fields["request_type"], fields["activity"], fields["position"], fields["note"], setting("default_academic_year", current_academic_year()), created_at),
        )
        req = db.execute(
            "SELECT id FROM certificate_requests WHERE student_id=? AND created_at=? ORDER BY id DESC LIMIT 1",
            (student["id"], created_at),
        ).fetchone()
        if req:
            add_request_update(db, req["id"], "Pending", "Certificate request submitted.", "student", student["name"])
        db.commit()
    notify_student(student["id"], "Request submitted", "Your certificate request has been submitted and is waiting for admin review.")
    flash("Certificate request submitted to the admin.", "success")
    return redirect(url_for("student_request_page"))


@app.get("/student/profile")
@require_role("student")
def student_profile():
    student = student_for_session()
    return render_template("student_profile.html", student=student, active="profile")



# ------------------------- ADVANCED ADMIN FEATURES -------------------------

@app.get("/admin/analytics")
@admin_permission("analytics")
def admin_analytics():
    ctx = admin_base_context("analytics")
    with get_db() as db:
        by_year = db.execute("SELECT academic_year, COUNT(*) c FROM certificates GROUP BY academic_year ORDER BY academic_year DESC").fetchall()
        by_type = db.execute("SELECT certificate_type, COUNT(*) c FROM certificates GROUP BY certificate_type ORDER BY c DESC").fetchall()
        by_department = db.execute("SELECT COALESCE(s.department,'CSE') department, COUNT(*) c FROM certificates c LEFT JOIN students s ON lower(s.roll_number)=lower(c.roll_number) GROUP BY department ORDER BY c DESC").fetchall()
        audit_rows = db.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 30").fetchall()
    return render_template("admin_analytics.html", **ctx, by_year=by_year, by_type=by_type, by_department=by_department, audit_rows=audit_rows)


@app.get("/admin/bulk")
@admin_permission("bulk")
def admin_bulk():
    ctx = admin_base_context("bulk")
    return render_template("admin_bulk.html", **ctx, request_types=REQUEST_TYPES, academic_year=setting("default_academic_year", current_academic_year()))


@app.post("/admin/bulk")
@admin_permission("bulk")
def admin_bulk_generate():
    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file.", "error")
        return redirect(url_for("admin_bulk"))
    try:
        text = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"Name","Roll Number","Activity","Position"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            flash("CSV must contain: Name, Roll Number, Activity, Position. Optional: Certificate Type, Academic Year, Template, Font Family.", "error")
            return redirect(url_for("admin_bulk"))
        tmpdir = Path(tempfile.mkdtemp(prefix="srgpc_bulk_"))
        generated = []
        skipped = []
        try:
            for idx, row in enumerate(reader, start=2):
                info = {
                    "name": clean(row.get("Name"),80), "roll_number": clean(row.get("Roll Number"),40),
                    "activity": clean(row.get("Activity"),140), "position": clean(row.get("Position"),80),
                    "certificate_type": clean(row.get("Certificate Type"),60) or "Achievement",
                    "academic_year": clean(row.get("Academic Year"),20) or setting("default_academic_year", current_academic_year()),
                    "template": allowed_template(row.get("Template") or setting("default_template","classic")),
                    "font_family": allowed_font(row.get("Font Family") or setting("default_font","Helvetica")),
                }
                if not all([info["name"],info["roll_number"],info["activity"],info["position"]]):
                    skipped.append(f"Row {idx}: missing required field")
                    continue
                with get_db() as db:
                    dup = db.execute("SELECT certificate_id FROM certificates WHERE lower(name)=lower(?) AND lower(roll_number)=lower(?) AND lower(activity)=lower(?) AND lower(position)=lower(?) AND status='Valid'", (info["name"],info["roll_number"],info["activity"],info["position"])).fetchone()
                if dup:
                    skipped.append(f"Row {idx}: duplicate {dup['certificate_id']}")
                    continue
                info["certificate_id"] = make_certificate_id(); info["payload_hash"] = cert_payload_hash(info); info["created_at"] = datetime.now().isoformat(timespec="seconds"); info["created_by"] = session.get("username",ADMIN_USERNAME)
                slug = re.sub(r"[^a-zA-Z0-9]+", "_", info["name"]).strip("_").lower() or "student"
                filename = f"{slug}_{info['certificate_id']}.pdf"
                outpath = tmpdir / filename
                render_certificate(outpath, info, public_verify_url(info["certificate_id"]))
                pdf_hash = file_sha256(outpath)
                final = GENERATED_DIR / filename
                shutil.copy2(outpath, final)
                with get_db() as db:
                    db.execute("INSERT INTO certificates(certificate_id,name,roll_number,activity,position,template,font_family,filename,created_at,certificate_type,academic_year,status,payload_hash,pdf_sha256,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (info["certificate_id"],info["name"],info["roll_number"],info["activity"],info["position"],info["template"],info["font_family"],filename,info["created_at"],info["certificate_type"],info["academic_year"],"Valid",info["payload_hash"],pdf_hash,info["created_by"]))
                    db.commit()
                generated.append(filename)
                audit("Bulk generate", "certificate", info["certificate_id"], f"CSV row {idx}")
            zip_path = GENERATED_DIR / f"SRGPC_Bulk_{datetime.now():%Y%m%d_%H%M%S}.zip"
            with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
                for fn in generated:
                    z.write(GENERATED_DIR/fn, arcname=fn)
            flash(f"Generated {len(generated)} certificates; skipped {len(skipped)} rows.", "success")
            if skipped: flash("Skipped: " + " | ".join(skipped[:8]), "error")
            return send_from_directory(GENERATED_DIR, zip_path.name, as_attachment=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as exc:
        flash(f"Bulk generation failed: {exc}", "error")
        return redirect(url_for("admin_bulk"))


@app.post("/admin/certificate/<certificate_id>/revoke")
@admin_permission("certificates")
def admin_revoke_certificate(certificate_id):
    reason = clean(request.form.get("reason"), 240) or "Revoked by administrator"
    with get_db() as db:
        cert = db.execute("SELECT * FROM certificates WHERE certificate_id=?", (certificate_id,)).fetchone()
        if not cert:
            flash("Certificate not found.","error"); return redirect(url_for("admin_certificates"))
        db.execute("UPDATE certificates SET status='Revoked', revoked_at=?, revoke_reason=? WHERE certificate_id=?", (datetime.now().isoformat(timespec="seconds"),reason,certificate_id))
        student = db.execute("SELECT id FROM students WHERE lower(roll_number)=lower(?)", (cert["roll_number"],)).fetchone()
        db.commit()
    if student: notify_student(student["id"], "Certificate revoked", f"Certificate {certificate_id} has been revoked. Reason: {reason}")
    audit("Revoke certificate", "certificate", certificate_id, reason)
    flash("Certificate revoked.","success")
    return redirect(url_for("admin_certificates"))


@app.post("/admin/certificate/<certificate_id>/reissue")
@admin_permission("certificates")
def admin_reissue_certificate(certificate_id):
    with get_db() as db:
        old = db.execute("SELECT * FROM certificates WHERE certificate_id=?", (certificate_id,)).fetchone()
    if not old:
        flash("Certificate not found.","error"); return redirect(url_for("admin_certificates"))
    info = {k: old[k] for k in ["name","roll_number","activity","position","template","font_family","certificate_type","academic_year"]}
    info["certificate_id"] = make_certificate_id(); info["payload_hash"] = cert_payload_hash(info); info["created_at"] = datetime.now().isoformat(timespec="seconds"); info["created_by"] = session.get("username",ADMIN_USERNAME); info["reissued_from"] = old["certificate_id"]
    slug = re.sub(r"[^a-zA-Z0-9]+","_",info["name"]).strip("_").lower() or "student"
    filename = f"{slug}_{info['certificate_id']}.pdf"
    out = GENERATED_DIR / filename
    render_certificate(out, info, public_verify_url(info["certificate_id"]))
    pdf_hash = file_sha256(out)
    with get_db() as db:
        db.execute("UPDATE certificates SET status='Reissued' WHERE certificate_id=?", (certificate_id,))
        db.execute("INSERT INTO certificates(certificate_id,name,roll_number,activity,position,template,font_family,filename,created_at,certificate_type,academic_year,status,payload_hash,pdf_sha256,created_by,reissued_from) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (info["certificate_id"],info["name"],info["roll_number"],info["activity"],info["position"],info["template"],info["font_family"],filename,info["created_at"],info["certificate_type"],info["academic_year"],"Valid",info["payload_hash"],pdf_hash,info["created_by"],certificate_id))
        student = db.execute("SELECT id FROM students WHERE lower(roll_number)=lower(?)", (info["roll_number"],)).fetchone()
        db.commit()
    if student: notify_student(student["id"], "Certificate reissued", f"Your replacement certificate is ready: {info['certificate_id']}")
    audit("Reissue certificate", "certificate", info["certificate_id"], f"Reissued from {certificate_id}")
    flash(f"Replacement certificate created: {info['certificate_id']}","success")
    return redirect(url_for("admin_certificates"))


@app.get("/admin/audit")
@admin_permission("analytics")
def admin_audit():
    ctx = admin_base_context("audit")
    with get_db() as db: rows=db.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 250").fetchall()
    return render_template("admin_audit.html", **ctx, rows=rows)


@app.get("/admin/access")
@admin_permission("dashboard")
def admin_access():
    if session.get("admin_role") != "superadmin":
        return redirect(url_for("admin_dashboard"))
    ctx = admin_base_context("admin_access")
    student_query = clean(request.args.get("q"), 100)
    with get_db() as db:
        if student_query:
            like = f"%{student_query}%"
            students = db.execute(
                """SELECT id,username,name,roll_number,gmail,admin_enabled
                   FROM students
                   WHERE LOWER(name) LIKE LOWER(?) OR LOWER(username) LIKE LOWER(?)
                      OR LOWER(roll_number) LIKE LOWER(?) OR LOWER(gmail) LIKE LOWER(?)
                   ORDER BY LOWER(name) LIMIT 100""",
                (like, like, like, like),
            ).fetchall()
        else:
            students = db.execute(
                """SELECT id,username,name,roll_number,gmail,admin_enabled
                   FROM students ORDER BY LOWER(name) LIMIT 100"""
            ).fetchall()
    return render_template("admin_access.html", **ctx, students=students, student_query=student_query)


@app.get("/admin/users")
@admin_permission("dashboard")
def admin_users():
    return redirect(url_for("admin_access"))


@app.post("/admin/student-admin/<int:student_id>/toggle")
@admin_permission("dashboard")
def admin_student_admin_toggle(student_id):
    if session.get("admin_role") != "superadmin":
        flash("Only the superadmin can grant or revoke student admin access.", "error")
        return redirect(url_for("admin_access"))
    with get_db() as db:
        student = db.execute(
            "SELECT id,username,name,admin_enabled FROM students WHERE id=?",
            (student_id,),
        ).fetchone()
        if not student:
            abort(404)
        enabled = 0 if student["admin_enabled"] else 1
        db.execute(
            "UPDATE students SET admin_enabled=?,admin_role=? WHERE id=?",
            (enabled, "admin" if enabled else "", student_id),
        )
        db.commit()
    audit("Student admin access changed", "student", student_id, f"enabled={enabled}")
    flash(
        f"Admin access {'granted' if enabled else 'revoked'} for {student['name'] or student['username']}.",
        "success",
    )
    query = urllib.parse.quote_plus(clean(request.form.get("q"), 100))
    return redirect(url_for("admin_access") + (f"?q={query}" if query else ""))


@app.get("/admin/notifications")
@require_role("admin")
def admin_notifications():
    return redirect(url_for("admin_dashboard"))


@app.get("/student/notifications/read/<int:notification_id>")
@require_role("student")
def student_notification_read(notification_id):
    student = student_for_session()
    with get_db() as db:
        db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND student_id=?", (notification_id, student["id"]))
        db.commit()
    return redirect(request.referrer or url_for("student_dashboard"))


@app.get("/student/notifications/read")
@require_role("student")
def student_notifications_read():
    student=student_for_session()
    with get_db() as db: db.execute("UPDATE notifications SET is_read=1 WHERE student_id=?",(student["id"],)); db.commit()
    return redirect(url_for("student_dashboard"))


@app.get("/verify", defaults={"certificate_id": ""})
@app.get("/verify/<certificate_id>")
def public_verify(certificate_id):
    certificate_id=clean(certificate_id,80).upper()
    cert=None
    if certificate_id:
        with get_db() as db: cert=db.execute("SELECT certificate_id,name,roll_number,activity,position,certificate_type,academic_year,template,font_family,created_at,status,payload_hash,pdf_sha256,revoke_reason,reissued_from,created_by,revoked_at FROM certificates WHERE certificate_id=?",(certificate_id,)).fetchone()
    return render_template("public_verify.html", certificate=cert, query=certificate_id)


@app.get("/api/verify/<certificate_id>")
def api_verify(certificate_id):
    with get_db() as db: cert=db.execute("SELECT certificate_id,name,roll_number,activity,position,certificate_type,academic_year,created_at,status,payload_hash,pdf_sha256,revoke_reason,reissued_from FROM certificates WHERE certificate_id=?",(clean(certificate_id,80).upper(),)).fetchone()
    if not cert: return {"valid":False,"status":"NOT_FOUND","certificate_id":clean(certificate_id,80).upper()},404
    return {"valid": cert["status"]=="Valid", **dict(cert)}

# ------------------------- FILE ACCESS -------------------------

@app.get("/download/<path:filename>")
def download(filename):
    role = session.get("role")
    if role not in {"admin", "student"}:
        return redirect(url_for("login"))
    cert = certificate_for_filename(filename)
    if not cert:
        abort(404)
    if role == "student":
        student = student_for_session()
        if not student or student["roll_number"].casefold() != cert["roll_number"].casefold():
            abort(403)

    # Render's free web-service filesystem is ephemeral, so generated PDFs can
    # disappear after a new deployment. Rebuild a missing certificate from the
    # immutable certificate record instead of returning a 404.
    pdf_path = GENERATED_DIR / filename
    if not pdf_path.exists():
        info = {
            "name": cert["name"],
            "roll_number": cert["roll_number"],
            "activity": cert["activity"],
            "position": cert["position"],
            "certificate_type": cert["certificate_type"],
            "academic_year": cert["academic_year"],
            "template": allowed_template(cert["template"]),
            "font_family": allowed_font(cert["font_family"]),
            "certificate_id": cert["certificate_id"],
            "payload_hash": cert["payload_hash"],
            "created_at": cert["created_at"],
            "created_by": cert["created_by"],
        }
        render_certificate(pdf_path, info, public_verify_url(cert["certificate_id"]))
        # Keep the stored integrity hash in sync with a regenerated file.
        new_hash = file_sha256(pdf_path)
        with get_db() as db:
            db.execute("UPDATE certificates SET pdf_sha256=? WHERE certificate_id=?", (new_hash, cert["certificate_id"]))
            db.commit()

    return send_from_directory(GENERATED_DIR, filename, as_attachment=True)


@app.get("/static-signature/<kind>")
@require_role("admin")
def signature_preview(kind):
    if kind not in {"teacher", "principal"}:
        return "", 404
    path = current_signature_path(kind)
    if not path:
        return "", 404
    return send_from_directory(path.parent, path.name)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
