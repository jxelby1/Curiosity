'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { checkTopicPlausibility, createTopicAndInitialize, getMyProgressSummary, listTopics } from '@/lib/api';
import {
  ASSESSMENT_STYLE_OPTIONS,
  COURSE_DEPTH_OPTIONS,
  DEFAULT_ASSESSMENT_STYLES,
  STARTING_SKILL_LEVEL_OPTIONS,
} from '@/lib/course-options';
import { AssessmentStyle, CourseDepth, StartingSkillLevel, Topic, TopicMode, TopicPlausibilityCheck, UserProgressSummary } from '@/lib/types';

const TOPIC_NAME_MAX = 120;
const TOPIC_DESC_MAX = 500;
const TOPIC_GOAL_MAX = 500;

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function stageLabel(stage: number): string {
  if (stage >= 6) return 'Flourishing';
  if (stage >= 5) return 'Mature';
  if (stage >= 4) return 'Growing';
  if (stage >= 3) return 'Developing';
  if (stage >= 2) return 'Sprouting';
  return 'Seed';
}

export function TopicsDashboard() {
  const router = useRouter();
  const { user } = useAuth();

  const [topics, setTopics] = useState<Topic[]>([]);
  const [progressSummary, setProgressSummary] = useState<UserProgressSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [goal, setGoal] = useState('');
  const [topicMode, setTopicMode] = useState<TopicMode>('factual');
  const [courseDepth, setCourseDepth] = useState<CourseDepth>('standard');
  const [startingSkillLevel, setStartingSkillLevel] = useState<StartingSkillLevel>('beginner');
  const [assessmentStyles, setAssessmentStyles] = useState<AssessmentStyle[]>(DEFAULT_ASSESSMENT_STYLES);
  const [assessmentPickerOpen, setAssessmentPickerOpen] = useState(false);
  const [plausibilityPrompt, setPlausibilityPrompt] = useState<TopicPlausibilityCheck | null>(null);
  const [creating, setCreating] = useState(false);

  const topicById = useMemo(() => {
    const map = new Map<number, Topic>();
    for (const topic of topics) {
      map.set(topic.id, topic);
    }
    return map;
  }, [topics]);

  const rankedTopics = useMemo(() => {
    const items =
      progressSummary?.topics ||
      topics.map((topic) => ({
        topic_id: topic.id,
        topic_name: topic.name,
        total_nodes: 0,
        verified_nodes: 0,
        mastery_average: 0,
        tree_stage: 1,
      }));
    return [...items].sort((a, b) => {
      const aProgress = a.total_nodes > 0 ? a.verified_nodes / a.total_nodes : 0;
      const bProgress = b.total_nodes > 0 ? b.verified_nodes / b.total_nodes : 0;
      return bProgress - aProgress;
    });
  }, [progressSummary, topics]);

  const continueTopic = useMemo(() => {
    if (!rankedTopics.length) return null;
    return rankedTopics.find((item) => item.verified_nodes < item.total_nodes) || rankedTopics[0];
  }, [rankedTopics]);

  async function loadDashboard() {
    setLoading(true);
    setError('');
    const [topicsResult, summaryResult] = await Promise.allSettled([
      listTopics(),
      getMyProgressSummary(),
    ]);
    if (topicsResult.status === 'fulfilled') {
      setTopics(topicsResult.value);
    } else {
      setTopics([]);
      setError(
        topicsResult.reason instanceof Error
          ? topicsResult.reason.message
          : 'Failed to load dashboard'
      );
    }
    if (summaryResult.status === 'fulfilled') {
      setProgressSummary(summaryResult.value);
    } else {
      setProgressSummary(null);
    }
    setLoading(false);
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  useEffect(() => {
    setPlausibilityPrompt(null);
  }, [name, description, goal]);

  async function runTopicCreation(modeOverride?: TopicMode, skipPlausibilityCheck = false) {
    const trimmedName = name.trim();
    if (trimmedName.length < 2) {
      setError('Topic name must be at least 2 characters.');
      return;
    }
    if (assessmentStyles.length === 0) {
      setError('Select at least one assessment style.');
      return;
    }

    const effectiveMode = modeOverride ?? topicMode;
    setCreating(true);
    setError('');
    setPlausibilityPrompt(null);
    try {
      if (!skipPlausibilityCheck) {
        const plausibility = await checkTopicPlausibility({
          name: trimmedName,
          description: description.trim(),
          goal: goal.trim(),
          topic_mode: effectiveMode,
        });
        if ((plausibility.status === 'clarify' || plausibility.status === 'block') && effectiveMode === 'factual') {
          setPlausibilityPrompt(plausibility);
          return;
        }
      }

      const result = await createTopicAndInitialize({
        name: trimmedName,
        description: description.trim(),
        goal: goal.trim(),
        topic_mode: effectiveMode,
        course_depth: courseDepth,
        starting_skill_level: startingSkillLevel,
        assessment_styles: assessmentStyles,
      });
      router.push(`/topics/${result.topic.id}/initializing`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create topic');
    } finally {
      setCreating(false);
    }
  }

  async function onCreateTopic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runTopicCreation();
  }

  return (
    <main className="mx-auto w-full max-w-7xl p-6 md:p-10">
      <section className="relative overflow-hidden rounded-2xl border border-black/10 bg-gradient-to-br from-[#eef4ff] via-[#f8f7f2] to-[#eef7ed] p-6 md:p-8">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-ink/10 blur-3xl" />
        <div className="absolute -left-20 bottom-[-60px] h-52 w-52 rounded-full bg-emerald-300/20 blur-3xl" />

        <div className="relative grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <p className="badge mb-3">Learning home</p>
            <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
              Welcome back{user?.display_name ? `, ${user.display_name}` : ''}.
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-black/70 md:text-base">
              Pick up your momentum with clear next steps, balanced progression, and evolving topic trees.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {continueTopic ? (
                <Link
                  href={`/topics/${continueTopic.topic_id}`}
                  className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white"
                >
                  Continue learning
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => document.getElementById('create-topic-form')?.scrollIntoView({ behavior: 'smooth' })}
                  className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white"
                >
                  Create your first topic
                </button>
              )}
              <Link href="/garden" className="rounded-lg border border-black/20 bg-white/90 px-4 py-2 text-sm">
                View garden
              </Link>
            </div>
          </div>

          <article className="rounded-xl border border-black/10 bg-white/80 p-4 backdrop-blur-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/60">Progress snapshot</h2>
            {loading ? (
              <div className="mt-3 space-y-2">
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
              </div>
            ) : (
              <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-xs uppercase tracking-[0.12em] text-black/55">Topics</p>
                  <p className="mt-1 text-xl font-semibold">{progressSummary?.topics_total ?? topics.length}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-xs uppercase tracking-[0.12em] text-black/55">Verified skills</p>
                  <p className="mt-1 text-xl font-semibold">{progressSummary?.verified_nodes_total ?? 0}</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-xs uppercase tracking-[0.12em] text-black/55">Mastery average</p>
                  <p className="mt-1 text-xl font-semibold">
                    {pct(progressSummary?.mastery_average ?? 0)}
                  </p>
                </div>
              </div>
            )}
          </article>
        </div>
      </section>

      <section className="mt-8 grid gap-8 lg:grid-cols-[1.25fr_0.95fr]">
        <article className="panel p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Active topics</h2>
              <p className="muted mt-1 text-sm">Your current learning paths and their growth state.</p>
            </div>
            <button className="text-sm underline underline-offset-4" onClick={loadDashboard}>
              Refresh
            </button>
          </div>

          {loading && (
            <div className="space-y-3">
              <div className="skeleton h-20 w-full" />
              <div className="skeleton h-20 w-full" />
              <div className="skeleton h-20 w-full" />
            </div>
          )}

          {!loading && topics.length === 0 && (
            <article className="rounded-xl border border-black/10 bg-gradient-to-br from-white to-[#eef6ec] p-5">
              <p className="text-xs uppercase tracking-[0.14em] text-black/55">First steps</p>
              <h3 className="mt-2 text-xl font-semibold">Your learning tree starts here.</h3>
              <p className="mt-2 text-sm text-black/70">
                Create one topic to unlock your guided path, exercises, and progress journal in a single flow.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">1. Pick a topic</p>
                  <p className="mt-1 text-xs text-black/70">Start with one clear learning goal.</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">2. Enter your path</p>
                  <p className="mt-1 text-xs text-black/70">Your first lesson and examples are prepared automatically.</p>
                </div>
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">3. Build momentum</p>
                  <p className="mt-1 text-xs text-black/70">Complete nodes, unlock branches, and grow your garden.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => document.getElementById('create-topic-form')?.scrollIntoView({ behavior: 'smooth' })}
                className="mt-4 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white"
              >
                Create your first topic
              </button>
            </article>
          )}

          {topics.length > 0 && (
            <div className="space-y-3">
              {rankedTopics.map((item) => {
                const topic = topicById.get(item.topic_id);
                const progress = item.total_nodes > 0 ? item.verified_nodes / item.total_nodes : 0;
                return (
                  <Link
                    key={item.topic_id}
                    href={`/topics/${item.topic_id}`}
                    className="block rounded-xl border border-black/10 bg-white p-4 transition hover:-translate-y-0.5 hover:shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-base font-semibold">{item.topic_name}</p>
                        <p className="muted mt-1 text-sm">{topic?.description || 'No description yet.'}</p>
                      </div>
                      <span className="badge">{stageLabel(item.tree_stage)}</span>
                    </div>
                    <div className="mt-3 space-y-2">
                      <div className="h-2 overflow-hidden rounded-full bg-black/10">
                        <div
                          className="h-full rounded-full bg-ink/80"
                          style={{ width: `${Math.max(6, Math.round(progress * 100))}%` }}
                        />
                      </div>
                      <p className="text-xs text-black/70">
                        {item.verified_nodes}/{item.total_nodes} verified · mastery {pct(item.mastery_average)}
                      </p>
                      {topic && (
                        <p className="text-xs text-black/60">
                          {topic.course_depth.replace('_', ' ')} · {topic.starting_skill_level} · {topic.assessment_styles.length} assessment styles
                        </p>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </article>

        <article id="create-topic-form" className="panel p-6">
          <h2 className="mb-2 text-xl font-semibold">Create a new topic</h2>
          <p className="muted mb-4 text-sm">Set the core goal, then optionally tune learning preferences.</p>
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

            <div className="rounded-xl border border-black/10 bg-white/70 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Topic framing</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {[
                  { value: 'factual', label: 'Factual' },
                  { value: 'fictional', label: 'Fictional' },
                  { value: 'hypothetical', label: 'Hypothetical' },
                  { value: 'creative', label: 'Creative' },
                ].map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => {
                      setTopicMode(item.value as TopicMode);
                      setPlausibilityPrompt(null);
                    }}
                    className={`rounded-md border px-3 py-1.5 text-xs ${
                      topicMode === item.value
                        ? 'border-ink bg-white text-ink shadow-sm'
                        : 'border-black/15 bg-white/70 text-black/70'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-black/60">
                Keep factual for real-world topics. Use fictional or hypothetical framing for creative scenarios.
              </p>
            </div>

            <div className="rounded-xl border border-black/10 bg-black/[0.02] p-3">
              <h3 className="text-sm font-semibold">Learning preferences</h3>
              <p className="muted mt-1 text-xs">Simple defaults work well. Expand only if you want to customize.</p>

              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Course depth</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {COURSE_DEPTH_OPTIONS.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => setCourseDepth(item.value)}
                      className={`rounded-md border p-2 text-left ${
                        courseDepth === item.value
                          ? 'border-ink bg-white shadow-sm'
                          : 'border-black/10 bg-white/80'
                      }`}
                    >
                      <p className="text-sm font-semibold">{item.label}</p>
                      <p className="mt-1 text-xs text-black/60">{item.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Starting skill level</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {STARTING_SKILL_LEVEL_OPTIONS.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => setStartingSkillLevel(item.value)}
                      className={`rounded-md border p-2 text-left ${
                        startingSkillLevel === item.value
                          ? 'border-ink bg-white shadow-sm'
                          : 'border-black/10 bg-white/80'
                      }`}
                    >
                      <p className="text-sm font-semibold">{item.label}</p>
                      <p className="mt-1 text-xs text-black/60">{item.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-3 rounded-lg border border-black/10 bg-white/75 p-2">
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left"
                  onClick={() => setAssessmentPickerOpen((prev) => !prev)}
                  aria-expanded={assessmentPickerOpen}
                >
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">
                    Assessment methods
                  </span>
                  <span className="text-xs text-black/65">
                    {assessmentStyles.length} selected · {assessmentPickerOpen ? 'Hide' : 'Customize'}
                  </span>
                </button>
                <p className="px-2 pb-2 text-xs text-black/60">
                  Default: short answer, multiple choice, flashcard.
                </p>
                {assessmentPickerOpen && (
                  <div className="grid gap-2 px-2 pb-2 sm:grid-cols-2">
                    {ASSESSMENT_STYLE_OPTIONS.map((item) => {
                      const selected = assessmentStyles.includes(item.value);
                      return (
                        <button
                          key={item.value}
                          type="button"
                          onClick={() =>
                            setAssessmentStyles((prev) =>
                              prev.includes(item.value)
                                ? prev.filter((style) => style !== item.value)
                                : [...prev, item.value]
                            )
                          }
                          className={`rounded-md border p-2 text-left ${
                            selected ? 'border-ink bg-white shadow-sm' : 'border-black/10 bg-white/80'
                          }`}
                        >
                          <p className="text-sm font-semibold">{item.label}</p>
                          <p className="mt-1 text-xs text-black/60">{item.description}</p>
                          <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-black/45">{item.category}</p>
                        </button>
                      );
                    })}
                    <div className="sm:col-span-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-md border border-black/15 bg-white px-2.5 py-1.5 text-xs"
                        onClick={() => setAssessmentStyles(DEFAULT_ASSESSMENT_STYLES)}
                      >
                        Reset to defaults
                      </button>
                      <button
                        type="button"
                        className="rounded-md border border-black/15 bg-white px-2.5 py-1.5 text-xs"
                        onClick={() => setAssessmentStyles(ASSESSMENT_STYLE_OPTIONS.map((item) => item.value))}
                      >
                        Select all
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {plausibilityPrompt && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
                <p className="font-semibold text-amber-900">This topic may need clarification</p>
                <p className="mt-1 text-amber-900/90">{plausibilityPrompt.reason}</p>
                {plausibilityPrompt.suggested_reframe && (
                  <p className="mt-1 text-amber-900/80">{plausibilityPrompt.suggested_reframe}</p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-black/20 bg-white px-3 py-1.5 text-xs"
                    onClick={() => {
                      setTopicMode('factual');
                      setPlausibilityPrompt(null);
                    }}
                  >
                    Revise topic
                  </button>
                  <button
                    type="button"
                    className="rounded-md bg-ink px-3 py-1.5 text-xs text-white disabled:opacity-60"
                    disabled={creating}
                    onClick={() => {
                      setTopicMode('fictional');
                      void runTopicCreation('fictional', true);
                    }}
                  >
                    Continue as fictional
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-black/20 bg-white px-3 py-1.5 text-xs disabled:opacity-60"
                    disabled={creating}
                    onClick={() => {
                      setTopicMode('hypothetical');
                      void runTopicCreation('hypothetical', true);
                    }}
                  >
                    Continue as hypothetical
                  </button>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {creating ? 'Creating topic...' : 'Create topic'}
            </button>
          </form>
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
