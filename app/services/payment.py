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

client = razorpay.Client(
    auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET,
    )
)


def create_razorpay_order(amount: float, receipt: str):
    data = {
        "amount": int(amount * 100),
        "currency": "INR",
        "receipt": receipt
    }

    return client.order.create(data=data)


def fetch_razorpay_payment(payment_id: str):
    return client.payment.fetch(payment_id)


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
