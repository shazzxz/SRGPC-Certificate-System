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


def test_mobile_google_oauth_state_is_self_contained(app):
    flask_app, _ = app
    with flask_app.test_request_context("/"):
        from app import _create_mobile_google_state, _read_mobile_google_state
        state = _create_mobile_google_state("student")
        payload = _read_mobile_google_state(state)
        assert payload["mobile"] is True
        assert payload["login_mode"] == "student"
        assert _read_mobile_google_state(state[:-1] + ("0" if state[-1] != "0" else "1")) is None


def test_mobile_oauth_handoff_is_one_time(app):
    flask_app, _ = app
    with flask_app.test_request_context("/"):
        from app import _create_mobile_oauth_handoff, _consume_mobile_oauth_handoff
        token = _create_mobile_oauth_handoff({
            "login_mode": "student",
            "pending_google": {"sub": "test-sub", "gmail": "test@gmail.com", "name": "Test"},
        })
        first = _consume_mobile_oauth_handoff(token)
        second = _consume_mobile_oauth_handoff(token)
    assert first["login_mode"] == "student"
    assert second is None


def test_mobile_complete_rejects_unknown_token(app):
    _, client = app
    response = client.get("/auth/mobile/complete?token=definitely-invalid")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_mobile_oauth_state_can_be_created_and_consumed(app):
    flask_app, _ = app
    from app import _create_mobile_google_state, _read_mobile_google_state
    with flask_app.app_context():
        state = _create_mobile_google_state("student")
        row = _read_mobile_google_state(state)
        assert row is not None
        assert row["login_mode"] == "student"
        assert _read_mobile_google_state(state) is not None


def test_mobile_oauth_response_returns_app_callback(app):
    flask_app, _ = app
    from app import _mobile_oauth_response
    with flask_app.app_context():
        html = _mobile_oauth_response("abc123")
        assert "oauth2callback?token=abc123" in html


def _create_test_student(client):
    import secrets
    from app import get_db
    from werkzeug.security import generate_password_hash
    from datetime import datetime

    suffix = secrets.token_hex(4)
    username = f"student-test-{suffix}"
    roll_number = f"CSETEST{suffix.upper()}"
    gmail = f"{username}@gmail.com"
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO students(username,password_hash,mobile,roll_number,gmail,name,created_at) VALUES(?,?,?,?,?,?,?)",
            (username, generate_password_hash("student-pass"), "9999999999", roll_number, gmail, "Test Student", datetime.now().isoformat(timespec="seconds")),
        )
        student_id = cursor.lastrowid
        db.commit()
    with client.session_transaction() as session_data:
        session_data["role"] = "student"
        session_data["student_id"] = student_id
        session_data["username"] = username
    return student_id, roll_number


def test_student_request_page_uses_one_respectful_free_text_box(app):
    _, client = app
    _create_test_student(client)
    response = client.get("/student/request")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="request_text"' in html
    assert 'name="request_type"' not in html
    assert 'name="activity"' not in html
    assert 'name="position"' not in html
    assert "Requesting as" in html
    assert "student-request-account" in html
    assert "What certificate would you like to request?" not in html
    assert "Describe what you need in your own words." not in html


def test_student_free_text_request_uses_registered_identity(app):
    _, client = app
    student_id, roll_number = _create_test_student(client)
    page = client.get("/student/request")
    token = csrf(page.get_data(as_text=True))
    response = client.post(
        "/student/request",
        data={"_csrf_token": token, "request_text": "I need a certificate for volunteering at the college technical fest."},
        follow_redirects=False,
    )
    assert response.status_code == 302
    from app import get_db
    with get_db() as db:
        row = db.execute(
            "SELECT name,roll_number,request_type,activity,position,note FROM certificate_requests WHERE student_id=? ORDER BY id DESC LIMIT 1",
            (student_id,),
        ).fetchone()
    assert row is not None
    assert row["name"] == "Test Student"
    assert row["roll_number"] == roll_number
    assert row["request_type"] == "Other"
    assert row["activity"] == "Student request"
    assert row["note"] == "I need a certificate for volunteering at the college technical fest."


def test_certificate_layout_header_footer_clearance(app):
    from pathlib import Path
    import certificate_renderer as renderer

    root = Path(__file__).resolve().parents[1]
    preview = (root / "static" / "app.js").read_text(encoding="utf-8")

    # Keep the crest clear of the institute label and leave generous gaps
    # between the institution, title, subtitle, and body copy.
    assert renderer.LOGO_CENTER_Y - renderer.LOGO_MAX_H / 2 > renderer.INSTITUTION_Y
    assert renderer.INSTITUTION_Y - renderer.TITLE_Y >= 40
    assert renderer.TITLE_Y - renderer.SUBTITLE_Y >= 25
    assert renderer.SUBTITLE_Y - renderer.PRESENTED_TO_Y >= 28

    # Reserve a distinct footer zone and keep the QR panel inside the frame.
    assert renderer.FOOTER_PANEL_BOTTOM + renderer.FOOTER_PANEL_HEIGHT < renderer.SIGNATURE_LINE_Y - 17
    assert renderer.QR_BOX_X + renderer.QR_BOX <= renderer.PAGE_W - 40
    assert renderer.SIGNATURE_LINE_Y > renderer.QR_BOX_Y + 80

    for template in renderer.TEMPLATES:
        panel_left, panel_bottom, panel_width, panel_height = renderer.footer_panel_bounds(template)
        assert panel_left >= renderer.content_bounds(template)[0]
        assert panel_bottom == 44
        assert panel_width > 0 and panel_height == 46
        assert panel_left + panel_width <= renderer.QR_BOX_X - 12

    # The live SVG preview must use the same spacing and no crest-crossing rule.
    assert "addImage(svg,stage.dataset.logoUrl,cx-40,34,80,80)" in preview
    assert "addText(svg,'SRGPC',cx,132" in preview
    assert "addText(svg,'CERTIFICATE OF ACHIEVEMENT',cx,179" in preview
    assert "Protected footer panel" in preview and "CERTIFICATE TYPE / YEAR" in preview
    assert "addRect(svg,qrX,475,96,96" in preview
    assert "addLine(svg,36,84,806,84" not in preview



def test_admin_can_issue_pending_request_to_linked_student_account(app):
    from app import get_db

    _, client = app
    student_id, original_roll = _create_test_student(client)

    # Submit a request as the student using their authenticated identity.
    student_page = client.get("/student/request")
    student_token = csrf(student_page.get_data(as_text=True))
    submitted = client.post(
        "/student/request",
        data={
            "_csrf_token": student_token,
            "request_text": "Please provide my participation certificate for the annual technical fest.",
        },
        follow_redirects=False,
    )
    assert submitted.status_code == 302

    with get_db() as db:
        request_row = db.execute(
            "SELECT * FROM certificate_requests WHERE student_id=? ORDER BY id DESC LIMIT 1",
            (student_id,),
        ).fetchone()
        assert request_row is not None
        request_id = request_row["id"]

        # Simulate a profile update after the request was first submitted.
        # The live student profile, not the stale request snapshot, must issue
        # the certificate and remain its permanent account owner.
        db.execute(
            "UPDATE students SET name=?, roll_number=? WHERE id=?",
            ("Current Profile Name", "CSECURRENT01", student_id),
        )
        db.execute(
            "UPDATE certificate_requests SET name=?, roll_number=? WHERE id=?",
            ("Old Request Snapshot", original_roll, request_id),
        )
        db.commit()

    # Sign in as admin without moving the request through the old review step.
    with client.session_transaction() as session_data:
        session_data.clear()
    login_page = client.get("/")
    admin_token = csrf(login_page.get_data(as_text=True))
    login = client.post(
        "/login",
        data={
            "role": "admin",
            "username": "ADMIN",
            "password": "0000",
            "_csrf_token": admin_token,
        },
        follow_redirects=False,
    )
    assert login.status_code == 302

    detail = client.get(f"/admin/request/{request_id}")
    assert detail.status_code == 200
    detail_html = detail.get_data(as_text=True)
    assert "Current Profile Name" in detail_html
    assert "CSECURRENT01" in detail_html
    assert "Generate &amp; send to student" in detail_html
    assert "readonly" in detail_html

    # Direct generation from Pending must succeed; no /review POST required.
    generate_token = csrf(detail_html)
    generated = client.post(
        f"/admin/request/{request_id}/generate",
        data={
            "_csrf_token": generate_token,
            "certificate_type": "Participation",
            "activity": "Annual Technical Fest",
            "position": "Volunteer",
            "template": "classic",
            "font_family": "Helvetica",
        },
        follow_redirects=False,
    )
    assert generated.status_code == 302

    with get_db() as db:
        request_after = db.execute(
            "SELECT status,certificate_id FROM certificate_requests WHERE id=?",
            (request_id,),
        ).fetchone()
        certificate = db.execute(
            "SELECT * FROM certificates WHERE certificate_id=?",
            (request_after["certificate_id"],),
        ).fetchone()
        notification = db.execute(
            "SELECT * FROM notifications WHERE student_id=? AND title='Certificate generated' ORDER BY id DESC LIMIT 1",
            (student_id,),
        ).fetchone()

    assert request_after["status"] == "Generated"
    assert certificate is not None
    assert certificate["request_id"] == request_id
    assert certificate["name"] == "Current Profile Name"
    assert certificate["roll_number"] == "CSECURRENT01"
    assert certificate["activity"] == "Annual Technical Fest"
    assert notification is not None

    # The issued PDF and detail page belong to that exact account even if its
    # roll number later changes; another student with a different ID cannot see it.
    with get_db() as db:
        db.execute("UPDATE students SET roll_number='CSEUPDATED02' WHERE id=?", (student_id,))
        db.commit()
    with client.session_transaction() as session_data:
        session_data.clear()
        session_data["role"] = "student"
        session_data["student_id"] = student_id
    wallet = client.get("/student/certificates")
    assert wallet.status_code == 200
    assert request_after["certificate_id"] in wallet.get_data(as_text=True)
    student_detail = client.get(f"/student/certificate/{request_after['certificate_id']}")
    assert student_detail.status_code == 200
    download = client.get(f"/download/{certificate['filename']}")
    assert download.status_code == 200
    assert download.data.startswith(b"%PDF")

    other_student_id, _ = _create_test_student(client)
    assert other_student_id != student_id
    denied_detail = client.get(f"/student/certificate/{request_after['certificate_id']}")
    assert denied_detail.status_code == 404
    denied_download = client.get(f"/download/{certificate['filename']}")
    assert denied_download.status_code == 403


def test_mobile_student_layout_has_stacked_actions_and_compact_request_ui(app):
    root = Path(__file__).resolve().parents[1]
    mobile_css = (root / "static" / "mobile-polish.css").read_text(encoding="utf-8")
    request_template = (root / "templates" / "student_request.html").read_text(encoding="utf-8")
    wallet_template = (root / "templates" / "student_certificates.html").read_text(encoding="utf-8")

    assert "grid-template-columns: minmax(0, 1fr) !important" in mobile_css
    assert ".glass-ui .notification-row" in mobile_css
    assert ".glass-ui .panel-head" in mobile_css
    assert "student-request-account" in request_template
    assert "What certificate would you like to request?" not in request_template
    assert "No name search is required" not in wallet_template


def test_all_certificate_templates_and_fonts_use_aligned_safe_areas(monkeypatch):
    """Exercise every selectable PDF theme, all supported fonts and its real page box."""
    import re
    from io import BytesIO

    import app as portal
    import certificate_renderer as renderer
    from reportlab.pdfbase.pdfmetrics import stringWidth

    assert set(portal.TEMPLATES) == set(renderer.TEMPLATES)
    assert len(renderer.TEMPLATES) == 20

    # The browser preview must use the same page baselines and asymmetric
    # content centers as the authoritative PDF renderer.
    root = Path(__file__).resolve().parents[1]
    preview_js = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "opts.baseline||'alphabetic'" in preview_js
    assert "contentCenters={modern:462,skyline:468,coastal:442}" in preview_js
    assert "Protected footer panel" in preview_js and "footerColumns" in preview_js

    original_fit = renderer.draw_fit_centered
    original_logo = renderer._logo
    original_signature = renderer.draw_signature

    for template in renderer.TEMPLATES:
        left, right = renderer.content_bounds(template)
        center = renderer.content_center(template)
        assert center == pytest.approx((left + right) / 2, abs=0.01)

        # Signature rules are mirrored around the same visual center and stay
        # inside the content rail for each template.
        signature_xs = renderer.signature_centers(template)
        assert sum(signature_xs) / 2 == pytest.approx(center, abs=0.01)
        assert signature_xs[0] - 80 >= left
        assert signature_xs[1] + 80 <= right
        assert signature_xs[0] - 95 >= left
        assert signature_xs[1] + 95 < renderer.QR_BOX_X

        # Footer columns must not touch one another or collide with the QR box.
        roll_x, roll_w, type_x, type_w, cert_x, cert_w = renderer._footer_positions(template)
        footer_regions = [
            (roll_x - roll_w / 2, roll_x + roll_w / 2),
            (type_x - type_w / 2, type_x + type_w / 2),
            (cert_x - cert_w / 2, cert_x + cert_w / 2),
        ]
        assert footer_regions[0][1] < footer_regions[1][0]
        assert footer_regions[1][1] < footer_regions[2][0]
        assert footer_regions[0][0] >= left
        assert footer_regions[2][1] < renderer.QR_BOX_X

        for family in renderer.FONT_OPTIONS:
            fit_records = []
            logo_records = []
            signature_records = []

            def checked_fit(canvas, text, font, x, y, max_width, start_size, min_size, color, step=0.5):
                size = original_fit(canvas, text, font, x, y, max_width, start_size, min_size, color, step)
                width = stringWidth(renderer._safe_text(text), font, size)
                assert width <= max_width + 0.1, (template, family, text, width, max_width, size)
                fit_records.append((text, x, y, max_width, size))
                return size

            def checked_logo(canvas, path, x, y, max_w=62, max_h=62):
                logo_records.append((x, y, max_w, max_h))
                return original_logo(canvas, path, x, y, max_w, max_h)

            def checked_signature(canvas, path, center_x, line_y, label, font, ink, line_color):
                signature_records.append(center_x)
                return original_signature(canvas, path, center_x, line_y, label, font, ink, line_color)

            monkeypatch.setattr(renderer, "draw_fit_centered", checked_fit)
            monkeypatch.setattr(renderer, "_logo", checked_logo)
            monkeypatch.setattr(renderer, "draw_signature", checked_signature)

            target = BytesIO()
            renderer.draw_certificate(
                target,
                {
                    "template": template,
                    "font_family": family,
                    "name": "Shashwat Solanki",
                    "roll_number": "CSE2026-24039C04060",
                    "activity": "Inter-College Technical Festival and Innovation Challenge 2026",
                    "position": "First Place / Overall Winner",
                    "certificate_type": "Workshop / Training",
                    "academic_year": "2026-27",
                    "certificate_id": "SRGPC-2026-DF4971159AF1",
                },
                verification_url=None,
                logo_path=None,
                show_qr=False,
            )
            pdf = target.getvalue()
            assert pdf.startswith(b"%PDF-")
            page_box = re.search(
                rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]",
                pdf,
            )
            assert page_box, (template, family, "missing PDF page box")
            page_width, page_height = map(float, page_box.groups())
            assert page_width == pytest.approx(renderer.PAGE_W, abs=0.02)
            assert page_height == pytest.approx(renderer.PAGE_H, abs=0.02)
            assert page_width > page_height  # A4 landscape, not a portrait crop.

            assert len(logo_records) == 1
            assert logo_records[0][0] == pytest.approx(center, abs=0.01)
            assert logo_records[0][1] == renderer.LOGO_CENTER_Y
            assert logo_records[0][2:] == (renderer.LOGO_MAX_W, renderer.LOGO_MAX_H)

            assert len(signature_records) == 2
            assert signature_records == pytest.approx(signature_xs, abs=0.01)

            header_positions = {
                text: x for text, x, _y, _width, _size in fit_records
                if text in {"SRGPC", "CERTIFICATE OF ACHIEVEMENT"}
            }
            assert header_positions["SRGPC"] == pytest.approx(center, abs=0.01)
            assert header_positions["CERTIFICATE OF ACHIEVEMENT"] == pytest.approx(center, abs=0.01)


def test_certificate_content_bounds_cover_all_three_asymmetric_frames():
    import certificate_renderer as renderer

    expected = {
        "modern": (106.0, renderer.PAGE_W - renderer.SAFE),
        "skyline": (118.0, renderer.PAGE_W - renderer.SAFE),
        "coastal": (66.0, renderer.PAGE_W - renderer.SAFE),
    }
    assert renderer.TEMPLATE_CONTENT_BOUNDS == expected

    for template in renderer.TEMPLATES:
        left, right = renderer.content_bounds(template)
        assert left >= 0
        assert right <= renderer.PAGE_W
        assert right > left
        assert renderer.content_center(template) == pytest.approx((left + right) / 2, abs=0.01)


def test_live_preview_asset_cache_key_is_bumped():
    root = Path(__file__).resolve().parents[1]
    base_template = (root / "templates" / "base.html").read_text(encoding="utf-8")
    preview_js = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "filename='app.js', v='12'" in base_template
    assert "Protected footer panel" in preview_js
    assert "footerLayouts" not in preview_js
    assert "label:'CERTIFICATE ID'" in preview_js
