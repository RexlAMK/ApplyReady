"""
ats_utils.py
Lightweight, dependency-free heuristics used as a fallback whenever the
Groq API is unavailable (missing key, network error, rate limit, etc.).
These are intentionally simple keyword/structure-based estimates -- they
exist so the app never breaks even with zero AI access.
"""

import re

STOPWORDS = set("""
a an the and or but of to in on for with at by from as is are was were be been
being this that these those it its into your you our their his her they i we
will can may should would could not no yes about over under between within
""".split())

COMMON_SECTION_HEADINGS = [
    "experience", "education", "skills", "summary", "projects",
    "certifications", "achievements", "awards", "contact", "profile",
    "objective", "internship", "volunteer", "references",
]

ACTION_VERBS = [
    "led", "built", "created", "developed", "designed", "managed",
    "implemented", "improved", "optimized", "increased", "reduced",
    "launched", "delivered", "coordinated", "analyzed", "achieved",
    "streamlined", "automated", "spearheaded", "organized",
]


def _tokenize(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\+\#\.\-]{1,}", (text or "").lower())
    return [w.strip(".-") for w in words if w.strip(".-") and w not in STOPWORDS]


def extract_keywords(text, top_n=25):
    """Very simple frequency-based keyword extraction."""
    words = _tokenize(text)
    freq = {}
    for w in words:
        if len(w) < 3:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


def heuristic_ats_score(resume_text):
    """
    Fallback ATS score when AI is unavailable. Returns the same schema as
    groq_utils.analyze_ats's content field.
    """
    text = resume_text or ""
    lower = text.lower()
    score = 40  # baseline
    strengths = []
    improvements = []

    # Section headings present
    found_sections = [s for s in COMMON_SECTION_HEADINGS if s in lower]
    if len(found_sections) >= 3:
        score += 15
        strengths.append("Resume includes standard, ATS-recognizable section headings.")
    else:
        improvements.append("Add clear standard section headings (Experience, Education, Skills).")

    # Bullet points / structure
    bullet_count = text.count("\n-") + text.count("\n•") + text.count("\n*")
    if bullet_count >= 4:
        score += 10
        strengths.append("Uses bullet points for readability and parsing.")
    else:
        improvements.append("Use bullet points to list responsibilities and achievements.")

    # Action verbs
    verb_hits = sum(1 for v in ACTION_VERBS if v in lower)
    if verb_hits >= 3:
        score += 10
        strengths.append("Good use of strong action verbs.")
    else:
        improvements.append("Start more bullet points with strong action verbs (e.g., 'led', 'built', 'improved').")

    # Quantifiable achievements (numbers/%)
    if re.search(r"\d+%|\$\d+|\b\d{2,}\b", text):
        score += 10
        strengths.append("Includes some measurable/quantifiable results.")
    else:
        improvements.append("Add measurable achievements where possible (numbers, percentages, results).")

    # Length sanity check
    word_count = len(text.split())
    if 200 <= word_count <= 1200:
        score += 10
        strengths.append("Resume length is within a reasonable range.")
    elif word_count < 200:
        improvements.append("Resume seems short — consider adding more relevant detail.")
    else:
        improvements.append("Resume seems long — consider tightening content for clarity.")

    # Contact info
    if re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text):
        score += 5
        strengths.append("Contact email is present.")
    else:
        improvements.append("Add a clear, professional email address.")

    score = max(0, min(100, score))
    missing_keywords = []  # unknown without a job description in this fallback

    if not strengths:
        strengths.append("Resume text was successfully processed.")
    if not improvements:
        improvements.append("Consider a final proofread for tone and consistency.")

    return {
        "score": score,
        "strengths": strengths,
        "improvements": improvements,
        "missing_keywords": missing_keywords,
    }


def heuristic_job_match(resume_text, job_description):
    """
    Fallback job-match score using keyword overlap when AI is unavailable.
    Returns the same schema as groq_utils.analyze_job_match's content field.
    """
    resume_words = set(_tokenize(resume_text))
    jd_words = _tokenize(job_description)
    jd_keywords = extract_keywords(job_description, top_n=30)

    jd_unique = set(jd_words)
    matching = sorted([w for w in jd_unique if w in resume_words and len(w) > 2])
    missing = sorted([w for w in jd_keywords if w not in resume_words])

    if jd_unique:
        overlap_ratio = len(matching) / max(1, len(jd_unique))
    else:
        overlap_ratio = 0
    match_score = int(min(100, max(5, overlap_ratio * 140)))  # scaled heuristic

    # naive job title guess: first line of JD, trimmed
    first_line = (job_description or "").strip().split("\n")[0][:80]

    recommendations = []
    if missing:
        recommendations.append(
            "Consider highlighting or genuinely gaining experience in: " + ", ".join(missing[:8])
        )
    recommendations.append("Mirror the exact terminology used in the job description where truthful.")

    return {
        "job_title": first_line or "Target Role",
        "match_score": match_score,
        "matching_skills": matching[:15],
        "missing_skills": missing[:15],
        "keywords": jd_keywords[:20],
        "relevant_experience": [],
        "recommendations": recommendations,
    }
