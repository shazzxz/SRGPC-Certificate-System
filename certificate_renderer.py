from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.pdfmetrics import getFont

FONT_OPTIONS = {
    "Helvetica": {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"},
    "Times": {"regular": "Times-Roman", "bold": "Times-Bold", "italic": "Times-Italic"},
    "Courier": {"regular": "Courier", "bold": "Courier-Bold", "italic": "Courier-Oblique"},
}

PAGE_W, PAGE_H = landscape(A4)
SAFE = 24
QR_BOX = 98
QR_SIZE = 74
QR_BOX_X = PAGE_W - SAFE - QR_BOX
QR_BOX_Y = 24
FOOTER_TOP = 120
SIGNATURE_LINE_Y = 138
SIGNATURE_XS = (214, PAGE_W - 214)

# The renderer deliberately uses one shared content grid for every template.
# This prevents the browser preview and the PDF from drifting into different
# layouts and gives long values the same safety limits in every theme.
TEMPLATES = {
    "classic": {"bg": "#fbf8ef", "ink": "#202124", "muted": "#7c7366", "accent": "#b38724", "accent_soft": "#efe2be"},
    "modern": {"bg": "#f7faff", "ink": "#0f172a", "muted": "#64748b", "accent": "#2563eb", "accent_soft": "#dbeafe"},
    "emerald": {"bg": "#f7fcfa", "ink": "#123c37", "muted": "#67817c", "accent": "#0f766e", "accent_soft": "#d9f2eb"},
    "midnight": {"bg": "#0b1426", "ink": "#f8fafc", "muted": "#9fb1ca", "accent": "#7dd3fc", "accent_soft": "#18345c"},
    "royal": {"bg": "#fbf9ff", "ink": "#2f204b", "muted": "#7e7192", "accent": "#6d28d9", "accent_soft": "#eee6ff"},
    "burgundy": {"bg": "#fffaf7", "ink": "#3f1719", "muted": "#8b6d6e", "accent": "#8f2027", "accent_soft": "#f2e0d8"},
    "skyline": {"bg": "#f6fbff", "ink": "#10233c", "muted": "#6e8197", "accent": "#0ea5e9", "accent_soft": "#dff4ff"},
    "minimal": {"bg": "#ffffff", "ink": "#111827", "muted": "#6b7280", "accent": "#334155", "accent_soft": "#f1f5f9"},
}


def _font_family(name: str):
    return FONT_OPTIONS.get(name, FONT_OPTIONS["Helvetica"])


def _safe_text(value: object, fallback: str = "") -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\n", " ").split())
    return text or fallback


def _draw_image(c: canvas.Canvas, path: Optional[Path], x: float, y: float, max_w: float, max_h: float):
    if not path:
        return
    path = Path(path)
    if not path.exists():
        return
    try:
        iw, ih = ImageReader(str(path)).getSize()
        if iw <= 0 or ih <= 0:
            return
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        c.drawImage(ImageReader(str(path)), x - w / 2, y - h / 2, width=w, height=h, preserveAspectRatio=True, mask="auto")
    except Exception:
        return


def _logo(c: canvas.Canvas, logo_path: Optional[Path], x: float, y: float, max_w: float = 62, max_h: float = 62):
    _draw_image(c, logo_path, x, y, max_w, max_h)


def _fit_size(text: str, font: str, start: float, min_size: float, max_width: float, step: float = 0.5) -> float:
    text = _safe_text(text)
    size = float(start)
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= step
    return max(min_size, size)


def _split_long_word(word: str, font: str, size: float, max_width: float):
    if stringWidth(word, font, size) <= max_width:
        return [word]
    chunks = []
    current = ""
    for ch in word:
        trial = current + ch
        if current and stringWidth(trial, font, size) > max_width:
            chunks.append(current)
            current = ch
        else:
            current = trial
    if current:
        chunks.append(current)
    return chunks or [word]


def wrap_lines(text: str, font: str, size: float, max_width: float, max_lines: Optional[int] = None):
    words = _safe_text(text).split()
    lines = []
    current = ""
    for word in words:
        pieces = _split_long_word(word, font, size, max_width)
        for piece in pieces:
            trial = f"{current} {piece}".strip()
            if current and stringWidth(trial, font, size) > max_width:
                lines.append(current)
                current = piece
                if max_lines and len(lines) >= max_lines:
                    return lines[:max_lines]
            else:
                current = trial
    if current:
        lines.append(current)
    return lines[:max_lines] if max_lines else lines


def draw_fit_centered(c: canvas.Canvas, text: str, font: str, x: float, y: float, max_width: float,
                      start_size: float, min_size: float, color, step: float = 0.5):
    text = _safe_text(text)
    size = _fit_size(text, font, start_size, min_size, max_width, step)
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(x, y, text)
    return size


def draw_wrapped_center_fit(c: canvas.Canvas, text: str, font: str, x: float, y: float, max_width: float,
                            start_size: float = 13, min_size: float = 10, max_lines: int = 2,
                            leading: float = 18, color=colors.black):
    text = _safe_text(text)
    size = start_size
    lines = wrap_lines(text, font, size, max_width, max_lines=max_lines)
    while size > min_size and len(wrap_lines(text, font, size, max_width, max_lines=max_lines)) > max_lines:
        size -= 0.5
        lines = wrap_lines(text, font, size, max_width, max_lines=max_lines)
    # If a long value still needs more lines, keep two lines and shrink enough
    # that the last line can fit. We never paint outside the fixed text box.
    if len(lines) > max_lines:
        size = min_size
        lines = wrap_lines(text, font, size, max_width, max_lines=max_lines)
    c.setFont(font, max(size, min_size))
    c.setFillColor(color)
    for idx, line in enumerate(lines):
        c.drawCentredString(x, y - idx * leading, line)
    return y - max(0, len(lines) - 1) * leading


def draw_qr(c: canvas.Canvas, data: str, x: float, y: float, size: float = QR_SIZE):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    tmp = BytesIO()
    img.save(tmp, format="PNG")
    tmp.seek(0)
    c.drawImage(ImageReader(tmp), x, y, width=size, height=size, preserveAspectRatio=True, mask="auto")


def draw_signature(c: canvas.Canvas, path: Optional[Path], center_x: float, line_y: float, label: str, font: str, ink, line_color):
    if path and Path(path).exists():
        try:
            iw, ih = ImageReader(str(path)).getSize()
            max_w, max_h = 126, 44
            scale = min(max_w / iw, max_h / ih)
            w, h = iw * scale, ih * scale
            # Keep the whole image comfortably above the line.
            c.drawImage(ImageReader(str(path)), center_x - w / 2, line_y + 7, width=w, height=h, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    c.setStrokeColor(line_color)
    c.setLineWidth(0.9)
    c.line(center_x - 86, line_y, center_x + 86, line_y)
    draw_fit_centered(c, label, font, center_x, line_y - 17, 182, 8.5, 6.7, ink, 0.25)


def draw_footer(c: canvas.Canvas, info: dict, verification_url: Optional[str], font: dict, theme: dict, tpl: str):
    text = colors.HexColor(theme["muted"])
    regular = font["regular"]
    # Footer information occupies only the safe band left of the QR panel.
    roll_x, center_x, cert_x = (220, 450, 645) if tpl == "skyline" else (165, 425, 645)
    draw_fit_centered(c, f"Roll No. {_safe_text(info.get('roll_number'), '-')}", regular, roll_x, 49, 170, 8.3, 6.6, text, 0.25)
    center_text = f"{_safe_text(info.get('certificate_type'), 'Achievement')} - {_safe_text(info.get('academic_year'), '2026-27')}"
    draw_fit_centered(c, center_text, regular, center_x, 49, 230, 8.3, 6.4, text, 0.25)
    draw_fit_centered(c, _safe_text(info.get('certificate_id'), 'SRGPC-PREVIEW'), regular, cert_x, 49, 135, 7.3, 5.7, text, 0.2)

    if verification_url:
        # Large QR block: 98pt panel, 74pt QR, with a quiet zone and label.
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor(theme["accent"]))
        c.setLineWidth(0.7)
        c.roundRect(QR_BOX_X, QR_BOX_Y, QR_BOX, QR_BOX, 8, fill=1, stroke=1)
        draw_qr(c, verification_url, QR_BOX_X + (QR_BOX - QR_SIZE) / 2, QR_BOX_Y + 19, QR_SIZE)
        draw_fit_centered(c, "SCAN TO VERIFY", regular, QR_BOX_X + QR_BOX / 2, QR_BOX_Y + 8, QR_BOX - 10, 6.4, 5.2, colors.HexColor(theme["accent"]), 0.2)


def draw_frame(c: canvas.Canvas, tpl: str, theme: dict):
    bg = colors.HexColor(theme["bg"])
    ink = colors.HexColor(theme["ink"])
    accent = colors.HexColor(theme["accent"])
    soft = colors.HexColor(theme["accent_soft"])
    c.setFillColor(bg)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    if tpl == "classic":
        c.setStrokeColor(accent); c.setLineWidth(2.2); c.roundRect(SAFE, SAFE, PAGE_W-2*SAFE, PAGE_H-2*SAFE, 10, fill=0, stroke=1)
        c.setStrokeColor(colors.HexColor("#d7c596")); c.setLineWidth(0.7); c.roundRect(SAFE+12, SAFE+12, PAGE_W-2*(SAFE+12), PAGE_H-2*(SAFE+12), 8, fill=0, stroke=1)
    elif tpl == "modern":
        c.setFillColor(colors.HexColor("#0f172a")); c.rect(0, PAGE_H-78, PAGE_W, 78, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#eaf2ff")); c.rect(0, 0, 88, PAGE_H-78, fill=1, stroke=0)
        c.setFillColor(colors.white); c.roundRect(PAGE_W/2-46, 456, 92, 96, 12, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#cbd5e1")); c.setLineWidth(0.7); c.rect(SAFE+10, SAFE+10, PAGE_W-2*(SAFE+10), PAGE_H-2*(SAFE+10), fill=0, stroke=1)
    elif tpl == "emerald":
        c.setStrokeColor(accent); c.setLineWidth(2.3); c.roundRect(SAFE, SAFE, PAGE_W-2*SAFE, PAGE_H-2*SAFE, 12, fill=0, stroke=1)
        c.setStrokeColor(colors.HexColor("#a5d4c8")); c.setLineWidth(0.7); c.roundRect(SAFE+12, SAFE+12, PAGE_W-2*(SAFE+12), PAGE_H-2*(SAFE+12), 9, fill=0, stroke=1)
        c.setFillColor(soft); c.circle(PAGE_W/2, PAGE_H-68, 42, fill=1, stroke=0)
    elif tpl == "midnight":
        c.setStrokeColor(colors.HexColor("#a7b5ff")); c.setLineWidth(1.5); c.roundRect(SAFE, SAFE, PAGE_W-2*SAFE, PAGE_H-2*SAFE, 12, fill=0, stroke=1)
        c.setStrokeColor(accent); c.setLineWidth(1.1); c.line(SAFE+24, 458, PAGE_W-SAFE-24, 458)
        c.setStrokeColor(colors.HexColor("#32496f")); c.setLineWidth(0.7); c.roundRect(SAFE+14, SAFE+14, PAGE_W-2*(SAFE+14), PAGE_H-2*(SAFE+14), 9, fill=0, stroke=1)
    elif tpl == "royal":
        c.setStrokeColor(accent); c.setLineWidth(2.4); c.roundRect(SAFE, SAFE, PAGE_W-2*SAFE, PAGE_H-2*SAFE, 12, fill=0, stroke=1)
        c.setStrokeColor(colors.HexColor("#c9b7e8")); c.setLineWidth(0.75); c.roundRect(SAFE+12, SAFE+12, PAGE_W-2*(SAFE+12), PAGE_H-2*(SAFE+12), 9, fill=0, stroke=1)
        c.setFillColor(soft)
        for x, y in [(60, PAGE_H-60),(PAGE_W-60, PAGE_H-60),(60,60),(PAGE_W-60,60)]:
            c.circle(x, y, 7, fill=1, stroke=0)
    elif tpl == "burgundy":
        wine = colors.HexColor("#6f1d2a")
        wine2 = colors.HexColor("#8f2f42")
        gold = colors.HexColor("#c6a15b")
        ivory = colors.HexColor("#fffaf5")
        c.setFillColor(ivory); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(wine); c.rect(0, PAGE_H-30, PAGE_W, 30, fill=1, stroke=0)
        c.setFillColor(wine2); c.rect(0, 0, PAGE_W, 12, fill=1, stroke=0)
        c.setStrokeColor(gold); c.setLineWidth(1.5); c.roundRect(SAFE, SAFE, PAGE_W-2*SAFE, PAGE_H-2*SAFE, 12, fill=0, stroke=1)
        c.setStrokeColor(colors.HexColor("#dfcda4")); c.setLineWidth(0.6); c.roundRect(SAFE+10, SAFE+10, PAGE_W-2*(SAFE+10), PAGE_H-2*(SAFE+10), 9, fill=0, stroke=1)
        # restrained corner ornaments instead of a heavy top banner
        for ox, oy, sx, sy in [(SAFE+20, PAGE_H-SAFE-20, 1, -1), (PAGE_W-SAFE-20, PAGE_H-SAFE-20, -1, -1),
                               (SAFE+20, SAFE+20, 1, 1), (PAGE_W-SAFE-20, SAFE+20, -1, 1)]:
            c.setStrokeColor(gold); c.setLineWidth(0.8)
            c.line(ox, oy, ox+sx*18, oy+sy*18)
            c.line(ox+sx*5, oy, ox+sx*18, oy+sy*13)
    elif tpl == "skyline":
        c.setFillColor(colors.HexColor("#0b3b72")); c.rect(0, 0, 102, PAGE_H, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#0ea5e9")); c.rect(0, PAGE_H-10, PAGE_W, 10, fill=1, stroke=0)
        for x, h in [(18, 90), (38, 135), (58, 108), (78, 160)]:
            c.setFillColor(colors.HexColor("#14508d")); c.rect(x, 28, 13, h, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#cbd5e1")); c.setLineWidth(0.7); c.rect(118, 24, PAGE_W-142, PAGE_H-48, fill=0, stroke=1)
    else:  # minimal
        c.setStrokeColor(colors.HexColor("#cbd5e1")); c.setLineWidth(0.9); c.rect(SAFE+10, SAFE+10, PAGE_W-2*(SAFE+10), PAGE_H-2*(SAFE+10), fill=0, stroke=1)
        c.setStrokeColor(colors.HexColor("#e2e8f0")); c.setLineWidth(0.7); c.line(180, 104, PAGE_W-180, 104)


def _title_band(c, info, theme, font, cx):
    regular, bold = font["regular"], font["bold"]
    dark = colors.HexColor(theme["ink"])
    muted = colors.HexColor(theme["muted"])
    accent = colors.HexColor(theme["accent"])

    # Protected top zone shared by every template. The logo is intentionally
    # larger, but its full bounding box stays inside the inner certificate frame.
    # The title stack sits below it with fixed breathing room so fonts can never
    # collide with the logo.
    if theme["ink"] in ("#f8fafc",):
        c.setFillColor(colors.white)
        c.roundRect(cx - 43, 484, 86, 70, 11, fill=1, stroke=0)
    _logo(c, info.get("logo_path"), cx, 506, 76, 80)
    draw_fit_centered(c, "SRGPC", bold, cx, 456, 160, 14.5, 10.5, accent, 0.2)

    title = _safe_text(info.get("title"), "CERTIFICATE OF ACHIEVEMENT")
    draw_fit_centered(c, title, bold, cx, 420, 670, 29, 19, dark, 0.5)
    draw_fit_centered(c, "Presented in recognition of outstanding performance", regular, cx, 395, 560, 10.6, 8.2, muted, 0.25)


def content_center(tpl: str) -> float:
    return (118 + PAGE_W) / 2 if tpl == "skyline" else PAGE_W / 2


def signature_centers(tpl: str):
    return (306, 610) if tpl == "skyline" else SIGNATURE_XS


def draw_certificate(target, info: dict, verification_url: Optional[str] = None,
                     logo_path: Optional[Path] = None, teacher_sig: Optional[Path] = None,
                     principal_sig: Optional[Path] = None, show_qr: bool = True):
    """Render the authoritative A4-landscape certificate layout.

    The exact same function is used by final generation and the web live preview.
    It enforces text-fit limits, a dedicated footer safe-zone, and a large QR box.
    """
    close_stream = not hasattr(target, "write")
    stream = str(target) if close_stream else target
    c = canvas.Canvas(stream, pagesize=(PAGE_W, PAGE_H))
    tpl = info.get("template") if info.get("template") in TEMPLATES else "classic"
    theme = TEMPLATES[tpl]
    font = _font_family(info.get("font_family", "Helvetica"))
    cx = content_center(tpl)
    dark = colors.HexColor(theme["ink"])
    muted = colors.HexColor(theme["muted"])
    accent = colors.HexColor(theme["accent"])

    draw_frame(c, tpl, theme)
    _title_band(c, {**info, "logo_path": logo_path}, theme, font, cx)

    draw_fit_centered(c, "Presented to", font["regular"], cx, 374, 280, 11, 8.5, muted, 0.25)

    student_name = _safe_text(info.get("name"), "Student Name")
    draw_fit_centered(c, student_name, font["bold"], cx, 334, 600, 32, 14, dark, 0.5)

    c.setStrokeColor(accent)
    c.setLineWidth(1.2)
    c.line(cx - 160, 314, cx + 160, 314)

    cert_type = _safe_text(info.get("certificate_type"), "Achievement")
    activity = _safe_text(info.get("activity"), "Activity / Event")
    position = _safe_text(info.get("position"), "Position / Achievement")
    sentence = f"for securing {position} in {activity}."
    # The achievement statement is the key semantic line, so keep it bold in
    # every template. Fit within a dedicated two-line safe box.
    draw_wrapped_center_fit(c, sentence, font["bold"], cx, 279, 610, start_size=13.2, min_size=9.5, max_lines=2, leading=18, color=dark)

    # Achievement/type badge uses a width derived from the actual text, capped to a safe range.
    badge_font = _fit_size(cert_type.upper(), font["bold"], 8.8, 6.6, 205, 0.25)
    badge_w = min(240, max(152, stringWidth(cert_type.upper(), font["bold"], badge_font) + 42))
    badge_y = 202
    c.setFillColor(colors.HexColor(theme["accent_soft"]))
    c.roundRect(cx - badge_w / 2, badge_y, badge_w, 36, 18, fill=1, stroke=0)
    draw_fit_centered(c, cert_type.upper(), font["bold"], cx, badge_y + 12, badge_w - 22, 8.8, 6.6, accent, 0.25)

    # Signatures live in a dedicated band above the footer. Their lines are always
    # inside the page border and to the left of the QR verification panel.
    line_color = colors.HexColor("#94a3b8") if tpl != "midnight" else colors.HexColor("#64748b")
    sig_ink = colors.HexColor(theme["ink"])
    sig_xs = signature_centers(tpl)
    if tpl == "midnight":
        for sx, sig_path in zip(sig_xs, (teacher_sig, principal_sig)):
            if sig_path and Path(sig_path).exists():
                c.setFillColor(colors.white)
                c.roundRect(sx-67, SIGNATURE_LINE_Y+5, 134, 46, 6, fill=1, stroke=0)
    draw_signature(c, teacher_sig, sig_xs[0], SIGNATURE_LINE_Y, "Faculty / Coordinator", font["regular"], sig_ink, line_color)
    draw_signature(c, principal_sig, sig_xs[1], SIGNATURE_LINE_Y, "Principal / Head of Institution", font["regular"], sig_ink, line_color)

    if show_qr and verification_url:
        draw_footer(c, info, verification_url, font, theme, tpl)
    else:
        text = colors.HexColor(theme["muted"])
        roll_x, center_x, cert_x = (220, 450, 645) if tpl == "skyline" else (165, 425, 645)
        draw_fit_centered(c, f"Roll No. {_safe_text(info.get('roll_number'), '-')}", font["regular"], roll_x, 49, 170, 8.3, 6.6, text)
        draw_fit_centered(c, f"{cert_type} - {_safe_text(info.get('academic_year'), '2026-27')}", font["regular"], center_x, 49, 230, 8.3, 6.4, text)
        draw_fit_centered(c, _safe_text(info.get('certificate_id'), 'SRGPC-PREVIEW'), font["regular"], cert_x, 49, 135, 7.3, 5.7, text)

    c.showPage()
    c.save()
    if not close_stream and hasattr(target, "seek"):
        target.seek(0)
