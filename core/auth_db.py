import hashlib
import os
import time
from typing import Any, Optional

import httpx
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(override=True)


def get_config_value(key: str) -> str:
    """Read a secret from Streamlit Cloud Secrets first, then fallback to .env."""
    value = ""
    try:
        if key in st.secrets:
            value = str(st.secrets[key])
    except Exception:
        value = ""

    if not value:
        value = os.getenv(key, "")

    return value.strip().strip('"').strip("'")


def init_supabase() -> Client:
    """Initialize and validate the Supabase client."""
    url = get_config_value("SUPABASE_URL")
    key = get_config_value("SUPABASE_KEY")

    if not url or not url.startswith("https://") or ".supabase.co" not in url:
        raise ValueError(
            "Invalid or missing SUPABASE_URL. Expected format: https://<project-id>.supabase.co"
        )
    if not key:
        raise ValueError("Missing SUPABASE_KEY in Secrets or .env.")

    return create_client(url, key)


def hash_pin(mobile: str, pin: str) -> str:
    """Create a salted SHA-256 hash of the contractor's 4-digit PIN."""
    raw = f"{mobile.strip()}:{pin.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _execute_with_retry(query_fn, retries: int = 3, delay: float = 1.0) -> Any:
    """Execute a Supabase PostgREST call with automatic retry on transient network drops."""
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return query_fn()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise ConnectionError(
        "Unable to reach Supabase database. Verify SUPABASE_URL in Streamlit Secrets and confirm your Supabase project is Active (not paused)."
    ) from last_err


def auto_login_by_device(supabase: Client, device_id: str) -> Optional[dict[str, Any]]:
    """Return the contractor record if this device_id is already bound to a mobile number."""
    if not device_id:
        return None

    def _run():
        return (
            supabase.table("contractors")
            .select("*")
            .eq("active_device_id", device_id)
            .limit(1)
            .execute()
        )

    res = _execute_with_retry(_run)
    if res.data:
        return res.data[0]
    return None


def login_or_register_contractor(
    supabase: Client, mobile: str, pin: str, device_id: str
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Authenticate an existing contractor or register a new one, enforcing 1 number = 1 mobile."""
    clean_mobile = "".join(ch for ch in mobile if ch.isdigit())
    clean_pin = pin.strip()

    if len(clean_mobile) != 10:
        return False, "Please enter a valid 10-digit mobile number.", None
    if len(clean_pin) != 4 or not clean_pin.isdigit():
        return False, "Please enter a 4-digit numeric PIN.", None

    pin_digest = hash_pin(clean_mobile, clean_pin)

    def _fetch():
        return (
            supabase.table("contractors")
            .select("*")
            .eq("mobile", clean_mobile)
            .limit(1)
            .execute()
        )

    existing = _execute_with_retry(_fetch)

    if existing.data:
        user = existing.data[0]
        if user.get("pin_hash") != pin_digest:
            return False, "Incorrect 4-digit Secret PIN for this mobile number.", None

        bound_device = user.get("active_device_id") or ""
        if bound_device and bound_device != device_id:
            return (
                False,
                "This mobile number is already locked to another phone (1 number = 1 mobile). Contact PreBuild AI support on WhatsApp to reset your device.",
                None,
            )

        if not bound_device:
            def _bind():
                return (
                    supabase.table("contractors")
                    .update({"active_device_id": device_id})
                    .eq("mobile", clean_mobile)
                    .execute()
                )

            updated = _execute_with_retry(_bind)
            if updated.data:
                user = updated.data[0]

        return True, "Logged in successfully.", user

    new_record = {
        "mobile": clean_mobile,
        "pin_hash": pin_digest,
        "active_device_id": device_id,
        "credits": 1,
    }

    def _insert():
        return supabase.table("contractors").insert(new_record).execute()

    created = _execute_with_retry(_insert)
    user_data = created.data[0] if created.data else new_record
    return True, "Account registered and locked to this device.", user_data


def deduct_credit(supabase: Client, mobile: str, current_credits: int) -> int:
    """Deduct 1 scan credit only after a successful AI tender analysis."""
    new_credits = max(0, current_credits - 1)

    def _update():
        return (
            supabase.table("contractors")
            .update({"credits": new_credits})
            .eq("mobile", mobile)
            .execute()
        )

    _execute_with_retry(_update)
    return new_credits