from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import verify_password
from app.db.models import PasswordResetToken, User
from app.services.password_reset import PasswordResetService


def _session() -> Session:
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    PasswordResetToken.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_password_reset_token_created_and_used_once() -> None:
    db = _session()
    service = PasswordResetService()

    user = User(
        email='reset@example.com',
        hashed_password='pbkdf2_sha256$29000$dummy$dummy',
        display_name='Reset User',
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, _ = service.create_reset_token(db, user=user)
    assert token

    token_rows = db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).all()
    assert len(token_rows) == 1
    assert token_rows[0].used_at is None

    success = service.reset_password(db, token=token, new_password='newpassword123')
    assert success is True

    db.refresh(user)
    assert verify_password('newpassword123', user.hashed_password)

    second_use = service.reset_password(db, token=token, new_password='anotherpass123')
    assert second_use is False


def test_password_reset_token_expires() -> None:
    db = _session()
    service = PasswordResetService()

    user = User(
        email='expired@example.com',
        hashed_password='pbkdf2_sha256$29000$dummy$dummy',
        display_name='Expired User',
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token, _ = service.create_reset_token(db, user=user)
    row = db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).first()
    assert row is not None

    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    success = service.reset_password(db, token=token, new_password='newpassword123')
    assert success is False


def test_password_reset_token_rotation_invalidates_previous_token() -> None:
    db = _session()
    service = PasswordResetService()

    user = User(
        email='rotate@example.com',
        hashed_password='pbkdf2_sha256$29000$dummy$dummy',
        display_name='Rotate User',
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    first_token, _ = service.create_reset_token(db, user=user)
    second_token, _ = service.create_reset_token(db, user=user)
    assert first_token != second_token

    first_use = service.reset_password(db, token=first_token, new_password='newpassword123')
    assert first_use is False

    second_use = service.reset_password(db, token=second_token, new_password='newpassword123')
    assert second_use is True
