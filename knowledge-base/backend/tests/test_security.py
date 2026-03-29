from __future__ import annotations

import pytest

pytest.importorskip('jose')
pytest.importorskip('passlib')

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    password = 'strong-password-123'
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password('wrong-password', hashed)


def test_access_token_roundtrip() -> None:
    token = create_access_token('42', extra={'scope': 'test'})
    payload = decode_access_token(token)
    assert payload.get('sub') == '42'
    assert payload.get('scope') == 'test'
