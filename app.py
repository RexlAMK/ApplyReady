"""
ApplyReady AI
"From your photo and profile to a job-ready application."

Main Streamlit application. Run with:
    streamlit run app.py
"""

import logging
import os

import streamlit as st

from utils import ats_utils, document_utils, groq_utils, image_utils, resume_utils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("applyready.app")

# ---------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="ApplyReady AI",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
:root {
    --ar-bg: #05070c;
    --ar-card: #10141c;
    --ar-card-border: rgba(56, 189, 248, 0.18);
    --ar-blue: #2f6feb;
    --ar-cyan: #22d3ee;
    --ar-text: #e7edf5;
    --ar-muted: #93a1b5;
}

.stApp {
    background: radial-gradient(circle at 15% 0%, #0b1220 0%, #05070c 55%, #030407 100%);
    color: var(--ar-text);
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #070a11 0%, #04060a 100%);
    border-right: 1px solid rgba(56, 189, 248, 0.12);
}

h1, h2, h3, h4 {
    color: var(--ar-text) !important;
    letter-spacing: 0.2px;
}

.ar-hero {
    padding: 2.4rem 2rem;
    border-radius: 18px;
    background: linear-gradient(135deg, rgba(47,111,235,0.20), rgba(34,211,238,0.08));
    border: 1px solid var(--ar-card-border);
    margin-bottom: 1.6rem;
}
.ar-hero h1 {
    font-size: 2.4rem;
    margin-bottom: 0.2rem;
    background: linear-gradient(90deg, #7dd3fc, #60a5fa 45%, #22d3ee);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent !important;
}
.ar-hero p {
    color: var(--ar-muted);
    font-size: 1.05rem;
    margin: 0;
}

.ar-card {
    background: linear-gradient(160deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01));
    border: 1px solid var(--ar-card-border);
    border-radius: 16px;
    padding: 1.3rem 1.4rem;
    backdrop-filter: blur(6px);
    height: 100%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
}
.ar-card h3 {
    margin-top: 0;
    font-size: 1.15rem;
}
.ar-card p {
    color: var(--ar-muted);
    font-size: 0.92rem;
}

.ar-badge {
    display: inline-block;
    padding: 0.15rem 0.65rem;
    border-radius: 999px;
    background: rgba(34,211,238,0.12);
    border: 1px solid rgba(34,211,238,0.35);
    color: #67e8f9;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
}

.stButton > button, .stDownloadButton > button {
    background: linear-gradient(90deg, var(--ar-blue), var(--ar-cyan));
    color: #04060a;
    font-weight: 700;
    border: none;
    border-radius: 10px;
    padding: 0.55rem 1.2rem;
    transition: all 0.15s ease-in-out;
    box-shadow: 0 4px 14px rgba(34, 211, 238, 0.18);
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(34, 211, 238, 0.32);
    filter: brightness(1.06);
}

.ar-score-wrap {
    text-align: center;
    padding: 1rem;
}
.ar-score-num {
    font-size: 2.6rem;
    font-weight: 800;
    background: linear-gradient(90deg, #7dd3fc, #22d3ee);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.ar-footer {
    text-align: center;
    color: var(--ar-muted);
    padding: 2rem 0 1rem 0;
    font-size: 0.85rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    margin-top: 2.5rem;
}
hr { border-color: rgba(255,255,255,0.08); }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

PAGES = ["Home", "Smart Photo", "Resume Builder", "ATS Analyzer", "Cover Letter", "Application Pack"]


# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------

def init_session_state():
    defaults = {
        "page": "Home",
        "uploaded_photo": None,          # raw bytes of the source photo
        "generated_photo": None,         # PIL Image of final passport photo
        "generated_photo_bytes": None,   # JPG bytes of final passport photo
        "photo_meta": {},                # dict of dims/bg/mode/size for display
        "print_sheet_pdf": None,
        "resume_mode": None,             # "upload" or "manual"
        "resume_data": resume_utils.empty_resume_data(),
        "resume_text": "",               # working plain-text resume (source of truth)
        "resume_text_improved": "",      # AI-improved version
        "include_photo_in_resume": True,
        "resume_docx_bytes": None,
        "resume_pdf_bytes": None,
        "ats_result": None,
        "job_description": "",
        "job_match_result": None,
        "tailored_resume_text": "",
        "tailored_resume_docx_bytes": None,
        "tailored_resume_pdf_bytes": None,
        "cover_letter_job_title": "",
        "cover_letter_company": "",
        "cover_letter_text": "",
        "cover_letter_docx_bytes": None,
        "cover_letter_pdf_bytes": None,
        "generated_files": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to(page_name):
    st.session_state.page = page_name


init_session_state()

# ---------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🚀 ApplyReady AI")
    st.caption("From your photo and profile to a job-ready application.")
    st.markdown("---")
    choice = st.radio("Navigate", PAGES, index=PAGES.index(st.session_state.page), label_visibility="collapsed")
    if choice != st.session_state.page:
        st.session_state.page = choice
    st.markdown("---")
    if groq_utils.is_configured():
        st.success("Groq AI: Connected", icon="✅")
    else:
        st.warning("Groq AI: Not configured", icon="⚠️")
        st.caption("Set GROQ_API_KEY to enable AI features. Core tools still work without it.")
    st.markdown("---")
    st.caption("Built with Python • Streamlit • Groq AI")


# ---------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------

def render_home():
    st.markdown(
        """
        <div class="ar-hero">
            <div class="ar-badge">AI Career Technology</div>
            <h1>APPLYREADY AI</h1>
            <p>One profile. One photo. One complete job application.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    features = [
        ("📸", "Smart ID Photo", "Turn a phone photo into a professional passport-ready image.", "Smart Photo"),
        ("📄", "AI Resume Builder", "Transform your information into an ATS-friendly resume.", "Resume Builder"),
        ("🎯", "ATS Match", "See how closely your resume matches the job.", "ATS Analyzer"),
        ("✉️", "Tailored Cover Letter", "Generate a job-specific cover letter in seconds.", "Cover Letter"),
    ]
    for col, (icon, title, desc, target) in zip(cols, features):
        with col:
            st.markdown(
                f"""
                <div class="ar-card">
                    <div style="font-size:1.6rem;">{icon}</div>
                    <h3>{title}</h3>
                    <p>{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open →", key=f"home_btn_{target}", use_container_width=True):
                go_to(target)
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### How it works")
    steps = [
        "Capture or upload a photo and generate a professional passport photo.",
        "Build your resume — upload an existing CV or fill in a guided form.",
        "Paste a job description to get an ATS score and job-match analysis.",
        "Generate a tailored resume and a job-specific cover letter.",
        "Download your complete, job-ready application pack.",
    ]
    for i, s in enumerate(steps, 1):
        st.markdown(f"**{i}.** {s}")

    st.markdown(
        '<div class="ar-footer">Built with Python • Streamlit • Groq AI</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
# SMART PHOTO
# ---------------------------------------------------------------------

def render_smart_photo():
    st.markdown("## 📸 Smart Passport / ID Photo Generator")
    st.caption("Upload or capture a photo, choose your options, and generate a print-ready passport photo.")

    tab_upload, tab_camera = st.tabs(["Upload Photo", "Use Camera"])
    raw_bytes = None
    with tab_upload:
        uploaded = st.file_uploader("Upload a JPG or PNG photo", type=["jpg", "jpeg", "png"], key="photo_uploader")
        if uploaded is not None:
            raw_bytes = uploaded.getvalue()
    with tab_camera:
        camera_img = st.camera_input("Take a photo", key="photo_camera")
        if camera_img is not None:
            raw_bytes = camera_img.getvalue()

    if raw_bytes is not None:
        st.session_state.uploaded_photo = raw_bytes

    if not st.session_state.uploaded_photo:
        st.info("Upload or capture a photo above to get started.")
        return

    st.markdown("### Step 2 — Choose Photo Size")
    size_mode = st.radio("Size", ["Standard Passport Size", "Custom Dimensions"], horizontal=True)

    if size_mode == "Standard Passport Size":
        st.caption(
            f"Default size: {image_utils.DEFAULT_WIDTH_MM}mm × {image_utils.DEFAULT_HEIGHT_MM}mm. "
            "Exact official dimensions can differ by country or organization — check your "
            "specific requirements before submitting official documents."
        )
        target_w_px = image_utils.convert_to_pixels(image_utils.DEFAULT_WIDTH_MM, "mm")
        target_h_px = image_utils.convert_to_pixels(image_utils.DEFAULT_HEIGHT_MM, "mm")
        size_label = f"{image_utils.DEFAULT_WIDTH_MM}mm × {image_utils.DEFAULT_HEIGHT_MM}mm (standard)"
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            width_val = st.number_input("Width", min_value=0.1, value=35.0, step=0.5)
        with c2:
            height_val = st.number_input("Height", min_value=0.1, value=45.0, step=0.5)
        with c3:
            unit = st.selectbox("Unit", ["mm", "cm", "inches", "px"])
        target_w_px = image_utils.convert_to_pixels(width_val, unit)
        target_h_px = image_utils.convert_to_pixels(height_val, unit)
        size_label = f"{width_val} × {height_val} {unit} (custom)"

    st.markdown("### Step 3 — Background")
    bg_choice_label = st.radio("Background", ["Professional Blue", "White", "Keep Original"], horizontal=True)
    bg_choice_map = {"Professional Blue": "blue", "White": "white", "Keep Original": "original"}
    bg_choice = bg_choice_map[bg_choice_label]

    st.markdown("### Step 4 — Color Mode")
    black_and_white = st.toggle("Black & White", value=False)

    st.markdown("### Step 5 — Generate")
    if st.button("✨ Generate Passport Photo", type="primary"):
        with st.spinner("Processing your photo..."):
            result = image_utils.generate_passport_photo(
                st.session_state.uploaded_photo, target_w_px, target_h_px, bg_choice, black_and_white
            )
        if not result["ok"]:
            st.error(result["error"])
        else:
            if result["warning"]:
                st.warning(result["warning"])
            st.session_state.generated_photo = result["image"]
            st.session_state.generated_photo_bytes = image_utils.image_to_jpg_bytes(result["image"])
            st.session_state.photo_meta = {
                "size_label": size_label,
                "dimensions_px": f"{target_w_px} × {target_h_px} px",
                "background": bg_choice_label,
                "mode": "Black & White" if black_and_white else "Color",
                "file_size_kb": round(len(st.session_state.generated_photo_bytes) / 1024, 1),
            }
            st.success("Passport photo generated!")

    if st.session_state.generated_photo is not None:
        st.markdown("### Step 6 — Preview")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Original**")
            orig_img = image_utils.load_image_from_bytes(st.session_state.uploaded_photo)
            if orig_img:
                st.image(orig_img, use_container_width=True)
        with col2:
            st.markdown("**Generated Passport Photo**")
            st.image(st.session_state.generated_photo, use_container_width=True)

        meta = st.session_state.photo_meta
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Dimensions", meta.get("dimensions_px", "-"))
        m2.metric("Background", meta.get("background", "-"))
        m3.metric("Mode", meta.get("mode", "-"))
        m4.metric("File Size", f"{meta.get('file_size_kb', 0)} KB")

        st.markdown("### Step 7 — Download")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇️ Download JPG",
                data=st.session_state.generated_photo_bytes,
                file_name="passport_photo.jpg",
                mime="image/jpeg",
                use_container_width=True,
            )
        with d2:
            paper_choice = st.selectbox("Print sheet paper size", ["4x6 inch", "A4"])
            if st.button("🖨️ Generate Print Sheet", use_container_width=True):
                with st.spinner("Building your print sheet..."):
                    sheet, count = image_utils.build_print_sheet(st.session_state.generated_photo, paper_choice)
                    pdf_bytes = image_utils.sheet_to_pdf_bytes(sheet)
                    st.session_state.print_sheet_pdf = pdf_bytes
                st.success(f"Print sheet ready with {count} copies on {paper_choice}.")

            if st.session_state.print_sheet_pdf:
                st.download_button(
                    "⬇️ Download Print Sheet (PDF)",
                    data=st.session_state.print_sheet_pdf,
                    file_name="passport_photo_print_sheet.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

        st.session_state.generated_files["passport_photo.jpg"] = st.session_state.generated_photo_bytes
        if st.session_state.print_sheet_pdf:
            st.session_state.generated_files["passport_photo_print_sheet.pdf"] = st.session_state.print_sheet_pdf

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Want a Professional Resume? →", type="primary", use_container_width=True):
            go_to("Resume Builder")
            st.rerun()


# ---------------------------------------------------------------------
# RESUME BUILDER
# ---------------------------------------------------------------------

def render_dynamic_entries(section_key, empty_entry_fn, field_labels, title):
    """
    Render a dynamic list of entries (education/experience/etc.) with
    Add/Remove controls, storing state in st.session_state.resume_data[section_key].
    """
    st.markdown(f"#### {title}")
    entries = st.session_state.resume_data.setdefault(section_key, [])

    if not entries:
        entries.append(empty_entry_fn())

    to_remove = None
    for idx, entry in enumerate(entries):
        with st.container(border=True):
            cols = st.columns(len(field_labels))
            for col, (field_key, label) in zip(cols, field_labels.items()):
                with col:
                    if "responsibilities" in field_key or "achievements" in field_key or "description" in field_key or "coursework" in field_key:
                        entry[field_key] = st.text_area(
                            label, value=entry.get(field_key, ""), key=f"{section_key}_{field_key}_{idx}", height=90
                        )
                    else:
                        entry[field_key] = st.text_input(
                            label, value=entry.get(field_key, ""), key=f"{section_key}_{field_key}_{idx}"
                        )
            if len(entries) > 1:
                if st.button("Remove entry", key=f"remove_{section_key}_{idx}"):
                    to_remove = idx

    if to_remove is not None:
        entries.pop(to_remove)
        st.rerun()

    if st.button(f"+ Add another {title[:-1] if title.endswith('s') else title}", key=f"add_{section_key}"):
        entries.append(empty_entry_fn())
        st.rerun()


def render_manual_resume_form():
    data = st.session_state.resume_data

    st.markdown("#### Personal Information")
    c1, c2, c3 = st.columns(3)
    data["personal"]["full_name"] = c1.text_input("Full Name", value=data["personal"].get("full_name", ""))
    data["personal"]["title"] = c2.text_input("Professional Title", value=data["personal"].get("title", ""))
    data["personal"]["email"] = c3.text_input("Email", value=data["personal"].get("email", ""))
    c4, c5, c6 = st.columns(3)
    data["personal"]["phone"] = c4.text_input("Phone", value=data["personal"].get("phone", ""))
    data["personal"]["location"] = c5.text_input("Location", value=data["personal"].get("location", ""))
    data["personal"]["linkedin"] = c6.text_input("LinkedIn", value=data["personal"].get("linkedin", ""))
    data["personal"]["portfolio"] = st.text_input("Portfolio / GitHub", value=data["personal"].get("portfolio", ""))

    st.markdown("#### Professional Summary (optional)")
    data["summary"] = st.text_area("Summary", value=data.get("summary", ""), height=90, label_visibility="collapsed")

    st.markdown("---")
    render_dynamic_entries(
        "education", resume_utils.empty_education_entry,
        {"degree": "Degree", "institution": "Institution", "location": "Location",
         "start_year": "Start Year", "end_year": "End Year", "gpa": "GPA/CGPA", "coursework": "Relevant Coursework"},
        "Education",
    )

    st.markdown("---")
    render_dynamic_entries(
        "experience", resume_utils.empty_experience_entry,
        {"title": "Job Title", "company": "Company", "location": "Location",
         "start_date": "Start Date", "end_date": "End Date",
         "responsibilities": "Responsibilities", "achievements": "Achievements"},
        "Experience",
    )

    st.markdown("---")
    render_dynamic_entries(
        "internships", resume_utils.empty_experience_entry,
        {"title": "Role", "company": "Organization", "location": "Location",
         "start_date": "Start Date", "end_date": "End Date", "responsibilities": "Responsibilities"},
        "Internships",
    )

    st.markdown("---")
    render_dynamic_entries(
        "projects", resume_utils.empty_project_entry,
        {"name": "Project Name", "role": "Role", "technologies": "Technologies",
         "description": "Description", "achievements": "Achievements"},
        "Projects",
    )

    st.markdown("---")
    st.markdown("#### Skills")
    s1, s2 = st.columns(2)
    data["skills"]["technical"] = s1.text_area("Technical Skills", value=data["skills"].get("technical", ""))
    data["skills"]["tools"] = s2.text_area("Tools", value=data["skills"].get("tools", ""))
    s3, s4 = st.columns(2)
    data["skills"]["soft"] = s3.text_area("Soft Skills", value=data["skills"].get("soft", ""))
    data["skills"]["languages"] = s4.text_area("Languages", value=data["skills"].get("languages", ""))

    st.markdown("---")
    data["certifications"] = st.text_area("Certifications", value=data.get("certifications", ""))
    data["awards"] = st.text_area("Awards / Achievements", value=data.get("awards", ""))
    data["volunteer"] = st.text_area("Volunteer / Extracurricular", value=data.get("volunteer", ""))
    data["references"] = st.text_area("References (optional)", value=data.get("references", ""))

    st.session_state.resume_data = data


def render_resume_builder():
    st.markdown("## 📄 Resume Builder")
    st.caption("Upload your existing CV or enter your information manually.")

    mode_label = st.radio(
        "How would you like to build your resume?",
        ["Upload Existing CV", "Enter Information Manually"],
        horizontal=True,
    )

    if mode_label == "Upload Existing CV":
        st.session_state.resume_mode = "upload"
        cv_file = st.file_uploader("Upload your CV", type=["pdf", "docx", "txt"], key="cv_uploader")
        if cv_file is not None:
            text, error = resume_utils.extract_text_from_upload(cv_file)
            if error:
                st.error(error)
            else:
                st.success("Text extracted. Review and edit below before continuing.")
                st.session_state.resume_text = text

        if st.session_state.resume_text:
            st.markdown("#### Review / Edit Extracted Text")
            st.session_state.resume_text = st.text_area(
                "Extracted resume content", value=st.session_state.resume_text, height=350
            )
    else:
        st.session_state.resume_mode = "manual"
        render_manual_resume_form()
        st.session_state.resume_text = resume_utils.resume_data_to_text(st.session_state.resume_data)
        with st.expander("Preview plain-text resume"):
            st.text(st.session_state.resume_text or "(Nothing entered yet.)")

    if not st.session_state.resume_text or not st.session_state.resume_text.strip():
        st.info("Add your resume content above to continue.")
        return

    st.markdown("---")
    st.markdown("### Passport Photo")
    if st.session_state.generated_photo_bytes:
        c1, c2 = st.columns([1, 3])
        with c1:
            st.image(st.session_state.generated_photo, width=110)
        with c2:
            st.session_state.include_photo_in_resume = st.toggle(
                "Include passport photo in resume", value=st.session_state.include_photo_in_resume
            )
    else:
        st.caption("No passport photo generated yet. You can add one from the Smart Photo page (optional).")
        st.session_state.include_photo_in_resume = False

    st.markdown("---")
    st.markdown("### Generate Professional Resume")
    st.caption("AI will improve grammar, tone, structure, and ATS-friendliness — without inventing new facts.")

    if st.button("🤖 Generate Professional Resume", type="primary"):
        source_text = st.session_state.resume_text
        final_text = source_text
        if groq_utils.is_configured():
            with st.spinner("Improving your resume with AI..."):
                result = groq_utils.improve_resume_text(source_text)
            if result["ok"]:
                final_text = result["content"]
            else:
                st.warning(f"AI improvement unavailable ({result['error']}). Using your original text instead.")
        else:
            st.info("Groq AI is not configured — using your original resume text without AI polishing.")

        st.session_state.resume_text_improved = final_text

        photo_bytes = st.session_state.generated_photo_bytes if st.session_state.include_photo_in_resume else None
        try:
            st.session_state.resume_docx_bytes = document_utils.build_resume_docx(final_text, photo_bytes)
            st.session_state.resume_pdf_bytes = document_utils.build_resume_pdf(final_text, photo_bytes)
        except Exception as e:
            logger.exception("Resume document generation failed")
            st.error(f"Could not generate resume documents: {e}")

        # Compute ATS score right away so it's ready on the ATS Analyzer page
        if groq_utils.is_configured():
            with st.spinner("Calculating estimated ATS compatibility score..."):
                ats_res = groq_utils.analyze_ats(final_text)
            if ats_res["ok"]:
                st.session_state.ats_result = ats_res["content"]
            else:
                st.session_state.ats_result = ats_utils.heuristic_ats_score(final_text)
        else:
            st.session_state.ats_result = ats_utils.heuristic_ats_score(final_text)

        st.success("Professional resume generated!")

    if st.session_state.resume_text_improved:
        with st.expander("View improved resume text", expanded=False):
            st.text(st.session_state.resume_text_improved)

        d1, d2 = st.columns(2)
        if st.session_state.resume_docx_bytes:
            d1.download_button(
                "⬇️ Download Resume (DOCX)", data=st.session_state.resume_docx_bytes,
                file_name="resume.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            st.session_state.generated_files["resume.docx"] = st.session_state.resume_docx_bytes
        if st.session_state.resume_pdf_bytes:
            d2.download_button(
                "⬇️ Download Resume (PDF)", data=st.session_state.resume_pdf_bytes,
                file_name="resume.pdf", mime="application/pdf", use_container_width=True,
            )
            st.session_state.generated_files["resume.pdf"] = st.session_state.resume_pdf_bytes

        if st.session_state.ats_result:
            st.markdown("#### Estimated ATS Compatibility Score")
            st.caption("This is an estimate. Real ATS systems each use different, proprietary algorithms.")
            score = st.session_state.ats_result.get("score", 0)
            st.markdown(
                f'<div class="ar-score-wrap"><div class="ar-score-num">{score} / 100</div></div>',
                unsafe_allow_html=True,
            )
            st.progress(min(100, max(0, int(score))) / 100)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Continue to ATS Analyzer →", type="primary", use_container_width=True):
            go_to("ATS Analyzer")
            st.rerun()


# ---------------------------------------------------------------------
# ATS ANALYZER
# ---------------------------------------------------------------------

def render_ats_analyzer():
    st.markdown("## 🎯 ATS Analyzer & Job Match")

    working_resume = st.session_state.resume_text_improved or st.session_state.resume_text
    if not working_resume or not working_resume.strip():
        st.info("Build your resume first in the Resume Builder section.")
        if st.button("Go to Resume Builder →"):
            go_to("Resume Builder")
            st.rerun()
        return

    st.markdown("### Estimated ATS Compatibility Score")
    st.caption("Estimated only — real ATS systems use different, proprietary algorithms.")
    if st.button("Recalculate ATS Score"):
        if groq_utils.is_configured():
            with st.spinner("Analyzing resume..."):
                res = groq_utils.analyze_ats(working_resume)
            st.session_state.ats_result = res["content"] if res["ok"] else ats_utils.heuristic_ats_score(working_resume)
        else:
            st.session_state.ats_result = ats_utils.heuristic_ats_score(working_resume)

    if st.session_state.ats_result:
        ats = st.session_state.ats_result
        score = ats.get("score", 0)
        st.markdown(
            f'<div class="ar-score-wrap"><div class="ar-score-num">{score} / 100</div></div>',
            unsafe_allow_html=True,
        )
        st.progress(min(100, max(0, int(score))) / 100)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Strengths**")
            for s in ats.get("strengths", []):
                st.markdown(f"- ✅ {s}")
        with c2:
            st.markdown("**Improvements**")
            for imp in ats.get("improvements", []):
                st.markdown(f"- ⚠️ {imp}")
        if ats.get("missing_keywords"):
            st.markdown("**Missing Keywords**")
            st.write(", ".join(ats["missing_keywords"]))

    st.markdown("---")
    st.markdown("### Job Description Analysis")
    st.session_state.job_description = st.text_area(
        "Paste the target job description", value=st.session_state.job_description, height=180,
        placeholder="e.g. HBL Cashier — responsibilities include handling cash transactions, customer service...",
    )

    if st.button("🔍 Analyze Job Match", type="primary"):
        if not st.session_state.job_description.strip():
            st.error("Please paste a job description first.")
        else:
            if groq_utils.is_configured():
                with st.spinner("Comparing your resume with the job description..."):
                    res = groq_utils.analyze_job_match(working_resume, st.session_state.job_description)
                if res["ok"]:
                    st.session_state.job_match_result = res["content"]
                else:
                    st.warning(f"AI analysis unavailable ({res['error']}). Showing a keyword-based estimate instead.")
                    st.session_state.job_match_result = ats_utils.heuristic_job_match(
                        working_resume, st.session_state.job_description
                    )
            else:
                st.info("Groq AI not configured — showing a keyword-based estimate.")
                st.session_state.job_match_result = ats_utils.heuristic_job_match(
                    working_resume, st.session_state.job_description
                )

    if st.session_state.job_match_result:
        jm = st.session_state.job_match_result
        st.caption("Estimated match — not an official score from any employer's ATS.")
        st.markdown(
            f'<div class="ar-score-wrap"><div class="ar-score-num">{jm.get("match_score", 0)}% Match</div></div>',
            unsafe_allow_html=True,
        )
        st.progress(min(100, max(0, int(jm.get("match_score", 0)))) / 100)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Matching Skills**")
            st.write(", ".join(jm.get("matching_skills", [])) or "—")
            st.markdown("**Relevant Experience**")
            for e in jm.get("relevant_experience", []) or []:
                st.markdown(f"- {e}")
        with c2:
            st.markdown("**Missing Skills**")
            st.write(", ".join(jm.get("missing_skills", [])) or "—")
            st.markdown("**Important Keywords**")
            st.write(", ".join(jm.get("keywords", [])) or "—")

        if jm.get("recommendations"):
            st.markdown("**Recommendations**")
            for r in jm["recommendations"]:
                st.markdown(f"- 💡 {r}")

        st.markdown("---")
        if st.button("✨ Optimize Resume for This Job", type="primary"):
            if groq_utils.is_configured():
                with st.spinner("Tailoring your resume..."):
                    res = groq_utils.generate_tailored_resume(
                        working_resume, st.session_state.job_description, jm.get("job_title", "")
                    )
                if res["ok"]:
                    st.session_state.tailored_resume_text = res["content"]
                else:
                    st.warning(f"AI tailoring unavailable ({res['error']}). Using your current resume text instead.")
                    st.session_state.tailored_resume_text = working_resume
            else:
                st.info("Groq AI not configured — the tailored resume will match your current resume text.")
                st.session_state.tailored_resume_text = working_resume

            photo_bytes = st.session_state.generated_photo_bytes if st.session_state.include_photo_in_resume else None
            try:
                st.session_state.tailored_resume_docx_bytes = document_utils.build_resume_docx(
                    st.session_state.tailored_resume_text, photo_bytes
                )
                st.session_state.tailored_resume_pdf_bytes = document_utils.build_resume_pdf(
                    st.session_state.tailored_resume_text, photo_bytes
                )
            except Exception as e:
                logger.exception("Tailored resume document generation failed")
                st.error(f"Could not generate tailored resume documents: {e}")
            st.success("Tailored resume ready!")

    if st.session_state.tailored_resume_text:
        with st.expander("View tailored resume text"):
            st.text(st.session_state.tailored_resume_text)
        d1, d2 = st.columns(2)
        if st.session_state.tailored_resume_docx_bytes:
            d1.download_button(
                "⬇️ Download Tailored Resume (DOCX)", data=st.session_state.tailored_resume_docx_bytes,
                file_name="tailored_resume.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            st.session_state.generated_files["tailored_resume.docx"] = st.session_state.tailored_resume_docx_bytes
        if st.session_state.tailored_resume_pdf_bytes:
            d2.download_button(
                "⬇️ Download Tailored Resume (PDF)", data=st.session_state.tailored_resume_pdf_bytes,
                file_name="tailored_resume.pdf", mime="application/pdf", use_container_width=True,
            )
            st.session_state.generated_files["tailored_resume.pdf"] = st.session_state.tailored_resume_pdf_bytes

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Continue to Cover Letter →", type="primary", use_container_width=True):
            go_to("Cover Letter")
            st.rerun()


# ---------------------------------------------------------------------
# COVER LETTER
# ---------------------------------------------------------------------

def render_cover_letter():
    st.markdown("## ✉️ Cover Letter Generator")

    working_resume = (
        st.session_state.tailored_resume_text
        or st.session_state.resume_text_improved
        or st.session_state.resume_text
    )
    if not working_resume or not working_resume.strip():
        st.info("Build your resume first in the Resume Builder section.")
        if st.button("Go to Resume Builder →"):
            go_to("Resume Builder")
            st.rerun()
        return

    st.markdown("### What job are you applying for?")
    st.session_state.cover_letter_job_title = st.text_input(
        "Job title", value=st.session_state.cover_letter_job_title, placeholder="e.g. HBL Cashier"
    )
    st.session_state.cover_letter_company = st.text_input(
        "Company name (optional)", value=st.session_state.cover_letter_company
    )
    jd_for_letter = st.text_area(
        "Paste job description (optional)",
        value=st.session_state.job_description,
        height=140,
    )

    if st.button("✉️ Generate Cover Letter", type="primary"):
        if not st.session_state.cover_letter_job_title.strip():
            st.error("Please enter the job title you're applying for.")
        else:
            if groq_utils.is_configured():
                with st.spinner("Writing your cover letter..."):
                    res = groq_utils.generate_cover_letter(
                        working_resume,
                        st.session_state.cover_letter_job_title,
                        st.session_state.cover_letter_company,
                        jd_for_letter,
                    )
                if res["ok"]:
                    st.session_state.cover_letter_text = res["content"]
                else:
                    st.error(f"Could not generate cover letter: {res['error']}")
            else:
                st.error("Groq AI is not configured, so a cover letter can't be generated. "
                          "Set GROQ_API_KEY to enable this feature.")

    if st.session_state.cover_letter_text:
        st.markdown("### Edit Your Cover Letter")
        st.session_state.cover_letter_text = st.text_area(
            "Cover letter", value=st.session_state.cover_letter_text, height=380, label_visibility="collapsed"
        )

        applicant_name = st.session_state.resume_data.get("personal", {}).get("full_name", "")
        try:
            st.session_state.cover_letter_docx_bytes = document_utils.build_cover_letter_docx(
                st.session_state.cover_letter_text, applicant_name
            )
            st.session_state.cover_letter_pdf_bytes = document_utils.build_cover_letter_pdf(
                st.session_state.cover_letter_text, applicant_name
            )
        except Exception as e:
            logger.exception("Cover letter document generation failed")
            st.error(f"Could not generate cover letter documents: {e}")

        d1, d2 = st.columns(2)
        if st.session_state.cover_letter_docx_bytes:
            d1.download_button(
                "⬇️ Download DOCX", data=st.session_state.cover_letter_docx_bytes,
                file_name="cover_letter.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            st.session_state.generated_files["cover_letter.docx"] = st.session_state.cover_letter_docx_bytes
        if st.session_state.cover_letter_pdf_bytes:
            d2.download_button(
                "⬇️ Download PDF", data=st.session_state.cover_letter_pdf_bytes,
                file_name="cover_letter.pdf", mime="application/pdf", use_container_width=True,
            )
            st.session_state.generated_files["cover_letter.pdf"] = st.session_state.cover_letter_pdf_bytes

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Go to Application Pack →", type="primary", use_container_width=True):
            go_to("Application Pack")
            st.rerun()


# ---------------------------------------------------------------------
# APPLICATION PACK
# ---------------------------------------------------------------------

def render_application_pack():
    st.markdown("## 📦 Your Application Pack")

    checklist = [
        ("Passport Photo", "passport_photo.jpg" in st.session_state.generated_files),
        ("ATS-Friendly Resume", st.session_state.resume_docx_bytes is not None),
        ("Tailored Resume", st.session_state.tailored_resume_docx_bytes is not None),
        ("ATS Compatibility Score", st.session_state.ats_result is not None),
        ("Job Match Score", st.session_state.job_match_result is not None),
        ("Tailored Cover Letter", st.session_state.cover_letter_docx_bytes is not None),
    ]

    for label, done in checklist:
        st.markdown(f"{'✅' if done else '⬜'} {label}")

    st.markdown("---")
    st.markdown("### Individual Downloads")
    if not st.session_state.generated_files:
        st.info("Nothing generated yet. Work through the other sections first.")
    else:
        cols = st.columns(2)
        items = list(st.session_state.generated_files.items())
        for i, (filename, content) in enumerate(items):
            with cols[i % 2]:
                mime = "application/octet-stream"
                if filename.endswith(".pdf"):
                    mime = "application/pdf"
                elif filename.endswith(".docx"):
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif filename.endswith(".jpg"):
                    mime = "image/jpeg"
                st.download_button(f"⬇️ {filename}", data=content, file_name=filename, mime=mime,
                                     use_container_width=True, key=f"pack_dl_{filename}")

    st.markdown("---")
    st.markdown("### Complete Application Pack")
    if st.session_state.generated_files:
        if st.button("📦 Build Complete Application Pack (ZIP)", type="primary"):
            zip_bytes = document_utils.build_application_pack_zip(st.session_state.generated_files)
            st.session_state["_pack_zip"] = zip_bytes
            st.success("Application pack ready!")

        if st.session_state.get("_pack_zip"):
            st.download_button(
                "⬇️ Download Complete Application Pack (ZIP)",
                data=st.session_state["_pack_zip"],
                file_name="ApplyReady_Application_Pack.zip",
                mime="application/zip",
                use_container_width=True,
            )
    else:
        st.caption("Generate at least one item before building the pack.")


# ---------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------

PAGE_RENDERERS = {
    "Home": render_home,
    "Smart Photo": render_smart_photo,
    "Resume Builder": render_resume_builder,
    "ATS Analyzer": render_ats_analyzer,
    "Cover Letter": render_cover_letter,
    "Application Pack": render_application_pack,
}

PAGE_RENDERERS.get(st.session_state.page, render_home)()
