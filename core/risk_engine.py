import time
import fitz  # PyMuPDF
from google import genai
from groq import Groq

from core.auth_db import get_config_value

SYSTEM_PROMPT = """You are PreBuild AI, a senior civil engineering estimator and government tender consultant in Telangana & Andhra Pradesh, India.
Analyze the provided construction tender document to help a small contractor maximize net profit on a ~₹10 Lakh project and avoid hidden financial traps.

Provide a clear, practical report in BOTH *English* and *తెలుగు (Telugu)* with these exact sections:
1. *Tender Snapshot & Margin Potential* (Estimated work value, EMD/SD requirements, completion timeline, realistic net profit margin %)
2. *Top Cost-Saving Opportunities (Where to Save Money)* (Material procurement timing, local quarry/aggregate sourcing, labor scheduling, BOQ rate optimization)
3. *High-Risk Clauses & Penalty Traps* (Liquidated damages, defect liability period, price escalation exclusions, strict material testing clauses)
4. *Final Bid Recommendation* (Clear GO / CAUTION / NO-GO verdict and optimal bid quote strategy)

Keep every point concrete, actionable, and tailored for a field contractor reading on a mobile screen."""


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 28000) -> str:
    """Extract clean text across all pages of an uploaded tender PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[str] = []
    total_len = 0

    for page_idx, page in enumerate(doc, start=1):
        page_text = page.get_text("text").strip()
        if not page_text:
            continue
        header = f"\n--- Page {page_idx} ---\n"
        block = header + page_text
        chunks.append(block)
        total_len += len(block)
        if total_len >= max_chars:
            break

    doc.close()
    combined = "\n".join(chunks).strip()
    if not combined:
        raise ValueError(
            "No readable text found in this PDF. Please upload a digital tender PDF (not a blank or pure image scan)."
        )
    return combined[:max_chars]


def _call_gemini(prompt: str) -> str:
    api_key = get_config_value("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key)
    last_exc: Exception | None = None

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as exc:
            last_exc = exc
            if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                time.sleep(2)
                continue
            raise

    raise RuntimeError(f"Gemini unavailable: {last_exc}")


def _call_groq(prompt: str) -> str:
    api_key = get_config_value("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured for fallback.")

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=3000,
    )
    return (completion.choices[0].message.content or "").strip()


def analyze_tender_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """Analyze tender PDF and return (report_markdown, engine_used)."""
    tender_text = extract_pdf_text(pdf_bytes)
    full_prompt = f"{SYSTEM_PROMPT}\n\n=== TENDER DOCUMENT TEXT ===\n{tender_text}"

    try:
        report = _call_gemini(full_prompt)
        return report, "Gemini 2.5 Flash"
    except Exception as gemini_err:
        groq_key = get_config_value("GROQ_API_KEY")
        if groq_key:
            report = _call_groq(f"=== TENDER DOCUMENT TEXT ===\n{tender_text}")
            return report, "Groq Llama 3.3 70B (Auto-Fallback)"
        raise RuntimeError(f"{gemini_err}. No credit was deducted.") from gemini_err