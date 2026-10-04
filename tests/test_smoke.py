import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    generated_dir = tmp_path / "generated"
    signature_dir = data_dir / "signatures"
    monkeypatch.setenv("SRGPC_DB_PATH", str(db_path))
    monkeypatch.setenv("SRGPC_GENERATED_DIR", str(generated_dir))
    monkeypatch.setenv("SRGPC_SIGNATURE_DIR", str(signature_dir))
    monkeypatch.setenv("SRGPC_TESTING", "1")
    monkeypatch.setenv("SRGPC_SESSION_KEY", "test-session-key")
    monkeypatch.setenv("SRGPC_ADMIN_USERNAME", "ADMIN")
    monkeypatch.setenv("SRGPC_ADMIN_PASSWORD", "0000")
    from app import app as flask_app
    flask_app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    with flask_app.test_client() as client:
        yield flask_app, client


def csrf(html):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert match
    return match.group(1)


def test_healthz(app):
    _, client = app
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_csrf_rejects_state_change_without_token(app):
    _, client = app
    response = client.post("/login", data={"role": "admin", "username": "ADMIN", "password": "0000"})
    assert response.status_code == 403
    assert "CSRF" in response.get_json()["error"]


def test_admin_login_with_csrf(app):
    _, client = app
    page = client.get("/")
    token = csrf(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"role": "admin", "username": "ADMIN", "password": "0000", "_csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")


def test_security_headers(app):
    _, client = app
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert "X-Request-ID" in response.headers

def test_login_has_accessibility_and_branding_markers(app):
    _, client = app
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert 'Skip to login form' in html
    assert 'Certificate Management System' in html
    assert 'college_logo.png' in html
    assert 'id="login-main"' in html
    assert 'aria-pressed="true"' in html


def test_custom_404_state(app):
    _, client = app
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "This page isn't available" in html


def test_all_certificate_templates_render(app, tmp_path):
    from app import TEMPLATES as APP_TEMPLATES
    from certificate_renderer import TEMPLATES as RENDER_TEMPLATES, draw_certificate

    assert len(APP_TEMPLATES) == 20
    assert set(APP_TEMPLATES) == set(RENDER_TEMPLATES)

    sample = {
        "name": "Aarav Sharma",
        "roll_number": "CSE24017",
        "activity": "National Technical Innovation Challenge",
        "position": "First Position",
        "certificate_type": "Achievement",
        "academic_year": "2026-27",
        "certificate_id": "SRGPC-2026-TEST01",
        "font_family": "Helvetica",
        "title": "CERTIFICATE OF ACHIEVEMENT",
    }
    for template in RENDER_TEMPLATES:
        output = tmp_path / f"{template}.pdf"
        draw_certificate(output, {**sample, "template": template}, "https://example.com/verify/SRGPC-2026-TEST01")
        pdf = output.read_bytes()
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 2000


def test_signature_library_persists_named_drawings(app, tmp_path):
    import base64
    from app import current_signature_path, get_db, save_signature_data, set_setting

    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    save_signature_data(
        "teacher",
        "data:image/png;base64," + png,
        "Dr. R. K. Sharma Signature",
    )

    with get_db() as db:
        row = db.execute(
            "SELECT name,filename,mime_type,data_base64 FROM signature_library WHERE kind='teacher' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["name"] == "Dr. R. K. Sharma Signature"
    assert row["mime_type"] == "image/png"
    assert base64.b64decode(row["data_base64"]) == base64.b64decode(png)

    active = current_signature_path("teacher")
    assert active and active.exists()
    active.unlink()
    restored = current_signature_path("teacher")
    assert restored and restored.exists()
    assert restored.read_bytes() == base64.b64decode(png)

    set_setting("teacher_signature", "")
