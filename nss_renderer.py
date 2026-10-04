from __future__ import annotations

from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

REFERENCE_IMAGE = Path(__file__).resolve().parent / "static" / "nss_ref.jpg"


def _fit_size(text: str, font: str, max_size: float, min_size: float, max_width: float) -> float:
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return max(min_size, size)


def _draw_centered(c, text: str, x: float, y: float, font: str, max_size: float,
                   min_size: float, max_width: float, color):
    size = _fit_size(text, font, max_size, min_size, max_width)
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(x, y, text)


def render_nss_certificate(target, info: dict, verification_url: Optional[str],
                           logo_path: Optional[Path], teacher_sig: Optional[Path],
                           principal_sig: Optional[Path], page_width: float, page_height: float):
    """Render the supplied official NSS artwork and replace only its variable fields."""
    close_stream = not hasattr(target, "write")
    stream = str(target) if close_stream else target
    c = canvas.Canvas(stream, pagesize=(page_width, page_height))

    if not REFERENCE_IMAGE.exists():
        raise FileNotFoundError(f"NSS reference artwork is missing: {REFERENCE_IMAGE}")

    c.drawImage(
        ImageReader(str(REFERENCE_IMAGE)),
        0, 0, width=page_width, height=page_height,
        preserveAspectRatio=False, mask="auto"
    )

    # Cover only the placeholders in the supplied reference. Everything else stays
    # exactly as the supplied artwork, including Hindi text, logos and signatures.
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.white)
    c.rect(page_width * 0.835, page_height * 0.700, page_width * 0.145, page_height * 0.055, fill=1, stroke=0)
    c.rect(page_width * 0.440, page_height * 0.390, page_width * 0.280, page_height * 0.070, fill=1, stroke=0)
    c.rect(page_width * 0.685, page_height * 0.205, page_width * 0.285, page_height * 0.075, fill=1, stroke=0)

    cert_id = str(info.get("certificate_id") or "SRGPC-PREVIEW")
    student_name = str(info.get("name") or "Student Name")
    date_from = str(info.get("date_from") or "")
    date_to = str(info.get("date_to") or "")

    def date_text(value: str) -> str:
        try:
            from datetime import datetime
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")
        except Exception:
            return value or "Date"

    date_range = f"{date_text(date_from)} – {date_text(date_to)}" if date_from or date_to else "DATE RANGE"

    _draw_centered(
        c, cert_id, page_width * 0.907, page_height * 0.727,
        "Times-Bold", 9.0, 6.4, page_width * 0.135,
        colors.HexColor("#173b93")
    )
    _draw_centered(
        c, student_name, page_width * 0.580, page_height * 0.417,
        "Times-Bold", 17.0, 10.0, page_width * 0.245,
        colors.HexColor("#b51e27")
    )
    _draw_centered(
        c, date_range, page_width * 0.825, page_height * 0.245,
        "Times-Bold", 12.0, 7.0, page_width * 0.255,
        colors.HexColor("#b51e27")
    )

    # This official artwork has its own printed signatory names. Keep the template
    # visually exact instead of adding extra QR/signature blocks not present in it.
    c.showPage()
    c.save()
    if not close_stream and hasattr(target, "seek"):
        target.seek(0)
