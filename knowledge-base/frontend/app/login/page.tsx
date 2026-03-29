'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { PRODUCT_NAME } from '@/lib/brand';

const EMAIL_MAX = 255;
const PASSWORD_MAX = 120;

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, status } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await login({ email: email.trim(), password });
      const nextPath = searchParams.get('next');
      router.push(nextPath ? decodeURIComponent(nextPath) : '/topics');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.');
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return (
      <main className="mx-auto max-w-xl p-6 md:p-10">
        <section className="panel space-y-3 p-6">
          <div className="skeleton h-6 w-48" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-10 w-full" />
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl p-6 md:p-10">
      <section className="panel p-6 md:p-8">
        <p className="badge mb-3">{PRODUCT_NAME}</p>
        <h1 className="text-3xl">Welcome back</h1>
        <p className="muted mt-2 text-sm">Return to your active studies, notebook reflections, and next move.</p>

        <form className="mt-6 space-y-3" onSubmit={onSubmit}>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Email</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              maxLength={EMAIL_MAX}
              className="studio-input"
              placeholder="you@example.com"
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              maxLength={PASSWORD_MAX}
              className="studio-input"
              placeholder="Your password"
              required
            />
          </label>
          <div className="text-right text-sm">
            <Link href="/forgot-password" className="underline underline-offset-4">
              Forgot password?
            </Link>
          </div>
          <button
            type="submit"
            className="studio-button-primary w-full disabled:opacity-60"
            disabled={submitting}
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="mt-4 text-sm">
          New here?{' '}
          <Link href="/signup" className="underline underline-offset-4">
            Create an account
          </Link>
        </p>

        {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </section>
    </main>
  );
}
