import urllib.parse
import uuid
import streamlit as st

from core.auth_db import (
    auto_login_by_device,
    deduct_credit,
    init_supabase,
    login_or_register_contractor,
)
from core.risk_engine import analyze_tender_pdf

st.set_page_config(
    page_title="PreBuild AI",
    page_icon="🏗️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #141519; color: #F4F4F6; }
    .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 680px; }
    .brand-title { font-size: 2rem; font-weight: 800; margin-bottom: 0.1rem; color: #FFFFFF; }
    .brand-sub { font-size: 0.95rem; color: #B0B3BC; margin-bottom: 1.4rem; }
    .stButton > button {
        width: 100%;
        background-color: #FF6B6B;
        color: #FFFFFF;
        font-weight: 700;
        border: none;
        border-radius: 10px;
        padding: 0.65rem 1rem;
    }
    .stButton > button:hover { background-color: #FF5252; color: #FFFFFF; }
    .whatsapp-btn {
        display: inline-block;
        width: 100%;
        text-align: center;
        background-color: #25D366;
        color: #111111 !important;
        font-weight: 700;
        padding: 0.7rem 1rem;
        border-radius: 10px;
        text-decoration: none;
        margin-top: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_or_create_device_id() -> str:
    """Persist a unique device_id in URL query params and session_state."""
    if "device_id" in st.session_state and st.session_state["device_id"]:
        return st.session_state["device_id"]

    qp_device = st.query_params.get("device_id", "")
    if isinstance(qp_device, list):
        qp_device = qp_device[0] if qp_device else ""

    if qp_device and len(qp_device) >= 8:
        st.session_state["device_id"] = qp_device
        return qp_device

    new_id = f"mob-{uuid.uuid4().hex[:12]}"
    st.session_state["device_id"] = new_id
    st.query_params["device_id"] = new_id
    return new_id


st.markdown('<div class="brand-title">🏗️ PreBuild AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="brand-sub">Construction Tender Profit & Risk Analyzer (English + తెలుగు)</div>',
    unsafe_allow_html=True,
)

try:
    supabase = init_supabase()
except Exception as cfg_err:
    st.error(f"Database Configuration Error: {cfg_err}")
    st.stop()

device_id = get_or_create_device_id()

if "user" not in st.session_state:
    st.session_state["user"] = None

if st.session_state["user"] is None:
    try:
        st.session_state["user"] = auto_login_by_device(supabase, device_id)
    except ConnectionError as conn_err:
        st.error(str(conn_err))
        st.info(
            "Tip: Check Streamlit Cloud → Settings → Secrets for SUPABASE_URL & SUPABASE_KEY, and make sure your Supabase project is not paused."
        )
        st.stop()

# --- LOGIN / REGISTER SCREEN ---
if st.session_state["user"] is None:
    st.subheader("🔒 Contractor Login / Register")
    st.caption(
        "First time? Type your 10-digit mobile number and create a 4-digit secret PIN. "
        "Your account locks to this phone (1 number = 1 mobile)."
    )

    with st.form("login_form"):
        mobile_input = st.text_input(
            "10-Digit Mobile Number",
            max_chars=10,
            placeholder="e.g. 9876543210",
        )
        pin_input = st.text_input(
            "4-Digit Secret PIN",
            type="password",
            max_chars=4,
            placeholder="••••",
        )
        submitted = st.form_submit_button("Enter PreBuild AI →")

    if submitted:
        try:
            ok, msg, user_obj = login_or_register_contractor(
                supabase, mobile_input, pin_input, device_id
            )
            if ok and user_obj:
                st.session_state["user"] = user_obj
                st.rerun()
            else:
                st.error(f"🔒 {msg}")
        except ConnectionError as conn_err:
            st.error(str(conn_err))

    st.stop()

# --- AUTHENTICATED CONTRACTOR DASHBOARD ---
user = st.session_state["user"]
mobile = user.get("mobile", "")
credits = int(user.get("credits", 0))

col1, col2, col3 = st.columns([2, 2, 1.3])
with col1:
    st.markdown(f"*📱 {mobile}*")
with col2:
    st.markdown(f"*🎟️ Credits: {credits}*")
with col3:
    if st.button("Lock"):
        st.session_state["user"] = None
        st.query_params.clear()
        st.rerun()

st.divider()
st.subheader("📄 Upload Tender PDF")

uploaded_pdf = st.file_uploader(
    "Select Tender PDF",
    type=["pdf"],
    help="Upload any government tender notice, NIT, or BOQ PDF (English or Telugu).",
)

if "last_report" not in st.session_state:
    st.session_state["last_report"] = ""
if "last_engine" not in st.session_state:
    st.session_state["last_engine"] = ""

if st.button("🚀 Maximize Profit & Analyse Tender"):
    if not uploaded_pdf:
        st.warning("Please select a Tender PDF file first.")
    elif credits <= 0:
        st.error(
            "You have 0 scan credits remaining. Contact PreBuild AI on WhatsApp to top up credits."
        )
    else:
        with st.spinner("Analyzing tender clauses, BOQ margins & risks..."):
            try:
                report_text, engine_name = analyze_tender_pdf(uploaded_pdf.getvalue())
                updated_credits = deduct_credit(supabase, mobile, credits)
                st.session_state["user"]["credits"] = updated_credits
                st.session_state["last_report"] = report_text
                st.session_state["last_engine"] = engine_name
                st.rerun()
            except Exception as scan_err:
                st.error(
                    f"Last scan failed: {uploaded_pdf.name} ({scan_err}) No credit was deducted."
                )

if st.session_state["last_report"]:
    st.success(f"Analysis Complete • Engine: {st.session_state['last_engine']}")
    st.markdown(st.session_state["last_report"])

    wa_summary = urllib.parse.quote(
        f"PreBuild AI Tender Report ({mobile})\n\n{st.session_state['last_report'][:1800]}"
    )
    st.markdown(
        f'<a class="whatsapp-btn" href="https://wa.me/?text={wa_summary}" target="_blank">📲 Share Report on WhatsApp</a>',
        unsafe_allow_html=True,
    )