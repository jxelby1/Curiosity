from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_password_reset_token, hash_password, hash_password_reset_token
from app.db.models import PasswordResetToken, User


logger = logging.getLogger(__name__)


class PasswordResetService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create_reset_token(self, db: Session, *, user: User) -> tuple[str, str]:
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.settings.password_reset_token_ttl_minutes)

        db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )

        plain_token = generate_password_reset_token()
        token_hash = hash_password_reset_token(plain_token)

        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                used_at=None,
                created_at=now,
            )
        )
        db.commit()

        reset_link = f'{self.settings.password_reset_base_url}?token={plain_token}'
        logger.info('auth.password_reset_token_created user_id=%s expires_at=%s', user.id, expires_at.isoformat())
        if not self.settings.password_reset_send_email or self.settings.password_reset_debug_expose_token:
            logger.info('auth.password_reset_link user_id=%s link=%s', user.id, reset_link)
        return plain_token, reset_link

    def reset_password(self, db: Session, *, token: str, new_password: str) -> bool:
        token_hash = hash_password_reset_token(token)
        now = datetime.utcnow()

        reset_record = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
        if not reset_record:
            return False
        if reset_record.used_at is not None:
            return False
        if reset_record.expires_at <= now:
            reset_record.used_at = now
            db.commit()
            return False

        user = db.query(User).filter(User.id == reset_record.user_id).first()
        if not user:
            reset_record.used_at = now
            db.commit()
            return False

        user.hashed_password = hash_password(new_password)
        user.updated_at = now
        reset_record.used_at = now

        db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )

        db.commit()
        logger.info('auth.password_reset_complete user_id=%s', user.id)
        return True

    def debug_token_response(self, *, real_token: str | None = None) -> str | None:
        if not self.settings.password_reset_debug_expose_token:
            return None

        if real_token and self.settings.password_reset_allow_user_discovery:
            return real_token

        if real_token and not self.settings.password_reset_allow_user_discovery:
            return 'Token generated. Check backend logs for the reset link in local development.'

        # Provide a generic opaque value to avoid indicating account existence.
        return generate_password_reset_token()[:24]
