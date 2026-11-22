from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..ratelimit import limit
from ..security import (
    burn_password_check,
    check_password_strength,
    clear_session_cookie,
    current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)
from ..services import mailer
from ..services.accounts import consume_token, create_company, find_user, frontend_link, issue_token, normalize_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_SIGNUP = "Check your email for a link to verify your address and finish signing up."
GENERIC_FORGOT = "If an account exists for that email, a password reset link is on its way."


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str
    company_name: str = Field(min_length=1, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    token: str
    password: str


class MeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def me_payload(user: User) -> dict:
    companies = sorted(
        (
            {"id": m.company.id, "name": m.company.name, "role": m.role, "suspended": m.company.suspended_at is not None}
            for m in user.memberships
        ),
        key=lambda c: c["name"].lower(),
    )
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_platform_admin": user.is_platform_admin,
        "companies": companies,
    }


def _send_verification(db: Session, user: User) -> str | None:
    raw = issue_token(db, user, "verify_email")
    link = frontend_link(f"/verify-email?token={raw}")
    sent = mailer.send(
        user.email,
        "Verify your email for Pallet Builder",
        f"Hi {user.name or 'there'},\n\nConfirm your email address to finish setting up Pallet Builder:\n\n{link}\n\n"
        "If you didn't sign up, you can ignore this email.",
    )
    return mailer.link_for_response(sent, link)


@router.post("/signup", dependencies=[Depends(limit("signup", 10, 3600))])
def signup(body: SignupIn, db: Session = Depends(get_db)) -> dict:
    check_password_strength(body.password)
    email = normalize_email(body.email)
    existing = find_user(db, email)
    dev_link = None
    if existing is None:
        user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
        create_company(db, user, body.company_name)
        dev_link = _send_verification(db, user)
    elif existing.email_verified_at is None:
        dev_link = _send_verification(db, existing)
    else:
        mailer.send(
            existing.email,
            "Someone tried to sign up with your email",
            "Someone (hopefully you) tried to create a Pallet Builder account with this email, but you already "
            f"have one. Sign in at {frontend_link('/login')} or reset your password at "
            f"{frontend_link('/forgot-password')}.",
        )
    db.commit()
    return {"message": GENERIC_SIGNUP, "dev_link": dev_link}


@router.post("/resend-verification", dependencies=[Depends(limit("resend", 5, 900))])
def resend_verification(body: EmailIn, db: Session = Depends(get_db)) -> dict:
    user = find_user(db, body.email)
    dev_link = None
    if user is not None and user.email_verified_at is None:
        dev_link = _send_verification(db, user)
        db.commit()
    return {"message": GENERIC_SIGNUP, "dev_link": dev_link}


@router.post("/verify-email", dependencies=[Depends(limit("verify", 20, 900))])
def verify_email(body: TokenIn, response: Response, db: Session = Depends(get_db)) -> dict:
    user = consume_token(db, body.token, "verify_email")
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This verification link is invalid or has expired.")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    set_session_cookie(response, user)
    return me_payload(user)


@router.post("/login", dependencies=[Depends(limit("login", 10, 300))])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict:
    user = find_user(db, body.email)
    if user is None:
        burn_password_check(body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "email_unverified", "message": "Please verify your email before signing in."},
        )
    set_session_cookie(response, user)
    return me_payload(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user.token_version += 1
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return me_payload(user)


@router.put("/me")
def update_me(body: MeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user.name = body.name.strip()
    db.commit()
    return me_payload(user)


@router.put("/me/password")
def change_password(
    body: PasswordChange, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    check_password_strength(body.new_password)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # signs out every other session
    db.commit()
    set_session_cookie(response, user)
    return {"ok": True}


@router.post("/forgot-password", dependencies=[Depends(limit("forgot", 5, 900))])
def forgot_password(body: EmailIn, db: Session = Depends(get_db)) -> dict:
    user = find_user(db, body.email)
    dev_link = None
    if user is not None:
        raw = issue_token(db, user, "reset_password")
        link = frontend_link(f"/reset-password?token={raw}")
        sent = mailer.send(
            user.email,
            "Reset your Pallet Builder password",
            f"Reset your password here (the link works once and expires soon):\n\n{link}\n\n"
            "If you didn't ask for this, you can ignore this email.",
        )
        dev_link = mailer.link_for_response(sent, link)
        db.commit()
    return {"message": GENERIC_FORGOT, "dev_link": dev_link}


@router.post("/reset-password", dependencies=[Depends(limit("reset", 10, 900))])
def reset_password(body: ResetIn, response: Response, db: Session = Depends(get_db)) -> dict:
    check_password_strength(body.password)
    user = consume_token(db, body.token, "reset_password")
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")
    user.password_hash = hash_password(body.password)
    user.token_version += 1
    if user.email_verified_at is None:  # they proved they own the inbox
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    set_session_cookie(response, user)
    return me_payload(user)
