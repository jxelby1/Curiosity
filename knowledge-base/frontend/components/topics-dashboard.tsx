'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useEffect, useState } from 'react';

import { createTopicAndInitialize, listTopics } from '@/lib/api';
import { Topic } from '@/lib/types';

const TOPIC_NAME_MAX = 120;
const TOPIC_DESC_MAX = 500;
const TOPIC_GOAL_MAX = 500;

export function TopicsDashboard() {
  const router = useRouter();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [goal, setGoal] = useState('');
  const [creating, setCreating] = useState(false);

  async function loadTopics() {
    setLoading(true);
    setError('');
    try {
      const data = await listTopics();
      setTopics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topics');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTopics();
  }, []);

  async function onCreateTopic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (trimmedName.length < 2) {
      setError('Topic name must be at least 2 characters.');
      return;
    }

    setCreating(true);
    setError('');
    try {
      const result = await createTopicAndInitialize({
        name: trimmedName,
        description: description.trim(),
        goal: goal.trim()
      });
      router.push(`/topics/${result.topic.id}/initializing`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create topic');
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <header className="mb-10">
        <p className="badge mb-3">Personal Learning Companion</p>
        <h1 className="text-3xl font-semibold md:text-4xl">Knowledge Base</h1>
        <p className="muted mt-3 max-w-2xl text-sm md:text-base">
          Build your topic roadmap, track mastery, and learn through focused node-by-node progression.
        </p>
        <div className="mt-3">
          <Link href="/garden" className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Open Garden
          </Link>
        </div>
      </header>

      <section className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
        <article className="panel p-6">
          <h2 className="mb-4 text-xl font-semibold">Create New Topic</h2>
          <form className="space-y-3" onSubmit={onCreateTopic}>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
              placeholder="Topic (e.g. Python debugging)"
              maxLength={TOPIC_NAME_MAX}
              required
            />
            <p className="text-right text-xs text-black/60">{name.length}/{TOPIC_NAME_MAX}</p>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-24 w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
              placeholder="Short topic description"
              maxLength={TOPIC_DESC_MAX}
            />
            <p className="text-right text-xs text-black/60">{description.length}/{TOPIC_DESC_MAX}</p>
            <textarea
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              className="min-h-20 w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
              placeholder="Outcome goal (optional)"
              maxLength={TOPIC_GOAL_MAX}
            />
            <p className="text-right text-xs text-black/60">{goal.length}/{TOPIC_GOAL_MAX}</p>
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {creating ? 'Creating topic...' : 'Create Topic'}
            </button>
          </form>
        </article>

        <article className="panel p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Topics</h2>
            <button className="text-sm underline underline-offset-4" onClick={loadTopics}>
              Refresh
            </button>
          </div>

          {loading && (
            <div className="space-y-3">
              <div className="skeleton h-16 w-full" />
              <div className="skeleton h-16 w-full" />
              <div className="skeleton h-16 w-full" />
            </div>
          )}
          {!loading && topics.length === 0 && (
            <p className="muted rounded-lg border border-dashed border-black/15 bg-white p-4 text-sm">
              No topics yet. Create your first topic to start your skill tree.
            </p>
          )}

          <div className="space-y-3">
            {topics.map((topic) => (
              <Link
                key={topic.id}
                href={`/topics/${topic.id}`}
                className="block rounded-xl border border-black/10 bg-white p-4 transition hover:-translate-y-0.5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-base font-semibold">{topic.name}</p>
                    <p className="muted mt-1 text-sm">{topic.description || 'No description yet.'}</p>
                  </div>
                  <span className="badge">Open</span>
                </div>
                <p className="mt-3 text-xs text-black/70">Goal: {topic.goal || 'Not set'}</p>
              </Link>
            ))}
          </div>
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
