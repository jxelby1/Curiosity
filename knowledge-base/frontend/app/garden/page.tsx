'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { getMyProgressSummary } from '@/lib/api';
import { UserProgressSummary, UserTopicProgressSummary } from '@/lib/types';
import { GardenScene } from '@/components/garden/garden-scene';

function parseLatestActivity(value: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function recencyLine(value: string | null): string {
  const latest = parseLatestActivity(value);
  if (!latest) return 'Waiting for its first return.';
  const hours = Math.max(1, Math.round((Date.now() - latest.getTime()) / (1000 * 60 * 60)));
  if (hours < 24) return 'Tended today.';
  if (hours < 48) return 'Tended yesterday.';
  if (hours < 24 * 7) return `Tended ${Math.round(hours / 24)} days ago.`;
  return 'Ready for a quiet return.';
}

function layeringLine(topic: UserTopicProgressSummary): string {
  if (topic.notes_count > 0 && topic.branch_count > 0) {
    return `${topic.notes_count} notebook note${topic.notes_count === 1 ? '' : 's'} and ${topic.branch_count} branch path${topic.branch_count === 1 ? '' : 's'} are deepening this plot.`;
  }
  if (topic.notes_count > 0) {
    return `${topic.notes_count} notebook note${topic.notes_count === 1 ? '' : 's'} are giving this plot a memory trail.`;
  }
  if (topic.branch_count > 0) {
    return `${topic.branch_count} branch path${topic.branch_count === 1 ? '' : 's'} are making this plot more layered.`;
  }
  return 'This plot is still forming along the core path.';
}

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
  const recentlyTended = useMemo(() => {
    if (!summary) return null;
    return [...summary.topics]
      .filter((topic) => topic.latest_activity_at)
      .sort((a, b) => new Date(b.latest_activity_at || 0).getTime() - new Date(a.latest_activity_at || 0).getTime())[0] || null;
  }, [summary]);

  const layeredPlot = useMemo(() => {
    if (!summary) return null;
    return [...summary.topics].sort((a, b) => (b.notes_count + b.branch_count * 2) - (a.notes_count + a.branch_count * 2))[0] || null;
  }, [summary]);

  return (
    <main className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 md:py-8 lg:px-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="badge mb-3">Learning Garden</p>
          <h1 className="text-3xl md:text-4xl">Your study grove</h1>
          <p className="muted mt-2 max-w-3xl text-sm md:text-base">
            The grove holds where study is still alive, where notebook memory is beginning to gather, and which plots are quietly ready for your return.
          </p>
        </div>
        <Link href="/topics" className="studio-button-secondary px-3 py-2 text-sm">
          Back to topics
        </Link>
      </header>

      {loading && (
        <section className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="panel p-4">
              <div className="skeleton h-5 w-32" />
              <div className="skeleton mt-2 h-5 w-48" />
              <div className="skeleton mt-3 h-10 w-full" />
            </div>
            <div className="panel p-4">
              <div className="skeleton h-5 w-32" />
              <div className="skeleton mt-2 h-5 w-48" />
              <div className="skeleton mt-3 h-10 w-full" />
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
          <section className="mb-5 grid gap-4 lg:grid-cols-2">
            <article className="panel p-5">
              <p className="text-xs uppercase tracking-[0.14em] text-black/62">Garden signal</p>
              <h2 className="mt-2 text-xl font-semibold">Recently tended</h2>
              <p className="mt-2 text-sm text-black/68">
                {recentlyTended
                  ? `${recentlyTended.topic_name} is the warmest plot right now. ${recencyLine(recentlyTended.latest_activity_at)}`
                  : 'No plot has been tended yet. Your first return will start the grove moving.'}
              </p>
              {recentlyTended && (
                <Link
                  href={`/topics/${recentlyTended.topic_id}`}
                  className="mt-4 inline-flex rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-black/82"
                >
                  Return to {recentlyTended.topic_name}
                </Link>
              )}
            </article>

            <article className="panel p-5">
              <p className="text-xs uppercase tracking-[0.14em] text-black/62">Garden signal</p>
              <h2 className="mt-2 text-xl font-semibold">Memory in bloom</h2>
              <p className="mt-2 text-sm text-black/68">
                {layeredPlot && layeredPlot.notes_count + layeredPlot.branch_count > 0
                  ? `${layeringLine(layeredPlot)} ${layeredPlot.topic_name} is carrying the richest trace of memory right now.`
                  : 'Notebook trails and branch paths are still beginning. The grove will deepen as you reflect and take selective side paths.'}
              </p>
              {layeredPlot && layeredPlot.notes_count + layeredPlot.branch_count > 0 && (
                <Link
                  href={`/topics/${layeredPlot.topic_id}/notes`}
                  className="mt-4 inline-flex rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-black/82"
                >
                  Open {layeredPlot.topic_name} notebook
                </Link>
              )}
            </article>
          </section>

          <GardenScene topics={summary.topics} />

          <section className="mt-4 panel p-4">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/62">Plots in the grove</h2>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {summary.topics.map((topic) => (
                <Link
                  key={topic.topic_id}
                  href={`/topics/${topic.topic_id}`}
                  className="rounded-lg border border-black/10 bg-white px-3 py-2 text-sm hover:bg-black/[0.02]"
                >
                  <p className="font-semibold">{topic.topic_name}</p>
                  <p className="mt-0.5 text-[11px] uppercase tracking-[0.12em] text-black/55">Stage {topic.tree_stage}</p>
                  <p className="mt-1 text-xs text-black/66">{recencyLine(topic.latest_activity_at)}</p>
                  <p className="mt-1 text-xs text-black/58">{layeringLine(topic)}</p>
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
