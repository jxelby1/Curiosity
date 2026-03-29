'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useState } from 'react';

import { resetPassword } from '@/lib/api';

const TOKEN_MAX = 256;
const PASSWORD_MAX = 120;

export default function ResetPasswordPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [token, setToken] = useState(searchParams.get('token') || '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token.trim()) {
      setError('Enter your reset token.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    setError('');
    setMessage('');

    try {
      const result = await resetPassword({ token: token.trim(), new_password: password });
      setMessage(result.message);
      setTimeout(() => router.push('/login'), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-xl p-6 md:p-10">
      <section className="panel p-6 md:p-8">
        <p className="badge mb-3">Password reset</p>
        <h1 className="text-3xl font-semibold">Create a new password</h1>
        <p className="muted mt-2 text-sm">Enter your reset token and choose a new password.</p>

        <form className="mt-6 space-y-3" onSubmit={onSubmit}>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Reset token</span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              type="text"
              maxLength={TOKEN_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Paste your reset token"
              required
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium">New password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              maxLength={PASSWORD_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="At least 8 characters"
              required
            />
          </label>

          <label className="block space-y-1">
            <span className="text-sm font-medium">Confirm password</span>
            <input
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              type="password"
              maxLength={PASSWORD_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Repeat your new password"
              required
            />
          </label>

          <button
            type="submit"
            className="w-full rounded-md bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            disabled={submitting}
          >
            {submitting ? 'Saving...' : 'Reset password'}
          </button>
        </form>

        <p className="mt-4 text-sm">
          Back to{' '}
          <Link href="/login" className="underline underline-offset-4">
            sign in
          </Link>
        </p>

        {message && <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
        {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </section>
    </main>
  );
}
