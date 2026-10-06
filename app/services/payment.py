import importlib
import hashlib
import hmac
import razorpay

config_module = None

for _name in ("app.config", "config"):
    try:
        config_module = importlib.import_module(_name)
        break
    except ImportError:
        continue

if config_module is None:
    raise ImportError(
        "Could not import 'app.config' or 'config' module for settings"
    )

settings = config_module.settings

def razorpay_is_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID or "", settings.RAZORPAY_KEY_SECRET or "")) if razorpay_is_configured() else None


def _require_client():
    if client is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Razorpay env details not present")
    return client


def create_razorpay_order(amount: float, receipt: str):
    data = {
        "amount": int(round(amount * 100)),
        "currency": "INR",
        "receipt": receipt
    }

    return _require_client().order.create(data=data)


def fetch_razorpay_payment(payment_id: str):
    return _require_client().payment.fetch(payment_id)


def refund_razorpay_payment(payment_id: str, amount_paise: int, notes: dict | None = None):
    return _require_client().payment.refund(payment_id, data={"amount": amount_paise, "notes": notes or {}})


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not settings.RAZORPAY_KEY_SECRET:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Razorpay env details not present")
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
