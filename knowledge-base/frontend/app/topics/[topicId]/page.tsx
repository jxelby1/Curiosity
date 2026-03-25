'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { getRecommendations, getSkillTree } from '@/lib/api';
import { RecommendationItem, SkillNode, SkillTree } from '@/lib/types';

function statusClasses(status: SkillNode['status']): string {
  if (status === 'mastered') return 'bg-emerald-100 text-emerald-900 border-emerald-300';
  if (status === 'in_progress') return 'bg-amber-100 text-amber-900 border-amber-300';
  if (status === 'available') return 'bg-sky-100 text-sky-900 border-sky-300';
  return 'bg-zinc-100 text-zinc-700 border-zinc-300';
}

function progressStateLabel(state: SkillNode['progress_state']): string {
  if (state === 'not_started') return 'Not started';
  if (state === 'learning') return 'Learning';
  if (state === 'completed') return 'Completed';
  return 'Verified';
}

function progressStateClasses(state: SkillNode['progress_state']): string {
  if (state === 'verified') return 'bg-emerald-100 text-emerald-900 border-emerald-300';
  if (state === 'completed') return 'bg-sky-100 text-sky-900 border-sky-300';
  if (state === 'learning') return 'bg-amber-100 text-amber-900 border-amber-300';
  return 'bg-zinc-100 text-zinc-700 border-zinc-300';
}

export default function TopicOverviewPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;

  const [tree, setTree] = useState<SkillTree | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [treeData, recData] = await Promise.all([getSkillTree(topicId), getRecommendations(topicId)]);
      setTree(treeData);
      setRecommendations(recData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topic');
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const stats = useMemo(() => {
    if (!tree) return { total: 0, available: 0, mastered: 0 };
    return {
      total: tree.nodes.length,
      available: tree.nodes.filter((node) => node.status !== 'locked').length,
      mastered: tree.nodes.filter((node) => node.status === 'mastered').length
    };
  }, [tree]);

  const suggestedNode = useMemo(() => {
    if (!tree?.nodes?.length) return null;
    const fromRec = recommendations[0]?.skill_node_id;
    if (fromRec) {
      return tree.nodes.find((node) => node.id === fromRec) || null;
    }
    return tree.nodes.find((node) => node.status === 'available') || tree.nodes[0] || null;
  }, [tree, recommendations]);

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl p-6 md:p-10">
        <p className="panel p-4 text-sm">Loading topic overview...</p>
      </main>
    );
  }

  if (!tree) {
    return (
      <main className="mx-auto max-w-7xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Topic not found.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-black/60">
            <Link href="/topics" className="underline underline-offset-4">
              Topics
            </Link>
            <span>/</span>
            <span>{tree.topic.name}</span>
          </div>
          <h1 className="mt-2 text-3xl font-semibold md:text-4xl">{tree.topic.name}</h1>
          <p className="muted mt-2 max-w-3xl text-sm md:text-base">{tree.topic.description || 'No description provided.'}</p>
          <p className="mt-2 text-xs text-black/70">Goal: {tree.topic.goal || 'Not set'}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Notes
          </Link>
          <Link href={`/topics/${topicId}/chat`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Tutor Chat
          </Link>
          {suggestedNode && (
            <Link
              href={`/topics/${topicId}/skills/${suggestedNode.id}`}
              className="rounded-md bg-ink px-3 py-2 text-sm text-white"
            >
              Continue Learning
            </Link>
          )}
        </div>
      </header>

      <section className="mb-6 grid gap-3 md:grid-cols-3">
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Nodes</p>
          <p className="mt-2 text-2xl font-semibold">{stats.total}</p>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Unlocked</p>
          <p className="mt-2 text-2xl font-semibold">{stats.available}</p>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Mastered</p>
          <p className="mt-2 text-2xl font-semibold">{stats.mastered}</p>
        </article>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="panel p-5 md:p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Skill Tree</h2>
            <button className="text-sm underline underline-offset-4" onClick={loadOverview}>
              Refresh
            </button>
          </div>

          <div className="space-y-2">
            {tree.nodes.map((node) => (
              <Link
                key={node.id}
                href={`/topics/${topicId}/skills/${node.id}`}
                className="block rounded-xl border border-black/10 bg-white p-3 transition hover:-translate-y-0.5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{node.name}</p>
                    <p className="muted mt-1 text-xs">{node.description}</p>
                  </div>
                  <span className={`badge border ${statusClasses(node.status)}`}>{node.status.replace('_', ' ')}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-black/70">
                  <span className={`badge border ${progressStateClasses(node.progress_state)}`}>
                    {progressStateLabel(node.progress_state)}
                  </span>
                  <span>Difficulty: {node.difficulty}</span>
                  <span>Prereqs: {node.prerequisites.length}</span>
                </div>
                <p className="muted mt-2 text-xs">Next: {node.recommended_next_action}</p>
              </Link>
            ))}
          </div>
        </article>

        <article className="space-y-4">
          <div className="panel p-5">
            <h2 className="text-lg font-semibold">Recommendations</h2>
            <div className="mt-3 space-y-2">
              {recommendations.map((rec) => (
                <Link
                  key={rec.skill_node_id}
                  href={`/topics/${topicId}/skills/${rec.skill_node_id}`}
                  className="block rounded-lg border border-black/10 bg-white p-3"
                >
                  <p className="text-sm font-semibold">{rec.skill_name}</p>
                  <p className="muted mt-1 text-xs leading-relaxed">{rec.rationale}</p>
                  <p className="mt-2 text-xs text-black/70">
                    Mode: {rec.resource_mode} · Confidence: {(rec.confidence * 100).toFixed(0)}%
                  </p>
                </Link>
              ))}
              {recommendations.length === 0 && <p className="muted text-sm">No recommendations yet.</p>}
            </div>
          </div>

          <div className="panel p-5">
            <h2 className="text-lg font-semibold">Next Action</h2>
            {suggestedNode ? (
              <div className="mt-3 space-y-2">
                <p className="font-semibold">{suggestedNode.name}</p>
                <p className="muted text-sm">{suggestedNode.recommended_next_action}</p>
                <Link
                  href={`/topics/${topicId}/skills/${suggestedNode.id}`}
                  className="inline-flex rounded-md bg-ink px-3 py-2 text-sm text-white"
                >
                  Open Skill Workspace
                </Link>
              </div>
            ) : (
              <p className="muted mt-2 text-sm">No suggested node available.</p>
            )}
          </div>
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
