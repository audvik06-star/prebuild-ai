import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from supabase import Client

MOBILE_COL = "mobile"  # Change to "phone" if your Supabase column is named "phone"
FREE_STARTER_CREDITS = 2


def is_valid_indian_mobile(mobile: str) -> bool:
    return bool(re.fullmatch(r"[6-9]\d{9}", mobile.strip()))


def is_valid_pin(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", pin.strip()))


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        salt, expected_hex = stored_hash.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


def auto_login_by_device(supabase: Client, device_id: str) -> Optional[dict[str, Any]]:
    if not device_id or len(device_id) < 10:
        return None
    res = (
        supabase.table("contractors")
        .select("*")
        .eq("active_device_id", device_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def login_or_register_contractor(
    supabase: Client,
    mobile: str,
    pin: str,
    device_id: str,
) -> Tuple[bool, str, Optional[dict[str, Any]]]:
    mobile = mobile.strip()
    pin = pin.strip()

    if not is_valid_indian_mobile(mobile):
        return False, "Enter a valid 10-digit Indian mobile number (starts with 6-9).", None
    if not is_valid_pin(pin):
        return False, "Enter a 4-digit numeric PIN.", None
    if not device_id:
        return False, "Open PreBuild AI from the official app icon so your phone can be verified.", None

    now_iso = datetime.now(timezone.utc).isoformat()
    res = supabase.table("contractors").select("*").eq(MOBILE_COL, mobile).limit(1).execute()

    # 1. New Contractor -> Create account & lock to this phone
    if not res.data:
        new_row = {
            MOBILE_COL: mobile,
            "credits": FREE_STARTER_CREDITS,
            "pin_hash": hash_pin(pin),
            "active_device_id": device_id,
            "job_status": "idle",
            "updated_at": now_iso,
        }
        inserted = supabase.table("contractors").insert(new_row).execute()
        return True, "Account created and locked to this mobile!", inserted.data[0]

    user = res.data[0]
    existing_device = user.get("active_device_id")
    existing_pin_hash = user.get("pin_hash")

    # 2. Enforce One-Mobile-One-Number Lock
    if existing_device and existing_device != device_id:
        return (
            False,
            "🔒 This mobile number is already locked to another phone (1 number = 1 mobile). "
            "Contact PreBuild AI support on WhatsApp to reset your device.",
            None,
        )

    # 3. Existing account created before PIN update -> Save PIN & lock phone now
    if not existing_pin_hash:
        updated = (
            supabase.table("contractors")
            .update({
                "pin_hash": hash_pin(pin),
                "active_device_id": device_id,
                "updated_at": now_iso,
            })
            .eq(MOBILE_COL, mobile)
            .execute()
        )
        return True, "PIN created and locked to this phone!", updated.data[0]

    # 4. Returning contractor on same phone -> Verify PIN
    if not verify_pin(pin, existing_pin_hash):
        return False, "Wrong 4-digit PIN. Please try again.", None

    if not existing_device:
        supabase.table("contractors").update({
            "active_device_id": device_id,
            "updated_at": now_iso,
        }).eq(MOBILE_COL, mobile).execute()

    return True, "Welcome back!", user


def update_job_status(
    supabase: Client,
    mobile: str,
    status: str,
    filename: Optional[str] = None,
) -> None:
    payload: dict[str, Any] = {
        "job_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if filename is not None:
        payload["last_job_filename"] = filename
    supabase.table("contractors").update(payload).eq(MOBILE_COL, mobile).execute()