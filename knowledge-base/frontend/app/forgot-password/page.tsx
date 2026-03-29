'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';

import { forgotPassword } from '@/lib/api';

const EMAIL_MAX = 255;

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [debugToken, setDebugToken] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) {
      setError('Enter your email address.');
      return;
    }

    setSubmitting(true);
    setError('');
    setMessage('');
    setDebugToken(null);

    try {
      const result = await forgotPassword(email.trim());
      setMessage(result.message);
      if (result.debug_reset_token) {
        setDebugToken(result.debug_reset_token);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not process your request right now.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-xl p-6 md:p-10">
      <section className="panel p-6 md:p-8">
        <p className="badge mb-3">Password reset</p>
        <h1 className="text-3xl font-semibold">Reset your password</h1>
        <p className="muted mt-2 text-sm">Enter your email and we will help you set a new password.</p>

        <form className="mt-6 space-y-3" onSubmit={onSubmit}>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Email</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              maxLength={EMAIL_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="you@example.com"
              required
            />
          </label>

          <button
            type="submit"
            className="w-full rounded-md bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            disabled={submitting}
          >
            {submitting ? 'Sending...' : 'Send reset instructions'}
          </button>
        </form>

        <p className="mt-4 text-sm">
          Back to{' '}
          <Link href="/login" className="underline underline-offset-4">
            sign in
          </Link>
        </p>

        {message && <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
        {debugToken && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-semibold">Development token</p>
            <p className="mt-1 break-all font-mono text-xs">{debugToken}</p>
            <p className="mt-2 text-xs">Use this on the reset password page in local development.</p>
          </div>
        )}
        {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </section>
    </main>
  );
}
