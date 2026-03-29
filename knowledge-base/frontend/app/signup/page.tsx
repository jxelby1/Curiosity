'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useState } from 'react';

import { useAuth } from '@/components/auth-provider';

const NAME_MAX = 120;
const EMAIL_MAX = 255;
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 120;

export default function SignupPage() {
  const router = useRouter();
  const { register, status } = useAuth();

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password.length < PASSWORD_MIN) {
      setError(`Password must be at least ${PASSWORD_MIN} characters.`);
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await register({
        display_name: displayName.trim(),
        email: email.trim(),
        password
      });
      router.push('/topics');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-up failed.');
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
          <div className="skeleton h-10 w-full" />
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl p-6 md:p-10">
      <section className="panel p-6 md:p-8">
        <p className="badge mb-3">Create account</p>
        <h1 className="text-3xl font-semibold">Start learning with your profile</h1>
        <p className="muted mt-2 text-sm">
          Your topics, notes, assessments, and mastery progress are stored per authenticated account.
        </p>

        <form className="mt-6 space-y-3" onSubmit={onSubmit}>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Display name</span>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              maxLength={NAME_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Your name"
              required
            />
            <p className="text-right text-xs text-black/60">{displayName.length}/{NAME_MAX}</p>
          </label>

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

          <label className="block space-y-1">
            <span className="text-sm font-medium">Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              minLength={PASSWORD_MIN}
              maxLength={PASSWORD_MAX}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="At least 8 characters"
              required
            />
            <p className="text-right text-xs text-black/60">{password.length}/{PASSWORD_MAX}</p>
          </label>

          <button
            type="submit"
            className="w-full rounded-md bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            disabled={submitting}
          >
            {submitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="mt-4 text-sm">
          Already have an account?{' '}
          <Link href="/login" className="underline underline-offset-4">
            Sign in
          </Link>
        </p>

        {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      </section>
    </main>
  );
}
