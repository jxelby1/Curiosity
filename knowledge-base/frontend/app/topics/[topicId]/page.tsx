'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  acceptBranchSuggestion,
  createDeepDiveBranch,
  deleteTopic,
  dismissTopicReminder,
  forceUnlockSkill,
  generateBranchSuggestions,
  getSkillTree,
  getTopicRetentionLoop,
  listBranchSuggestions,
  markMilestoneSeen,
  rejectBranchSuggestion,
} from '@/lib/api';
import {
  invalidateTopicCache,
  readSkillTreeCache,
  writeSkillTreeCache,
} from '@/lib/cache';
import { BranchPurpose } from '@/lib/branch-purpose';
import { formatDisplayTag } from '@/lib/display-format';
import { BranchSuggestion, SkillNode, SkillTree, TopicRetentionLoop } from '@/lib/types';
import { derivePrimaryTopicNextStep, LEARNING_LOOP_LABELS } from '@/lib/next-step';
import { TopicOverviewSkeleton } from '@/components/page-skeletons';
import { PremiumSkillTree } from '@/components/skill-tree/premium-skill-tree';
import { SkillNodeInspector } from '@/components/skill-tree/skill-node-inspector';

function defaultSelectedNode(tree: SkillTree | null, retention: TopicRetentionLoop | null): number | null {
  if (!tree?.nodes?.length) return null;
  const fromActions = retention?.next_actions.find((item) => item.skill_node_id)?.skill_node_id;
  if (fromActions && tree.nodes.some((item) => item.id === fromActions)) return fromActions;
  const available = tree.nodes.find((item) => item.status !== 'locked');
  if (available) return available.id;
  return tree.nodes[0]?.id ?? null;
}

function CompactProgressBar({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: 'cyan' | 'emerald';
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const bg = tone === 'cyan' ? 'from-cyan-400 to-sky-300' : 'from-emerald-400 to-lime-300';

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-medium text-black/70">{label}</span>
        <span className="text-black/55">
          {value}/{total} ({pct}%)
        </span>
      </div>
      <div className="h-2 rounded-full bg-black/10">
        <div className={`h-full rounded-full bg-gradient-to-r ${bg}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function TopicOverviewPage({ params }: { params: { topicId: string } }) {
  const router = useRouter();
  const topicId = params.topicId;
  const cachedTree = readSkillTreeCache(topicId);

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [retention, setRetention] = useState<TopicRetentionLoop | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(defaultSelectedNode(cachedTree, null));
  const [branchSuggestionsByNode, setBranchSuggestionsByNode] = useState<Record<number, BranchSuggestion[]>>({});
  const [branchSuggestionLoadingByNode, setBranchSuggestionLoadingByNode] = useState<Record<number, boolean>>({});
  const [branchActionLoadingByNode, setBranchActionLoadingByNode] = useState<Record<number, boolean>>({});
  const [branchErrorByNode, setBranchErrorByNode] = useState<Record<number, string>>({});
  const [loadingTree, setLoadingTree] = useState(!cachedTree);
  const [loadingRetention, setLoadingRetention] = useState(true);
  const [forcingUnlock, setForcingUnlock] = useState(false);

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

  const loadRetention = useCallback(async () => {
    setLoadingRetention(true);
    try {
      const data = await getTopicRetentionLoop(topicId);
      setRetention(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load learning loop');
    } finally {
      setLoadingRetention(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadTree();
    loadRetention();
  }, [loadTree, loadRetention]);

  useEffect(() => {
    setSelectedNodeId((prev) => {
      if (!tree) return prev;
      if (prev && tree.nodes.some((node) => node.id === prev)) return prev;
      return defaultSelectedNode(tree, retention);
    });
  }, [tree, retention]);

  const selectedNode = useMemo(() => {
    if (!tree || selectedNodeId == null) return null;
    return tree.nodes.find((node) => node.id === selectedNodeId) || null;
  }, [tree, selectedNodeId]);

  useEffect(() => {
    if (!selectedNode || selectedNode.status === 'locked') return;
    if (branchSuggestionsByNode[selectedNode.id]) return;
    void ensureBranchSuggestions(selectedNode.id, false);
  }, [selectedNode?.id, selectedNode?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedPrerequisites = useMemo(() => {
    if (!tree || !selectedNode) return [];
    const map = new Map(tree.nodes.map((node) => [node.id, node]));
    return (selectedNode.prerequisites || []).map((id) => map.get(id)).filter((item): item is SkillNode => !!item);
  }, [tree, selectedNode]);

  const primaryNextStep = useMemo(
    () =>
      derivePrimaryTopicNextStep({
        topicId,
        retention,
        tree,
      }),
    [retention, topicId, tree]
  );

  const totalNodes = retention?.total_nodes ?? tree?.nodes.length ?? 0;
  const unlockedNodes = retention?.available_nodes ?? tree?.nodes.filter((node) => node.status !== 'locked').length ?? 0;
  const verifiedNodes = retention?.verified_nodes ?? tree?.nodes.filter((node) => node.progress_state === 'verified').length ?? 0;
  const masteryAvg = Math.round((retention?.mastery_average ?? 0) * 100);
  const reminderHref =
    retention?.reminder?.action_skill_node_id != null
      ? `/topics/${topicId}/skills/${retention.reminder.action_skill_node_id}?tab=${retention.reminder.action_tab}`
      : null;
  const unlockNextHref =
    retention?.unlock_anticipation?.next_step_skill_node_id != null
      ? `/topics/${topicId}/skills/${retention.unlock_anticipation.next_step_skill_node_id}?tab=${retention.unlock_anticipation.next_step_tab}`
      : null;

  async function refreshEverything() {
    setError('');
    await loadTree(true);
    await loadRetention();
  }

  function setBranchLoading(skillId: number, value: boolean) {
    setBranchSuggestionLoadingByNode((prev) => ({ ...prev, [skillId]: value }));
  }

  function setBranchActionLoading(skillId: number, value: boolean) {
    setBranchActionLoadingByNode((prev) => ({ ...prev, [skillId]: value }));
  }

  function setBranchError(skillId: number, message: string) {
    setBranchErrorByNode((prev) => ({ ...prev, [skillId]: message }));
  }

  async function ensureBranchSuggestions(skillId: number, force = false) {
    if (!force && branchSuggestionsByNode[skillId]) return;
    setBranchLoading(skillId, true);
    setBranchError(skillId, '');
    try {
      const suggestions = await listBranchSuggestions(skillId, 'pending');
      setBranchSuggestionsByNode((prev) => ({ ...prev, [skillId]: suggestions.slice(0, 1) }));
    } catch (err) {
      setBranchError(skillId, err instanceof Error ? err.message : 'Failed to load branch suggestions.');
    } finally {
      setBranchLoading(skillId, false);
    }
  }

  async function handleGenerateBranchSuggestions(skillId: number) {
    setBranchLoading(skillId, true);
    setBranchError(skillId, '');
    try {
      const suggestions = await generateBranchSuggestions({ skillId, limit: 1, trigger_event: 'manual' });
      setBranchSuggestionsByNode((prev) => ({ ...prev, [skillId]: suggestions.slice(0, 1) }));
    } catch (err) {
      setBranchError(skillId, err instanceof Error ? err.message : 'Failed to generate branch suggestions.');
    } finally {
      setBranchLoading(skillId, false);
    }
  }

  async function handleCreateBranch(
    skillId: number,
    input: {
      focus?: string;
      purpose: BranchPurpose;
    }
  ) {
    setBranchActionLoading(skillId, true);
    setBranchError(skillId, '');
    setError('');
    try {
      const nextTree = await createDeepDiveBranch({
        skillId,
        focus: input.focus,
        branch_size: 1,
        purpose: input.purpose,
      });
      setTree(nextTree);
      writeSkillTreeCache(topicId, nextTree);
      await loadRetention();
      await ensureBranchSuggestions(skillId, true);
    } catch (err) {
      setBranchError(skillId, err instanceof Error ? err.message : 'Failed to create branch.');
    } finally {
      setBranchActionLoading(skillId, false);
    }
  }

  async function handleAcceptBranchSuggestion(skillId: number, suggestionId: number) {
    setBranchActionLoading(skillId, true);
    setBranchError(skillId, '');
    try {
      const nextTree = await acceptBranchSuggestion({ suggestionId });
      setTree(nextTree);
      writeSkillTreeCache(topicId, nextTree);
      await loadRetention();
      await ensureBranchSuggestions(skillId, true);
    } catch (err) {
      setBranchError(skillId, err instanceof Error ? err.message : 'Failed to accept branch suggestion.');
    } finally {
      setBranchActionLoading(skillId, false);
    }
  }

  async function handleRejectBranchSuggestion(skillId: number, suggestionId: number) {
    setBranchActionLoading(skillId, true);
    setBranchError(skillId, '');
    try {
      await rejectBranchSuggestion(suggestionId);
      await ensureBranchSuggestions(skillId, true);
    } catch (err) {
      setBranchError(skillId, err instanceof Error ? err.message : 'Failed to reject branch suggestion.');
    } finally {
      setBranchActionLoading(skillId, false);
    }
  }

  async function onForceUnlock(skillNodeId: number) {
    setForcingUnlock(true);
    setError('');
    try {
      await forceUnlockSkill(skillNodeId);
      await refreshEverything();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to force unlock node');
    } finally {
      setForcingUnlock(false);
    }
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
      setRetention((prev) => (prev ? { ...prev, milestones: prev.milestones.filter((item) => item.id !== milestoneId) } : prev));
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
      <main className="mx-auto max-w-6xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Topic not found.</p>
      </main>
    );
  }

  const topMilestone = retention?.milestones?.[0] || null;

  return (
    <main className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 md:py-8 lg:px-8">
      <header className="mb-6 flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-black/58">
            <Link href="/topics" className="underline underline-offset-4">
              Studies
            </Link>
            <span>/</span>
            <span>{tree.topic.name}</span>
          </div>
          <h1 className="mt-2 text-3xl tracking-tight md:text-4xl">{tree.topic.name}</h1>
          <p className="muted mt-2 max-w-3xl text-sm md:text-base">
            {tree.topic.description || 'Continue your study path through this constellation of concepts and practices.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="badge border border-black/15 bg-white">Study Stage {retention?.tree_stage || 1}</span>
            {retention && <span className="badge border border-black/15 bg-white">{retention.cadence === 'daily' ? 'Daily Plan' : 'Weekly Plan'}</span>}
            {!!retention?.streak_days && <span className="badge border border-black/15 bg-white">{retention.streak_days}-Day Streak</span>}
          </div>
        </div>

        <div className="flex flex-wrap items-start gap-2">
          <Link href={primaryNextStep.href} className="studio-button-primary px-3 py-2 text-sm">
            {primaryNextStep.label}
          </Link>
          <Link href={`/topics/${topicId}/notes`} className="studio-button-secondary px-3 py-2 text-sm">
            Notebook
          </Link>
          <details className="group relative">
            <summary className="studio-button-secondary flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm [&::-webkit-details-marker]:hidden">
              Study tools
              <span className="text-xs text-black/45 transition group-open:rotate-180">▾</span>
            </summary>
            <div className="absolute right-0 z-20 mt-2 w-[320px] rounded-2xl border border-black/10 bg-white p-4 shadow-[0_18px_42px_rgba(16,19,33,0.16)]">
              <div className="space-y-2">
                <Link
                  href={`/topics/${topicId}/chat`}
                  className="flex items-center justify-between rounded-lg border border-black/10 bg-paper/25 px-3 py-2 text-sm text-black/82 hover:bg-black/[0.03]"
                >
                  <span>Dialogue</span>
                  <span className="text-xs uppercase tracking-[0.12em] text-black/45">Companion</span>
                </Link>
                <Link
                  href="/garden"
                  className="flex items-center justify-between rounded-lg border border-black/10 bg-paper/25 px-3 py-2 text-sm text-black/82 hover:bg-black/[0.03]"
                >
                  <span>Garden</span>
                  <span className="text-xs uppercase tracking-[0.12em] text-black/45">Overview</span>
                </Link>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-lg border border-black/10 bg-paper/25 px-3 py-2 text-sm text-black/82 hover:bg-black/[0.03]"
                  onClick={() => refreshEverything()}
                >
                  <span>Refresh study home</span>
                  <span className="text-xs uppercase tracking-[0.12em] text-black/45">Sync</span>
                </button>
              </div>

              <div className="mt-4 rounded-xl border border-black/10 bg-paper/35 p-3">
                <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Study frame</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="badge border border-black/10 bg-white">{formatDisplayTag(tree.topic.course_depth)} Course</span>
                  <span className="badge border border-black/10 bg-white">{formatDisplayTag(tree.topic.starting_skill_level)} Start</span>
                  <span className="badge border border-black/10 bg-white">{formatDisplayTag(tree.topic.technical_depth)} Depth</span>
                </div>
              </div>

              <div className="mt-4 border-t border-black/10 pt-4">
                <button
                  type="button"
                  className="text-sm font-medium text-red-700 underline underline-offset-4"
                  onClick={() => {
                    setShowDeleteConfirm((prev) => !prev);
                    setDeleteConfirmInput('');
                  }}
                >
                  {showDeleteConfirm ? 'Cancel delete' : 'Delete study'}
                </button>

                {showDeleteConfirm && (
                  <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3">
                    <p className="text-sm text-red-800">
                      This removes the study, tree, generated content, assessment history, notes, and source documents.
                    </p>
                    <p className="mt-2 text-sm text-red-800">
                      Type <span className="font-semibold">{tree.topic.name}</span> to confirm.
                    </p>
                    <div className="mt-3 grid gap-2">
                      <input
                        value={deleteConfirmInput}
                        onChange={(event) => setDeleteConfirmInput(event.target.value)}
                        className="w-full rounded-md border border-red-200 bg-white px-3 py-2 text-sm"
                        placeholder="Enter study name"
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
                  </div>
                )}
              </div>
            </div>
          </details>
        </div>
      </header>

      <section className="mb-7 grid gap-4 xl:grid-cols-[minmax(0,1.38fr)_minmax(320px,0.92fr)]">
        <article className="rounded-[28px] border border-black/10 bg-[linear-gradient(165deg,rgba(255,255,255,0.97),rgba(241,249,236,0.9))] p-5 shadow-[0_20px_52px_rgba(16,19,33,0.14)] md:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-2xl">
              <p className="text-xs uppercase tracking-[0.18em] text-black/55">Primary Next Step</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-black md:text-[2.15rem]">{primaryNextStep.label}</h2>
              <p className="mt-3 text-sm leading-relaxed text-black/72 md:text-base">{primaryNextStep.reason}</p>
            </div>
            <div className="rounded-2xl border border-black/10 bg-white/85 px-4 py-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-black/48">Why now</p>
              <p className="mt-1 max-w-[220px] text-sm text-black/72">
                {retention?.next_actions?.[0]?.description || 'This move keeps the core path clear and the study home trustworthy.'}
              </p>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <Link href={primaryNextStep.href} className="rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-white">
              Start now
            </Link>
            <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-4 py-2.5 text-sm text-black/80">
              Open notebook
            </Link>
          </div>

          {retention?.plan_summary && <p className="mt-4 text-sm text-black/60">{retention.plan_summary}</p>}

          <div className="mt-5 grid gap-4 md:grid-cols-[0.92fr_1.08fr]">
            <div className="rounded-2xl border border-black/10 bg-white p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-black/55">At a glance</p>
              <div className="mt-3 space-y-3">
                <CompactProgressBar label="Unlocked nodes" value={unlockedNodes} total={totalNodes} tone="cyan" />
                <CompactProgressBar label="Verified nodes" value={verifiedNodes} total={totalNodes} tone="emerald" />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <div className="rounded-lg border border-black/10 bg-paper/30 px-3 py-2.5">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Total</p>
                  <p className="mt-1 text-lg font-semibold">{totalNodes}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-paper/30 px-3 py-2.5">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Unlocked</p>
                  <p className="mt-1 text-lg font-semibold">{unlockedNodes}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-paper/30 px-3 py-2.5">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Mastery</p>
                  <p className="mt-1 text-lg font-semibold">{masteryAvg}%</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-black/10 bg-white p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-black/55">Studio Loop</p>
              <ol className="mt-3 space-y-2 text-sm">
                {LEARNING_LOOP_LABELS.map((item, index) => {
                  const active = item.id === primaryNextStep.loopStep;
                  return (
                    <li
                      key={item.id}
                      className={`rounded-md border px-3 py-2 ${
                        active ? 'border-ink bg-ink/5 text-black' : 'border-black/10 bg-paper/25 text-black/68'
                      }`}
                    >
                      <span className="mr-2 text-xs text-black/55">{index + 1}.</span>
                      {item.label}
                    </li>
                  );
                })}
              </ol>
              <p className="mt-3 text-xs text-black/60">
                Keep one clear move in front, let the notebook hold what changes, and treat branches as deliberate side paths.
              </p>
            </div>
          </div>
        </article>

        <div className="grid gap-4">
          <article className="panel p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-black/55">Notebook Memory</p>
            <h2 className="mt-2 text-xl font-semibold">{retention?.notebook_memory?.recommended_lens_label || 'Reflection'}</h2>
            <p className="muted mt-2 text-sm">
              {retention?.notebook_memory?.recommended_lens_reason ||
                'Keep one living record of what changed, what deserves comparison, and what you want to follow next.'}
            </p>
            <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-xs uppercase tracking-[0.12em] text-emerald-900/70">Current prompt</p>
              <p className="mt-1 text-sm text-emerald-950">
                {retention?.notebook_memory?.prompt || 'Capture the strongest insight from this topic in your notebook.'}
              </p>
            </div>
            <p className="mt-3 text-xs text-black/62">
              {retention?.notebook_memory?.growth_signal || 'The notebook is ready for its next high-signal capture.'}
            </p>
            {retention?.notebook_memory?.latest_note_title && (
              <p className="mt-2 text-xs text-black/58">
                Latest memory: <span className="font-medium text-black/72">{retention.notebook_memory.latest_note_title}</span>
                {retention.notebook_memory.latest_note_skill_name
                  ? ` · ${retention.notebook_memory.latest_note_skill_name}`
                  : ''}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
                Open notebook
              </Link>
              <Link href={`/topics/${topicId}/chat`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
                Capture from dialogue
              </Link>
            </div>
          </article>

          <article className="panel p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-black/55">Study Signals</p>
            <div className="mt-3 space-y-3">
              {loadingRetention && !retention && <p className="text-sm text-black/58">Aligning your study home…</p>}

              {topMilestone && (
                <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-emerald-900/70">Milestone</p>
                      <p className="mt-1 text-sm font-semibold text-emerald-950">{topMilestone.title}</p>
                      <p className="mt-1 text-sm text-emerald-900">{topMilestone.message}</p>
                    </div>
                    <button
                      type="button"
                      className="shrink-0 rounded-md border border-emerald-300 bg-white px-3 py-2 text-xs text-emerald-900"
                      onClick={() => onAcknowledgeMilestone(topMilestone.id)}
                    >
                      Mark seen
                    </button>
                  </div>
                </div>
              )}

              {retention?.reminder && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-amber-900/70">Return cue</p>
                      <p className="mt-1 text-sm font-semibold text-amber-950">{retention.reminder.title}</p>
                      <p className="mt-1 text-sm text-amber-900">{retention.reminder.message}</p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      {reminderHref && (
                        <Link
                          href={reminderHref}
                          className="rounded-md bg-amber-700 px-3 py-2 text-xs font-medium text-white"
                        >
                          Resume
                        </Link>
                      )}
                      <button
                        type="button"
                        className="rounded-md border border-amber-300 bg-white px-3 py-2 text-xs text-amber-900"
                        onClick={onDismissReminder}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {retention?.unlock_anticipation && (
                <div className="rounded-xl border border-black/10 bg-paper/35 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Unlock horizon</p>
                      <p className="mt-1 text-sm font-semibold text-black">{retention.unlock_anticipation.skill_name}</p>
                    </div>
                    <span className="rounded-full border border-black/15 bg-white px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-black/62">
                      {retention.unlock_anticipation.status_label}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-black/68">{retention.unlock_anticipation.why_locked}</p>
                  <ul className="mt-2 space-y-1 text-xs text-black/62">
                    {retention.unlock_anticipation.steps.slice(0, 2).map((step) => (
                      <li key={step} className="flex gap-2">
                        <span className="mt-[2px] text-black/38">•</span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ul>
                  {unlockNextHref && (
                    <Link
                      href={unlockNextHref}
                      className="mt-3 inline-flex rounded-md border border-black/15 bg-white px-3 py-2 text-xs text-black/80"
                    >
                      Prep the unlock
                    </Link>
                  )}
                </div>
              )}

              {!topMilestone && !retention?.reminder && !retention?.unlock_anticipation && !loadingRetention && (
                <p className="text-sm text-black/58">
                  Your study home is in rhythm. The primary next step is the clearest move right now.
                </p>
              )}
            </div>
          </article>
        </div>
      </section>

      <section className="mb-7 grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)] xl:grid-cols-[minmax(0,1.68fr)_minmax(340px,1fr)]">
        <article className="rounded-3xl border border-black/10 bg-[linear-gradient(165deg,rgba(255,255,255,0.95),rgba(241,249,236,0.9))] p-4 shadow-[0_20px_52px_rgba(16,19,33,0.14)] md:p-5">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-black/58">Living Study Constellation</p>
              <p className="mt-1 text-sm text-black/66">
                Follow the core trunk, inspect context here, then open the workspace when you are ready to study.
              </p>
              <p className="mt-1 text-xs text-black/52">Branch opportunities are intentionally sparse and shown one at a time.</p>
            </div>
            {selectedNode && (
              <Link
                href={`/topics/${topicId}/skills/${selectedNode.id}`}
                className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-black/80 hover:bg-black/[0.03]"
              >
                Open selected workspace
              </Link>
            )}
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2.5 text-[10px] uppercase tracking-[0.14em] text-black/58">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-zinc-400" /> Locked
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-sky-400" /> Available
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-amber-400" /> In progress
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400" /> Verified
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-violet-400" /> Optional branch
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-2 w-2 rounded-full bg-fuchsia-400" /> Suggested branch (active)
            </span>
          </div>

          <PremiumSkillTree nodes={tree.nodes} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />
        </article>

        <div className="lg:sticky lg:top-4">
          <SkillNodeInspector
            topicId={topicId}
            node={selectedNode}
            prerequisites={selectedPrerequisites}
            branchSuggestions={selectedNode ? (branchSuggestionsByNode[selectedNode.id] || []).slice(0, 1) : []}
            branchSuggestionsLoading={selectedNode ? !!branchSuggestionLoadingByNode[selectedNode.id] : false}
            branchActionLoading={selectedNode ? !!branchActionLoadingByNode[selectedNode.id] : false}
            branchError={selectedNode ? branchErrorByNode[selectedNode.id] || '' : ''}
            onCreateBranch={(input) => {
              if (!selectedNode) return;
              void handleCreateBranch(selectedNode.id, input);
            }}
            onGenerateSuggestions={() => {
              if (!selectedNode) return;
              void handleGenerateBranchSuggestions(selectedNode.id);
            }}
            onAcceptSuggestion={(suggestionId) => {
              if (!selectedNode) return;
              void handleAcceptBranchSuggestion(selectedNode.id, suggestionId);
            }}
            onRejectSuggestion={(suggestionId) => {
              if (!selectedNode) return;
              void handleRejectBranchSuggestion(selectedNode.id, suggestionId);
            }}
            canForceUnlock={Boolean(retention?.dev_unlock_enabled)}
            forcingUnlock={forcingUnlock}
            onForceUnlock={onForceUnlock}
          />
        </div>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
