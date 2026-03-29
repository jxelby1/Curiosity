'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { getMyProgressSummary } from '@/lib/api';
import { UserProgressSummary } from '@/lib/types';
import { GardenScene } from '@/components/garden/garden-scene';

export default function GardenPage() {
  const [summary, setSummary] = useState<UserProgressSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const data = await getMyProgressSummary();
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load garden');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return (
    <main className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 md:py-8 lg:px-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="badge mb-3">Learning Garden</p>
          <h1 className="text-3xl font-semibold md:text-4xl">Your topic forest</h1>
          <p className="muted mt-2 max-w-3xl text-sm md:text-base">
            Progress grows each topic tree. Return often to keep your garden alive and expanding.
          </p>
        </div>
        <Link href="/topics" className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
          Back to topics
        </Link>
      </header>

      {loading && (
        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="panel p-4">
              <div className="skeleton h-5 w-24" />
              <div className="skeleton mt-2 h-7 w-16" />
            </div>
            <div className="panel p-4">
              <div className="skeleton h-5 w-24" />
              <div className="skeleton mt-2 h-7 w-16" />
            </div>
            <div className="panel p-4">
              <div className="skeleton h-5 w-24" />
              <div className="skeleton mt-2 h-7 w-16" />
            </div>
          </div>
          <div className="panel p-5">
            <div className="skeleton h-6 w-56" />
            <div className="skeleton mt-3 h-[460px] w-full" />
          </div>
        </section>
      )}

      {!loading && summary && summary.topics.length === 0 && (
        <p className="panel p-4 text-sm text-black/70">No topics yet. Create your first topic to start your garden.</p>
      )}

      {!loading && summary && summary.topics.length > 0 && (
        <>
          <section className="mb-4 grid gap-3 md:grid-cols-3">
            <article className="panel p-4">
              <p className="text-xs uppercase tracking-[0.14em] text-black/65">Topics</p>
              <p className="mt-2 text-2xl font-semibold">{summary.topics_total}</p>
            </article>
            <article className="panel p-4">
              <p className="text-xs uppercase tracking-[0.14em] text-black/65">Verified nodes</p>
              <p className="mt-2 text-2xl font-semibold">{summary.verified_nodes_total}</p>
            </article>
            <article className="panel p-4">
              <p className="text-xs uppercase tracking-[0.14em] text-black/65">Avg mastery</p>
              <p className="mt-2 text-2xl font-semibold">{Math.round(summary.mastery_average * 100)}%</p>
            </article>
          </section>

          <GardenScene topics={summary.topics} />

          <section className="mt-4 panel p-4">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/62">Topic index</h2>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {summary.topics.map((topic) => (
                <Link
                  key={topic.topic_id}
                  href={`/topics/${topic.topic_id}`}
                  className="rounded-lg border border-black/10 bg-white px-3 py-2 text-sm hover:bg-black/[0.02]"
                >
                  <p className="font-semibold">{topic.topic_name}</p>
                  <p className="mt-0.5 text-xs text-black/62">
                    Stage {topic.tree_stage} · {topic.verified_nodes}/{topic.total_nodes} verified
                  </p>
                </Link>
              ))}
            </div>
          </section>
        </>
      )}

      {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
