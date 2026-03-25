'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  deleteTopic,
  dismissTopicReminder,
  getRecommendations,
  getSkillTree,
  getTopicRetentionLoop,
  markMilestoneSeen
} from '@/lib/api';
import {
  invalidateTopicCache,
  readRecommendationCache,
  readSkillTreeCache,
  writeRecommendationCache,
  writeSkillTreeCache
} from '@/lib/cache';
import { LearningTab, RecommendationItem, SkillNode, SkillTree, TopicActionItem, TopicRetentionLoop } from '@/lib/types';
import { TopicOverviewSkeleton } from '@/components/page-skeletons';

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

function nodeKindClasses(nodeKind: SkillNode['node_kind']): string {
  if (nodeKind === 'optional_branch') return 'bg-violet-100 text-violet-800 border-violet-300';
  return 'bg-white text-black/70 border-black/20';
}

function tabLabel(tab: LearningTab): string {
  if (tab === 'quiz') return 'assessment';
  return tab;
}

export default function TopicOverviewPage({ params }: { params: { topicId: string } }) {
  const router = useRouter();
  const topicId = params.topicId;
  const cachedTree = readSkillTreeCache(topicId);
  const cachedRecommendations = readRecommendationCache(topicId) || [];

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>(cachedRecommendations);
  const [retention, setRetention] = useState<TopicRetentionLoop | null>(null);
  const [loadingTree, setLoadingTree] = useState(!cachedTree);
  const [loadingRecommendations, setLoadingRecommendations] = useState(cachedRecommendations.length === 0);
  const [loadingRetention, setLoadingRetention] = useState(!cachedTree);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmInput, setDeleteConfirmInput] = useState('');
  const [deletingTopic, setDeletingTopic] = useState(false);
  const [error, setError] = useState('');

  const loadTree = useCallback(
    async (showLoader = false) => {
      if (showLoader) setLoadingTree(true);
      try {
        const treeData = await getSkillTree(topicId);
        setTree(treeData);
        writeSkillTreeCache(topicId, treeData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load topic');
      } finally {
        setLoadingTree(false);
      }
    },
    [topicId]
  );

  const loadRecommendations = useCallback(
    async (refresh = false) => {
      setLoadingRecommendations(true);
      try {
        const recData = await getRecommendations(topicId, refresh);
        setRecommendations(recData);
        writeRecommendationCache(topicId, recData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load recommendations');
      } finally {
        setLoadingRecommendations(false);
      }
    },
    [topicId]
  );

  const loadRetention = useCallback(async () => {
    setLoadingRetention(true);
    try {
      const data = await getTopicRetentionLoop(topicId);
      setRetention(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load learning plan');
    } finally {
      setLoadingRetention(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadTree();
    loadRecommendations();
    loadRetention();
  }, [loadTree, loadRecommendations, loadRetention]);

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
    const fromActions = retention?.next_actions.find((item) => item.skill_node_id)?.skill_node_id;
    if (fromActions) return tree.nodes.find((node) => node.id === fromActions) || null;
    const fromRec = recommendations[0]?.skill_node_id;
    if (fromRec) return tree.nodes.find((node) => node.id === fromRec) || null;
    return tree.nodes.find((node) => node.status === 'available') || tree.nodes[0] || null;
  }, [tree, recommendations, retention]);

  const progress = useMemo(() => {
    const source = retention || {
      total_nodes: stats.total,
      available_nodes: stats.available,
      verified_nodes: 0,
      completed_nodes: 0,
      mastery_average: 0
    };
    const safeTotal = Math.max(1, source.total_nodes);
    return {
      unlockPct: Math.round((source.available_nodes / safeTotal) * 100),
      verifiedPct: Math.round((source.verified_nodes / safeTotal) * 100),
      completedPct: Math.round((source.completed_nodes / safeTotal) * 100),
      masteryPct: Math.round((source.mastery_average || 0) * 100)
    };
  }, [retention, stats]);

  function actionHref(action: TopicActionItem): string {
    if (!action.skill_node_id) return `/topics/${topicId}`;
    return `/topics/${topicId}/skills/${action.skill_node_id}?tab=${action.tab}`;
  }

  async function onDismissReminder() {
    if (!retention?.reminder) return;
    try {
      await dismissTopicReminder(topicId, retention.reminder.id);
      setRetention((prev) => (prev ? { ...prev, reminder: null } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss reminder');
    }
  }

  async function onAcknowledgeMilestone(milestoneId: number) {
    try {
      await markMilestoneSeen(topicId, milestoneId);
      setRetention((prev) =>
        prev ? { ...prev, milestones: prev.milestones.filter((item) => item.id !== milestoneId) } : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to acknowledge milestone');
    }
  }

  async function onDeleteTopic() {
    if (!tree) return;
    const expected = tree.topic.name.trim();
    if (deleteConfirmInput.trim() !== expected) {
      setError(`Type "${expected}" to confirm deletion.`);
      return;
    }

    setDeletingTopic(true);
    setError('');
    try {
      await deleteTopic(topicId);
      invalidateTopicCache(topicId);
      router.push('/topics');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete topic');
    } finally {
      setDeletingTopic(false);
    }
  }

  if (!tree && loadingTree) {
    return <TopicOverviewSkeleton />;
  }

  if (!tree) {
    return (
      <main className="mx-auto max-w-7xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Topic not found.</p>
      </main>
    );
  }

  const topMilestone = retention?.milestones?.[0] || null;

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
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
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="badge border border-emerald-300 bg-emerald-100 text-emerald-900">
              Growth Stage {retention?.tree_stage || 1}
            </span>
            {retention && (
              <span className="badge border border-sky-300 bg-sky-100 text-sky-900">
                {retention.cadence === 'daily' ? 'Daily plan' : 'Weekly plan'}
              </span>
            )}
            {!!retention?.streak_days && (
              <span className="badge border border-amber-300 bg-amber-100 text-amber-900">
                {retention.streak_days}-day streak
              </span>
            )}
          </div>
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
          <button
            type="button"
            className="rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-red-700"
            onClick={() => {
              setShowDeleteConfirm((prev) => !prev);
              setDeleteConfirmInput('');
            }}
          >
            {showDeleteConfirm ? 'Cancel delete' : 'Delete topic'}
          </button>
        </div>
      </header>

      {retention?.reminder && (
        <section className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-amber-900">{retention.reminder.title}</p>
              <p className="mt-1 text-sm text-amber-900">{retention.reminder.message}</p>
            </div>
            <div className="flex gap-2">
              {retention.reminder.action_skill_node_id && (
                <Link
                  href={`/topics/${topicId}/skills/${retention.reminder.action_skill_node_id}?tab=${retention.reminder.action_tab}`}
                  className="rounded-md bg-amber-700 px-3 py-2 text-sm text-white"
                >
                  Resume
                </Link>
              )}
              <button
                type="button"
                className="rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-amber-900"
                onClick={onDismissReminder}
              >
                Dismiss
              </button>
            </div>
          </div>
        </section>
      )}

      {topMilestone && (
        <section className="mb-4 rounded-xl border border-emerald-300 bg-emerald-50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-emerald-900">{topMilestone.title}</p>
              <p className="mt-1 text-sm text-emerald-800">{topMilestone.message}</p>
            </div>
            <button
              type="button"
              className="rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm text-emerald-900"
              onClick={() => onAcknowledgeMilestone(topMilestone.id)}
            >
              Nice
            </button>
          </div>
        </section>
      )}

      {showDeleteConfirm && (
        <section className="mb-6 rounded-xl border border-red-300 bg-red-50 p-4">
          <p className="text-sm text-red-800">
            This deletes the topic, skill tree, generated content, quiz history, notes, and source documents.
          </p>
          <p className="mt-2 text-sm text-red-800">
            Type <span className="font-semibold">{tree.topic.name}</span> to confirm.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={deleteConfirmInput}
              onChange={(event) => setDeleteConfirmInput(event.target.value)}
              className="w-full max-w-sm rounded-md border border-red-200 bg-white px-3 py-2 text-sm"
              placeholder="Enter topic name"
            />
            <button
              type="button"
              className="rounded-md bg-red-700 px-3 py-2 text-sm text-white disabled:opacity-60"
              disabled={deletingTopic}
              onClick={onDeleteTopic}
            >
              {deletingTopic ? 'Deleting...' : 'Confirm delete'}
            </button>
          </div>
        </section>
      )}

      <section className="mb-6 grid gap-3 md:grid-cols-4">
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Unlocked</p>
          <p className="mt-2 text-2xl font-semibold">
            {retention?.available_nodes ?? stats.available}/{retention?.total_nodes ?? stats.total}
          </p>
          <div className="mt-2 h-2 rounded-full bg-black/10">
            <div className="h-full rounded-full bg-sky-500" style={{ width: `${progress.unlockPct}%` }} />
          </div>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Verified</p>
          <p className="mt-2 text-2xl font-semibold">
            {retention?.verified_nodes ?? 0}/{retention?.total_nodes ?? stats.total}
          </p>
          <div className="mt-2 h-2 rounded-full bg-black/10">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progress.verifiedPct}%` }} />
          </div>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Completed</p>
          <p className="mt-2 text-2xl font-semibold">
            {retention?.completed_nodes ?? stats.mastered}/{retention?.total_nodes ?? stats.total}
          </p>
          <div className="mt-2 h-2 rounded-full bg-black/10">
            <div className="h-full rounded-full bg-violet-500" style={{ width: `${progress.completedPct}%` }} />
          </div>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-black/65">Mastery</p>
          <p className="mt-2 text-2xl font-semibold">{progress.masteryPct}%</p>
          <div className="mt-2 h-2 rounded-full bg-black/10">
            <div className="h-full rounded-full bg-amber-500" style={{ width: `${progress.masteryPct}%` }} />
          </div>
          {retention && <p className="mt-2 text-xs text-black/70">Active days (14d): {retention.activity_days_last_14}</p>}
        </article>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="panel p-5 md:p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Skill Tree</h2>
            <button className="text-sm underline underline-offset-4" onClick={() => loadTree(true)}>
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
                  <div className="flex flex-wrap items-center gap-2">
                    {node.node_kind === 'optional_branch' && (
                      <span className={`badge border ${nodeKindClasses(node.node_kind)}`}>Optional branch</span>
                    )}
                    <span className={`badge border ${statusClasses(node.status)}`}>{node.status.replace('_', ' ')}</span>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-black/70">
                  <span className={`badge border ${progressStateClasses(node.progress_state)}`}>
                    {progressStateLabel(node.progress_state)}
                  </span>
                  <span>Difficulty: {node.difficulty}</span>
                  <span>Prereqs: {node.prerequisites.length}</span>
                </div>
                {node.status === 'locked' && node.lock_reason && (
                  <p className="mt-2 text-xs text-red-700">{node.lock_reason}</p>
                )}
                <p className="muted mt-2 text-xs">Next: {node.recommended_next_action}</p>
              </Link>
            ))}
          </div>
        </article>

        <article className="space-y-4">
          <div className="panel p-5">
            <h2 className="text-lg font-semibold">Next 3 actions</h2>
            {loadingRetention && (
              <div className="mt-3 space-y-2">
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
              </div>
            )}
            {!loadingRetention && retention && (
              <div className="mt-3 space-y-2">
                {retention.next_actions.map((action, index) => (
                  <Link key={`${action.action_type}-${index}`} href={actionHref(action)} className="block rounded-lg border border-black/10 bg-white p-3">
                    <p className="text-sm font-semibold">{action.title}</p>
                    <p className="muted mt-1 text-xs leading-relaxed">{action.description}</p>
                    <p className="mt-2 text-xs text-black/70">Open {tabLabel(action.tab)} for {action.skill_name}</p>
                  </Link>
                ))}
                {retention.next_actions.length === 0 && <p className="muted text-sm">No immediate actions available.</p>}
              </div>
            )}
          </div>

          <div className="panel p-5">
            <h2 className="text-lg font-semibold">{retention?.cadence === 'daily' ? 'Today’s plan' : 'This week’s plan'}</h2>
            <p className="muted mt-1 text-sm">{retention?.plan_summary || 'Loading your plan...'}</p>
            {!loadingRetention && retention && (
              <ol className="mt-3 space-y-2 text-sm">
                {retention.learning_plan.map((item, index) => (
                  <li key={`${item.action_type}-${index}`} className="rounded-md border border-black/10 bg-white p-3">
                    <p className="font-semibold">
                      {index + 1}. {item.title}
                    </p>
                    <p className="muted mt-1 text-xs">{item.description}</p>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="panel p-5">
            <h2 className="text-lg font-semibold">Coming next</h2>
            {retention?.unlock_anticipation ? (
              <div className="mt-3 space-y-2">
                <p className="font-semibold">
                  {retention.unlock_anticipation.skill_name} · {retention.unlock_anticipation.status_label}
                </p>
                <p className="muted text-sm">{retention.unlock_anticipation.why_locked}</p>
                <ul className="space-y-1 text-sm">
                  {retention.unlock_anticipation.steps.map((step) => (
                    <li key={step}>• {step}</li>
                  ))}
                </ul>
                {retention.unlock_anticipation.next_step_skill_node_id && (
                  <Link
                    href={`/topics/${topicId}/skills/${retention.unlock_anticipation.next_step_skill_node_id}?tab=${retention.unlock_anticipation.next_step_tab}`}
                    className="inline-flex rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  >
                    Take the next step
                  </Link>
                )}
              </div>
            ) : (
              <p className="muted mt-2 text-sm">No locked nodes are close to unlocking yet.</p>
            )}
          </div>

          <div className="panel p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Recommendations</h2>
              <button className="text-xs underline underline-offset-4" onClick={() => loadRecommendations(true)}>
                Refresh
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {loadingRecommendations && recommendations.length === 0 && (
                <>
                  <div className="skeleton h-14 w-full" />
                  <div className="skeleton h-14 w-full" />
                </>
              )}
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
              {!loadingRecommendations && recommendations.length === 0 && <p className="muted text-sm">No recommendations yet.</p>}
            </div>
          </div>
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
