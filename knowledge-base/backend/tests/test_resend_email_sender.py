from __future__ import annotations

import types

import pytest

from app.core.config import Settings
from app.services.email_sender import ResendEmailSender


def _settings(**overrides: object) -> Settings:
    base = {
        'password_reset_send_email': True,
        'email_provider': 'resend',
        'resend_api_key': 're_test_key',
        'resend_from_email': 'Knowledge Base <no-reply@example.com>',
        'resend_base_url': 'https://api.resend.com',
        'resend_reply_to': '',
        'password_reset_email_subject': 'Reset your Knowledge Base password',
    }
    base.update(overrides)
    return Settings.model_validate(base)


def test_resend_sender_skips_when_email_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(password_reset_send_email=False)
    sender = ResendEmailSender(settings=settings)

    called = {'value': False}

    def _fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        called['value'] = True
        return types.SimpleNamespace(status_code=200, json=lambda: {'id': 'x'}, text='')

    monkeypatch.setattr('app.services.email_sender.httpx.post', _fake_post)

    sender.send_password_reset_email(
        to_email='user@example.com',
        display_name='User',
        reset_link='http://localhost:3000/reset-password?token=abc',
        expires_in_minutes=30,
    )
    assert called['value'] is False


def test_resend_sender_raises_when_key_missing() -> None:
    settings = _settings(resend_api_key='')
    sender = ResendEmailSender(settings=settings)

    with pytest.raises(RuntimeError, match='RESEND_API_KEY'):
        sender.send_password_reset_email(
            to_email='user@example.com',
            display_name='User',
            reset_link='http://localhost:3000/reset-password?token=abc',
            expires_in_minutes=30,
        )


def test_resend_sender_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(resend_reply_to='support@example.com')
    sender = ResendEmailSender(settings=settings)

    captured: dict[str, object] = {}

    def _fake_post(url, *, headers, json, timeout):  # type: ignore[no-untyped-def]
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        captured['timeout'] = timeout
        return types.SimpleNamespace(status_code=200, json=lambda: {'id': 'email_123'}, text='')

    monkeypatch.setattr('app.services.email_sender.httpx.post', _fake_post)

    sender.send_password_reset_email(
        to_email='learner@example.com',
        display_name='Learner',
        reset_link='http://localhost:3000/reset-password?token=abc',
        expires_in_minutes=30,
    )

    assert captured['url'] == 'https://api.resend.com/emails'
    payload = captured['json']
    assert isinstance(payload, dict)
    assert payload['to'] == ['learner@example.com']
    assert payload['reply_to'] == 'support@example.com'
