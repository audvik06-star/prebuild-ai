import os
import json
import streamlit as st
import fitz  # PyMuPDF
from core.risk_engine import detect_risks

# 1. Page Configuration
st.set_page_config(
    page_title="PreBuild AI | Contractor Profit & Risk Analyzer",
    page_icon="🏗️",
    layout="wide"
)

# 2. Credit & Used-Code Tracker
DB_FILE = "contractor_credits.json"

def load_credits():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_credits(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Validate Real Indian Mobile Numbers (Blocks 9999999999, 1234567890, etc.)
def is_valid_indian_mobile(num: str) -> bool:
    if len(num) != 10 or not num.isdigit():
        return False
    if num[0] not in ("6", "7", "8", "9"):
        return False
    if len(set(num)) <= 2:  # Blocks 9999999999, 9898989898, etc.
        return False
    if num in ("9876543210", "6789012345", "9123456789"):
        return False
    return True

# One-Time Unlock Codes (Each code works ONLY ONCE)
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

    # Your Personal Founder Demo Code (Reusable only by you)
    "CHIDU2026": {"credits": 999, "plan": "Founder Unlimited Demo Access"},
}

# 3. Architectural Blueprint Background & Construction UI Styling
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
    .hero-box {
        background: linear-gradient(135deg, #111827 0%, #1E293B 100%);
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-left: 6px solid #F59E0B;
        border-radius: 12px;
        padding: 22px 26px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
    }
    .hero-badge {
        display: inline-block;
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 4px 10px;
        border-radius: 6px;
        margin-bottom: 8px;
        text-transform: uppercase;
    }
    .hero-title {
        font-size: 30px;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0 0 6px 0;
    }
    .hero-subtitle {
        font-size: 15px;
        color: #CBD5E1;
        margin: 0;
    }
    [data-testid="stFileUploader"] {
        background-color: rgba(30, 41, 59, 0.75);
        border: 1px dashed #F59E0B;
        border-radius: 12px;
        padding: 16px;
    }
    .stButton > button {
        background: linear-gradient(90deg, #F59E0B 0%, #D97706 100%);
        color: #0B1120;
        font-weight: 700;
        font-size: 16px;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #FBBF24 0%, #F59E0B 100%);
        color: #0B1120;
        transform: translateY(-1px);
    }
    .report-card {
        background-color: rgba(15, 23, 42, 0.9);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px;
        margin-top: 16px;
    }
    .paywall-box {
        background: linear-gradient(135deg, #1E1B18 0%, #292018 100%);
        border: 1px solid #F59E0B;
        border-radius: 12px;
        padding: 22px;
        margin-top: 16px;
    }
    .wa-btn {
        display: inline-block;
        background-color: #25D366;
        color: #0B1120 !important;
        font-weight: 700;
        padding: 10px 18px;
        border-radius: 8px;
        text-decoration: none;
        margin-top: 8px;
        margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# 4. Header Banner
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

# 5. Contractor Mobile Number & Credit Check
credits_db = load_credits()

col1, col2 = st.columns([2, 1])
with col1:
    mobile = st.text_input(
        "📱 Enter Contractor Mobile Number (10 digits) / కాంట్రాక్టర్ మొబైల్ నంబర్:",
        max_chars=10,
        placeholder="Enter 10-digit mobile number"
    ).strip()

if is_valid_indian_mobile(mobile):
    # New real number starts with 1 Instant Free Trial (2nd free trial unlocked via WhatsApp SIM check)
    if mobile not in credits_db:
        credits_db[mobile] = {"credits": 1, "plan": "Instant Free Trial (1 Tender)"}
        save_credits(credits_db)

    user_info = credits_db[mobile]
    remaining = user_info["credits"]

    with col2:
        st.metric(label="🎟️ Credits Left", value=f"{remaining} Tenders")

    # 6. If Contractor Has Credits -> Show Upload & Analyze
    if remaining > 0:
        st.caption(f"Active Plan: *{user_info['plan']}*")
        uploaded_file = st.file_uploader("Upload Tender / Contract PDF", type=["pdf"])

        if uploaded_file is not None:
            if st.button("🚀 Maximize Profit & Analyze Tender"):
                with st.spinner("Reading English/Telugu clauses and calculating profit traps..."):
                    pdf_bytes = uploaded_file.read()
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    extracted_text = ""
                    for page_num, page in enumerate(doc, start=1):
                        extracted_text += f"\n--- Page {page_num} ---\n" + page.get_text()

                    report = detect_risks(extracted_text, pdf_bytes=pdf_bytes)

                    if not report.startswith("❌"):
                        credits_db[mobile]["credits"] -= 1
                        save_credits(credits_db)

                    st.markdown('<div class="report-card">', unsafe_allow_html=True)
                    st.subheader("📊 Contractor Profit Protection Report")
                    st.markdown(report)
                    st.markdown('</div>', unsafe_allow_html=True)

                    st.download_button(
                        label="📥 Download Profit Report (.txt)",
                        data=report,
                        file_name=f"PreBuild_Report_{uploaded_file.name}.txt",
                        mime="text/plain"
                    )

    # 7. Paywall + WhatsApp Verification Screen
    else:
        wa_message = f"Hi%20PreBuild%20AI,%20my%20mobile%20number%20is%20{mobile}.%20Please%20send%20my%20unlock%20code."
        wa_link = f"https://wa.me/918977744001?text={wa_message}"

        st.markdown(f"""
            <div class="paywall-box">
                <h3>🔒 Free Trial Completed — Unlock More Tender Reports</h3>
                <p>మీ ఉచిత టెండర్ రిపోర్ట్ పూర్తయింది. మరిన్ని ₹10 లక్షల కాంట్రాక్టుల లాభం మరియు ట్యాక్స్ వివరాల కోసం:</p>
                <ul>
                    <li><b>2nd Free Bonus Report:</b> Verify your real WhatsApp number below to get <b>1 more FREE report</b>.</li>
                    <li><b>Contractor Pro (₹999 / Month):</b> 15 Tender Analyses + Scanned Telugu PDF Support + WhatsApp Reports</li>
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
                used_codes = credits_db.get("_used_codes", [])

                if entered_code in used_codes and entered_code != "CHIDU2026":
                    st.error("❌ This code was already used once. Contact us on WhatsApp for a new code.")
                elif entered_code in UNLOCK_CODES:
                    pack = UNLOCK_CODES[entered_code]
                    credits_db[mobile]["credits"] += pack["credits"]
                    credits_db[mobile]["plan"] = pack["plan"]

                    if entered_code != "CHIDU2026":
                        used_codes.append(entered_code)
                        credits_db["_used_codes"] = used_codes

                    save_credits(credits_db)
                    st.success(f"🎉 Activated {pack['plan']}! Reloading...")
                    st.rerun()
                else:
                    st.error("❌ Invalid Unlock Code. Tap the green WhatsApp button above to get your code.")

elif mobile:
    st.error("❌ Please enter a real 10-digit Indian mobile number (starting with 6, 7, 8, or 9). Dummy numbers like 9999999999 are blocked.")
else:
    st.info("👆 Enter your real 10-digit mobile number above to start your *FREE Tender Profit Report*.")