"""
document_utils.py
Turns plain-text resume / cover-letter content into real downloadable
files: DOCX (python-docx), PDF (reportlab), and a ZIP application pack.
"""

import io
import logging
import zipfile

logger = logging.getLogger("applyready.documents")

SECTION_HEADINGS = {
    "PROFESSIONAL SUMMARY", "EXPERIENCE", "INTERNSHIPS", "EDUCATION",
    "PROJECTS", "SKILLS", "CERTIFICATIONS", "AWARDS / ACHIEVEMENTS",
    "VOLUNTEER / EXTRACURRICULAR", "REFERENCES",
}


def _looks_like_heading(line):
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.upper() in SECTION_HEADINGS:
        return True
    # All-caps short line also treated as a heading (handles AI-rewritten text)
    if stripped.isupper() and 2 <= len(stripped.split()) <= 5 and len(stripped) < 40:
        return True
    return False


def build_resume_docx(resume_text, photo_bytes=None):
    """
    Build an ATS-friendly Word document from plain-text resume content.
    Simple, standard layout: no tables, no text boxes, no images embedded
    inline with text (photo is placed once at the top, optionally).
    Returns bytes.
    """
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Base font for ATS readability
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    if photo_bytes:
        try:
            doc.add_picture(io.BytesIO(photo_bytes), width=Inches(1.2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        except Exception:
            logger.warning("Could not embed photo in DOCX resume.")

    lines = [l for l in resume_text.split("\n")]
    first_content_written = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if not first_content_written:
            # First non-empty line = name/title header
            p = doc.add_paragraph()
            run = p.add_run(line.strip())
            run.bold = True
            run.font.size = Pt(18)
            first_content_written = True
            continue

        if _looks_like_heading(line):
            heading = doc.add_paragraph()
            run = heading.add_run(line.strip().upper())
            run.bold = True
            run.font.size = Pt(13)
            run.font.color.rgb = None
            continue

        if line.strip().startswith(("-", "•", "*")):
            bullet_text = line.strip().lstrip("-•* ").strip()
            doc.add_paragraph(bullet_text, style="List Bullet")
            continue

        doc.add_paragraph(line.strip())

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_resume_pdf(resume_text, photo_bytes=None):
    """
    Build a simple, clean, ATS-friendly PDF resume using reportlab.
    Returns bytes.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.enums import TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                             leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle("NameStyle", parent=styles["Title"], alignment=TA_LEFT, fontSize=20, spaceAfter=4)
    heading_style = ParagraphStyle("HeadingStyle", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4,
                                    textColor="#1a1a1a")
    body_style = ParagraphStyle("BodyStyle", parent=styles["Normal"], fontSize=10.5, leading=14)
    bullet_style = ParagraphStyle("BulletStyle", parent=body_style, leftIndent=14, bulletIndent=0)

    story = []

    if photo_bytes:
        try:
            img = RLImage(io.BytesIO(photo_bytes), width=1.1 * inch, height=1.4 * inch)
            story.append(img)
            story.append(Spacer(1, 8))
        except Exception:
            logger.warning("Could not embed photo in PDF resume.")

    first_content_written = False
    for raw_line in resume_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        safe_line = _escape_html(line)

        if not first_content_written:
            story.append(Paragraph(safe_line, name_style))
            first_content_written = True
            continue

        if _looks_like_heading(line):
            story.append(Paragraph(safe_line.upper(), heading_style))
            continue

        if line.startswith(("-", "•", "*")):
            bullet_text = line.lstrip("-•* ").strip()
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{_escape_html(bullet_text)}", bullet_style))
            continue

        story.append(Paragraph(safe_line, body_style))

    doc.build(story)
    return buf.getvalue()


def build_cover_letter_docx(letter_text, applicant_name=""):
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    if applicant_name:
        p = doc.add_paragraph()
        run = p.add_run(applicant_name)
        run.bold = True
        run.font.size = Pt(14)
        doc.add_paragraph("")

    for para in letter_text.split("\n"):
        if para.strip():
            doc.add_paragraph(para.strip())
        else:
            doc.add_paragraph("")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_cover_letter_pdf(letter_text, applicant_name=""):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
                             leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                             topMargin=0.8 * inch, bottomMargin=0.8 * inch)
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle("Name", parent=styles["Heading1"], fontSize=15, spaceAfter=14)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=10)

    story = []
    if applicant_name:
        story.append(Paragraph(_escape_html(applicant_name), name_style))

    for para in letter_text.split("\n"):
        if para.strip():
            story.append(Paragraph(_escape_html(para.strip()), body_style))
        else:
            story.append(Spacer(1, 6))

    doc.build(story)
    return buf.getvalue()


def build_application_pack_zip(files: dict):
    """
    files: dict of {filename: bytes}. Only non-empty entries are included.
    Returns zip bytes.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            if content:
                zf.writestr(filename, content)
    return buf.getvalue()


def _escape_html(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
