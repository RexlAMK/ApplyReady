"""
groq_utils.py
Helper functions for talking to the Groq API (OpenAI-compatible chat completions).
All AI-powered features (resume improvement, ATS scoring, job matching,
tailored resume generation, cover letter generation) go through here.

Design goals:
- Never crash the app if the API key is missing or the request fails.
- Prefer structured JSON responses so the rest of the app doesn't need
  fragile text parsing.
- Never invent information that the user did not provide (enforced via
  prompt instructions + downstream validation where practical).
"""

import json
import logging
import os
import re

logger = logging.getLogger("applyready.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

# Groq periodically changes which models are available on a standard
# developer API key (some get moved behind Enterprise/contact-sales
# pricing, deprecated, etc.). Rather than hardcoding one model name that
# can silently 404, we keep an ordered list of reasonable candidates and
# automatically fall through to the next one if a model is unavailable.
# Override with the GROQ_MODEL environment variable / Streamlit secret to
# force a specific model.
DEFAULT_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

# Remembers the first model that actually worked this run, so we don't
# re-probe the fallback list on every single call.
_working_model = None


def get_preferred_model():
    """Resolve a model override from env var or Streamlit secrets, if set."""
    model = os.getenv("GROQ_MODEL")
    if model:
        return model.strip()
    try:
        import streamlit as st
        model = st.secrets["GROQ_MODEL"]
        if model:
            return str(model).strip()
    except Exception:
        pass
    return None


def get_api_key():
    try:
        import streamlit as st
        user_key = st.session_state.get("user_groq_key")
        if user_key:
            return str(user_key).strip()
    except Exception:
        pass

    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        return api_key.strip()

    try:
        import streamlit as st
        api_key = st.secrets["GROQ_API_KEY"]
        if api_key:
            return str(api_key).strip()
    except Exception:
        pass

    return None
    """
    Resolve the Groq API key from environment variable first, then
    Streamlit secrets. Returns None if not found anywhere (never raises).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        return api_key.strip()

    try:
        import streamlit as st
        api_key = st.secrets["GROQ_API_KEY"]
        if api_key:
            return str(api_key).strip()
    except Exception:
        pass

    return None


def is_configured():
    return bool(get_api_key())


def _extract_json(text):
    """
    Best-effort extraction of a JSON object from model output, in case the
    model wraps it in prose or markdown code fences.
    """
    if not text:
        return None
    text = text.strip()
    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fall back to finding the first {...} or [...] block
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return None


def _post_chat_completion(api_key, model, messages, temperature, max_tokens, json_mode):
    """Single raw request to Groq. Returns (status_code, parsed_json_or_None, raw_text, request_error_or_None)."""
    try:
        import requests
    except ImportError:
        return None, None, None, "The 'requests' package is not installed."

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    except Exception as e:
        logger.exception("Groq request failed")
        return None, None, None, f"Could not reach Groq API: {e}"

    try:
        body = resp.json()
    except Exception:
        body = None

    return resp.status_code, body, resp.text, None


def _is_model_error(status_code, body):
    """Detect a 'model not found / no access' style error worth falling back on."""
    if status_code == 404:
        return True
    if status_code == 400 and body:
        msg = str(body.get("error", {}).get("message", "")).lower()
        if "model" in msg and ("does not exist" in msg or "decommission" in msg or "not found" in msg):
            return True
    return False


def call_groq(messages, json_mode=False, temperature=0.4, max_tokens=2000, model=None):
    """
    Send a chat completion request to Groq.

    Returns a dict: {"ok": bool, "content": str or dict, "error": str or None}

    If json_mode is True, attempts to parse the response as JSON and
    returns the parsed object as "content". If parsing fails, returns
    ok=False with the raw text preserved in "raw".

    If the requested/default model returns a "model not found / no access"
    style error, automatically retries with the next candidate in
    FALLBACK_MODELS before giving up, and remembers whichever model works
    for the rest of the session.
    """
    global _working_model

    api_key = get_api_key()
    if not api_key:
        return {
            "ok": False,
            "content": None,
            "error": "Groq API key is not configured. Add GROQ_API_KEY as an "
                     "environment variable or in Streamlit secrets.",
        }

    # Build the ordered list of models to attempt.
    explicit = model or get_preferred_model()
    if explicit:
        candidates = [explicit]
    elif _working_model:
        candidates = [_working_model] + [m for m in FALLBACK_MODELS if m != _working_model]
    else:
        candidates = list(FALLBACK_MODELS)

    last_error = None
    for candidate in candidates:
        status_code, body, raw_text, request_error = _post_chat_completion(
            api_key, candidate, messages, temperature, max_tokens, json_mode
        )

        if request_error:
            return {"ok": False, "content": None, "error": request_error}

        if status_code == 200 and body is not None:
            _working_model = candidate
            try:
                text = body["choices"][0]["message"]["content"]
            except Exception as e:
                logger.exception("Unexpected Groq response shape")
                return {"ok": False, "content": None, "error": f"Unexpected response from Groq: {e}"}

            if not json_mode:
                return {"ok": True, "content": text, "error": None}

            parsed = _extract_json(text)
            if parsed is None:
                return {"ok": False, "content": None,
                         "error": "Could not parse structured response from AI.", "raw": text}
            return {"ok": True, "content": parsed, "error": None}

        # Non-200 response
        detail = ""
        if body:
            detail = body.get("error", {}).get("message", (raw_text or "")[:300])
        else:
            detail = (raw_text or "")[:300]
        logger.error("Groq API error %s (model=%s): %s", status_code, candidate, detail)
        last_error = f"Groq API error ({status_code}): {detail}"

        if _is_model_error(status_code, body):
            # Try the next candidate model.
            continue
        else:
            # A different kind of error (auth, rate limit, etc.) — no point
            # trying other models, it will fail the same way.
            return {"ok": False, "content": None, "error": last_error}

    return {"ok": False, "content": None,
             "error": last_error or "All Groq model candidates were unavailable."}


SAFETY_CLAUSE = (
    "CRITICAL RULES: Only use information explicitly provided below. "
    "Never invent, assume, or embellish jobs, companies, degrees, certifications, "
    "skills, achievements, metrics, responsibilities, or dates that are not present "
    "in the provided information. If something is missing or unclear, leave it out "
    "or keep the original wording rather than fabricating detail."
)


def improve_resume_text(resume_text):
    """
    Ask the AI to improve grammar, tone, structure, action verbs, and
    ATS-friendliness of the resume WITHOUT inventing new content.
    Returns {"ok", "content": improved_text, "error"}.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert professional resume writer and ATS optimization "
                "specialist. You improve wording, grammar, structure, bullet clarity, "
                "and action verbs. " + SAFETY_CLAUSE
            ),
        },
        {
            "role": "user",
            "content": (
                "Improve the following resume content for professional tone, grammar, "
                "concise strong bullet points, and ATS-friendly plain-text formatting. "
                "Keep the same section structure. Do not add any new facts, employers, "
                "dates, or skills that are not already present.\n\n"
                f"RESUME CONTENT:\n{resume_text}"
            ),
        },
    ]
    return call_groq(messages, json_mode=False, temperature=0.4, max_tokens=2200)


def analyze_ats(resume_text):
    """
    Estimate an ATS compatibility score with strengths/improvements.
    Returns {"ok", "content": {...}, "error"}.
    Content schema:
      {
        "score": int 0-100,
        "strengths": [str, ...],
        "improvements": [str, ...],
        "missing_keywords": [str, ...]
      }
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are an ATS (Applicant Tracking System) resume auditor. "
                "You always respond with strictly valid JSON and nothing else. " + SAFETY_CLAUSE
            ),
        },
        {
            "role": "user",
            "content": (
                "Evaluate this resume for general ATS-friendliness (formatting clarity, "
                "standard section headings, keyword presence, quantifiable achievements, "
                "strong bullet points). This is an ESTIMATE, not tied to any specific employer's ATS.\n\n"
                f"RESUME:\n{resume_text}\n\n"
                "Respond ONLY with JSON in exactly this schema:\n"
                '{"score": <int 0-100>, "strengths": [<string>, ...], '
                '"improvements": [<string>, ...], "missing_keywords": [<string>, ...]}'
            ),
        },
    ]
    return call_groq(messages, json_mode=True, temperature=0.3, max_tokens=1200)


def analyze_job_match(resume_text, job_description):
    """
    Compare resume to a job description.
    Content schema:
      {
        "job_title": str,
        "match_score": int 0-100,
        "matching_skills": [str,...],
        "missing_skills": [str,...],
        "keywords": [str,...],
        "relevant_experience": [str,...],
        "recommendations": [str,...]
      }
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a recruiting and ATS keyword-matching expert. "
                "You always respond with strictly valid JSON and nothing else. " + SAFETY_CLAUSE
            ),
        },
        {
            "role": "user",
            "content": (
                "Compare the candidate resume with the target job description below. "
                "Produce an ESTIMATED match score (0-100), not an official score from any vendor.\n\n"
                f"RESUME:\n{resume_text}\n\n"
                f"JOB DESCRIPTION:\n{job_description}\n\n"
                "Respond ONLY with JSON in exactly this schema:\n"
                '{"job_title": <string>, "match_score": <int 0-100>, '
                '"matching_skills": [<string>, ...], "missing_skills": [<string>, ...], '
                '"keywords": [<string>, ...], "relevant_experience": [<string>, ...], '
                '"recommendations": [<string>, ...]}'
            ),
        },
    ]
    return call_groq(messages, json_mode=True, temperature=0.3, max_tokens=1500)


def generate_tailored_resume(resume_text, job_description, job_title=""):
    """
    Produce a tailored version of the resume text using only information
    already present in resume_text. Returns {"ok", "content": text, "error"}.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert resume writer specializing in tailoring resumes "
                "to specific jobs. " + SAFETY_CLAUSE
            ),
        },
        {
            "role": "user",
            "content": (
                f"Target job title: {job_title or '(not specified)'}\n\n"
                f"JOB DESCRIPTION:\n{job_description}\n\n"
                f"CANDIDATE RESUME:\n{resume_text}\n\n"
                "Rewrite the resume tailored to this job: reorder/emphasize relevant "
                "skills and experience, sharpen bullet points, incorporate legitimate "
                "keywords from the job description that genuinely match the candidate's "
                "real background, and tighten the summary. Do not add any skill, job, "
                "certification, or achievement the candidate did not already list. "
                "Keep the same overall section structure as the original resume."
            ),
        },
    ]
    return call_groq(messages, json_mode=False, temperature=0.4, max_tokens=2200)


def generate_cover_letter(resume_text, job_title, company_name="", job_description=""):
    """
    Generate a tailored, professional cover letter.
    Returns {"ok", "content": text, "error"}.
    """
    context = f"Target job title: {job_title}\n"
    if company_name:
        context += f"Company: {company_name}\n"
    if job_description:
        context += f"Job description:\n{job_description}\n"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert cover letter writer. You write specific, warm, "
                "professional, non-generic cover letters grounded strictly in the "
                "candidate's real background. " + SAFETY_CLAUSE
            ),
        },
        {
            "role": "user",
            "content": (
                f"{context}\n"
                f"CANDIDATE RESUME:\n{resume_text}\n\n"
                "Write a complete, ready-to-send professional cover letter (3-4 "
                "paragraphs) for this candidate applying to this role. Reference "
                "specific real skills/experience from the resume. Do not invent "
                "achievements, employers, or skills not present in the resume. "
                "Avoid generic filler phrases like 'I am a hard worker'. Do not "
                "include placeholder brackets like [Company Name] unless that "
                "information is genuinely unknown, in which case use a neutral "
                "phrase like 'your organization'."
            ),
        },
    ]
    return call_groq(messages, json_mode=False, temperature=0.5, max_tokens=1200)
