import os
import hashlib
import secrets
import smtplib
import base64
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from email.message import EmailMessage

from dotenv import load_dotenv
from jose import jwt
from pwdlib import PasswordHash
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.customer import AccountToken
from config import settings

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)

password_hash = PasswordHash.recommended()


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
):
    return password_hash.verify(
        plain_password,
        hashed_password
    )


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def create_account_token(db: Session, user_id: int, purpose: str, minutes: int = 30) -> str:
    now = datetime.utcnow()
    db.query(AccountToken).filter(
        AccountToken.user_id == user_id,
        AccountToken.purpose == purpose,
        AccountToken.consumed_at.is_(None),
    ).update({AccountToken.consumed_at: now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    db.add(AccountToken(
        user_id=user_id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        purpose=purpose,
        expires_at=now + timedelta(minutes=minutes),
    ))
    return raw_token


def consume_account_token(db: Session, raw_token: str, purpose: str):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = db.query(AccountToken).filter(
        AccountToken.token_hash == token_hash,
        AccountToken.purpose == purpose,
        AccountToken.consumed_at.is_(None),
        AccountToken.expires_at > datetime.utcnow(),
    ).first()
    if not record:
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    record.consumed_at = datetime.utcnow()
    return record


def send_account_email(recipient: str, subject: str, body: str) -> None:
    if not email_delivery_is_configured():
        raise HTTPException(status_code=503, detail="Email env details not present")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.EMAIL_FROM
    message["To"] = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=502, detail="Email delivery failed; check SMTP env details") from exc


def email_delivery_is_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.EMAIL_FROM and (not settings.SMTP_USERNAME or settings.SMTP_PASSWORD))


def sms_delivery_is_configured() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER)


def send_account_sms(recipient: str, body: str) -> None:
    if not sms_delivery_is_configured():
        raise HTTPException(status_code=503, detail="Phone verification env details not present")
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    payload = urlencode({"To": recipient, "From": settings.TWILIO_FROM_NUMBER, "Body": body}).encode()
    credentials = base64.b64encode(f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()).decode()
    request = Request(endpoint, data=payload, headers={"Authorization": f"Basic {credentials}"})
    try:
        with urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise HTTPException(status_code=502, detail="SMS delivery failed; check Twilio env details")
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=502, detail="SMS delivery failed; check Twilio env details") from exc
