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


def test_named_signature_survives_logout_and_login(app):
    import base64
    from app import save_signature_data

    _, client = app
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    save_signature_data("principal", "data:image/png;base64," + png, "Principal Office Signature")

    login_page = client.get("/")
    token = csrf(login_page.get_data(as_text=True))
    logged_in = client.post(
        "/login",
        data={"role": "admin", "username": "ADMIN", "password": "0000", "_csrf_token": token},
        follow_redirects=False,
    )
    assert logged_in.status_code == 302
    client.get("/logout")

    relogin_page = client.get("/")
    relogin_token = csrf(relogin_page.get_data(as_text=True))
    relogin = client.post(
        "/login",
        data={"role": "admin", "username": "ADMIN", "password": "0000", "_csrf_token": relogin_token},
        follow_redirects=False,
    )
    assert relogin.status_code == 302
    page = client.get("/admin/signatures")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Principal Office Signature" in html
    assert "Saved Signature Library" in html
    assert "Currently active" in html



def test_generate_form_omits_non_certificate_academic_fields(app):
    _, client = app
    page = client.get("/")
    token = csrf(page.get_data(as_text=True))
    login = client.post(
        "/login",
        data={"role":"admin","username":"ADMIN","password":"0000","_csrf_token":token},
        follow_redirects=False,
    )
    assert login.status_code == 302
    response = client.get("/admin/generate")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="department"' not in html
    assert 'name="programme"' not in html
    assert 'name="semester"' not in html



def test_legacy_template_display_falls_back_safely(app):
    flask_app, _ = app
    from flask import render_template_string
    with flask_app.test_request_context("/"):
        html = render_template_string(
            "{{ templates.get(item.template, {}).get('name', 'Legacy Certificate') }}",
            item={"template": "nss_seven_day"},
            templates={"classic": {"name": "Classic Gold"}},
        )
    assert html.strip() == "Legacy Certificate"


def test_student_certificate_wallet_hides_template_names(app):
    flask_app, _ = app
    from flask import render_template
    with flask_app.test_request_context("/student/certificates"):
        html = render_template(
            "student_certificates.html",
            student={"name":"Test Student","roll_number":"CSE0001"},
            certs=[{
                "status":"Valid","created_at":"2026-10-05",
                "position":"1st","activity":"Competition","certificate_type":"Achievement",
                "academic_year":"2026-27","template":"royal","certificate_id":"TEST-001",
                "filename":"TEST-001.pdf",
            }],
            search_name="",
            templates={"royal":{"name":"Royal Violet"}},
        )
    assert "2026-27" in html
    assert "Royal Violet" not in html


def test_pwa_assets_are_available(app):
    _, client = app
    manifest = client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["Content-Type"].startswith("application/manifest+json")
    body = manifest.get_json()
    assert body["display"] == "standalone"
    assert body["start_url"] == "/"
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert "Cache-Control" in worker.headers


def test_mobile_oauth_handoff_is_one_time(app):
    flask_app, _ = app
    with flask_app.test_request_context("/"):
        token = flask_app.view_functions["_create_mobile_oauth_handoff"]({
            "login_mode": "student",
            "pending_google": {"sub": "test-sub", "gmail": "test@gmail.com", "name": "Test"},
        })
        first = flask_app.view_functions["_consume_mobile_oauth_handoff"](token)
        second = flask_app.view_functions["_consume_mobile_oauth_handoff"](token)
    assert first["login_mode"] == "student"
    assert second is None


def test_mobile_complete_rejects_unknown_token(app):
    _, client = app
    response = client.get("/auth/mobile/complete?token=definitely-invalid")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
