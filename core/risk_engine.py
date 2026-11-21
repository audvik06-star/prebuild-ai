import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from groq import Groq

load_dotenv()

def build_prompt(contract_text: str = "") -> str:
    source_section = f"CONTRACT TEXT:\n{contract_text[:150000]}" if contract_text.strip() else "Read the attached scanned tender/contract PDF directly (it may be in Telugu, English, or both)."

    return f"""
    You are an expert Construction Profit & Contract Advisor for small Indian civil contractors 
    bidding on Telangana government tenders (around ₹10 Lakhs).

    The tender/contract may be written in *Telugu, English, or a mix of both*. 
    Analyze every clause and show the contractor how to MAXIMIZE PROFIT and avoid losing money.

    CRITICAL LANGUAGE RULE:
    Write EVERY section and bullet point in BOTH *English* and *simple, natural Telugu* 
    (first the English point, immediately followed by its Telugu explanation). Keep common 
    construction words like GST, EMD, BOQ, Retention Money, and M-Book clear.

    Organize your report into these 5 sections:
    1. 💰 *Profit Protection & GST Check (లాభం రక్షణ & GST తనిఖీ):* 
       - Is the quote GST-inclusive or exclusive (18%)? 
       - What statutory deductions apply (2% GST TDS, 1% Labour Cess, IT TDS, Seigniorage)?
    2. 📈 *Extra Money & Allowances to Claim (క్లెయిమ్ చేసుకోవాల్సిన అదనపు డబ్బు & అలవెన్సులు):* 
       - Are municipal/panchayat allowances, extra lead/conveyance charges, or price escalation clauses available?
    3. ⚠️ *Hidden Traps & Penalty Clauses (దాగి ఉన్న నష్టాలు & పెనాల్టీ నిబంధనలు):* 
       - Highlight Liquidated Damages (delay penalties), strict completion deadlines, and rules for getting written approval before doing extra/deviation work.
    4. 🔒 *Deposits & Cash Lock-in (డిపాజిట్లు & ఆగిపోయే నగదు వివరాలు):* 
       - List exact EMD, Security Deposit, and Retention Money percentages, plus when the contractor can claim them back.
    5. ✅ *Before-You-Bid Checklist (టెండర్ వేసే ముందు తప్పనిసరి చెక్‌లిస్ట్):* 
       - List every mandatory certificate, stamp paper, and deadline required so the bid is not rejected.

    Always quote the exact clause or page reference from the document where found.

    {source_section}
    """

def detect_risks(contract_text: str, pdf_bytes: bytes = None) -> str:
    prompt = build_prompt(contract_text)
    error_log = []

    # 1. Primary: Google Gemini (Handles both Digital Text AND Scanned Telugu PDFs)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        client = genai.Client(api_key=gemini_key)
        gemini_models = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
        ]

        # If scanned PDF (no extracted text), attach raw PDF directly for Gemini Vision
        if not contract_text.strip() and pdf_bytes:
            contents_payload = [
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt,
            ]
        else:
            contents_payload = prompt

        for model_name in gemini_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                )
                return f"Analyzed using Gemini ({model_name})\n\n" + response.text
            except errors.APIError as e:
                error_log.append(f"Gemini {model_name}: {e.code}")
                time.sleep(1)
            except Exception as e:
                error_log.append(f"Gemini {model_name}: {str(e)}")

    # 2. Free Backup: Groq (Works when digital text was extracted)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and contract_text.strip():
        try:
            groq_client = Groq(api_key=groq_key)
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
            )
            return "Analyzed using Groq Free AI (llama-3.3-70b)\n\n" + response.choices[0].message.content
        except Exception as e:
            error_log.append(f"Groq: {str(e)}")

    return "❌ Could not analyze PDF (if scanned, Gemini may be busy—try again in 10 seconds).\n\nDetails: " + " | ".join(error_log)