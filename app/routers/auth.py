from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token
)
from app.dependencies import get_current_user
from app.schemas.customer import AccountTokenRequest, PasswordReset, PasswordResetRequest
from app.services.auth import (
    create_account_token, consume_account_token, send_account_email, send_account_sms,
    email_delivery_is_configured, sms_delivery_is_configured,
)
from config import settings


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# -------------------------
# REGISTER
# -------------------------

@router.post("/register", response_model=UserResponse)
def register(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    new_user = User(
        name=user.name,
        email=user.email,
        password=hash_password(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# -------------------------
# LOGIN
# -------------------------

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # OAuth2 calls this field "username",
    # but we are using the email here.
    existing_user = db.query(User).filter(
        User.email == form_data.username
    ).first()

    if not existing_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not verify_password(
        form_data.password,
        existing_user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    token = create_access_token({
        "sub": str(existing_user.id),
        "token_version": existing_user.token_version,
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# -------------------------
# CURRENT USER
# -------------------------

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.token_version += 1
    db.commit()
    return {"message": "All active sessions have been logged out"}


@router.post("/verification/request", status_code=202)
def request_email_verification(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.email_verified:
        return {"message": "Email is already verified"}
    if not email_delivery_is_configured():
        raise HTTPException(status_code=503, detail="Email env details not present")
    raw_token = create_account_token(db, current_user.id, "EMAIL_VERIFY", minutes=60)
    verify_url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={raw_token}" if settings.FRONTEND_URL else raw_token
    send_account_email(current_user.email, "Verify your account", f"Verify your email using this link:\n{verify_url}")
    db.commit()
    return {"message": "Verification email sent"}


@router.post("/verification/confirm")
def confirm_email_verification(
    request: AccountTokenRequest,
    db: Session = Depends(get_db),
):
    token = consume_account_token(db, request.token, "EMAIL_VERIFY")
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    user.email_verified = True
    db.commit()
    return {"message": "Email verified"}


@router.post("/password/forgot", status_code=202)
def forgot_password(
    request: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    if not email_delivery_is_configured():
        raise HTTPException(status_code=503, detail="Email env details not present")
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        raw_token = create_account_token(db, user.id, "PASSWORD_RESET", minutes=30)
        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={raw_token}" if settings.FRONTEND_URL else raw_token
        send_account_email(user.email, "Reset your password", f"Reset your password using this link:\n{reset_url}")
        db.commit()
    return {"message": "If the account exists, password reset instructions were sent"}


@router.post("/password/reset")
def reset_password(request: PasswordReset, db: Session = Depends(get_db)):
    token = consume_account_token(db, request.token, "PASSWORD_RESET")
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    user.password = hash_password(request.new_password)
    user.token_version += 1
    db.commit()
    return {"message": "Password reset successfully"}


@router.post("/phone/verification/request", status_code=202)
def request_phone_verification(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.phone:
        raise HTTPException(status_code=400, detail="Add a phone number to your profile first")
    if not sms_delivery_is_configured():
        raise HTTPException(status_code=503, detail="Phone verification env details not present")
    raw_token = create_account_token(db, current_user.id, "PHONE_VERIFY", minutes=10)
    send_account_sms(current_user.phone, f"Your verification code is {raw_token}")
    db.commit()
    return {"message": "Verification code sent"}


@router.post("/phone/verification/confirm")
def confirm_phone_verification(request: AccountTokenRequest, db: Session = Depends(get_db)):
    token = consume_account_token(db, request.token, "PHONE_VERIFY")
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user or not user.phone:
        raise HTTPException(status_code=400, detail="Token is invalid or expired")
    user.phone_verified = True
    db.commit()
    return {"message": "Phone verified"}
