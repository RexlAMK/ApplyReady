# ApplyReady AI 🚀

**From your photo and profile to a job-ready application.**

ApplyReady AI is a working (not a chatbot!) Streamlit tool that takes a user from
a phone photo and their career information to a complete, downloadable job
application: a professional passport/ID photo, an ATS-friendly resume, an
estimated ATS compatibility score, a job-match analysis, a tailored resume, and
a job-specific cover letter — all bundled into one ZIP application pack.

## Features

- **Smart Passport/ID Photo Generator**
  - Upload a photo or capture one with your camera
  - Standard passport size or fully custom dimensions (mm / cm / inches / px)
  - Professional blue, white, or original background (best-effort AI background removal via `rembg`, with a graceful fallback if unavailable)
  - Black & white mode with contrast preservation
  - Face-aware cropping (OpenCV) that avoids distorting the subject
  - Download as JPG, plus a print-ready sheet (4×6" or A4) as PDF

- **Resume Builder**
  - Upload an existing CV (PDF / DOCX / TXT) and review/edit the extracted text, or
  - Fill in a detailed multi-section manual form (personal info, summary, education, experience, internships, projects, skills, certifications, awards, volunteer work, references)
  - Automatically reuses your generated passport photo (toggle on/off)
  - AI-polishes grammar, tone, structure, and ATS-friendliness **without inventing new facts**

- **ATS Analyzer**
  - Estimated ATS Compatibility Score (0–100) with strengths & improvements
  - Paste any job description to get an estimated Job Match Score, matching/missing skills, keywords, and recommendations
  - One-click "Optimize Resume for This Job" — tailors your resume using only information you already provided

- **Cover Letter Generator**
  - Enter a job title (and optionally company name / job description)
  - AI drafts a specific, professional cover letter grounded in your real resume content
  - Fully editable before download

- **Application Pack**
  - Checklist of everything generated
  - Individual downloads for every file
  - One-click ZIP download of the complete application pack

All AI text generation is powered by the **Groq API**. All scores are clearly
labeled as *estimates* — they are not official scores from any specific
employer's ATS.

## Architecture

```
ApplyReadyAI/
├── app.py                  # Streamlit app: UI, navigation, session state
├── requirements.txt
├── README.md
├── .env.example
└── utils/
    ├── image_utils.py      # Passport photo processing pipeline
    ├── resume_utils.py     # File text extraction + resume data model
    ├── document_utils.py   # DOCX / PDF / ZIP generation
    ├── groq_utils.py       # Groq API integration (structured JSON where useful)
    └── ats_utils.py        # Local heuristic fallback scoring (no AI required)
```

The app is deliberately dependency-light and defensive: every AI call and every
image/file operation is wrapped so a missing API key, a scanned PDF, a corrupt
image, or a network error produces a friendly message instead of a crash.

## Installation (local)

```bash
git clone <this project folder>
cd ApplyReadyAI
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Optional:** for real AI background removal in the passport photo tool, also install:

```bash
pip install -r requirements-optional.txt
```

This is separate from the core install because it pulls in `rembg`, which
depends on heavier packages (`scikit-image`, `numba`, `onnxruntime`) that
can conflict with other environments (see the Colab note in
Troubleshooting below). The app works fully without it — background
removal automatically falls back to keeping the original background.

### Groq API Setup

1. Create a free account and API key at https://console.groq.com
2. Set the key using **one** of these methods:

   **Environment variable**
   ```bash
   export GROQ_API_KEY="your_key_here"      # macOS/Linux
   setx GROQ_API_KEY "your_key_here"        # Windows
   ```

   **Streamlit secrets** — create `.streamlit/secrets.toml`:
   ```toml
   GROQ_API_KEY = "your_key_here"
   ```

The app works without a key: the sidebar will show "Groq AI: Not configured"
and the photo tools, resume builder, document generation, and a
keyword-based ATS/job-match estimate will still work — only the AI text
generation (resume polishing, AI-based scoring, tailored resume, cover
letter) requires the key.

## Run Locally

```bash
streamlit run app.py
```

Then open the URL shown in the terminal (usually http://localhost:8501).

## Run in Google Colab

```python
!pip install -r requirements.txt -q
!wget -q -O - https://loca.lt/mytunnelpassword  # optional, for LocalTunnel password
!streamlit run app.py &>/content/logs.txt &
!npx localtunnel --port 8501
```

Or with a Cloudflare Tunnel:

```python
!pip install -r requirements.txt -q
!streamlit run app.py &>/content/logs.txt &
!cloudflared tunnel --url http://localhost:8501
```

Set `GROQ_API_KEY` in Colab first, e.g.:

```python
import os
os.environ["GROQ_API_KEY"] = "your_key_here"
```

## Troubleshooting

- **"Groq AI: Not configured"** — set `GROQ_API_KEY` as described above. The rest of the app still works.
- **Background removal didn't seem to apply** — `rembg` is an optional dependency (see Installation above). If it isn't installed, or fails to install, the app automatically keeps the original background and tells you so; cropping, resizing, and black & white still work normally.
- **"ERROR: pip's dependency resolver does not currently take into account..."** — despite the word "ERROR", this is a **non-fatal warning**, not a failed install. It appears whenever installing a package changes a version that some other, unrelated package in the environment wanted. Check whether the install actually finished (look for `Successfully installed ...` above the warning) — if so, you can safely continue to the next step. This is especially common in Colab, which ships a large preinstalled data-science/GPU stack (jax, pytensor, cudf, cuml, cucim, shap, etc.) that our lightweight app doesn't touch at all.
- **Colab: numpy or numba/scikit-image conflicts specifically** — this project's `requirements.txt` intentionally has **no upper-bound version pins**, so a normal `pip install -r requirements.txt` should just reuse Colab's existing numpy/opencv rather than downgrading them. The optional `rembg` package (see Installation above) is the most common source of numba/scikit-image conflicts — it's deliberately kept out of the core `requirements.txt` for this reason. If you still see resolver warnings, `!pip install -r requirements.txt --upgrade-strategy only-if-needed -q` tells pip to avoid touching already-satisfied packages.
- **"No readable text was found in this PDF"** — the PDF is likely a scanned image without embedded text. Use "Enter Information Manually" instead, or run OCR on the file first.
- **Camera input doesn't show a device** — this depends on your browser granting camera permission to the page; use the Upload tab instead if needed.
- **Resume documents look plain** — this is intentional: the layout avoids tables, text boxes, and images-with-text so it stays machine-readable for real ATS software.
- **"Groq API error (404): The model `...` does not exist or you do not have access to it"** — Groq periodically changes which models are available on a standard developer key (some move to Enterprise-only pricing, get deprecated, etc.). The app already tries a short list of current fallback models automatically (`openai/gpt-oss-120b` → `openai/gpt-oss-20b` → `llama-3.3-70b-versatile` → `llama-3.1-8b-instant`) and remembers whichever one works. If all of them fail for your account, check https://console.groq.com/docs/models for the current list and set a specific one yourself with an environment variable: `os.environ["GROQ_MODEL"] = "model-id-here"` (or `GROQ_MODEL` in Streamlit secrets).

## Limitations

- Passport photo dimensions follow a common, widely recognizable default (35mm × 45mm) and are clearly labeled as such — always confirm exact requirements with the specific country or organization you're applying to before using a photo for an official document.
- ATS Compatibility Score and Job Match Score are heuristic **estimates** (AI-assisted when Groq is configured, keyword-based otherwise) and are not affiliated with, or guaranteed to match, any specific commercial ATS product.
- Background removal quality depends on the `rembg` library and the input photo; results vary with lighting, hair detail, and image complexity.
- The AI is instructed not to invent resume content, but as with any LLM output, it's worth reviewing generated text before sending your application.

---

Built with Python • Streamlit • Groq AI
