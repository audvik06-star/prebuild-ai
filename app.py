import os
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import streamlit as st
from dotenv import load_dotenv
from google import genai
from supabase import Client, create_client

from core.auth_db import (
    MOBILE_COL,
    auto_login_by_device,
    login_or_register_contractor,
    update_job_status,
)

load_dotenv()

st.set_page_config(
    page_title="PreBuild AI",
    page_icon="icon.png" if os.path.exists("icon.png") else "🏗️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Pure #000000 dark theme & clean mobile layout
st.markdown(
    """
    <style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #000000 !important;
        color: #FFFFFF !important;
    }
    #MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] {
        visibility: hidden !important;
        height: 0 !important;
    }
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 3rem !important;
        max-width: 680px !important;
    }
    div[data-testid="stForm"] {
        background-color: #0A0A0A !important;
        border: 1px solid #262626 !important;
        border-radius: 14px !important;
        padding: 1.1rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_secret(key: str) -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, "")


@st.cache_resource
def init_supabase() -> Optional[Client]:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if url and key:
        return create_client(url, key)
    return None


supabase = init_supabase()

# Header with custom logo
col_logo, col_title = st.columns([1, 5])
with col_logo:
    if os.path.exists("icon.png"):
        st.image("icon.png", width=56)
with col_title:
    st.markdown("### PreBuild AI")
    st.caption("Construction Tender Profit & Risk Analyzer (English + తెలుగు)")

if not supabase:
    st.error("Cloud database not configured. Add SUPABASE_URL and SUPABASE_KEY in Secrets.")
    st.stop()

# 1. Read permanent Device ID from PWA wrapper (or auto-create one for direct laptop access)
device_id = str(st.query_params.get("device_id", ""))
if not device_id:
    device_id = f"laptop-{uuid.uuid4().hex[:12]}"
    st.query_params["device_id"] = device_id

# 2. Auto-login if phone/device is already linked (survives app swipe & refresh)
if "contractor" not in st.session_state or st.session_state.contractor is None:
    if device_id:
        saved_user = auto_login_by_device(supabase, device_id)
        if saved_user:
            st.session_state.contractor = saved_user

# 3. Login / Registration Gate with Full-Width ENTER Button
if not st.session_state.get("contractor"):
    st.subheader("🔐 Contractor Login / Register")
    st.caption(
        "First time? Type your 10-digit mobile number and create a 4-digit secret PIN. "
        "Your account locks to this phone (1 number = 1 mobile)."
    )

    with st.form("mobile_login_form", clear_on_submit=False):
        mobile_input = st.text_input(
            "10-Digit Mobile Number",
            max_chars=10,
            placeholder="e.g. 9848012345",
        )
        pin_input = st.text_input(
            "4-Digit Secret PIN",
            type="password",
            max_chars=4,
            placeholder="e.g. 4521",
        )
        enter_clicked = st.form_submit_button(
            "Enter PreBuild AI →",
            type="primary",
            use_container_width=True,
        )

    if enter_clicked:
        ok, msg, user_row = login_or_register_contractor(
            supabase, mobile_input, pin_input, device_id
        )
        if ok:
            st.session_state.contractor = user_row
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)
    st.stop()

# 4. Refresh latest contractor state from Supabase
contractor: Dict[str, Any] = st.session_state.contractor
mobile = str(contractor[MOBILE_COL])

fresh_res = supabase.table("contractors").select("*").eq(MOBILE_COL, mobile).limit(1).execute()
if fresh_res.data:
    contractor = fresh_res.data[0]
    st.session_state.contractor = contractor

credits = int(contractor.get("credits") or 0)
history: List[Dict[str, Any]] = contractor.get("history") or []

# Top Status Bar
c1, c2, c3 = st.columns([2, 2, 1])
c1.markdown(f"*📱 {mobile}*")
c2.markdown(f"*🎟️ Credits: {credits}*")
if c3.button("Lock", use_container_width=True):
    st.session_state.contractor = None
    st.rerun()

st.divider()

# 5. Auto-Resume Background Job if contractor swiped away mid-analysis
if contractor.get("job_status") == "processing":
    active_name = (
        contractor.get("last_job_filename")
        or contractor.get("job_file")
        or "your tender"
    )
    st.info(
        f"⏳ Analyzing *{active_name}* in the background... "
        "You can safely minimize the app and return in 20 seconds."
    )
    time.sleep(4)
    st.rerun()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: List[str] = []
    for idx, page in enumerate(doc, start=1):
        txt = page.get_text("text").strip()
        if txt:
            pages.append(f"--- PDF Page {idx} ---\n{txt}")
    return "\n\n".join(pages)


def run_gemini_analysis(pdf_text: str) -> str:
    api_key = get_secret("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    prompt = f"""
You are a Senior Civil Construction Contract & Tender Risk Advisor for Telangana municipal and government contractors.
Analyze the following tender document and produce a clear, bilingual (English + Telugu) Contractor Profit & Risk Report.

Rules:
- Cite exact Clause numbers (e.g., Clause 2.54, Clause 3.92) rather than shifted PDF page numbers.
- Explicitly check and warn about:
  1. GST-inclusive vs GST-exclusive rates, 2% GST TDS, 1% BOCW Labour Cess, IT TDS, and Seigniorage/Royalty deductions.
  2. Price escalation availability, Municipal Area Labour Allowance rules (warn if 20% allowance is NOT automatic), and Base Quarry Lead (e.g., 5 km base lead).
  3. Liquidated Damages (weekly penalty % and max cap), >5% Variation prior written approval rule, and 48-hour written Hindrance Notice rule.
  4. Exact EMD, FSD, Additional Performance Security (APS), and Retention Money % + Defect Liability Period lock-in duration.
  5. Mandatory Cover-I Before-You-Bid Document Checklist.

Use these exact 5 headings with both English and Telugu bullet points under each:
### 1. 💰 Profit Protection & GST Check (లాభం రక్షణ & GST తనిఖీ)
### 2. 📈 Extra Money & Allowances to Claim (క్లెయిమ్ చేసుకోవాల్సిన అదనపు డబ్బు & అలవెన్సులు)
### 3. ⚠️ Hidden Traps & Penalty Clauses (దాగి ఉన్న నష్టాలు & పెనాల్టీ నిబంధనలు)
### 4. 🔒 Deposits & Cash Lock-in (డిపాజిట్లు & ఆగిపోయే నగదు వివరాలు)
### 5. ✅ Before-You-Bid Checklist (టెండర్ వేసే ముందు తప్పనిసరి చెక్‌లిస్ట్)

TENDER DOCUMENT TEXT:
{pdf_text[:180000]}
"""
    candidate_models = [
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
    ]
    try:
        for m in client.models.list():
            name = getattr(m, "name", "").replace("models/", "")
            actions = getattr(m, "supported_actions", []) or []
            if (
                "flash" in name.lower()
                and "generateContent" in actions
                and name not in candidate_models
            ):
                candidate_models.append(name)
    except Exception:
        pass

    last_err: Optional[Exception] = None
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response.text:
                return response.text
        except Exception as exc:
            last_err = exc
            if "404" in str(exc) or "NOT_FOUND" in str(exc):
                continue
            raise

    raise RuntimeError(f"No working Gemini model found: {last_err}")


def background_worker(
    sb_url: str,
    sb_key: str,
    user_mobile: str,
    filename: str,
    pdf_bytes: bytes,
    current_credits: int,
    existing_history: List[Dict[str, Any]],
) -> None:
    worker_sb = create_client(sb_url, sb_key)
    try:
        raw_text = extract_pdf_text(pdf_bytes)
        report_md = run_gemini_analysis(raw_text)

        new_entry = {
            "filename": filename,
            "created_at": datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p"),
            "report": report_md,
        }
        updated_history = [new_entry] + existing_history[:14]

        worker_sb.table("contractors").update(
            {
                "credits": max(0, current_credits - 1),
                "history": updated_history,
                "job_status": "completed",
                "job_error": "",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq(MOBILE_COL, user_mobile).execute()
    except Exception as exc:
        err_msg = str(exc)[:100]
        worker_sb.table("contractors").update(
            {
                "job_status": "failed",
                "job_error": err_msg,
                "last_job_filename": f"{filename} (Error: {err_msg})",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq(MOBILE_COL, user_mobile).execute()


# 6. Upload & Background Analyze Section
st.subheader("📄 Upload Tender PDF")

if contractor.get("job_status") == "failed":
    st.error(
        f"Last scan failed: {contractor.get('last_job_filename', '')}. No credit was deducted."
    )

if credits <= 0:
    st.warning("You have 0 credits left. Recharge ₹999 for 15 Tender Analyses via WhatsApp.")
    wa_recharge = urllib.parse.quote(
        f"Hi PreBuild AI, I want to recharge ₹999 (15 credits) for mobile {mobile}."
    )
    st.link_button(
        "💳 Recharge ₹999 on WhatsApp",
        f"https://wa.me/?text={wa_recharge}",
        use_container_width=True,
    )
else:
    uploaded_file = st.file_uploader("Select Tender PDF", type=["pdf"])
    if uploaded_file is not None:
        if st.button(
            "🚀 Maximize Profit & Analyze Tender",
            type="primary",
            use_container_width=True,
        ):
            pdf_data = uploaded_file.read()
            update_job_status(supabase, mobile, "processing", uploaded_file.name)

            thread = threading.Thread(
                target=background_worker,
                args=(
                    get_secret("SUPABASE_URL"),
                    get_secret("SUPABASE_KEY"),
                    mobile,
                    uploaded_file.name,
                    pdf_data,
                    credits,
                    history,
                ),
                daemon=True,
            )
            thread.start()
            st.rerun()

# 7. Saved Cloud Reports + 1-Tap WhatsApp Sharing
if history:
    st.divider()
    st.subheader("📂 Saved Tender Reports (Cloud History)")

    report_titles = [
        f"{item.get('filename', 'Tender')} — {item.get('created_at', item.get('date', ''))}"
        for item in history
    ]
    selected_idx = st.selectbox(
        "Select Report",
        range(len(report_titles)),
        format_func=lambda i: report_titles[i],
    )
    selected_item = history[selected_idx]
    report_text = str(selected_item.get("report", ""))

    wa_summary = urllib.parse.quote(
        f"PreBuild AI Tender Report — {selected_item.get('filename', '')}\n\n"
        f"{report_text[:3200]}\n\n_Generated by PreBuild AI_"
    )
    st.link_button(
        "📲 Share Report on WhatsApp",
        f"https://wa.me/?text={wa_summary}",
        use_container_width=True,
    )
    st.download_button(
        "⬇️ Download Report (.txt)",
        data=report_text,
        file_name=f"PreBuild_Report_{selected_item.get('filename', 'tender')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

    st.markdown(report_text)