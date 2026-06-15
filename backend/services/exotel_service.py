"""
THOOKU MADURAI — Exotel Service
Handles: OTP SMS, Voice Call OTP, Masked Calls (customer ↔ rider)
"""
import os
import random
import string
import requests
from requests.auth import HTTPBasicAuth
import logging

logger = logging.getLogger(__name__)

# ── Exotel Credentials ────────────────────────────────────────────────────────
EXOTEL_SID    = os.environ.get("EXOTEL_SID", "")
EXOTEL_KEY    = os.environ.get("EXOTEL_API_KEY", os.environ.get("EXOTEL_API_TOKEN", ""))
EXOTEL_TOKEN  = os.environ.get("EXOTEL_TOKEN", "")
EXOTEL_PHONE  = os.environ.get("EXOTEL_PHONE", "")

BASE_URL = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}" if EXOTEL_SID else ""
AUTH     = HTTPBasicAuth(EXOTEL_KEY, EXOTEL_TOKEN) if EXOTEL_KEY and EXOTEL_TOKEN else None
HEADERS  = {"Content-Type": "application/x-www-form-urlencoded"}


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


def _normalize_phone(phone: str) -> str:
    """Ensure phone is in 0XXXXXXXXXX format for Exotel."""
    phone = str(phone).strip().replace(" ", "").replace("-", "")
    if phone.startswith("+91"):
        phone = "0" + phone[3:]
    elif phone.startswith("91") and len(phone) == 12:
        phone = "0" + phone[2:]
    elif len(phone) == 10:
        phone = "0" + phone
    return phone


# ── OTP via SMS ───────────────────────────────────────────────────────────────
def send_otp_sms(phone: str, otp: str) -> dict:
    """
    Send OTP via Exotel SMS.
    Returns: { "success": bool, "message": str, "sid": str|None }
    """
    if not EXOTEL_SID or not AUTH or not EXOTEL_PHONE:
        return {"success": False, "message": "Exotel not configured"}
    to = _normalize_phone(phone)
    message = f"Your Thooku Madurai OTP is: {otp}. Valid for 5 minutes. Do not share this OTP with anyone."

    try:
        resp = requests.post(
            f"{BASE_URL}/Sms/send",
            auth=AUTH,
            headers=HEADERS,
            data={
                "From":   EXOTEL_PHONE,
                "To":     to,
                "Body":   message,
                "DltTemplateId": "1007161112012345678",  # Update with DLT registered template ID
            },
            timeout=10,
        )
        logger.info("Exotel SMS response [%s]: %s", resp.status_code, resp.text[:200])

        if resp.status_code in (200, 201):
            data = resp.json()
            sms_data = data.get("SMSMessage", {})
            return {
                "success": True,
                "message": "OTP sent successfully",
                "sid": sms_data.get("Sid"),
            }
        else:
            logger.error("Exotel SMS failed: %s %s", resp.status_code, resp.text)
            return {"success": False, "message": f"SMS gateway error: {resp.status_code}"}

    except requests.exceptions.Timeout:
        logger.error("Exotel SMS timeout for %s", phone)
        return {"success": False, "message": "SMS gateway timeout. Try again."}
    except Exception as e:
        logger.error("Exotel SMS exception: %s", str(e))
        return {"success": False, "message": "Failed to send OTP. Try again."}


# ── OTP via Voice Call (fallback) ─────────────────────────────────────────────
def send_otp_call(phone: str, otp: str) -> dict:
    """
    Make a text-to-speech call that reads the OTP aloud.
    Uses Exotel TTS passthru.
    """
    to = _normalize_phone(phone)
    spoken_otp = " ".join(list(otp))  # "1 2 3 4 5 6"

    try:
        resp = requests.post(
            f"{BASE_URL}/Calls/connect.json",
            auth=AUTH,
            headers=HEADERS,
            data={
                "From":     EXOTEL_PHONE,
                "To":       to,
                "CallerId": EXOTEL_PHONE,
                "Url":      f"http://my.exotel.com/{EXOTEL_SID}/exoml/start/tts?text=Your+Thooku+Madurai+OTP+is+{spoken_otp}+Your+OTP+is+{spoken_otp}",
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            call = data.get("Call", {})
            return {
                "success": True,
                "message": "OTP call initiated",
                "call_sid": call.get("Sid"),
            }
        else:
            logger.error("Exotel Voice OTP failed: %s", resp.text)
            return {"success": False, "message": "Voice call failed"}
    except Exception as e:
        logger.error("Exotel Voice OTP exception: %s", str(e))
        return {"success": False, "message": str(e)}


# ── Masked Call (Customer ↔ Rider, like Swiggy) ───────────────────────────────
def initiate_masked_call(caller_phone: str, callee_phone: str, call_type: str = "customer_to_rider") -> dict:
    if not EXOTEL_SID or not AUTH or not EXOTEL_PHONE:
        return {"success": False, "message": "Exotel not configured"}
    """
    Bridges a call between two parties via virtual number.
    Neither party sees the other's real number.
    
    Flow:
      1. Exotel calls `caller_phone` from EXOTEL_PHONE
      2. Once caller picks up, Exotel bridges to `callee_phone`
      3. Callee sees EXOTEL_PHONE as caller ID
    
    Args:
        caller_phone: Phone that initiates (customer or rider)
        callee_phone: Phone to bridge to (rider or restaurant)
        call_type: "customer_to_rider" | "rider_to_restaurant" | "admin_to_any"
    """
    from_number = _normalize_phone(caller_phone)
    to_number   = _normalize_phone(callee_phone)

    try:
        resp = requests.post(
            f"{BASE_URL}/Calls/connect.json",
            auth=AUTH,
            headers=HEADERS,
            data={
                "From":              from_number,
                "To":                to_number,
                "CallerId":          EXOTEL_PHONE,
                "TimeLimit":         300,          # 5-min call limit
                "TimeOut":           30,           # Ring for 30s
                "Record":            "true",       # Record for dispute resolution
                "RecordingChannels": "dual",
            },
            timeout=15,
        )
        logger.info("Masked call [%s → %s] response %s: %s",
                    caller_phone[-4:], callee_phone[-4:], resp.status_code, resp.text[:200])

        if resp.status_code in (200, 201):
            data = resp.json()
            call = data.get("Call", {})
            return {
                "success":  True,
                "call_sid": call.get("Sid"),
                "status":   call.get("Status"),
                "virtual_number": EXOTEL_PHONE,
                "message":  "Call initiated. Connecting...",
            }
        else:
            logger.error("Masked call failed: %s %s", resp.status_code, resp.text)
            return {"success": False, "message": f"Call failed: {resp.status_code}"}

    except requests.exceptions.Timeout:
        return {"success": False, "message": "Call gateway timeout. Try again."}
    except Exception as e:
        logger.error("Masked call exception: %s", str(e))
        return {"success": False, "message": str(e)}


# ── Get Call Status ───────────────────────────────────────────────────────────
def get_call_status(call_sid: str) -> dict:
    """Poll the status of a call by its SID."""
    try:
        resp = requests.get(
            f"{BASE_URL}/Calls/{call_sid}.json",
            auth=AUTH,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            call = data.get("Call", {})
            return {
                "success":        True,
                "status":         call.get("Status"),
                "duration":       call.get("Duration"),
                "recording_url":  call.get("RecordingUrl"),
            }
        return {"success": False, "message": "Call not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── SMS Notification ──────────────────────────────────────────────────────────
def send_sms_notification(phone: str, message: str) -> dict:
    """Generic SMS notification (order updates, alerts)."""
    to = _normalize_phone(phone)
    try:
        resp = requests.post(
            f"{BASE_URL}/Sms/send",
            auth=AUTH,
            headers=HEADERS,
            data={"From": EXOTEL_PHONE, "To": to, "Body": message},
            timeout=10,
        )
        return {"success": resp.status_code in (200, 201)}
    except Exception as e:
        logger.error("SMS notification failed: %s", str(e))
        return {"success": False}


def notify_order_placed(customer_phone: str, order_id: str, restaurant: str, amount: int) -> None:
    """Notify customer when order is placed."""
    msg = (f"Order {order_id} placed at {restaurant}! "
           f"Total: Rs.{amount} (incl. delivery & platform fee). "
           f"Track: thookumadurai.in - Thooku Madurai")
    send_sms_notification(customer_phone, msg)


def notify_order_accepted(customer_phone: str, order_id: str, restaurant: str) -> None:
    """Notify customer when restaurant accepts."""
    msg = f"Your order {order_id} is being prepared at {restaurant}. We'll notify you when it's on the way! - Thooku Madurai"
    send_sms_notification(customer_phone, msg)


def notify_rider_assigned(customer_phone: str, rider_name: str, vehicle: str) -> None:
    """Notify customer when rider is assigned."""
    msg = (f"Your delivery partner {rider_name} ({vehicle}) is on the way! "
           f"Call via: {EXOTEL_PHONE} - Thooku Madurai")
    send_sms_notification(customer_phone, msg)


def notify_delivered(customer_phone: str, order_id: str) -> None:
    """Notify customer on delivery."""
    msg = f"Order {order_id} delivered! Rate your experience at thookumadurai.in. Thank you! - Thooku Madurai"
    send_sms_notification(customer_phone, msg)
