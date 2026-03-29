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
        recommendations: [],
        tree,
      }),
    [retention, topicId, tree]
  );

  const totalNodes = retention?.total_nodes ?? tree?.nodes.length ?? 0;
  const unlockedNodes = retention?.available_nodes ?? tree?.nodes.filter((node) => node.status !== 'locked').length ?? 0;
  const verifiedNodes = retention?.verified_nodes ?? tree?.nodes.filter((node) => node.progress_state === 'verified').length ?? 0;
  const masteryAvg = Math.round((retention?.mastery_average ?? 0) * 100);

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
      purpose: 'exploration' | 'specialization' | 'enrichment' | 'remediation';
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
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-black/58">
            <Link href="/topics" className="underline underline-offset-4">
              Topics
            </Link>
            <span>/</span>
            <span>{tree.topic.name}</span>
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">{tree.topic.name}</h1>
          <p className="muted mt-2 max-w-3xl text-sm md:text-base">
            {tree.topic.description || 'Continue your progression path through this topic skill constellation.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="badge border border-black/15 bg-white">Growth Stage {retention?.tree_stage || 1}</span>
            <span className="badge border border-black/15 bg-white">{formatDisplayTag(tree.topic.course_depth)} Course</span>
            <span className="badge border border-black/15 bg-white">{formatDisplayTag(tree.topic.starting_skill_level)} Start</span>
            <span className="badge border border-black/15 bg-white">{formatDisplayTag(tree.topic.technical_depth)} Depth</span>
            {retention && <span className="badge border border-black/15 bg-white">{retention.cadence === 'daily' ? 'Daily Plan' : 'Weekly Plan'}</span>}
            {!!retention?.streak_days && <span className="badge border border-black/15 bg-white">{retention.streak_days}-Day Streak</span>}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link href="/garden" className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Garden
          </Link>
          <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Notes
          </Link>
          <Link href={`/topics/${topicId}/chat`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            Tutor chat
          </Link>
          <Link href={primaryNextStep.href} className="rounded-md bg-ink px-3 py-2 text-sm text-white">
            {primaryNextStep.label}
          </Link>
            <button
              type="button"
              className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              onClick={() => refreshEverything()}
            >
              Refresh
            </button>
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
            This deletes the topic, skill tree, generated content, assessment history, notes, and source documents.
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

      <section className="mb-5 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <article className="panel p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-black/62">Progress overview</h2>
          <div className="space-y-3">
            <CompactProgressBar label="Unlocked nodes" value={unlockedNodes} total={totalNodes} tone="cyan" />
            <CompactProgressBar label="Verified nodes" value={verifiedNodes} total={totalNodes} tone="emerald" />
          </div>
        </article>
        <article className="panel grid grid-cols-3 gap-3 p-4">
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-black/58">Total</p>
            <p className="mt-1 text-xl font-semibold">{totalNodes}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-black/58">Unlocked</p>
            <p className="mt-1 text-xl font-semibold">{unlockedNodes}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-black/58">Mastery</p>
            <p className="mt-1 text-xl font-semibold">{masteryAvg}%</p>
          </div>
        </article>
      </section>

      <section className="mb-7 grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)] xl:grid-cols-[minmax(0,1.68fr)_minmax(340px,1fr)]">
        <article className="rounded-3xl border border-black/10 bg-[linear-gradient(165deg,rgba(255,255,255,0.95),rgba(241,249,236,0.9))] p-4 shadow-[0_20px_52px_rgba(16,19,33,0.14)] md:p-5">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-black/58">Skill Constellation</p>
              <p className="mt-1 text-sm text-black/66">Follow the core trunk and grow optional offshoot branches as your interests evolve.</p>
              <p className="mt-1 text-xs text-black/52">
                Select an unlocked node to continue learning. Recommended branch opportunities appear one at a time in the inspector.
              </p>
            </div>
            {selectedNode && (
              <Link
                href={`/topics/${topicId}/skills/${selectedNode.id}`}
                className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-black/80 hover:bg-black/[0.03]"
              >
                Open workspace
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
              <span className="inline-flex h-2 w-2 rounded-full bg-fuchsia-400" /> Recommended branch (active)
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

      <section className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <article className="panel p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-black/55">Primary Next Step</p>
          <h2 className="mt-2 text-2xl font-semibold">{primaryNextStep.label}</h2>
          <p className="muted mt-2 text-sm">{primaryNextStep.reason}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href={primaryNextStep.href} className="rounded-md bg-ink px-3 py-2 text-sm text-white">
              Start now
            </Link>
            <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
              Reflect in journal
            </Link>
          </div>
          {retention?.plan_summary && <p className="mt-3 text-xs text-black/58">{retention.plan_summary}</p>}
        </article>

        <article className="panel p-5">
          <p className="text-xs uppercase tracking-[0.16em] text-black/55">Learning Loop</p>
          <ol className="mt-3 space-y-2 text-sm">
            {LEARNING_LOOP_LABELS.map((item, index) => {
              const active = item.id === primaryNextStep.loopStep;
              return (
                <li
                  key={item.id}
                  className={`rounded-md border px-3 py-2 ${
                    active ? 'border-ink bg-ink/5 text-black' : 'border-black/10 bg-white text-black/68'
                  }`}
                >
                  <span className="mr-2 text-xs text-black/55">{index + 1}.</span>
                  {item.label}
                </li>
              );
            })}
          </ol>
          {retention?.unlock_anticipation && (
            <div className="mt-4 rounded-md border border-black/10 bg-white p-3 text-xs text-black/68">
              <p className="font-semibold">{retention.unlock_anticipation.skill_name}</p>
              <p className="mt-1">{retention.unlock_anticipation.why_locked}</p>
            </div>
          )}
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
