from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import (
    AuthForgotPasswordRequest,
    AuthForgotPasswordResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthResetPasswordRequest,
    AuthResetPasswordResponse,
    AuthTokenResponse,
    AuthUserResponse,
)
from app.services.email_sender import ResendEmailSender
from app.services.password_reset import PasswordResetService


router = APIRouter(prefix='/auth', tags=['auth'])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')
password_reset_service = PasswordResetService()
email_sender = ResendEmailSender()
settings = get_settings()


def user_has_dev_tools(user: User) -> bool:
    if not settings.enable_dev_unlocks:
        return False
    if user.subscription_tier in {'dev', 'admin'}:
        return True
    if user.email.lower() in settings.dev_unlock_email_list:
        return True
    prefs = user.preferences or {}
    if isinstance(prefs, dict) and bool(prefs.get('developer_mode') or prefs.get('dev_tools_enabled')):
        return True
    return False


def _user_to_response(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        onboarding_state=user.onboarding_state,
        subscription_tier=user.subscription_tier,
        dev_tools_enabled=user_has_dev_tools(user),
        xp=user.xp,
        level=user.level,
        preferences=user.preferences or {},
        current_goal_summary=user.current_goal_summary or '',
        created_at=user.created_at,
        updated_at=user.updated_at or user.created_at,
    )


def _authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user:
        return None
    if not user.hashed_password or not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Invalid authentication credentials.',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise unauthorized from exc

    subject = payload.get('sub')
    if not subject:
        raise unauthorized
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise unauthorized from exc

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post('/register', response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if existing:
        raise HTTPException(status_code=409, detail='An account with this email already exists.')

    now = datetime.utcnow()
    user = User(
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        onboarding_state='onboarding',
        subscription_tier='free',
        xp=0,
        level=1,
        preferences={},
        current_goal_summary='',
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id))
    return AuthTokenResponse(access_token=token)


@router.post('/login', response_model=AuthTokenResponse)
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    user = _authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail='Incorrect email or password.')
    token = create_access_token(str(user.id))
    return AuthTokenResponse(access_token=token)


@router.get('/me', response_model=AuthUserResponse)
def me(current_user: CurrentUser) -> AuthUserResponse:
    return _user_to_response(current_user)


@router.post('/logout')
def logout(_: CurrentUser) -> dict[str, str]:
    return {'status': 'ok'}


@router.post('/me/upgrade-dev', response_model=AuthUserResponse)
def upgrade_my_account_to_dev(current_user: CurrentUser, db: Session = Depends(get_db)) -> AuthUserResponse:
    if settings.environment.lower() == 'production':
        raise HTTPException(status_code=403, detail='Dev upgrade is disabled in production.')

    preferences = dict(current_user.preferences or {})
    preferences['developer_mode'] = True
    preferences['dev_tools_enabled'] = True
    current_user.preferences = preferences
    current_user.subscription_tier = 'dev'
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return _user_to_response(current_user)


@router.post('/forgot-password', response_model=AuthForgotPasswordResponse)
def forgot_password(payload: AuthForgotPasswordRequest, db: Session = Depends(get_db)) -> AuthForgotPasswordResponse:
    generic_message = 'If an account exists for this email, password reset instructions have been sent.'
    expose_debug_token = not password_reset_service.settings.password_reset_send_email
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user:
        return AuthForgotPasswordResponse(
            message=generic_message,
            debug_reset_token=password_reset_service.debug_token_response(real_token=None) if expose_debug_token else None,
        )

    token, reset_link = password_reset_service.create_reset_token(db, user=user)
    try:
        email_sender.send_password_reset_email(
            to_email=user.email,
            display_name=user.display_name,
            reset_link=reset_link,
            expires_in_minutes=password_reset_service.settings.password_reset_token_ttl_minutes,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Password reset email is currently unavailable. Try again after configuring email settings.',
        ) from exc

    return AuthForgotPasswordResponse(
        message=generic_message,
        debug_reset_token=password_reset_service.debug_token_response(real_token=token) if expose_debug_token else None,
    )


@router.post('/reset-password', response_model=AuthResetPasswordResponse)
def reset_password(payload: AuthResetPasswordRequest, db: Session = Depends(get_db)) -> AuthResetPasswordResponse:
    success = password_reset_service.reset_password(
        db,
        token=payload.token.strip(),
        new_password=payload.new_password,
    )
    if not success:
        raise HTTPException(status_code=400, detail='Invalid or expired reset token.')
    return AuthResetPasswordResponse(message='Your password has been reset successfully.')
