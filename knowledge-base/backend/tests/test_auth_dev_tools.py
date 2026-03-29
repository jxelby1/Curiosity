from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.auth import upgrade_my_account_to_dev, user_has_dev_tools
from app.db.models import User


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_user_has_dev_tools_enabled_for_dev_tier() -> None:
    user = User(email='dev@example.com', hashed_password='x', display_name='Dev', subscription_tier='dev')
    assert user_has_dev_tools(user) is True


def test_upgrade_my_account_to_dev_marks_preferences_and_subscription() -> None:
    db = _session()
    user = User(email='learner@example.com', hashed_password='x', display_name='Learner', subscription_tier='free')
    db.add(user)
    db.commit()
    db.refresh(user)

    response = upgrade_my_account_to_dev(current_user=user, db=db)

    assert response.subscription_tier == 'dev'
    assert response.dev_tools_enabled is True
    assert response.preferences.get('developer_mode') is True
    assert response.preferences.get('dev_tools_enabled') is True


def test_upgrade_my_account_to_dev_blocked_in_production() -> None:
    db = _session()
    user = User(email='learner@example.com', hashed_password='x', display_name='Learner', subscription_tier='free')
    db.add(user)
    db.commit()
    db.refresh(user)

    with patch('app.api.auth.settings.environment', 'production'):
        try:
            upgrade_my_account_to_dev(current_user=user, db=db)
            assert False, 'Expected production guardrail'
        except HTTPException as exc:
            assert exc.status_code == 403
