import importlib
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