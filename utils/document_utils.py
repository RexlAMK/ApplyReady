"""
document_utils.py
Turns plain-text resume / cover-letter content into real downloadable
files: DOCX (python-docx), PDF (reportlab), and a ZIP application pack.
"""

import io
import logging
import re
import unicodedata
import zipfile
from collections import OrderedDict

logger = logging.getLogger("applyready.documents")

SECTION_HEADINGS = {
    "PROFESSIONAL SUMMARY", "SUMMARY", "PROFILE", "OBJECTIVE",
    "EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE", "INTERNSHIPS",
    "EDUCATION", "PROJECTS", "PROJECT", "SKILLS", "TECHNICAL SKILLS", "KEY SKILLS",
    "CORE COMPETENCIES", "CERTIFICATIONS", "CERTIFICATION",
    "AWARDS / ACHIEVEMENTS", "AWARDS", "ACHIEVEMENTS", "KEY ACHIEVEMENTS",
    "VOLUNTEER / EXTRACURRICULAR", "VOLUNTEER", "ACTIVITIES", "LANGUAGES",
    "REFERENCES", "ADDITIONAL INFORMATION",
}

# Canonical bucket membership, used to force the required section order:
# HEADER -> PROFILE -> EDUCATION -> EXPERIENCE -> SKILLS -> everything else.
_PROFILE_KEYS = {"PROFESSIONAL SUMMARY", "SUMMARY", "PROFILE", "OBJECTIVE"}
_EDUCATION_KEYS = {"EDUCATION"}
_EXPERIENCE_KEYS = {"EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE", "INTERNSHIPS"}
_SKILLS_KEYS = {"SKILLS", "TECHNICAL SKILLS", "KEY SKILLS", "CORE COMPETENCIES"}

PASSPORT_BLUE_HEX = "#2f6feb"
DARK_TEXT_HEX = "#1a1a1a"
MUTED_TEXT_HEX = "#4a4a4a"


# ---------------------------------------------------------------------
# Text sanitization (fixes garbage "■" glyphs, stray control/space chars)
# ---------------------------------------------------------------------

_DASH_MAP = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
}
_QUOTE_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
}
_SPACE_MAP = {
    "\u00a0": " ", "\u2007": " ", "\u202f": " ",
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
    "\u2028": "\n", "\u2029": "\n",
}
_BULLET_CHARS = "•◦▪▫‣⁃●○∙·"


def sanitize_text(text):
    """
    Character-level cleanup applied to ALL resume text before rendering.
    Fixes the root cause of '■' glyphs: certain Unicode punctuation (e.g.
    the non-breaking hyphen U+2011 that AI models often emit for compound
    words) has no glyph in the PDF's base font encoding, so ReportLab
    draws a filled box instead. We normalize those to safe ASCII/Latin-1
    equivalents *without* deleting the meaning (Detail\u2011oriented ->
    Detail-oriented, never Detailoriented).
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for ch, repl in _DASH_MAP.items():
        text = text.replace(ch, repl)
    for ch, repl in _QUOTE_MAP.items():
        text = text.replace(ch, repl)
    for ch, repl in _SPACE_MAP.items():
        text = text.replace(ch, repl)
    # Drop the literal Unicode replacement character and stray control chars,
    # but keep newlines/tabs.
    text = text.replace("\ufffd", "")
    text = "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))
    return text


_MD_HEADING_RE = re.compile(r"^\#{1,6}\s*")
_BULLET_LINE_RE = re.compile(r"^[-*\u2022\u25aa\u25e6\u2023\u2043\u25cf\u25cb\u2219\u00b7]\s*")
_LONE_BULLET_RE = re.compile(r"^[-*\u2022\u25aa\u25e6\u2023\u2043\u25cf\u25cb\u2219\u00b7]$")


def clean_line(raw_line):
    """
    Clean a single line of resume text: strip markdown heading markers
    (###), strip bold markers (**) whether or not they're properly
    paired, detect + normalize bullet markers to a single style, and
    flag empty bullets so callers can drop them instead of rendering a
    lone '•' between sections.

    Returns (kind, text):
      kind == "blank"  -> nothing should be rendered for this line
      kind == "bullet" -> text is the bullet content (no marker)
      kind == "text"   -> text is a normal line (heading or paragraph)
    """
    line = raw_line.strip()
    if not line:
        return "blank", ""

    # Markdown bold markers are frequently unpaired in AI output
    # ("**Company**" opens fine but a trailing "**" on another line can
    # dangle) -- unconditionally removing "**" is safe since it never
    # carries meaning on its own.
    line = line.replace("**", "")
    line = _MD_HEADING_RE.sub("", line).strip()

    if not line or _LONE_BULLET_RE.match(line):
        return "blank", ""

    bullet_match = _BULLET_LINE_RE.match(line)
    if bullet_match:
        content = line[bullet_match.end():].strip()
        if not content:
            return "blank", ""
        return "bullet", content

    return "text", line


_DATE_RANGE_RE = re.compile(
    r"(\b\d{1,2}/\d{4}\b\s*[-\u2013]\s*(?:\b\d{1,2}/\d{4}\b|Present|present)"
    r"|\b\d{4}\b\s*[-\u2013]\s*(?:\b\d{4}\b|Present|present)"
    r"|\bPresent\b)\s*$"
)


def split_trailing_date(line):
    """
    If a line ends with a recognizable date range (e.g. '08/2020 - 08/2024'
    or '2012 - Present'), split it into (label, date) so the caller can
    right-align the date. Returns (label, date_or_None).
    """
    match = _DATE_RANGE_RE.search(line)
    if not match:
        return line, None
    date_part = match.group(1).strip()
    label = line[: match.start()].strip().rstrip("|,-\u2013").strip()
    if not label:
        return line, None
    return label, date_part


# Deliberately narrow: letters/spaces/&//- only. Excludes digits, colons,
# pipes, '@', parentheses -- so a GPA/date/contact line consisting only of
# uppercase letters (e.g. "GPA: 3.58 | 08/2020 - 08/2024", where the only
# *cased* characters happen to be uppercase) never gets misread as a
# section heading.
_HEADING_CANDIDATE_RE = re.compile(r"^[A-Z][A-Z /&\-]*$")


_PURE_DATE_RE = re.compile(
    r"^(?:\d{1,2}/\d{4}\s*[-\u2013]\s*(?:\d{1,2}/\d{4}|Present|present)"
    r"|\d{4}\s*[-\u2013]\s*(?:\d{4}|Present|present))$"
)


def _merge_standalone_date_lines(items):
    """
    Some resume text puts a degree/job title on its own line and the date
    range on the very next line (rather than the same line). Merge a
    standalone "08/2012 - 05/2014"-style line into the previous text line
    so split_trailing_date() can right-align it as intended, instead of
    it floating as an orphan left-aligned line.
    """
    merged = []
    for kind, content in items:
        if (kind == "text" and _PURE_DATE_RE.match(content.strip())
                and merged and merged[-1][0] == "text"):
            prev_kind, prev_content = merged[-1]
            merged[-1] = (prev_kind, f"{prev_content} {content.strip()}")
            continue
        merged.append((kind, content))
    return merged


def _looks_like_heading(line):
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.upper() in SECTION_HEADINGS:
        return True
    # All-caps short line (1-6 words) also treated as a heading, to catch
    # AI-generated headings that don't match our known list verbatim
    # (e.g. "KEY ACHIEVEMENTS", "CORE COMPETENCIES").
    if (_HEADING_CANDIDATE_RE.match(stripped)
            and 1 <= len(stripped.split()) <= 6 and len(stripped) < 40):
        return True
    return False


def _parse_resume_text(resume_text):
    """
    Sanitize + parse plain-text resume content into:
      header_lines: list of str (name/title/contact, before first heading)
      sections: OrderedDict[heading_str] -> list of ("bullet"|"text", content)
    """
    text = sanitize_text(resume_text)
    header_lines = []
    sections = OrderedDict()
    current_heading = None
    first_line_seen = False

    for raw_line in text.split("\n"):
        kind, content = clean_line(raw_line)
        if kind == "blank":
            continue

        # The very first non-blank line is always the candidate's name,
        # regardless of capitalization -- never run it through the
        # heading heuristic (an all-caps name would otherwise match it).
        if not first_line_seen:
            header_lines.append(content)
            first_line_seen = True
            continue

        if kind == "text" and _looks_like_heading(content):
            current_heading = content.upper()
            sections.setdefault(current_heading, [])
            continue
        if current_heading is None:
            header_lines.append(content)
        else:
            sections[current_heading].append((kind, content))

    return header_lines, sections


def _ordered_sections(sections):
    """
    Reorder parsed sections into: PROFILE -> EDUCATION -> EXPERIENCE ->
    SKILLS -> everything else (in original order), per the required
    section order. Never invents or drops sections -- only reorders.
    """
    used = set()
    ordered = []

    def take(keys):
        for heading in list(sections.keys()):
            if heading in keys and heading not in used and sections[heading]:
                ordered.append((heading, sections[heading]))
                used.add(heading)

    take(_PROFILE_KEYS)
    take(_EDUCATION_KEYS)
    take(_EXPERIENCE_KEYS)
    take(_SKILLS_KEYS)

    other = [
        (heading, content) for heading, content in sections.items()
        if heading not in used and content
    ]
    return ordered, other


# ---------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------

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

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    if photo_bytes:
        try:
            doc.add_picture(io.BytesIO(photo_bytes), width=Inches(1.2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        except Exception:
            logger.warning("Could not embed photo in DOCX resume.")

    header_lines, sections = _parse_resume_text(resume_text)
    profile_first, other_sections = _ordered_sections(sections)
    all_sections = profile_first + other_sections

    first_content_written = False
    for line in header_lines:
        p = doc.add_paragraph()
        run = p.add_run(line)
        if not first_content_written:
            run.bold = True
            run.font.size = Pt(18)
            first_content_written = True
        else:
            run.font.size = Pt(11)

    for heading, items in all_sections:
        h = doc.add_paragraph()
        run = h.add_run(heading)
        run.bold = True
        run.font.size = Pt(13)
        for kind, content in items:
            if kind == "bullet":
                doc.add_paragraph(content, style="List Bullet")
            else:
                doc.add_paragraph(content)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------
# PDF (resume) -- reference-style, one-page layout
# ---------------------------------------------------------------------

def _photo_flowable(photo_bytes, max_w_in, max_h_in):
    """Build a ReportLab Image sized to fit within max_w x max_h while
    preserving the original aspect ratio (never stretches/distorts)."""
    from reportlab.platypus import Image as RLImage
    from PIL import Image as PILImage

    try:
        pil_img = PILImage.open(io.BytesIO(photo_bytes))
        orig_w, orig_h = pil_img.size
        aspect = orig_w / orig_h
        target_w, target_h = max_w_in, max_w_in / aspect
        if target_h > max_h_in:
            target_h = max_h_in
            target_w = max_h_in * aspect
        img = RLImage(io.BytesIO(photo_bytes), width=target_w * 72, height=target_h * 72)
        return img
    except Exception:
        logger.warning("Could not size photo for PDF resume; skipping image.")
        return None


def _build_pdf_story(resume_text, photo_bytes, scale=1.0):
    """
    Build the ReportLab story (flowables) for the resume. `scale` shrinks
    fonts/spacing uniformly (never below a readable floor) so the caller
    can retry at a smaller scale if the content overflows one page,
    without ever clipping or hiding content.
    """
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors

    blue = colors.HexColor(PASSPORT_BLUE_HEX)
    dark = colors.HexColor(DARK_TEXT_HEX)
    muted = colors.HexColor(MUTED_TEXT_HEX)

    def pt(base):
        return max(7.0, base * scale)

    name_style = ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=pt(21),
                                 leading=pt(23), textColor=blue, spaceAfter=1)
    title_style = ParagraphStyle("JobTitle", fontName="Helvetica", fontSize=pt(11.5),
                                  leading=pt(14), textColor=dark, spaceAfter=2)
    contact_style = ParagraphStyle("Contact", fontName="Helvetica", fontSize=pt(9),
                                    leading=pt(12), textColor=muted)
    heading_style = ParagraphStyle("SectionHeading", fontName="Helvetica-Bold", fontSize=pt(10.5),
                                    leading=pt(13), textColor=blue, spaceBefore=pt(8), spaceAfter=pt(2))
    body_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=pt(9.3),
                                 leading=pt(12.2), textColor=dark, spaceAfter=pt(2))
    bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=10, bulletIndent=0,
                                   spaceAfter=pt(1.5))
    label_bold_style = ParagraphStyle("LabelBold", parent=body_style, fontName="Helvetica-Bold")
    date_style = ParagraphStyle("Date", parent=body_style, alignment=TA_RIGHT, textColor=muted)
    small_style = ParagraphStyle("Small", parent=body_style, fontSize=pt(8.6), textColor=muted,
                                  spaceAfter=pt(1.5))

    content_width = 7.4 * inch  # approx usable width at ~0.55in margins on A4

    story = []
    header_lines, sections = _parse_resume_text(resume_text)
    ordered_first, other_sections = _ordered_sections(sections)

    # ---- Header ----
    name = header_lines[0] if header_lines else ""
    rest = header_lines[1:]
    job_title = None
    contact_lines = []
    if rest:
        if "@" not in rest[0] and not re.search(r"\d{3,}", rest[0]):
            job_title = rest[0]
            contact_lines = rest[1:]
        else:
            contact_lines = rest

    left_flow = [Paragraph(_escape_html(name), name_style)]
    if job_title:
        left_flow.append(Paragraph(_escape_html(job_title), title_style))
    for cl in contact_lines:
        left_flow.append(Paragraph(_escape_html(cl), contact_style))

    photo_img = _photo_flowable(photo_bytes, 1.05, 1.3) if photo_bytes else None
    if photo_img:
        header_table = Table(
            [[left_flow, photo_img]],
            colWidths=[content_width - 1.1 * inch, 1.1 * inch],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
    else:
        story.extend(left_flow)

    story.append(Spacer(1, pt(5)))
    story.append(HRFlowable(width="100%", thickness=1.1, color=blue, spaceAfter=pt(6)))

    def render_heading(heading):
        story.append(Paragraph(heading.upper(), heading_style))
        story.append(HRFlowable(width="100%", thickness=0.6, color=blue, spaceAfter=pt(4)))

    def render_items(items, indent_meta=True):
        for kind, content in _merge_standalone_date_lines(items):
            if kind == "bullet":
                story.append(Paragraph(f"&bull;&nbsp;&nbsp;{_escape_html(content)}", bullet_style))
                continue
            is_meta = bool(re.match(r"^(GPA|Relevant coursework)\s*:", content, re.IGNORECASE))
            label, date = (content, None) if is_meta else split_trailing_date(content)
            if date:
                row = Table(
                    [[Paragraph(_escape_html(label), label_bold_style), Paragraph(_escape_html(date), date_style)]],
                    colWidths=[content_width * 0.72, content_width * 0.28],
                )
                row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                story.append(row)
            elif is_meta and indent_meta:
                story.append(Paragraph(_escape_html(content), small_style))
            else:
                story.append(Paragraph(_escape_html(content), body_style))

    def render_skills(items):
        tokens = []
        for kind, content in items:
            text = content
            if ":" in text:
                text = text.split(":", 1)[1]
            parts = [t.strip() for t in re.split(r"[,|]", text) if t.strip()]
            tokens.extend(parts if parts else ([text.strip()] if text.strip() else []))
        if not tokens:
            return
        cols = 3 if len(tokens) > 6 else 2
        rows = [tokens[i:i + cols] for i in range(0, len(tokens), cols)]
        for row in rows:
            while len(row) < cols:
                row.append("")
        cell_style = ParagraphStyle("SkillCell", parent=body_style, spaceAfter=pt(3))
        table_data = [[Paragraph(f"&bull;&nbsp;{_escape_html(c)}" if c else "", cell_style) for c in row] for row in rows]
        col_width = content_width / cols
        table = Table(table_data, colWidths=[col_width] * cols)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(table)

    # ---- Ordered required sections: PROFILE, EDUCATION, EXPERIENCE, SKILLS ----
    for heading, items in ordered_first:
        render_heading(heading)
        if heading in _SKILLS_KEYS:
            render_skills(items)
        else:
            render_items(items)

    # ---- Remaining sections, grouped compactly if there are several ----
    if len(other_sections) >= 3:
        render_heading("ADDITIONAL INFORMATION")
        for heading, items in other_sections:
            flat_bits = [_escape_html(content) for kind, content in items]
            if flat_bits:
                story.append(Paragraph(f"<b>{_escape_html(heading.title())}:</b> {'; '.join(flat_bits)}", body_style))
    else:
        for heading, items in other_sections:
            render_heading(heading)
            if heading in _SKILLS_KEYS:
                render_skills(items)
            else:
                render_items(items)

    return story


def build_resume_pdf(resume_text, photo_bytes=None):
    """
    Build a one-page, reference-styled, ATS-friendly PDF resume using
    reportlab. Iteratively shrinks font/spacing (never below a readable
    floor, never clipping content) if the content overflows one page.
    Returns bytes.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.units import inch

    def render_at_scale(scale, margin_in):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=margin_in * inch, rightMargin=margin_in * inch,
            topMargin=margin_in * inch, bottomMargin=margin_in * inch,
        )
        story = _build_pdf_story(resume_text, photo_bytes, scale=scale)
        doc.build(story)
        return buf.getvalue()

    def page_count(pdf_bytes):
        try:
            import pypdf
            return len(pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)
        except Exception:
            return 1

    attempts = [(1.0, 0.55), (0.92, 0.5), (0.85, 0.45), (0.8, 0.4)]
    last_bytes = None
    for scale, margin in attempts:
        pdf_bytes = render_at_scale(scale, margin)
        last_bytes = pdf_bytes
        if page_count(pdf_bytes) <= 1:
            return pdf_bytes

    logger.warning("Resume content did not fit one page even at minimum readable scale; "
                    "returning the best (smallest-scale) attempt without clipping content.")
    return last_bytes


# ---------------------------------------------------------------------
# Cover letter (unchanged behavior, now sanitized)
# ---------------------------------------------------------------------

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

    clean_text = sanitize_text(letter_text).replace("**", "")
    for para in clean_text.split("\n"):
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
        story.append(Paragraph(_escape_html(sanitize_text(applicant_name)), name_style))

    clean_text = sanitize_text(letter_text).replace("**", "")
    for para in clean_text.split("\n"):
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
