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


def _call_gemini(prompt: str) -> tuple[str, str]:
    api_key = get_config_value("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key)
    candidate_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    last_exc: Exception | None = None

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text.strip(), f"Gemini ({model_name})"
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(1.5)
                    continue
                break

    raise RuntimeError(f"Gemini failed: {last_exc}")


def _call_groq(prompt: str) -> tuple[str, str]:
    api_key = get_config_value("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing.")

    client = Groq(api_key=api_key)

    # Fetch currently active text models on your Groq account dynamically
    preferred = [
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-32b",
    ]
    try:
        live_ids = [
            m.id
            for m in client.models.list().data
            if not any(skip in m.id.lower() for skip in ("whisper", "guard", "tts", "orpheus"))
        ]
        ordered_models = [m for m in preferred if m in live_ids] + [
            m for m in live_ids if m not in preferred
        ]
    except Exception:
        ordered_models = preferred

    last_exc: Exception | None = None
    for model_name in ordered_models[:4]:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )
            text = (completion.choices[0].message.content or "").strip()
            if text:
                return text, f"Groq ({model_name})"
        except Exception as exc:
            last_exc = exc
            continue

    raise RuntimeError(f"Groq failed: {last_exc}")


def analyze_tender_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """Analyze tender PDF and return (report_markdown, engine_used)."""
    tender_text = extract_pdf_text(pdf_bytes)
    full_prompt = f"{SYSTEM_PROMPT}\n\n=== TENDER DOCUMENT TEXT ===\n{tender_text}"

    gemini_err_msg = ""
    try:
        return _call_gemini(full_prompt)
    except Exception as gemini_err:
        gemini_err_msg = str(gemini_err)

    try:
        return _call_groq(f"=== TENDER DOCUMENT TEXT ===\n{tender_text}")
    except Exception as groq_err:
        raise RuntimeError(f"{gemini_err_msg} | {groq_err}") from groq_err