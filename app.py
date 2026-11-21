import os
import json
import time
import threading
import urllib.parse
from datetime import datetime
import streamlit as st
import fitz  # PyMuPDF
from dotenv import load_dotenv
from core.risk_engine import detect_risks

load_dotenv()

# 1. Page Configuration
st.set_page_config(
    page_title="PreBuild AI | Contractor Profit & Risk Analyzer",
    page_icon="🏗️",
    layout="wide"
)

# 2. Cloud Database (Supabase) + Automatic Local Fallback
DB_FILE = "contractor_credits.json"

def get_secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            from supabase import create_client
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

sb = init_supabase()

def _load_local() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_local(data: dict) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user_record(mobile: str) -> dict:
    if sb:
        try:
            res = sb.table("contractors").select("*").eq("mobile", mobile).execute()
            if res.data:
                return res.data[0]
            new_row = {
                "mobile": mobile,
                "credits": 1,
                "plan": "Instant Free Trial (1 Tender)",
                "job_status": "idle",
                "job_file": "",
                "job_error": "",
                "history": []
            }
            sb.table("contractors").insert(new_row).execute()
            return new_row
        except Exception:
            pass

    db = _load_local()
    if mobile not in db:
        db[mobile] = {
            "mobile": mobile,
            "credits": 1,
            "plan": "Instant Free Trial (1 Tender)",
            "job_status": "idle",
            "job_file": "",
            "job_error": "",
            "history": []
        }
        _save_local(db)
    return db[mobile]

def update_user_record(mobile: str, fields: dict) -> None:
    if sb:
        try:
            sb.table("contractors").update(fields).eq("mobile", mobile).execute()
            return
        except Exception:
            pass

    db = _load_local()
    if mobile not in db:
        db[mobile] = {"mobile": mobile}
    db[mobile].update(fields)
    _save_local(db)

def is_code_used(code: str) -> bool:
    if sb:
        try:
            res = sb.table("used_codes").select("code").eq("code", code).execute()
            return len(res.data) > 0
        except Exception:
            pass
    db = _load_local()
    return code in db.get("_used_codes", [])

def mark_code_used(code: str, mobile: str) -> None:
    if sb:
        try:
            sb.table("used_codes").insert({"code": code, "used_by": mobile}).execute()
            return
        except Exception:
            pass
    db = _load_local()
    used = db.get("_used_codes", [])
    if code not in used:
        used.append(code)
    db["_used_codes"] = used
    _save_local(db)

# 3. Indian Mobile Number Validation & One-Time Unlock Codes
def is_valid_indian_mobile(num: str) -> bool:
    if len(num) != 10 or not num.isdigit():
        return False
    if num[0] not in ("6", "7", "8", "9"):
        return False
    if len(set(num)) <= 2:
        return False
    if num in ("9876543210", "6789012345", "9123456789"):
        return False
    return True

UNLOCK_CODES = {
    # WhatsApp-verified 2nd Free Trial Codes
    "FREE2-101": {"credits": 1, "plan": "WhatsApp Verified Bonus Trial (1 Tender)"},
    "FREE2-102": {"credits": 1, "plan": "WhatsApp Verified Bonus Trial (1 Tender)"},
    "FREE2-103": {"credits": 1, "plan": "WhatsApp Verified Bonus Trial (1 Tender)"},
    "FREE2-104": {"credits": 1, "plan": "WhatsApp Verified Bonus Trial (1 Tender)"},
    "FREE2-105": {"credits": 1, "plan": "WhatsApp Verified Bonus Trial (1 Tender)"},

    # ₹999/Month Pro Codes (15 Tenders)
    "KNR999-101": {"credits": 15, "plan": "Contractor Pro (₹999/Month - 15 Tenders)"},
    "KNR999-102": {"credits": 15, "plan": "Contractor Pro (₹999/Month - 15 Tenders)"},
    "KNR999-103": {"credits": 15, "plan": "Contractor Pro (₹999/Month - 15 Tenders)"},
    "KNR999-104": {"credits": 15, "plan": "Contractor Pro (₹999/Month - 15 Tenders)"},
    "KNR999-105": {"credits": 15, "plan": "Contractor Pro (₹999/Month - 15 Tenders)"},

    # ₹199 Single Pass Codes (1 Tender)
    "KNR199-201": {"credits": 1, "plan": "Single Tender Pass (₹199 - 1 Tender)"},
    "KNR199-202": {"credits": 1, "plan": "Single Tender Pass (₹199 - 1 Tender)"},

    # Founder Personal Demo Code
    "CHIDU2026": {"credits": 999, "plan": "Founder Unlimited Demo Access"},
}

# 4. Background Worker Thread (Continues Even If User Switches Apps on Mobile)
def run_background_analysis(mobile: str, pdf_bytes: bytes, file_name: str):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted_text = ""
        for page_num, page in enumerate(doc, start=1):
            extracted_text += f"\n--- Page {page_num} ---\n" + page.get_text()

        report = detect_risks(extracted_text, pdf_bytes=pdf_bytes)

        if report.startswith("❌"):
            update_user_record(mobile, {
                "job_status": "error",
                "job_error": report
            })
            return

        current_user = get_user_record(mobile)
        new_credits = max(0, int(current_user.get("credits", 1)) - 1)
        history = current_user.get("history") or []
        history.insert(0, {
            "file": file_name,
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "report": report
        })

        update_user_record(mobile, {
            "credits": new_credits,
            "job_status": "done",
            "job_error": "",
            "history": history[:15]  # Saves up to 15 tender reports in cloud history
        })
    except Exception as exc:
        update_user_record(mobile, {
            "job_status": "error",
            "job_error": f"❌ Analysis failed: {str(exc)}"
        })

# 5. Mobile-Responsive Blueprint UI Styling
st.markdown("""
    <style>
    .stApp {
        background-color: #0B1120;
        background-image: 
            radial-gradient(circle at 15% 15%, rgba(245, 158, 11, 0.08), transparent 40%),
            linear-gradient(rgba(56, 189, 248, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(56, 189, 248, 0.05) 1px, transparent 1px);
        background-size: 100% 100%, 36px 36px, 36px 36px;
        color: #F8FAFC;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    .block-container {
        padding-top: 3.2rem !important;
    }
    .hero-box {
        background: linear-gradient(135deg, #111827 0%, #1E293B 100%);
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-left: 6px solid #F59E0B;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 18px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
    }
    .hero-badge {
        display: inline-block;
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 4px 10px;
        border-radius: 6px;
        margin-bottom: 8px;
        text-transform: uppercase;
    }
    .hero-title {
        font-size: 26px;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0 0 6px 0;
    }
    .hero-subtitle {
        font-size: 14px;
        color: #CBD5E1;
        margin: 0;
    }
    [data-testid="stFileUploader"] {
        background-color: rgba(30, 41, 59, 0.75);
        border: 1px dashed #F59E0B;
        border-radius: 12px;
        padding: 14px;
    }
    .stButton > button {
        background: linear-gradient(90deg, #F59E0B 0%, #D97706 100%);
        color: #0B1120;
        font-weight: 700;
        font-size: 16px;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        width: 100%;
    }
    .report-card {
        background-color: rgba(15, 23, 42, 0.92);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    }
    .paywall-box {
        background: linear-gradient(135deg, #1E1B18 0%, #292018 100%);
        border: 1px solid #F59E0B;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    }
    .wa-btn {
        display: inline-block;
        background-color: #25D366;
        color: #0B1120 !important;
        font-weight: 700;
        padding: 11px 18px;
        border-radius: 8px;
        text-decoration: none;
        margin-top: 10px;
        margin-bottom: 12px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# 6. Header Banner
st.markdown("""
    <div class="hero-box">
        <div class="hero-badge">🏗️ Telangana Civil Tender Intelligence</div>
        <div class="hero-title">PreBuild AI — Profit & Risk Analyzer</div>
        <p class="hero-subtitle">
            Upload any government tender or contract PDF (English, Telugu, or Scanned) to uncover 
            hidden tax traps, unclaimed allowances, and profit-saving actions in <b>English & Telugu</b>.
        </p>
    </div>
""", unsafe_allow_html=True)

# 7. Contractor Mobile Number Input
col1, col2 = st.columns([2, 1])
with col1:
    mobile = st.text_input(
        "📱 Enter Contractor Mobile Number (10 digits) / కాంట్రాక్టర్ మొబైల్ నంబర్:",
        max_chars=10,
        placeholder="Enter 10-digit mobile number"
    ).strip()

if is_valid_indian_mobile(mobile):
    user_info = get_user_record(mobile)
    remaining = int(user_info.get("credits", 0))
    job_status = user_info.get("job_status", "idle")
    job_file = user_info.get("job_file", "")
    job_error = user_info.get("job_error", "")
    history = user_info.get("history") or []

    with col2:
        st.metric(label="🎟️ Credits Left", value=f"{remaining} Tenders")

    # 8. Background Job Status Banner (Auto-Polls Until Done)
    if job_status == "processing":
        st.info(f"⏳ *Analyzing {job_file} in the background...* You can safely switch apps; your report will be saved automatically when ready.")
        if st.button("🔄 Refresh Result Now"):
            st.rerun()
        time.sleep(3)
        st.rerun()

    elif job_status == "error" and job_error:
        st.error(job_error)
        update_user_record(mobile, {"job_status": "idle", "job_error": ""})

    # 9. Upload & Trigger Background Analysis (When Credits > 0 & Idle)
    elif remaining > 0:
        st.caption(f"Active Plan: *{user_info.get('plan', 'Free Trial')}* • Cloud Sync: *{'🟢 Active' if sb else '🟡 Local'}*")
        uploaded_file = st.file_uploader("Upload Tender / Contract PDF", type=["pdf"])

        if uploaded_file is not None:
            if st.button("🚀 Maximize Profit & Analyze Tender"):
                pdf_bytes = uploaded_file.read()
                file_name = uploaded_file.name
                update_user_record(mobile, {
                    "job_status": "processing",
                    "job_file": file_name,
                    "job_error": ""
                })
                worker = threading.Thread(
                    target=run_background_analysis,
                    args=(mobile, pdf_bytes, file_name),
                    daemon=True
                )
                worker.start()
                st.rerun()

    # 10. Cloud Report History + 1-Tap WhatsApp Share
    if history:
        st.markdown("### 📂 Saved Tender Reports (Cloud History)")
        selected_idx = st.selectbox(
            "Select a tender report:",
            range(len(history)),
            format_func=lambda i: f"{i + 1}. {history[i].get('file', 'Tender.pdf')} ({history[i].get('timestamp', '')})"
        )
        active_item = history[selected_idx]
        active_file = active_item.get("file", "Tender.pdf")
        active_report = active_item.get("report", "")

        st.markdown('<div class="report-card">', unsafe_allow_html=True)
        st.subheader(f"📊 Profit Protection Report ({active_file})")
        st.markdown(active_report)
        st.markdown('</div>', unsafe_allow_html=True)

        dl_col, wa_col = st.columns(2)
        with dl_col:
            st.download_button(
                label="📥 Download Full Report (.txt)",
                data=active_report,
                file_name=f"PreBuild_Report_{active_file}.txt",
                mime="text/plain"
            )
        with wa_col:
            wa_report_text = (
                f"🏗️ PreBuild AI Profit Report ({active_file})\n\n"
                f"{active_report[:1500]}\n\n"
                f"🔗 Analyze your tenders: https://prebuild-ai.streamlit.app"
            )
            encoded_report = urllib.parse.quote(wa_report_text)
            st.markdown(
                f'<a class="wa-btn" href="https://api.whatsapp.com/send?text={encoded_report}" target="_blank">📲 Share Report on WhatsApp</a>',
                unsafe_allow_html=True
            )

    # 11. Paywall + WhatsApp Verification Screen (Shown When Credits == 0)
    if remaining <= 0 and job_status != "processing":
        wa_message = f"Hi%20PreBuild%20AI,%20my%20mobile%20number%20is%20{mobile}.%20Please%20send%20my%20unlock%20code."
        wa_link = f"https://wa.me/918977744001?text={wa_message}"

        st.markdown(f"""
            <div class="paywall-box">
                <h3>🔒 Free Trial Completed — Unlock More Tender Reports</h3>
                <p>మీ ఉచిత టెండర్ రిపోర్ట్ పూర్తయింది. మరిన్ని ₹10 లక్షల కాంట్రాక్టుల లాభం మరియు ట్యాక్స్ వివరాల కోసం:</p>
                <ul>
                    <li><b>2nd Free Bonus Report:</b> Verify your real WhatsApp number below to get <b>1 more FREE report</b>.</li>
                    <li><b>Contractor Pro (₹999 / Month):</b> 15 Tender Analyses + Scanned Telugu PDF Support + Cloud History</li>
                    <li><b>Single Tender Pass (₹199):</b> 1 Tender Analysis Report</li>
                </ul>
                <p><b>Step 1:</b> Pay ₹999 (or ₹199) via PhonePe / GPay to <b>8977744001@ybl</b>, OR verify for your 2nd free report on WhatsApp:</p>
                <a class="wa-btn" href="{wa_link}" target="_blank">📲 Send Number on WhatsApp for Unlock Code</a>
                <p><b>Step 2:</b> Enter the 1-time Unlock Code you receive on WhatsApp below:</p>
            </div>
        """, unsafe_allow_html=True)

        code_col1, code_col2 = st.columns([2, 1])
        with code_col1:
            entered_code = st.text_input("🔑 Enter 1-Time Unlock Code:", placeholder="Enter code sent on WhatsApp").strip().upper()
        with code_col2:
            st.write("")
            st.write("")
            if st.button("✅ Activate Plan"):
                if entered_code != "CHIDU2026" and is_code_used(entered_code):
                    st.error("❌ This code was already used once. Contact us on WhatsApp for a new code.")
                elif entered_code in UNLOCK_CODES:
                    pack = UNLOCK_CODES[entered_code]
                    update_user_record(mobile, {
                        "credits": remaining + pack["credits"],
                        "plan": pack["plan"]
                    })
                    if entered_code != "CHIDU2026":
                        mark_code_used(entered_code, mobile)
                    st.success(f"🎉 Activated {pack['plan']}! Reloading...")
                    st.rerun()
                else:
                    st.error("❌ Invalid Unlock Code. Tap the green WhatsApp button above to get your code.")

elif mobile:
    st.error("❌ Please enter a real 10-digit Indian mobile number (starting with 6, 7, 8, or 9). Dummy numbers like 9999999999 are blocked.")
else:
    st.info("👆 Enter your real 10-digit mobile number above to start your *FREE Tender Profit Report*.")