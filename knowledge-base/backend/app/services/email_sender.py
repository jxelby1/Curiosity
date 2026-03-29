from __future__ import annotations

import logging
from html import escape

import httpx

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


class ResendEmailSender:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send_password_reset_email(
        self,
        *,
        to_email: str,
        display_name: str,
        reset_link: str,
        expires_in_minutes: int,
    ) -> None:
        if not self.settings.password_reset_send_email:
            logger.info('auth.password_reset_email_skipped to=%s reason=email_disabled', to_email)
            return

        if self.settings.email_provider != 'resend':
            raise RuntimeError(f'Unsupported email provider: {self.settings.email_provider}')
        if not self.settings.resend_api_key:
            raise RuntimeError('RESEND_API_KEY is not configured.')
        if not self.settings.resend_from_email:
            raise RuntimeError('RESEND_FROM_EMAIL is not configured.')

        safe_name = escape(display_name.strip() or 'there')
        safe_link = escape(reset_link)
        subject = self.settings.password_reset_email_subject
        text_body = (
            f'Hi {display_name or "there"},\n\n'
            f'Use this link to reset your password:\n{reset_link}\n\n'
            f'This link expires in {expires_in_minutes} minutes.\n'
            'If you did not request this, you can ignore this email.'
        )
        html_body = (
            '<div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #111827;">'
            f'<h2 style="margin-bottom: 12px;">Hi {safe_name},</h2>'
            '<p style="line-height: 1.5;">We received a request to reset your password for Knowledge Base.</p>'
            f'<p style="line-height: 1.5;">This link expires in {expires_in_minutes} minutes.</p>'
            f'<p style="margin: 24px 0;">'
            f'<a href="{safe_link}" '
            'style="background:#111827;color:#ffffff;padding:10px 14px;border-radius:8px;'
            'text-decoration:none;display:inline-block;">Reset password</a>'
            '</p>'
            f'<p style="line-height: 1.5;">If the button does not work, copy this URL:</p>'
            f'<p style="word-break: break-all; line-height: 1.5;"><a href="{safe_link}">{safe_link}</a></p>'
            '<p style="line-height: 1.5; color:#6b7280;">If you did not request this, you can ignore this email.</p>'
            '</div>'
        )

        payload: dict[str, object] = {
            'from': self.settings.resend_from_email,
            'to': [to_email],
            'subject': subject,
            'text': text_body,
            'html': html_body,
        }
        if self.settings.resend_reply_to:
            payload['reply_to'] = self.settings.resend_reply_to

        response = httpx.post(
            f'{self.settings.resend_base_url.rstrip("/")}/emails',
            headers={
                'Authorization': f'Bearer {self.settings.resend_api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=15.0,
        )
        if response.status_code >= 400:
            logger.error(
                'auth.password_reset_email_failed to=%s status=%s body=%s',
                to_email,
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError('Failed to send password reset email.')

        message_id = response.json().get('id')
        logger.info('auth.password_reset_email_sent to=%s provider=resend message_id=%s', to_email, message_id)
