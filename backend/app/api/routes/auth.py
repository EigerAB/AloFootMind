import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
    get_current_user,
    get_current_user_optional,
)
from app.db.models import EmailVerificationCode, PasswordResetCode, User
from app.db.postgres import get_db
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
        expires_at=datetime.utcnow() + timedelta(minutes=5),
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
    if datetime.utcnow() > verification.expires_at:
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

    access_token = create_access_token(user.id, user.email, user.nickname)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "nickname": user.nickname,
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest):
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user_id = int(payload["sub"])
    # We don't hit the DB here for speed; just issue a new access token.
    # The user info will be filled from the old payload if available,
    # but for simplicity we return just the access token.
    # In a real app, you'd look up the user to get current email/nickname.
    access_token = create_access_token(user_id, "", "")
    return {"access_token": access_token}


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    # Client-side only: frontend clears tokens.
    # Server-side: optionally add token to a blocklist (Redis) for extra security.
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
        expires_at=datetime.utcnow() + timedelta(hours=1),
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
    if datetime.utcnow() > reset.expires_at:
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
    }
