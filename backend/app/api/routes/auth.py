import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
    get_current_user,
    get_current_user_optional,
    revoke_refresh_token,
    is_refresh_token_revoked,
)
from app.db.models import EmailVerificationCode, PasswordResetCode, User
from app.db.postgres import get_db
from app.db.redis_client import get_redis
from app.services.email import send_password_reset_code, send_verification_code

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    nickname: str = Field(..., min_length=1, max_length=100)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict


def _generate_code() -> str:
    """Generate a 6-digit numeric code."""
    return f"{random.randint(0, 999999):06d}"


@router.post("/register")
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()

    if existing is not None and existing.is_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if existing is None:
        # Create unverified user
        user = User(
            email=body.email,
            nickname=body.nickname,
            password_hash=hash_password(body.password),
            is_verified=False,
        )
        session.add(user)
        await session.flush()
    else:
        # Unverified user exists — update info and resend code
        existing.nickname = body.nickname
        existing.password_hash = hash_password(body.password)
        user = existing

    # Invalidate previous codes for this email
    prev = await session.execute(
        select(EmailVerificationCode).where(
            EmailVerificationCode.email == body.email,
            EmailVerificationCode.used == False,
        )
    )
    for c in prev.scalars().all():
        c.used = True

    # Create new code
    code = _generate_code()
    verification = EmailVerificationCode(
        email=body.email,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session.add(verification)
    await session.commit()

    # Send email
    send_verification_code(body.email, code)

    return {"message": "Verification code sent"}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(EmailVerificationCode).where(
            EmailVerificationCode.email == body.email,
            EmailVerificationCode.code == body.code,
            EmailVerificationCode.used == False,
        )
    )
    verification = result.scalar_one_or_none()
    if verification is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    # Check expiry
    if datetime.now(timezone.utc) > verification.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code expired",
        )

    # Mark as used
    verification.used = True

    # Activate user
    user_result = await session.execute(
        select(User).where(User.email == body.email)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user.is_verified = True

    await session.commit()
    return {"message": "Email verified"}


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )

    # Block expired trial accounts
    if user.role == "trial" and user.trial_expires_at:
        if datetime.utcnow() > user.trial_expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trial account has expired",
            )

    # First login for trial: clone template data
    if user.role == "trial":
        await _clone_template_data_if_needed(session, user)

    access_token = create_access_token(user.id, user.email, user.nickname, user.role)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "nickname": user.nickname,
            "role": user.role,
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)):
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if await is_refresh_token_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )
    user_id = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not verified",
        )
    if user.role == "trial" and user.trial_expires_at:
        if datetime.utcnow() > user.trial_expires_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trial account has expired",
            )
    # Rotation: revoke old refresh token and issue a new one
    await revoke_refresh_token(body.refresh_token)
    access_token = create_access_token(user.id, user.email, user.nickname, user.role)
    new_refresh_token = create_refresh_token(user.id)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "user": {"id": user.id, "email": user.email, "nickname": user.nickname, "role": user.role},
    }


@router.post("/logout")
async def logout(body: LogoutRequest, user: User = Depends(get_current_user)):
    await revoke_refresh_token(body.refresh_token)
    return {"message": "Logged out"}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # Don't leak whether the email exists
        return {"message": "If the email exists, a reset code has been sent"}

    # Invalidate previous reset codes for this user
    prev = await session.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.used == False,
        )
    )
    for code in prev.scalars().all():
        code.used = True

    code = _generate_code()
    reset = PasswordResetCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(reset)
    await session.commit()

    send_password_reset_code(body.email, code)

    return {"message": "If the email exists, a reset code has been sent"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )

    code_result = await session.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.code == body.code,
            PasswordResetCode.used == False,
        )
    )
    reset = code_result.scalar_one_or_none()
    if reset is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    # Check expiry
    if datetime.now(timezone.utc) > reset.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code expired",
        )

    reset.used = True
    user.password_hash = hash_password(body.new_password)
    await session.commit()

    return {"message": "Password reset successful"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "role": user.role,
    }


@router.post("/guest-login")
async def guest_login(session: AsyncSession = Depends(get_db)):
    """Create a temporary guest user and return tokens."""
    email = f"guest-{uuid.uuid4().hex[:8]}@guest.local"
    user = User(
        email=email,
        nickname="Guest",
        password_hash=hash_password(uuid.uuid4().hex),
        is_verified=True,
        role="guest",
    )
    session.add(user)
    await session.flush()
    await session.commit()

    access_token = create_access_token(user.id, user.email, user.nickname, user.role)
    refresh_token = create_refresh_token(user.id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "nickname": user.nickname,
            "role": user.role,
        },
    }


class CreateTrialRequest(BaseModel):
    admin_secret: str = ""


@router.post("/create-trial")
async def create_trial(
    body: CreateTrialRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Create a trial user account with admin secret + IP-based rate limiting."""
    if body.admin_secret != settings.TRIAL_ADMIN_SECRET or not settings.TRIAL_ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin secret",
        )

    # Determine client IP
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    ip_key = f"trial:limit:{client_ip}"

    redis = await get_redis()
    count = int(await redis.get(ip_key) or 0)
    if count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trial account creation limit reached for this IP. Try again later.",
        )

    password = uuid.uuid4().hex[:12]
    email = f"trial-{uuid.uuid4().hex[:8]}@apollo.com"
    user = User(
        email=email,
        nickname="Trial User",
        password_hash=hash_password(password),
        is_verified=True,
        role="trial",
        trial_expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    session.add(user)
    await session.flush()
    await session.commit()

    # Increment IP counter
    await redis.incr(ip_key)
    await redis.expire(ip_key, 86400)

    return {
        "email": email,
        "password": password,
    }


@router.post("/unfreeze-trial")
async def unfreeze_trial(
    email: str,
    admin_secret: str,
    db: AsyncSession = Depends(get_db),
):
    """Unfreeze (renew) a trial account — script-only endpoint."""
    if admin_secret != settings.TRIAL_ADMIN_SECRET or not settings.TRIAL_ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin secret",
        )
    result = await db.execute(select(User).where(User.email == email, User.role == "trial"))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial user not found")
    user.trial_expires_at = datetime.utcnow() + timedelta(minutes=15)
    await db.commit()
    return {"message": "Trial account unfrozen", "trial_expires_at": user.trial_expires_at.isoformat()}


@router.delete("/delete-trial")
async def delete_trial(
    email: str,
    admin_secret: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a trial account and all associated data — script-only endpoint."""
    if admin_secret != settings.TRIAL_ADMIN_SECRET or not settings.TRIAL_ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin secret",
        )
    result = await db.execute(select(User).where(User.email == email, User.role == "trial"))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial user not found")

    uid = user.id
    # Cascade delete associated data
    await db.execute(text("DELETE FROM chat_sessions WHERE user_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM analysis_reports WHERE user_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM password_reset_codes WHERE user_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM email_verification_codes WHERE email = :email"), {"email": user.email})
    await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await db.commit()
    return {"message": "Trial account and associated data deleted"}


async def _template_user_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(User).where(User.email == settings.GUEST_TEMPLATE_EMAIL))
    u = result.scalar_one_or_none()
    return u.id if u else None


async def _clone_template_data_if_needed(db: AsyncSession, user: User) -> None:
    """Clone template user's chat_sessions and pre_match reports on first login."""
    # Check if user already has any data
    existing = await db.execute(
        text("SELECT COUNT(*) FROM chat_sessions WHERE user_id = :uid"),
        {"uid": user.id},
    )
    if existing.scalar_one() > 0:
        return

    template_uid = await _template_user_id(db)
    if template_uid is None:
        return

    # Clone chat_sessions
    sessions = await db.execute(
        text("SELECT name, messages, qa_meta FROM chat_sessions WHERE user_id = :uid"),
        {"uid": template_uid},
    )
    for row in sessions.mappings().all():
        await db.execute(
            text("""
                INSERT INTO chat_sessions (user_id, name, messages, qa_meta)
                VALUES (:uid, :name, :msgs, :qam)
            """),
            {
                "uid": user.id,
                "name": row["name"],
                "msgs": json.dumps(row["messages"]),
                "qam": json.dumps(row["qa_meta"]),
            },
        )

    # Clone pre_match analysis_reports
    reports = await db.execute(
        text("""
            SELECT match_id, report_type, home_team_id, away_team_id, report_markdown
            FROM analysis_reports
            WHERE user_id = :uid AND report_type = 'pre_match'
        """),
        {"uid": template_uid},
    )
    for row in reports.mappings().all():
        await db.execute(
            text("""
                INSERT INTO analysis_reports (match_id, report_type, home_team_id, away_team_id, report_markdown, user_id)
                VALUES (:mid, :rtype, :htid, :atid, :rmd, :uid)
            """),
            {
                "mid": row["match_id"],
                "rtype": row["report_type"],
                "htid": row["home_team_id"],
                "atid": row["away_team_id"],
                "rmd": row["report_markdown"],
                "uid": user.id,
            },
        )

    await db.commit()
