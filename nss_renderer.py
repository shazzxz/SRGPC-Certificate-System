from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import cairosvg
import qrcode
from xml.sax.saxutils import escape


def _img(path: Optional[Path]) -> str:
    if not path or not Path(path).exists():
        return ""
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def _qr(url: Optional[str]) -> str:
    if not url:
        return ""
    q = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    q.add_data(url)
    q.make(fit=True)
    im = q.make_image(fill_color="black", back_color="white").convert("RGB")
    b = BytesIO()
    im.save(b, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(b.getvalue()).decode('ascii')}"


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")
    except Exception:
        return value or "Date"


def render_nss_certificate(target, info: dict, verification_url: Optional[str],
                           logo_path: Optional[Path], teacher_sig: Optional[Path],
                           principal_sig: Optional[Path], page_width: float, page_height: float):
    name = escape(str(info.get("name") or "Student Name"))
    cert_id = escape(str(info.get("certificate_id") or "SRGPC-PREVIEW"))
    date_from = escape(_date(str(info.get("date_from") or "")))
    date_to = escape(_date(str(info.get("date_to") or "")))

    logo = _img(logo_path)
    teacher = _img(teacher_sig)
    principal = _img(principal_sig)
    qr = _qr(verification_url)

    logo_markup = (
        f'<image href="{logo}" x="33" y="24" width="74" height="74" preserveAspectRatio="xMidYMid meet"/>'
        if logo else '<circle cx="70" cy="62" r="34" fill="#e7efff" stroke="#173b93" stroke-width="2"/><text x="70" y="68" text-anchor="middle" font-family="Arial" font-size="13" font-weight="700" fill="#173b93">SRGPC</text>'
    )
    teacher_markup = f'<image href="{teacher}" x="98" y="418" width="160" height="48" preserveAspectRatio="xMidYMid meet"/>' if teacher else ""
    principal_markup = f'<image href="{principal}" x="584" y="418" width="160" height="48" preserveAspectRatio="xMidYMid meet"/>' if principal else ""
    qr_markup = (
        f'<rect x="391" y="465" width="60" height="60" rx="6" fill="#fff" stroke="#d5dce8"/>'
        f'<image href="{qr}" x="398" y="472" width="46" height="46"/>'
        f'<text x="421" y="536" text-anchor="middle" font-family="Arial" font-size="6.5" fill="#17345f">SCAN TO VERIFY</text>'
        if qr else ""
    )

    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="842" height="595" viewBox="0 0 842 595">
<rect width="842" height="595" fill="#fff"/>
<rect x="14" y="12" width="814" height="571" fill="none" stroke="#17345f" stroke-width="1.5"/>
<rect x="20" y="18" width="802" height="559" fill="none" stroke="#17345f" stroke-width="0.7"/>
<path d="M20 18 L180 18 L78 102 L20 118 Z" fill="#173b93"/>
<g font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif" text-anchor="middle">
<text x="421" y="74" font-size="21" font-weight="800" fill="#17345f">सहोद्रा राय शासकीय पॉलीटेक्निक महाविद्यालय सागर (म.प्र.)</text>
<text x="421" y="97" font-size="11" fill="#333">An ISO 9001:2015 Certified Institution</text>
</g>
__LOGO__
<text x="182" y="40" font-family="Arial" font-size="9" fill="#1f2b3d">युवा कार्यक्रम और खेल मंत्रालय</text>
<text x="182" y="54" font-family="Arial" font-size="8" fill="#1f2b3d">MINISTRY OF YOUTH AFFAIRS AND SPORTS</text>
<circle cx="300" cy="58" r="31" fill="#8b1e1e"/><circle cx="300" cy="58" r="24" fill="#fff"/><circle cx="300" cy="58" r="17" fill="#f47a1f"/>
<g stroke="#fff" stroke-width="2"><path d="M300 34V82M276 58H324M283 41L317 75M317 41L283 75"/></g>
<text x="300" y="101" text-anchor="middle" font-family="Arial" font-size="7" font-weight="700" fill="#17345f">NATIONAL SERVICE SCHEME</text>
<text x="472" y="62" text-anchor="middle" font-family="Arial" font-size="28" font-weight="800" fill="#ef3f2f">my</text>
<text x="522" y="62" text-anchor="middle" font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif" font-size="18" font-weight="800" fill="#1a7a49">भारत</text>
<circle cx="760" cy="58" r="29" fill="#fff" stroke="#bb8a31" stroke-width="5"/><circle cx="760" cy="58" r="20" fill="#ae2235"/>
<text x="760" y="62" text-anchor="middle" font-family="Arial" font-size="8" font-weight="700" fill="#fff">MP</text>
<text x="680" y="117" font-family="Arial" font-size="9" fill="#111">Certificate No.</text>
<text x="736" y="117" font-family="Arial" font-size="8.5" fill="#17345f" font-weight="700">__CERT_ID__</text>
<g font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif" text-anchor="middle">
<text x="421" y="153" font-size="27" font-weight="900" fill="#173b93">राष्ट्रीय सेवा योजना</text>
<text x="421" y="182" font-size="20" font-weight="800" fill="#1a4b9c">सात दिवसीय विशेष शिविर</text>
</g>
<path d="M250 210 L296 210 L314 224 L296 238 L250 238 L268 224 Z" fill="#b3202b"/><path d="M592 210 L546 210 L528 224 L546 238 L592 238 L574 224 Z" fill="#b3202b"/>
<rect x="296" y="205" width="250" height="44" rx="4" fill="#c9272d" stroke="#b89a5a" stroke-width="1.2"/>
<text x="421" y="235" text-anchor="middle" font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif" font-size="24" font-weight="900" fill="#fff">प्रमाण पत्र</text>
<g font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif">
<text x="55" y="286" font-size="13" font-weight="700" fill="#1a2c4c">प्रमाणित किया जाता है, कि</text>
<line x1="205" y1="289" x2="790" y2="289" stroke="#17345f" stroke-width="1.1" stroke-dasharray="2 3"/>
<text x="500" y="282" text-anchor="middle" font-size="15" font-weight="800" fill="#1b54ad">__NAME__</text><text x="790" y="286" font-size="13" font-weight="700" fill="#1a2c4c">ने</text>
<text x="55" y="322" font-size="12.5" font-weight="700" fill="#1a2c4c">राष्ट्रीय सेवा योजना (छात्र इकाई) के तत्वावधान में</text>
<text x="350" y="322" font-size="12.5" font-weight="800" fill="#16743f">‘मेरा युवा भारत एवं डिजिटल साक्षरता</text>
<text x="55" y="350" font-size="12.5" font-weight="800" fill="#16743f">के साथ युवाओं की सामाजिक सहभागिता’</text>
<text x="330" y="350" font-size="12.5" font-weight="700" fill="#1a2c4c">परिप्रेक्ष्य में आयोजित पूर्णकालिक सात-</text>
<text x="55" y="378" font-size="12.5" font-weight="700" fill="#1a2c4c">दिवसीय विशेष शिविर ग्राम मैनपानी, तहसील/जिला-सागर (म.प्र.) में</text>
<text x="530" y="378" font-size="12.5" font-weight="800" fill="#c92a2f">__DATE_FROM__</text><text x="662" y="378" font-size="12.5" font-weight="700" fill="#1a2c4c">से</text><text x="705" y="378" font-size="12.5" font-weight="800" fill="#c92a2f">__DATE_TO__</text>
<text x="55" y="406" font-size="12.5" font-weight="700" fill="#1a2c4c">तक स्वयं सेवक / सहयोगी के रूप में योगदान दिया।</text>
</g>
<line x1="78" y1="470" x2="278" y2="470" stroke="#17345f" stroke-width="0.9"/><line x1="564" y1="470" x2="764" y2="470" stroke="#17345f" stroke-width="0.9"/>
__TEACHER____PRINCIPAL__
<g font-family="Noto Sans Devanagari, DejaVu Sans, sans-serif" text-anchor="middle">
<text x="178" y="489" font-size="11.5" font-weight="800" fill="#b51e27">कार्यक्रम अधिकारी, रासेयो</text><text x="664" y="489" font-size="11.5" font-weight="800" fill="#173b93">प्राचार्य</text>
</g>
__QR__
</svg>'''

    svg = (
        svg.replace("__LOGO__", logo_markup)
        .replace("__CERT_ID__", cert_id)
        .replace("__NAME__", name)
        .replace("__DATE_FROM__", date_from)
        .replace("__DATE_TO__", date_to)
        .replace("__TEACHER__", teacher_markup)
        .replace("__PRINCIPAL__", principal_markup)
        .replace("__QR__", qr_markup)
    )

    if hasattr(target, "write"):
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=target, output_width=page_width, output_height=page_height)
        target.seek(0)
    else:
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(target), output_width=page_width, output_height=page_height)
