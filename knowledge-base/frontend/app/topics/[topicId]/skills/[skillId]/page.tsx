'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  createDeepDiveBranch,
  generateAssessment,
  generateResource,
  getExternalResources,
  getRecommendations,
  getSkillTree,
  submitAssessment,
  updateProgress
} from '@/lib/api';
import { readRecommendationCache, readSkillTreeCache, writeRecommendationCache, writeSkillTreeCache } from '@/lib/cache';
import {
  Assessment,
  AssessmentResponseInput,
  AssessmentSubmissionResult,
  ExternalResource,
  RecommendationItem,
  Resource,
  SkillNode,
  SkillTree
} from '@/lib/types';
import {
  ExamplesRenderer,
  ExercisesRenderer,
  LessonRenderer,
  parseExamplesContent,
  parseExercisesContent,
  parseLessonContent
} from '@/components/learning-content';
import { SkillWorkspaceSkeleton } from '@/components/page-skeletons';
import { TopicHeader } from '@/components/topic-header';

type LearningTab = 'overview' | 'lesson' | 'examples' | 'exercises' | 'quiz' | 'resources';
type ResourceKind = 'lesson' | 'examples' | 'exercises';
type ProgressState = 'not_started' | 'learning' | 'completed' | 'verified';

type NodeCache = {
  resources: Partial<Record<ResourceKind, Resource>>;
  assessment?: Assessment;
  assessmentResult?: AssessmentSubmissionResult;
  externalResources?: ExternalResource[];
};

type AssessmentDraft = {
  selected_option_index?: number;
  answer_text?: string;
};

function statusClasses(status: SkillNode['status']): string {
  if (status === 'mastered') return 'bg-emerald-100 text-emerald-900 border-emerald-300';
  if (status === 'in_progress') return 'bg-amber-100 text-amber-900 border-amber-300';
  if (status === 'available') return 'bg-sky-100 text-sky-900 border-sky-300';
  return 'bg-zinc-100 text-zinc-700 border-zinc-300';
}

function progressStateLabel(state: ProgressState): string {
  if (state === 'not_started') return 'Not started';
  if (state === 'learning') return 'Learning';
  if (state === 'completed') return 'Completed';
  return 'Verified';
}

function progressStateClasses(state: ProgressState): string {
  if (state === 'verified') return 'bg-emerald-100 text-emerald-900 border-emerald-300';
  if (state === 'completed') return 'bg-sky-100 text-sky-900 border-sky-300';
  if (state === 'learning') return 'bg-amber-100 text-amber-900 border-amber-300';
  return 'bg-zinc-100 text-zinc-700 border-zinc-300';
}

function nodeKindClasses(nodeKind: SkillNode['node_kind']): string {
  if (nodeKind === 'optional_branch') return 'bg-violet-100 text-violet-800 border-violet-300';
  return 'bg-white text-black/70 border-black/20';
}

function sourceCopy(source: 'stored' | 'generated' | 'regenerated'): string {
  if (source === 'stored') return 'Loaded from saved content';
  if (source === 'generated') return 'Generated and saved';
  return 'Regenerated and saved';
}

function questionTypeLabel(questionType: Assessment['questions'][number]['question_type']): string {
  if (questionType === 'multiple_choice') return 'Multiple choice';
  if (questionType === 'short_answer') return 'Short answer';
  if (questionType === 'explain') return 'Explain';
  if (questionType === 'scenario') return 'Applied scenario';
  if (questionType === 'error_spotting') return 'Error spotting';
  return 'Reflection';
}

const tabs: Array<{ id: LearningTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'lesson', label: 'Lesson' },
  { id: 'examples', label: 'Examples' },
  { id: 'exercises', label: 'Exercises' },
  { id: 'quiz', label: 'Assessment' },
  { id: 'resources', label: 'Resources' }
];

function ContentMeta({ source, version }: { source: 'stored' | 'generated' | 'regenerated'; version: number }) {
  return (
    <div className="rounded-lg border border-black/10 bg-white px-3 py-2 text-xs text-black/70">
      <p>
        <span className="font-semibold">Version {version}</span> · {sourceCopy(source)}
      </p>
    </div>
  );
}

function ProgressChecklistItem({ label, complete }: { label: string; complete: boolean }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${
          complete ? 'bg-emerald-500 text-white' : 'bg-zinc-200 text-zinc-700'
        }`}
      >
        {complete ? 'OK' : '--'}
      </span>
      <span>{label}</span>
    </li>
  );
}

export default function SkillWorkspacePage({ params }: { params: { topicId: string; skillId: string } }) {
  const topicId = params.topicId;
  const routeSkillId = Number(params.skillId);
  const searchParams = useSearchParams();
  const cachedTree = readSkillTreeCache(topicId);
  const cachedRecommendations = readRecommendationCache(topicId) || [];

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>(cachedRecommendations);
  const [activeTab, setActiveTab] = useState<LearningTab>('overview');

  const [contentCache, setContentCache] = useState<Record<number, NodeCache>>({});
  const [assessmentDraftsByNode, setAssessmentDraftsByNode] = useState<
    Record<number, Record<number, AssessmentDraft>>
  >({});
  const [loadingByKey, setLoadingByKey] = useState<Record<string, boolean>>({});
  const [errorByKey, setErrorByKey] = useState<Record<string, string>>({});

  const [loadingTree, setLoadingTree] = useState(!cachedTree);
  const [loadingRecommendations, setLoadingRecommendations] = useState(cachedRecommendations.length === 0);
  const [deepDiveFocus, setDeepDiveFocus] = useState('');
  const [pageError, setPageError] = useState('');

  const selectedSkill = useMemo(() => {
    if (!tree?.nodes?.length) return null;
    return tree.nodes.find((node) => node.id === routeSkillId) || null;
  }, [tree, routeSkillId]);

  const currentNodeCache = useMemo(() => {
    if (!selectedSkill) return undefined;
    return contentCache[selectedSkill.id] || { resources: {} };
  }, [contentCache, selectedSkill]);

  const assessmentDrafts = useMemo(() => {
    if (!selectedSkill) return {};
    return assessmentDraftsByNode[selectedSkill.id] || {};
  }, [assessmentDraftsByNode, selectedSkill]);

  const loadTree = useCallback(
    async (showLoader = false) => {
      if (showLoader) setLoadingTree(true);
      try {
        const nextTree = await getSkillTree(topicId);
        setTree(nextTree);
        writeSkillTreeCache(topicId, nextTree);
      } catch (err) {
        setPageError(err instanceof Error ? err.message : 'Failed to load skill workspace');
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
        const recs = await getRecommendations(topicId, refresh);
        setRecommendations(recs);
        writeRecommendationCache(topicId, recs);
      } catch (err) {
        setPageError(err instanceof Error ? err.message : 'Failed to load recommendations');
      } finally {
        setLoadingRecommendations(false);
      }
    },
    [topicId]
  );

  const refreshTopicData = useCallback(
    async (refreshRecommendations = false) => {
      setPageError('');
      await loadTree(false);
      if (refreshRecommendations) {
        await loadRecommendations(true);
      }
    },
    [loadRecommendations, loadTree]
  );

  useEffect(() => {
    loadTree();
    loadRecommendations();
  }, [loadRecommendations, loadTree]);

  useEffect(() => {
    const requested = (searchParams.get('tab') || 'overview') as LearningTab;
    if (tabs.some((item) => item.id === requested)) {
      setActiveTab(requested);
      return;
    }
    setActiveTab('overview');
  }, [routeSkillId, searchParams]);

  function keyFor(type: string, skillId?: number) {
    const id = skillId || selectedSkill?.id || 0;
    return `${id}:${type}`;
  }

  function setLoadingState(type: string, value: boolean, skillId?: number) {
    const key = keyFor(type, skillId);
    setLoadingByKey((prev) => ({ ...prev, [key]: value }));
  }

  function setErrorState(type: string, message: string, skillId?: number) {
    const key = keyFor(type, skillId);
    setErrorByKey((prev) => ({ ...prev, [key]: message }));
  }

  async function ensureResource(kind: ResourceKind, forceRegenerate = false) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState(kind, selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }
    const existing = contentCache[nodeId]?.resources?.[kind];
    if (existing && !forceRegenerate) return;

    setLoadingState(kind, true, nodeId);
    setErrorState(kind, '', nodeId);
    try {
      const resource = await generateResource({
        skillId: nodeId,
        kind,
        regenerate: forceRegenerate
      });
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            resources: {
              ...nodeCache.resources,
              [kind]: resource
            }
          }
        };
      });
      await loadTree(false);
    } catch (err) {
      setErrorState(kind, err instanceof Error ? err.message : `Failed to load ${kind}`, nodeId);
    } finally {
      setLoadingState(kind, false, nodeId);
    }
  }

  async function ensureExternalResources(force = false) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState('resources', selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }
    const existing = contentCache[nodeId]?.externalResources;
    if (existing && existing.length > 0 && !force) return;

    setLoadingState('resources', true, nodeId);
    setErrorState('resources', '', nodeId);
    try {
      const resources = await getExternalResources(nodeId);
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            externalResources: resources
          }
        };
      });
    } catch (err) {
      setErrorState('resources', err instanceof Error ? err.message : 'Failed to fetch resources', nodeId);
    } finally {
      setLoadingState('resources', false, nodeId);
    }
  }

  async function ensureAssessment(forceRegenerate = false) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState('quiz', selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }

    const existing = contentCache[nodeId]?.assessment;
    if (existing && !forceRegenerate) return;

    setLoadingState('quiz', true, nodeId);
    setErrorState('quiz', '', nodeId);
    try {
      const assessment = await generateAssessment({
        topic_id: Number(topicId),
        skill_node_id: nodeId,
        question_count: 6,
        regenerate: forceRegenerate
      });
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            assessment,
            assessmentResult: forceRegenerate ? undefined : nodeCache.assessmentResult
          }
        };
      });
      setAssessmentDraftsByNode((prev) => ({ ...prev, [nodeId]: {} }));
    } catch (err) {
      setErrorState('quiz', err instanceof Error ? err.message : 'Failed to generate assessment', nodeId);
    } finally {
      setLoadingState('quiz', false, nodeId);
    }
  }

  async function handleSubmitAssessment() {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState('quiz', selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }
    const assessment = contentCache[nodeId]?.assessment;
    if (!assessment) return;

    const responses: AssessmentResponseInput[] = [];
    for (const question of assessment.questions) {
      const draft = assessmentDraftsByNode[nodeId]?.[question.id] || {};
      if (question.question_type === 'multiple_choice') {
        if (typeof draft.selected_option_index !== 'number') {
          setErrorState('quiz', 'Please answer all multiple-choice questions before submitting.', nodeId);
          return;
        }
        responses.push({
          question_id: question.id,
          selected_option_index: draft.selected_option_index
        });
        continue;
      }
      const answer = (draft.answer_text || '').trim();
      if (!answer) {
        setErrorState('quiz', 'Please answer all open questions before submitting.', nodeId);
        return;
      }
      responses.push({
        question_id: question.id,
        answer_text: answer
      });
    }

    setLoadingState('quiz-submit', true, nodeId);
    setErrorState('quiz', '', nodeId);
    try {
      const result = await submitAssessment(assessment.id, responses);
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            assessmentResult: result
          }
        };
      });
      await refreshTopicData(true);
    } catch (err) {
      setErrorState('quiz', err instanceof Error ? err.message : 'Failed to submit assessment', nodeId);
    } finally {
      setLoadingState('quiz-submit', false, nodeId);
    }
  }

  async function handleProgressUpdate(action: 'complete_lesson' | 'complete_exercises') {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState('progress', selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }

    setLoadingState('progress', true, nodeId);
    setErrorState('progress', '', nodeId);
    try {
      await updateProgress({
        skillId: nodeId,
        action
      });
      await refreshTopicData(true);
    } catch (err) {
      setErrorState('progress', err instanceof Error ? err.message : 'Failed to update progress', nodeId);
    } finally {
      setLoadingState('progress', false, nodeId);
    }
  }

  async function handleDeepDive() {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    if (selectedSkill.status === 'locked') {
      setErrorState('deep-dive', selectedSkill.lock_reason || 'This node is locked. Complete prerequisites first.', nodeId);
      return;
    }

    setLoadingState('deep-dive', true, nodeId);
    setErrorState('deep-dive', '', nodeId);
    try {
      const nextTree = await createDeepDiveBranch({
        skillId: nodeId,
        focus: deepDiveFocus.trim() || undefined,
        branch_size: 3
      });
      setTree(nextTree);
      writeSkillTreeCache(topicId, nextTree);
      setDeepDiveFocus('');
      await loadRecommendations(true);
    } catch (err) {
      setErrorState('deep-dive', err instanceof Error ? err.message : 'Failed to create deep-dive branch', nodeId);
    } finally {
      setLoadingState('deep-dive', false, nodeId);
    }
  }

  async function onTabChange(tab: LearningTab) {
    if (selectedSkill?.status === 'locked' && tab !== 'overview') {
      return;
    }
    setActiveTab(tab);
    if (tab === 'lesson') await ensureResource('lesson');
    if (tab === 'examples') await ensureResource('examples');
    if (tab === 'exercises') await ensureResource('exercises');
    if (tab === 'resources') await ensureExternalResources();
    if (tab === 'quiz') await ensureAssessment();
  }

  function updateAssessmentDraft(questionId: number, patch: AssessmentDraft) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    setAssessmentDraftsByNode((prev) => ({
      ...prev,
      [nodeId]: {
        ...(prev[nodeId] || {}),
        [questionId]: {
          ...(prev[nodeId]?.[questionId] || {}),
          ...patch
        }
      }
    }));
  }

  if (!tree && loadingTree) return <SkillWorkspaceSkeleton />;

  if (!tree || !selectedSkill) {
    return (
      <main className="mx-auto max-w-7xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Skill not found.</p>
      </main>
    );
  }

  const activeNodeId = selectedSkill.id;
  const tabError = errorByKey[keyFor(activeTab, activeNodeId)] || '';
  const progressError = errorByKey[keyFor('progress', activeNodeId)] || '';
  const progressLoading = !!loadingByKey[keyFor('progress', activeNodeId)];

  const lessonLoading = !!loadingByKey[keyFor('lesson', activeNodeId)];
  const examplesLoading = !!loadingByKey[keyFor('examples', activeNodeId)];
  const exercisesLoading = !!loadingByKey[keyFor('exercises', activeNodeId)];
  const assessmentLoading = !!loadingByKey[keyFor('quiz', activeNodeId)];
  const assessmentSubmitLoading = !!loadingByKey[keyFor('quiz-submit', activeNodeId)];
  const resourcesLoading = !!loadingByKey[keyFor('resources', activeNodeId)];
  const deepDiveLoading = !!loadingByKey[keyFor('deep-dive', activeNodeId)];
  const deepDiveError = errorByKey[keyFor('deep-dive', activeNodeId)] || '';

  const lessonResource = currentNodeCache?.resources?.lesson;
  const examplesResource = currentNodeCache?.resources?.examples;
  const exercisesResource = currentNodeCache?.resources?.exercises;
  const externalResources = currentNodeCache?.externalResources || [];
  const assessment = currentNodeCache?.assessment;
  const assessmentResult = currentNodeCache?.assessmentResult;

  const lesson = parseLessonContent(lessonResource?.structured_content);
  const examples = parseExamplesContent(examplesResource?.structured_content);
  const exercises = parseExercisesContent(exercisesResource?.structured_content);

  const lessonComplete = selectedSkill.lesson_completed;
  const exercisesComplete = selectedSkill.exercises_completed;
  const quizTaken = selectedSkill.quiz_taken;
  const isVerified = selectedSkill.progress_state === 'verified';
  const isLocked = selectedSkill.status === 'locked';
  const bestQuizScorePct =
    typeof selectedSkill.best_quiz_score === 'number' ? Math.round(selectedSkill.best_quiz_score * 100) : null;

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <TopicHeader
        topicId={topicId}
        topicName={tree.topic.name}
        subtitle={`Focused node workspace for ${selectedSkill.name}`}
        rightSlot={
          <button
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            onClick={() => refreshTopicData(true)}
          >
            Refresh
          </button>
        }
      />

      <section className="grid gap-6 lg:grid-cols-[0.95fr_2fr]">
        <aside className="space-y-4">
          <article className="panel p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Skill Nodes</h2>
            <div className="space-y-2">
              {tree.nodes.map((node) => (
                <Link
                  key={node.id}
                  href={`/topics/${topicId}/skills/${node.id}`}
                  className={`block rounded-lg border p-3 text-sm transition ${
                    node.id === activeNodeId ? 'border-ink bg-white' : 'border-black/10 bg-white/80'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold leading-snug">{node.name}</p>
                    <div className="flex flex-wrap items-center gap-1">
                      {node.node_kind === 'optional_branch' && (
                        <span className={`badge border ${nodeKindClasses(node.node_kind)}`}>Optional</span>
                      )}
                      <span className={`badge border ${statusClasses(node.status)}`}>{node.status.replace('_', ' ')}</span>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className={`badge border ${progressStateClasses(node.progress_state)}`}>
                      {progressStateLabel(node.progress_state)}
                    </span>
                    <span className="text-xs text-black/65">Difficulty {node.difficulty}</span>
                  </div>
                  {node.status === 'locked' && node.lock_reason && (
                    <p className="mt-2 text-xs text-red-700">{node.lock_reason}</p>
                  )}
                </Link>
              ))}
            </div>
          </article>

          <article className="panel p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Recommended next nodes</h3>
            {loadingRecommendations && <p className="mt-2 text-xs text-black/60">Updating recommendations...</p>}
            <div className="mt-3 space-y-2">
              {recommendations.map((rec) => (
                <Link
                  key={rec.skill_node_id}
                  href={`/topics/${topicId}/skills/${rec.skill_node_id}`}
                  className="block rounded-lg border border-black/10 bg-white p-2 text-xs"
                >
                  <p className="font-semibold">{rec.skill_name}</p>
                  <p className="muted mt-1">{rec.rationale}</p>
                </Link>
              ))}
              {recommendations.length === 0 && <p className="muted text-xs">No recommendations available.</p>}
            </div>
          </article>
        </aside>

        <section className="panel p-5 md:p-6">
          <header className="mb-5 space-y-3 border-b border-black/10 pb-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-2xl font-semibold leading-tight">{selectedSkill.name}</h2>
                <p className="muted mt-2 max-w-3xl text-sm leading-relaxed">{selectedSkill.description}</p>
                {selectedSkill.status === 'locked' && selectedSkill.lock_reason && (
                  <p className="mt-2 text-sm text-red-700">{selectedSkill.lock_reason}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {selectedSkill.node_kind === 'optional_branch' && (
                  <span className={`badge border ${nodeKindClasses(selectedSkill.node_kind)}`}>Optional branch</span>
                )}
                <span className={`badge border ${progressStateClasses(selectedSkill.progress_state)}`}>
                  {progressStateLabel(selectedSkill.progress_state)}
                </span>
                <span className={`badge border ${statusClasses(selectedSkill.status)}`}>{selectedSkill.status.replace('_', ' ')}</span>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className={`rounded-md border px-3 py-1.5 text-sm transition ${
                    activeTab === tab.id
                      ? 'border-ink bg-ink text-white'
                      : isLocked && tab.id !== 'overview'
                        ? 'cursor-not-allowed border-black/10 bg-black/5 text-black/40'
                        : 'border-black/15 bg-white text-black hover:border-black/35'
                  }`}
                  onClick={() => onTabChange(tab.id)}
                  disabled={isLocked && tab.id !== 'overview'}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </header>

          {tabError && <p className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{tabError}</p>}

          {isLocked && activeTab !== 'overview' && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              This node is locked. Learning content becomes available after you verify prerequisites.
            </div>
          )}

          {activeTab === 'overview' && (
            <div className="space-y-5">
              <section className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-black/60">Node State</p>
                  <p className="mt-2 text-xl font-semibold">{progressStateLabel(selectedSkill.progress_state)}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-black/60">Best Assessment Score</p>
                  <p className="mt-2 text-xl font-semibold">{bestQuizScorePct !== null ? `${bestQuizScorePct}%` : 'Not taken'}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-black/60">Unlock Rule</p>
                  <p className="mt-2 text-sm font-medium">Prereqs must be verified</p>
                </div>
              </section>

              <section className="rounded-xl border border-black/10 bg-white p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Progress Checklist</h3>
                <ul className="mt-3 space-y-2">
                  <ProgressChecklistItem label="Lesson completed" complete={lessonComplete} />
                  <ProgressChecklistItem label="Exercises completed" complete={exercisesComplete} />
                  <ProgressChecklistItem label="Assessment taken" complete={quizTaken} />
                  <ProgressChecklistItem label="Node verified (score at least 70%)" complete={isVerified} />
                </ul>
              </section>

              <section className="rounded-xl border border-black/10 bg-white p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Progress Actions</h3>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    className="rounded-md bg-moss px-3 py-2 text-sm text-white disabled:opacity-50"
                    onClick={() => handleProgressUpdate('complete_lesson')}
                    disabled={progressLoading || selectedSkill.status === 'locked' || lessonComplete}
                  >
                    {lessonComplete ? 'Lesson completed' : 'Mark lesson complete'}
                  </button>
                  <button
                    className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-50"
                    onClick={() => handleProgressUpdate('complete_exercises')}
                    disabled={progressLoading || selectedSkill.status === 'locked' || !lessonComplete || exercisesComplete}
                  >
                    {exercisesComplete ? 'Exercises completed' : 'Mark exercises complete'}
                  </button>
                  <button
                    className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-50"
                    onClick={() => onTabChange('quiz')}
                    disabled={selectedSkill.status === 'locked'}
                    type="button"
                  >
                    Open assessment
                  </button>
                </div>
                {!lessonComplete && <p className="muted mt-3 text-xs">Complete the lesson first, then complete exercises, then pass the assessment.</p>}
                {isLocked && (
                  <p className="mt-3 text-xs text-red-700">
                    This node is locked. Verify prerequisite nodes to unlock learning content.
                  </p>
                )}
                {progressError && <p className="mt-3 text-sm text-red-700">{progressError}</p>}
              </section>

              <section className="rounded-xl border border-black/10 bg-white p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Explore Further (Optional)</h3>
                <p className="muted mt-2 text-sm">
                  Create a side branch with optional modules if you want to go deeper on this node.
                </p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    value={deepDiveFocus}
                    onChange={(event) => setDeepDiveFocus(event.target.value)}
                    className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm sm:max-w-md"
                    placeholder="Optional focus (e.g. groove timing, edge cases, troubleshooting)"
                    maxLength={180}
                  />
                  <button
                    className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-60"
                    onClick={handleDeepDive}
                    disabled={deepDiveLoading || isLocked}
                    type="button"
                  >
                    {deepDiveLoading ? 'Creating branch...' : 'Create optional branch'}
                  </button>
                </div>
                {deepDiveError && <p className="mt-2 text-sm text-red-700">{deepDiveError}</p>}
              </section>

              <section className="rounded-xl border border-black/10 bg-white p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Recommended Next Step</h3>
                <p className="muted mt-2 text-sm leading-relaxed">{selectedSkill.recommended_next_action}</p>
              </section>
            </div>
          )}

          {activeTab === 'lesson' && !isLocked && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {lessonResource && <ContentMeta source={lessonResource.source} version={lessonResource.version} />}
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureResource('lesson', !!lessonResource)}
                  disabled={lessonLoading}
                >
                  {lessonLoading ? 'Loading...' : lessonResource ? 'Regenerate lesson' : 'Generate lesson'}
                </button>
              </div>

              {lessonLoading && <p className="rounded-md border border-black/10 bg-white p-3 text-sm">Loading lesson...</p>}
              {lesson && <LessonRenderer content={lesson} />}
              {!lesson && lessonResource && !lessonLoading && (
                <div className="rounded-xl border border-black/10 bg-white p-4 text-sm">
                  Structured lesson format was invalid. Regenerate to refresh the saved content.
                </div>
              )}
            </div>
          )}

          {activeTab === 'examples' && !isLocked && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {examplesResource && <ContentMeta source={examplesResource.source} version={examplesResource.version} />}
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureResource('examples', !!examplesResource)}
                  disabled={examplesLoading}
                >
                  {examplesLoading ? 'Loading...' : examplesResource ? 'Regenerate examples' : 'Generate examples'}
                </button>
              </div>

              {examplesLoading && <p className="rounded-md border border-black/10 bg-white p-3 text-sm">Loading examples...</p>}
              {examples && <ExamplesRenderer content={examples} />}
              {!examples && examplesResource && !examplesLoading && (
                <div className="rounded-xl border border-black/10 bg-white p-4 text-sm">
                  Structured examples format was invalid. Regenerate to refresh the saved content.
                </div>
              )}
            </div>
          )}

          {activeTab === 'exercises' && !isLocked && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {exercisesResource && <ContentMeta source={exercisesResource.source} version={exercisesResource.version} />}
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureResource('exercises', !!exercisesResource)}
                  disabled={exercisesLoading}
                >
                  {exercisesLoading ? 'Loading...' : exercisesResource ? 'Regenerate exercises' : 'Generate exercises'}
                </button>
              </div>

              {exercisesLoading && <p className="rounded-md border border-black/10 bg-white p-3 text-sm">Loading exercises...</p>}
              {exercises && <ExercisesRenderer content={exercises} />}
              {!exercises && exercisesResource && !exercisesLoading && (
                <div className="rounded-xl border border-black/10 bg-white p-4 text-sm">
                  Structured exercises format was invalid. Regenerate to refresh the saved content.
                </div>
              )}
            </div>
          )}

          {activeTab === 'quiz' && !isLocked && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {assessment && <ContentMeta source={assessment.source} version={assessment.version} />}
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureAssessment(!!assessment)}
                  disabled={assessmentLoading}
                >
                  {assessmentLoading ? 'Loading...' : assessment ? 'Regenerate assessment' : 'Generate assessment'}
                </button>
              </div>

              {assessmentLoading && <p className="rounded-md border border-black/10 bg-white p-3 text-sm">Loading assessment...</p>}

              {assessment && (
                <div className="space-y-4">
                  <div className="rounded-lg border border-black/10 bg-white p-3 text-xs text-black/70">
                    <p>
                      Score at least <span className="font-semibold">70%</span> to verify this node.
                    </p>
                    <p className="mt-1">Difficulty: {assessment.difficulty} · Target level: {assessment.target_level}</p>
                  </div>

                  <h3 className="text-xl font-semibold">{assessment.title}</h3>

                  {assessment.questions.map((question, questionIndex) => {
                    const draft = assessmentDrafts[question.id] || {};
                    const isMCQ = question.question_type === 'multiple_choice';

                    return (
                      <article key={question.id} className="rounded-xl border border-black/10 bg-white p-4">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold">
                            {questionIndex + 1}. {question.prompt}
                          </p>
                          <span className="badge">{questionTypeLabel(question.question_type)}</span>
                        </div>

                        {isMCQ ? (
                          <div className="mt-3 space-y-2">
                            {question.choices.map((choice, choiceIndex) => (
                              <label
                                key={`${question.id}-${choiceIndex}`}
                                className="flex cursor-pointer items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-sm"
                              >
                                <input
                                  type="radio"
                                  name={`q-${activeNodeId}-${question.id}`}
                                  checked={draft.selected_option_index === choiceIndex}
                                  onChange={() => updateAssessmentDraft(question.id, { selected_option_index: choiceIndex })}
                                />
                                <span>{choice}</span>
                              </label>
                            ))}
                          </div>
                        ) : (
                          <textarea
                            value={draft.answer_text || ''}
                            onChange={(event) => updateAssessmentDraft(question.id, { answer_text: event.target.value })}
                            className="mt-3 min-h-[120px] w-full rounded-md border border-black/10 bg-white p-3 text-sm"
                            placeholder="Write your response..."
                            maxLength={4000}
                          />
                        )}

                      </article>
                    );
                  })}

                  <button
                    className="rounded-md bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
                    onClick={handleSubmitAssessment}
                    disabled={assessmentSubmitLoading}
                  >
                    {assessmentSubmitLoading ? 'Submitting...' : 'Submit assessment'}
                  </button>
                </div>
              )}

              {assessmentResult && (
                <section className="space-y-3 rounded-xl border border-black/10 bg-white p-4">
                  <p className="text-sm">
                    Score: <strong>{(assessmentResult.score * 100).toFixed(0)}%</strong>
                  </p>
                  <p className="muted text-sm">
                    Progress state: <strong>{progressStateLabel(assessmentResult.updated_progress_state)}</strong>
                  </p>
                  <p className="muted text-sm">
                    Progress updated. Current mastery estimate: {(assessmentResult.updated_mastery * 100).toFixed(0)}%
                  </p>

                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg border border-black/10 bg-paper/50 p-3">
                      <p className="text-xs uppercase tracking-[0.12em] text-black/65">Strengths</p>
                      <ul className="mt-2 space-y-1 text-sm">
                        {assessmentResult.strengths.map((item) => (
                          <li key={item}>• {item}</li>
                        ))}
                        {assessmentResult.strengths.length === 0 && <li className="text-black/60">No clear strengths captured.</li>}
                      </ul>
                    </div>
                    <div className="rounded-lg border border-black/10 bg-paper/50 p-3">
                      <p className="text-xs uppercase tracking-[0.12em] text-black/65">Weaknesses</p>
                      <ul className="mt-2 space-y-1 text-sm">
                        {assessmentResult.weaknesses.map((item) => (
                          <li key={item}>• {item}</li>
                        ))}
                        {assessmentResult.weaknesses.length === 0 && <li className="text-black/60">No major weaknesses captured.</li>}
                      </ul>
                    </div>
                  </div>

                  <div className="rounded-lg border border-black/10 bg-paper/50 p-3 text-sm">
                    <p>
                      <span className="font-semibold">Review next:</span> {assessmentResult.review_next}
                    </p>
                    <p className="mt-2">
                      <span className="font-semibold">Follow-up:</span> {assessmentResult.recommended_follow_up}
                    </p>
                  </div>

                  <div className="space-y-2">
                    {assessmentResult.feedback.map((item) => (
                      <div key={item.question_id} className="rounded-md border border-black/10 bg-white p-3 text-sm">
                        <p className="font-semibold">
                          Q{item.question_id} · {questionTypeLabel(item.question_type)}
                          {item.question_type === 'reflection' || item.score === null
                            ? ' · Reflection recorded'
                            : ` · ${(item.score * 100).toFixed(0)}%`}
                        </p>
                        <p className="muted mt-1">{item.feedback}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}

          {activeTab === 'resources' && !isLocked && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureExternalResources(true)}
                  disabled={resourcesLoading}
                >
                  {resourcesLoading ? 'Loading...' : 'Refresh resources'}
                </button>
              </div>

              {externalResources.length === 0 && !resourcesLoading && (
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureExternalResources()}
                >
                  Fetch external resources
                </button>
              )}

              <div className="grid gap-3 md:grid-cols-2">
                {externalResources.map((resource) => (
                  <a
                    key={resource.id}
                    href={resource.url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-xl border border-black/10 bg-white p-4"
                  >
                    <p className="text-base font-semibold">{resource.title}</p>
                    <p className="muted mt-2 text-sm leading-relaxed">{resource.summary}</p>
                    <p className="muted mt-2 text-sm">{resource.relevance_reason}</p>
                    <p className="mt-3 truncate text-xs text-black/70">{resource.url}</p>
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
      </section>

      {pageError && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{pageError}</p>}
    </main>
  );
}
