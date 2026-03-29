'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import {
  checkTopicPlausibility,
  createTopicAndInitialize,
  getMyProgressSummary,
  getTopicRetentionLoop,
  listTopics,
  upgradeMyAccountToDev,
} from '@/lib/api';
import {
  ASSESSMENT_STYLE_OPTIONS,
  COURSE_DEPTH_OPTIONS,
  DEFAULT_ASSESSMENT_STYLES,
  STARTING_SKILL_LEVEL_OPTIONS,
  TECHNICAL_DEPTH_OPTIONS,
} from '@/lib/course-options';
import { formatDisplayTag } from '@/lib/display-format';
import { derivePrimaryTopicNextStep, LEARNING_LOOP_LABELS } from '@/lib/next-step';
import { PRODUCT_NAME } from '@/lib/brand';
import { AssessmentStyle, CourseDepth, StartingSkillLevel, TechnicalDepth, Topic, TopicMode, TopicPlausibilityCheck, UserProgressSummary } from '@/lib/types';

const TOPIC_NAME_MAX = 120;
const TOPIC_DESC_MAX = 500;
const TOPIC_GOAL_MAX = 500;

type StudioStarter = {
  area: string;
  name: string;
  goal: string;
  description: string;
  mode: TopicMode;
};

const STUDIO_TOPIC_STARTERS: StudioStarter[] = [
  {
    area: 'Art',
    name: 'Modern Art Through 12 Works and Your Own Responses',
    goal: 'Build a repeatable habit of observing one artwork closely, writing a short interpretation, and refining your taste.',
    description: 'Study landmark works, compare interpretations, and create short response notes that connect form, feeling, and context.',
    mode: 'factual',
  },
  {
    area: 'Literature',
    name: 'Reading Novels Through Passages and Voice',
    goal: 'Develop a close-reading routine by annotating passages, comparing narrative voices, and testing interpretations.',
    description: 'Work passage-by-passage with short comparison notes so theory supports what you actually notice in the text.',
    mode: 'factual',
  },
  {
    area: 'Philosophy',
    name: 'Philosophy in Practice: Stoic and Buddhist Daily Exercises',
    goal: 'Use philosophy as lived practice by comparing short texts and trying simple reflection exercises each week.',
    description: 'Keep conceptual depth, but tie every concept to one concrete practice, interpretation, or decision in daily life.',
    mode: 'factual',
  },
  {
    area: 'Film',
    name: 'Cinema Through Scenes: Framing, Rhythm, and Mood',
    goal: 'Learn film appreciation by studying scenes, comparing directors, and capturing what each style makes you feel.',
    description: 'Anchor each lesson in concrete stills and scene comparisons, then write short interpretation and response notes.',
    mode: 'factual',
  },
  {
    area: 'Music',
    name: 'Listening Like a Curator: Jazz and Electronic Taste Building',
    goal: 'Develop listening taste by building themed playlists, comparing tracks, and writing concise curation notes.',
    description: 'Use theory as support while prioritizing listening practice, contrast drills, and personal taste articulation.',
    mode: 'factual',
  },
  {
    area: 'Architecture',
    name: 'Architecture by Looking: Cities, Buildings, and Sketch Notes',
    goal: 'Train architectural seeing through weekly building studies, quick sketches, and comparative place notes.',
    description: 'Study exemplar buildings with context and lineage, then practice observation through photo-plus-sketch responses.',
    mode: 'factual',
  },
  {
    area: 'Photography',
    name: 'Photograph with Intention: Light, Timing, and Editing',
    goal: 'Build a practical photography routine: shoot, review contact sheets, compare choices, and iterate deliberately.',
    description: 'Learn composition and visual storytelling through exemplar photos plus short weekly shooting prompts.',
    mode: 'creative',
  },
  {
    area: 'Writing',
    name: 'Short Reflective Essays from Art and Place Notes',
    goal: 'Grow a writing habit by turning observations from works, films, and places into concise reflective essays.',
    description: 'Use exemplar passages for craft study, then produce short response drafts with focused revision loops.',
    mode: 'creative',
  },
  {
    area: 'Design',
    name: 'Design Taste Studio: Interfaces, Posters, and Objects',
    goal: 'Develop design taste by collecting references, running side-by-side critiques, and making small redesign responses.',
    description: 'Train your eye for hierarchy, typography, and composition through concrete examples and practice prompts.',
    mode: 'factual',
  },
  {
    area: 'Cultural History',
    name: 'Cultural Movements Through Works, Venues, and Scenes',
    goal: 'Study a movement through artifacts and creators, then map influence using comparison and interpretation notes.',
    description: 'Keep historical depth, but center real works, listening/viewing sessions, and reflective synthesis.',
    mode: 'factual',
  },
  {
    area: 'City and Place',
    name: 'Creative Neighborhood Exploration Studio',
    goal: 'Learn a city through visits, photos, sketches, and cultural notes that build your own place-based archive.',
    description: 'Combine local observation with context and influence so place study feels lived, visual, and personal.',
    mode: 'factual',
  },
];

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
  const { user, refreshUser } = useAuth();

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
  const [technicalDepth, setTechnicalDepth] = useState<TechnicalDepth>('intermediate');
  const [assessmentStyles, setAssessmentStyles] = useState<AssessmentStyle[]>(DEFAULT_ASSESSMENT_STYLES);
  const [advancedOptionsOpen, setAdvancedOptionsOpen] = useState(false);
  const [assessmentPickerOpen, setAssessmentPickerOpen] = useState(false);
  const [plausibilityPrompt, setPlausibilityPrompt] = useState<TopicPlausibilityCheck | null>(null);
  const [creating, setCreating] = useState(false);
  const [upgradingDev, setUpgradingDev] = useState(false);
  const [devUpgradeMessage, setDevUpgradeMessage] = useState('');
  const [continueRetention, setContinueRetention] = useState<Awaited<ReturnType<typeof getTopicRetentionLoop>> | null>(null);
  const [loadingContinueAction, setLoadingContinueAction] = useState(false);

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

  useEffect(() => {
    let cancelled = false;
    const topicId = continueTopic?.topic_id;
    if (!topicId) {
      setContinueRetention(null);
      return;
    }
    setLoadingContinueAction(true);
    void getTopicRetentionLoop(String(topicId))
      .then((data) => {
        if (!cancelled) setContinueRetention(data);
      })
      .catch(() => {
        if (!cancelled) setContinueRetention(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingContinueAction(false);
      });
    return () => {
      cancelled = true;
    };
  }, [continueTopic?.topic_id]);

  const primaryNextStep = useMemo(() => {
    if (!continueTopic) {
      return {
        label: 'Start your first study',
        reason: 'Choose one focused study to begin your core learning rhythm.',
        href: '#create-topic-form',
        loopStep: 'learn' as const,
      };
    }
    const resolved = derivePrimaryTopicNextStep({
      topicId: String(continueTopic.topic_id),
      retention: continueRetention,
      recommendations: [],
      tree: null,
    });
    return {
      label: resolved.label,
      reason: resolved.reason,
      href: resolved.href,
      loopStep: resolved.loopStep,
    };
  }, [continueRetention, continueTopic]);

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
          technical_depth: technicalDepth,
        });
        if (
          (plausibility.status === 'clarify' || plausibility.status === 'needs_context' || plausibility.status === 'block')
          && effectiveMode === 'factual'
        ) {
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
        technical_depth: technicalDepth,
        assessment_styles: assessmentStyles,
      });
      router.push(`/topics/${result.topic.id}/initializing`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start study');
    } finally {
      setCreating(false);
    }
  }

  async function onCreateTopic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runTopicCreation();
  }

  async function onUpgradeToDev() {
    setUpgradingDev(true);
    setDevUpgradeMessage('');
    try {
      await upgradeMyAccountToDev();
      await refreshUser();
      setDevUpgradeMessage('Developer tools enabled for this account.');
    } catch (err) {
      setDevUpgradeMessage(err instanceof Error ? err.message : 'Unable to enable developer tools.');
    } finally {
      setUpgradingDev(false);
    }
  }

  function applyStarter(starter: StudioStarter) {
    setName(starter.name);
    setGoal(starter.goal);
    setDescription(starter.description);
    setTopicMode(starter.mode);
    setPlausibilityPrompt(null);
    setError('');
  }

  return (
    <main className="mx-auto w-full max-w-7xl p-6 md:p-10">
      <section className="relative overflow-hidden rounded-3xl border border-black/10 bg-gradient-to-br from-[#f9f5ea] via-[#f6f1e5] to-[#eef4ee] p-6 shadow-[0_24px_50px_rgba(20,26,24,0.1)] md:p-8">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-ink/10 blur-3xl" />
        <div className="absolute -left-20 bottom-[-60px] h-52 w-52 rounded-full bg-emerald-300/20 blur-3xl" />

        <div className="relative grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <p className="badge mb-3">{PRODUCT_NAME} Studio</p>
            <h1 className="text-3xl leading-tight md:text-4xl">
              Welcome back{user?.display_name ? `, ${user.display_name}` : ''}.
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-black/70 md:text-base">
              Continue with one clear next move, selective branching, and a practical creative rhythm.
            </p>
            <div className="mt-4 rounded-xl border border-black/10 bg-white/80 p-3">
              <p className="text-[10px] uppercase tracking-[0.16em] text-black/55">Primary Next Step</p>
              <p className="mt-1 text-base font-semibold">{primaryNextStep.label}</p>
              <p className="mt-1 text-sm text-black/68">
                {loadingContinueAction ? 'Updating your next step…' : primaryNextStep.reason}
              </p>
              <ol className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                {LEARNING_LOOP_LABELS.map((item, index) => (
                  <li
                    key={item.id}
                    className={`rounded-full border px-2 py-0.5 ${
                      item.id === primaryNextStep.loopStep
                        ? 'border-ink bg-ink/5 text-black'
                        : 'border-black/15 bg-white text-black/58'
                    }`}
                  >
                    {index + 1}. {item.label}
                  </li>
                ))}
              </ol>
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {continueTopic ? (
                <Link
                  href={primaryNextStep.href}
                  className="studio-button-primary px-4 py-2 text-sm"
                >
                  {primaryNextStep.label}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => document.getElementById('create-topic-form')?.scrollIntoView({ behavior: 'smooth' })}
                  className="studio-button-primary px-4 py-2 text-sm"
                >
                  Start your first study
                </button>
              )}
              <Link href="/garden" className="studio-button-secondary px-4 py-2 text-sm">
                View garden
              </Link>
              {!user?.dev_tools_enabled && (
                <button
                  type="button"
                  onClick={onUpgradeToDev}
                  className="rounded-lg border border-fuchsia-300 bg-fuchsia-50 px-4 py-2 text-sm text-fuchsia-900 disabled:opacity-60"
                  disabled={upgradingDev}
                >
                  {upgradingDev ? 'Enabling dev tools...' : 'Enable dev tools (local)'}
                </button>
              )}
              {user?.dev_tools_enabled && (
                <span className="rounded-lg border border-fuchsia-300 bg-fuchsia-50 px-3 py-2 text-xs text-fuchsia-900">
                  Dev tools enabled
                </span>
              )}
            </div>
            {devUpgradeMessage && (
              <p className="mt-2 text-xs text-black/70">{devUpgradeMessage}</p>
            )}
          </div>

          <article className="rounded-xl border border-black/10 bg-white/80 p-4 backdrop-blur-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/60">Studio pulse</h2>
            {loading ? (
              <div className="mt-3 space-y-2">
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
              </div>
            ) : (
              <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-xs uppercase tracking-[0.12em] text-black/55">Studies</p>
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
              <h2 className="text-xl font-semibold">Active studies</h2>
              <p className="muted mt-1 text-sm">Your current study paths and how they are maturing.</p>
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
              <p className="text-xs uppercase tracking-[0.14em] text-black/55">First study</p>
              <h3 className="mt-2 text-xl font-semibold">Your core trunk starts here.</h3>
              <p className="mt-2 text-sm text-black/70">
                Start one focused study to unlock exemplar-led lessons, comparison prompts, creative practice, and notebook memory.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <div className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">1. Choose a study</p>
                    <p className="mt-1 text-xs text-black/70">Anchor it in one concrete cultural or creative question.</p>
                  </div>
                  <div className="rounded-lg border border-black/10 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">2. Enter the studio</p>
                    <p className="mt-1 text-xs text-black/70">Your first lesson includes exemplars, observation prompts, and practice hooks.</p>
                  </div>
                  <div className="rounded-lg border border-black/10 bg-white p-3">
                    <p className="text-[11px] uppercase tracking-[0.12em] text-black/55">3. Build taste</p>
                    <p className="mt-1 text-xs text-black/70">Practice, compare, collect references, and grow your study tree over time.</p>
                  </div>
                </div>
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
                          {formatDisplayTag(topic.course_depth)} · {formatDisplayTag(topic.starting_skill_level)} · {formatDisplayTag(topic.technical_depth)} depth · {topic.assessment_styles.length} assessment styles
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
          <h2 className="mb-2 text-xl font-semibold">Start a new study path</h2>
          <p className="muted mb-4 text-sm">
            Frame one meaningful creative practice or cultural inquiry. We&apos;ll prepare a coherent path you can refine through doing.
          </p>
          <form className="space-y-3" onSubmit={onCreateTopic}>
            <div className="rounded-xl border border-black/10 bg-white/85 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Studio starters</p>
              <p className="mt-1 text-xs text-black/68">
                Practice-forward starters across art, literature, philosophy, film, music, design, and place-based exploration.
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {STUDIO_TOPIC_STARTERS.map((starter) => (
                  <button
                    key={starter.name}
                    type="button"
                    className="rounded-md border border-black/15 bg-white px-3 py-2 text-left text-xs transition hover:border-black/30"
                    onClick={() => applyStarter(starter)}
                  >
                    <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">{starter.area}</p>
                    <p className="mt-1 font-semibold text-black/84">{starter.name}</p>
                  </button>
                ))}
              </div>
            </div>

            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
              placeholder="Study title (e.g. Photographing your city with stronger composition)"
              maxLength={TOPIC_NAME_MAX}
              required
            />
            <p className="text-right text-xs text-black/60">{name.length}/{TOPIC_NAME_MAX}</p>

            <textarea
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              className="min-h-20 w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
              placeholder="What practice, taste, or creative ability do you want to build over the next few weeks?"
              maxLength={TOPIC_GOAL_MAX}
            />
            <p className="text-right text-xs text-black/60">{goal.length}/{TOPIC_GOAL_MAX}</p>

            <div className="rounded-xl border border-black/10 bg-white/80 p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Quick start defaults</p>
                  <p className="mt-1 text-sm text-black/75">
                    Grounded mode, standard depth, beginner start, and a balanced loop of exemplars, practice, and verification.
                  </p>
                  <p className="mt-1 text-xs text-black/60">Refine framing and rigor before starting if you want tighter control.</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setAdvancedOptionsOpen((prev) => {
                      const next = !prev;
                      if (!next) setAssessmentPickerOpen(false);
                      return next;
                    })
                  }
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-black/15 bg-white px-2.5 py-1.5 text-xs text-black/75"
                  aria-expanded={advancedOptionsOpen}
                >
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 20 20"
                    className="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                  >
                    <path d="M10 2.4v2.1M10 15.5v2.1M3.8 10h2.1M14.1 10h2.1M5.4 5.4l1.5 1.5M13.1 13.1l1.5 1.5M14.6 5.4l-1.5 1.5M6.9 13.1l-1.5 1.5" />
                    <circle cx="10" cy="10" r="3.1" />
                  </svg>
                  {advancedOptionsOpen ? 'Hide settings' : 'Customize'}
                </button>
              </div>
            </div>

            {advancedOptionsOpen && (
              <div className="rounded-xl border border-black/10 bg-black/[0.02] p-3">
                <h3 className="text-sm font-semibold">Advanced options</h3>
                <p className="muted mt-1 text-xs">
                  Tune framing and study controls. Defaults are calibrated for a calm, high-signal first run.
                </p>

                <div className="mt-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Description</p>
                  <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    className="mt-2 min-h-20 w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm"
                    placeholder="Optional context (period, movement, works, creators, place, or interpretive lens)"
                    maxLength={TOPIC_DESC_MAX}
                  />
                  <p className="mt-1 text-right text-xs text-black/60">{description.length}/{TOPIC_DESC_MAX}</p>
                </div>

                <div className="mt-3 rounded-xl border border-black/10 bg-white/70 p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Topic framing</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {[
                      { value: 'factual', label: 'Grounded' },
                      { value: 'fictional', label: 'Invented World' },
                      { value: 'hypothetical', label: 'Speculative' },
                      { value: 'creative', label: 'Creative Practice' },
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
                    Use grounded for real works and histories. Use speculative or creative framing for invention and studio exercises.
                  </p>
                </div>

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

                <div className="mt-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Technical depth</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {TECHNICAL_DEPTH_OPTIONS.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => setTechnicalDepth(item.value)}
                        className={`rounded-md border p-2 text-left ${
                          technicalDepth === item.value
                            ? 'border-ink bg-white shadow-sm'
                            : 'border-black/10 bg-white/80'
                        }`}
                      >
                        <p className="text-sm font-semibold">{item.label}</p>
                        <p className="mt-1 text-xs text-black/60">{item.description}</p>
                      </button>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-black/60">
                    Controls how rigorous lessons, exemplars, and assessments should be.
                  </p>
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
                    Default: multiple choice.
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
            )}

            {plausibilityPrompt && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
                <p className="font-semibold text-amber-900">
                  {plausibilityPrompt.status === 'needs_context'
                    ? 'This study needs stronger grounding'
                    : 'This framing may need clarification'}
                </p>
                <p className="mt-1 text-amber-900/90">{plausibilityPrompt.reason}</p>
                {plausibilityPrompt.suggested_reframe && (
                  <p className="mt-1 text-amber-900/80">{plausibilityPrompt.suggested_reframe}</p>
                )}
                {plausibilityPrompt.context_hint && (
                  <p className="mt-1 text-amber-900/80">{plausibilityPrompt.context_hint}</p>
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
                    Add more context
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
                    Continue as invented world
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
                    Continue as speculative
                  </button>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              {creating ? 'Starting study...' : 'Start study'}
            </button>
          </form>
        </article>
      </section>

      {error && <p className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
