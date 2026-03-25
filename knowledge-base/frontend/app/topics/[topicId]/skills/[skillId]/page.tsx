'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  generateQuiz,
  generateResource,
  getExternalResources,
  getRecommendations,
  getSkillTree,
  submitQuiz,
  updateProgress
} from '@/lib/api';
import {
  ExternalResource,
  Quiz,
  QuizSubmissionResult,
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
import { TopicHeader } from '@/components/topic-header';

type LearningTab = 'overview' | 'lesson' | 'examples' | 'exercises' | 'quiz' | 'resources';
type ResourceKind = 'lesson' | 'examples' | 'exercises';
type ProgressState = 'not_started' | 'learning' | 'completed' | 'verified';

type NodeCache = {
  resources: Partial<Record<ResourceKind, Resource>>;
  quiz?: Quiz;
  quizResult?: QuizSubmissionResult;
  externalResources?: ExternalResource[];
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

function sourceCopy(source: 'stored' | 'generated' | 'regenerated'): string {
  if (source === 'stored') return 'Loaded from saved content';
  if (source === 'generated') return 'Generated and saved';
  return 'Regenerated and saved';
}

const tabs: Array<{ id: LearningTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'lesson', label: 'Lesson' },
  { id: 'examples', label: 'Examples' },
  { id: 'exercises', label: 'Exercises' },
  { id: 'quiz', label: 'Quiz' },
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
      <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${complete ? 'bg-emerald-500 text-white' : 'bg-zinc-200 text-zinc-700'}`}>
        {complete ? 'OK' : '--'}
      </span>
      <span>{label}</span>
    </li>
  );
}

export default function SkillWorkspacePage({ params }: { params: { topicId: string; skillId: string } }) {
  const topicId = params.topicId;
  const routeSkillId = Number(params.skillId);

  const [tree, setTree] = useState<SkillTree | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [activeTab, setActiveTab] = useState<LearningTab>('overview');

  const [contentCache, setContentCache] = useState<Record<number, NodeCache>>({});
  const [quizAnswersByNode, setQuizAnswersByNode] = useState<Record<number, Record<number, number>>>({});
  const [loadingByKey, setLoadingByKey] = useState<Record<string, boolean>>({});
  const [errorByKey, setErrorByKey] = useState<Record<string, string>>({});

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');

  const selectedSkill = useMemo(() => {
    if (!tree?.nodes?.length) return null;
    return tree.nodes.find((node) => node.id === routeSkillId) || null;
  }, [tree, routeSkillId]);

  const currentNodeCache = useMemo(() => {
    if (!selectedSkill) return undefined;
    return contentCache[selectedSkill.id] || { resources: {} };
  }, [contentCache, selectedSkill]);

  const quizAnswers = useMemo(() => {
    if (!selectedSkill) return {};
    return quizAnswersByNode[selectedSkill.id] || {};
  }, [quizAnswersByNode, selectedSkill]);

  const refreshTopicData = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const [nextTree, recs] = await Promise.all([getSkillTree(topicId), getRecommendations(topicId)]);
      setTree(nextTree);
      setRecommendations(recs);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : 'Failed to load skill workspace');
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    refreshTopicData();
  }, [refreshTopicData]);

  useEffect(() => {
    setActiveTab('overview');
  }, [routeSkillId]);

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
      await refreshTopicData();
    } catch (err) {
      setErrorState(kind, err instanceof Error ? err.message : `Failed to load ${kind}`, nodeId);
    } finally {
      setLoadingState(kind, false, nodeId);
    }
  }

  async function ensureExternalResources(force = false) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
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

  async function ensureQuiz(forceRegenerate = false) {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    const existing = contentCache[nodeId]?.quiz;
    if (existing && !forceRegenerate) return;

    setLoadingState('quiz', true, nodeId);
    setErrorState('quiz', '', nodeId);
    try {
      const quiz = await generateQuiz(nodeId, 1, 3, forceRegenerate);
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            quiz,
            quizResult: forceRegenerate ? undefined : nodeCache.quizResult
          }
        };
      });
      setQuizAnswersByNode((prev) => ({ ...prev, [nodeId]: {} }));
    } catch (err) {
      setErrorState('quiz', err instanceof Error ? err.message : 'Failed to generate quiz', nodeId);
    } finally {
      setLoadingState('quiz', false, nodeId);
    }
  }

  async function handleSubmitQuiz() {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;
    const quiz = contentCache[nodeId]?.quiz;
    if (!quiz) return;

    const answers = quiz.questions.map((_, index) => quizAnswersByNode[nodeId]?.[index] ?? -1);

    setLoadingState('quiz-submit', true, nodeId);
    setErrorState('quiz', '', nodeId);
    try {
      const result = await submitQuiz(quiz.assessment_id, answers);
      setContentCache((prev) => {
        const nodeCache = prev[nodeId] || { resources: {} };
        return {
          ...prev,
          [nodeId]: {
            ...nodeCache,
            quizResult: result
          }
        };
      });
      await refreshTopicData();
    } catch (err) {
      setErrorState('quiz', err instanceof Error ? err.message : 'Failed to submit quiz', nodeId);
    } finally {
      setLoadingState('quiz-submit', false, nodeId);
    }
  }

  async function handleProgressUpdate(action: 'complete_lesson' | 'complete_exercises') {
    if (!selectedSkill) return;
    const nodeId = selectedSkill.id;

    setLoadingState('progress', true, nodeId);
    setErrorState('progress', '', nodeId);
    try {
      await updateProgress({
        skillId: nodeId,
        action
      });
      await refreshTopicData();
    } catch (err) {
      setErrorState('progress', err instanceof Error ? err.message : 'Failed to update progress', nodeId);
    } finally {
      setLoadingState('progress', false, nodeId);
    }
  }

  async function onTabChange(tab: LearningTab) {
    setActiveTab(tab);
    if (tab === 'lesson') await ensureResource('lesson');
    if (tab === 'examples') await ensureResource('examples');
    if (tab === 'exercises') await ensureResource('exercises');
    if (tab === 'resources') await ensureExternalResources();
    if (tab === 'quiz') await ensureQuiz();
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl p-6 md:p-10">
        <p className="panel p-4 text-sm">Loading skill workspace...</p>
      </main>
    );
  }

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
  const quizLoading = !!loadingByKey[keyFor('quiz', activeNodeId)];
  const quizSubmitLoading = !!loadingByKey[keyFor('quiz-submit', activeNodeId)];
  const resourcesLoading = !!loadingByKey[keyFor('resources', activeNodeId)];

  const lessonResource = currentNodeCache?.resources?.lesson;
  const examplesResource = currentNodeCache?.resources?.examples;
  const exercisesResource = currentNodeCache?.resources?.exercises;
  const externalResources = currentNodeCache?.externalResources || [];
  const quiz = currentNodeCache?.quiz;
  const quizResult = currentNodeCache?.quizResult;

  const lesson = parseLessonContent(lessonResource?.structured_content);
  const examples = parseExamplesContent(examplesResource?.structured_content);
  const exercises = parseExercisesContent(exercisesResource?.structured_content);

  const lessonComplete = selectedSkill.lesson_completed;
  const exercisesComplete = selectedSkill.exercises_completed;
  const quizTaken = selectedSkill.quiz_taken;
  const isVerified = selectedSkill.progress_state === 'verified';
  const bestQuizScorePct =
    typeof selectedSkill.best_quiz_score === 'number' ? Math.round(selectedSkill.best_quiz_score * 100) : null;

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <TopicHeader
        topicId={topicId}
        topicName={tree.topic.name}
        subtitle={`Focused node workspace for ${selectedSkill.name}`}
        rightSlot={
          <button className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm" onClick={refreshTopicData}>
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
                    <span className={`badge border ${statusClasses(node.status)}`}>{node.status.replace('_', ' ')}</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className={`badge border ${progressStateClasses(node.progress_state)}`}>
                      {progressStateLabel(node.progress_state)}
                    </span>
                    <span className="text-xs text-black/65">Difficulty {node.difficulty}</span>
                  </div>
                </Link>
              ))}
            </div>
          </article>

          <article className="panel p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Recommended next nodes</h3>
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
              </div>
              <div className="flex items-center gap-2">
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
                      : 'border-black/15 bg-white text-black hover:border-black/35'
                  }`}
                  onClick={() => onTabChange(tab.id)}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </header>

          {tabError && <p className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{tabError}</p>}

          {activeTab === 'overview' && (
            <div className="space-y-5">
              <section className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-black/60">Node State</p>
                  <p className="mt-2 text-xl font-semibold">{progressStateLabel(selectedSkill.progress_state)}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-black/60">Best Quiz Score</p>
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
                  <ProgressChecklistItem label="Quiz taken" complete={quizTaken} />
                  <ProgressChecklistItem label="Node verified (quiz score at least 70%)" complete={isVerified} />
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
                    className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                    onClick={() => onTabChange('quiz')}
                    type="button"
                  >
                    Open quiz
                  </button>
                </div>
                {!lessonComplete && <p className="muted mt-3 text-xs">Complete the lesson first, then complete exercises, then pass the quiz.</p>}
                {progressError && <p className="mt-3 text-sm text-red-700">{progressError}</p>}
              </section>

              <section className="rounded-xl border border-black/10 bg-white p-4">
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Recommended Next Step</h3>
                <p className="muted mt-2 text-sm leading-relaxed">{selectedSkill.recommended_next_action}</p>
              </section>
            </div>
          )}

          {activeTab === 'lesson' && (
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

          {activeTab === 'examples' && (
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

          {activeTab === 'exercises' && (
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

          {activeTab === 'quiz' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {quiz && <ContentMeta source={quiz.source} version={quiz.version} />}
                <button
                  className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
                  onClick={() => ensureQuiz(!!quiz)}
                  disabled={quizLoading}
                >
                  {quizLoading ? 'Loading...' : quiz ? 'Regenerate quiz' : 'Generate quiz'}
                </button>
              </div>

              {quizLoading && <p className="rounded-md border border-black/10 bg-white p-3 text-sm">Loading quiz...</p>}

              {quiz && (
                <div className="space-y-4">
                  <div className="rounded-lg border border-black/10 bg-white p-3 text-xs text-black/70">
                    Score at least <span className="font-semibold">70%</span> to verify this node.
                  </div>
                  <h3 className="text-xl font-semibold">{quiz.title}</h3>
                  {quiz.questions.map((question, questionIndex) => (
                    <article key={question.id} className="rounded-xl border border-black/10 bg-white p-4">
                      <p className="text-sm font-semibold">
                        {questionIndex + 1}. {question.prompt}
                      </p>
                      <div className="mt-3 space-y-2">
                        {question.choices.map((choice, choiceIndex) => (
                          <label
                            key={`${question.id}-${choiceIndex}`}
                            className="flex cursor-pointer items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-sm"
                          >
                            <input
                              type="radio"
                              name={`q-${activeNodeId}-${questionIndex}`}
                              checked={quizAnswers[questionIndex] === choiceIndex}
                              onChange={() =>
                                setQuizAnswersByNode((prev) => ({
                                  ...prev,
                                  [activeNodeId]: {
                                    ...(prev[activeNodeId] || {}),
                                    [questionIndex]: choiceIndex
                                  }
                                }))
                              }
                            />
                            <span>{choice}</span>
                          </label>
                        ))}
                      </div>
                    </article>
                  ))}

                  <button
                    className="rounded-md bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
                    onClick={handleSubmitQuiz}
                    disabled={quizSubmitLoading}
                  >
                    {quizSubmitLoading ? 'Submitting...' : 'Submit quiz'}
                  </button>
                </div>
              )}

              {quizResult && (
                <section className="rounded-xl border border-black/10 bg-white p-4">
                  <p className="text-sm">
                    Score: <strong>{(quizResult.score * 100).toFixed(0)}%</strong>
                  </p>
                  <p className="muted mt-1 text-sm">
                    State after submission: <strong>{progressStateLabel(quizResult.updated_progress_state)}</strong>
                  </p>
                  <p className="muted text-sm">Internal mastery signal: {(quizResult.updated_mastery * 100).toFixed(0)}%</p>

                  <div className="mt-3 space-y-2 text-sm">
                    {quizResult.feedback.map((item) => (
                      <div key={item.question_id} className="rounded-md border border-black/10 bg-white p-3">
                        <p className={item.correct ? 'text-emerald-700' : 'text-red-700'}>
                          {item.correct ? 'Correct' : 'Needs review'}
                        </p>
                        <p className="muted mt-1">{item.explanation}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}

          {activeTab === 'resources' && (
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
