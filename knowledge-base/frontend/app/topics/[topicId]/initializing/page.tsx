'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getTopicInitializationStatus, startTopicInitialization } from '@/lib/api';
import { PRODUCT_NAME } from '@/lib/brand';
import { TopicInitializationStatus } from '@/lib/types';

const FALLBACK_STEPS = [
  'Setting the trunk of your study',
  'Opening your starting path',
  'Preparing your first lesson',
  'Getting your first exemplars ready',
  'Preparing your first practice',
  'Finalising your opening session'
];

const STAGE_PROGRESS_BOUNDS: Record<string, { min: number; max: number }> = {
  setup: { min: 0.04, max: 0.12 },
  path: { min: 0.08, max: 0.24 },
  unlocks: { min: 0.2, max: 0.34 },
  lesson: { min: 0.32, max: 0.48 },
  examples: { min: 0.46, max: 0.6 },
  activities: { min: 0.58, max: 0.74 },
  finalising: { min: 0.72, max: 0.84 },
  ready: { min: 0.8, max: 0.9 },
  preloading: { min: 0.82, max: 0.98 },
  complete: { min: 1.0, max: 1.0 },
  failed: { min: 0.0, max: 0.0 },
};

const STAGE_HINTS: Record<string, string[]> = {
  setup: ['Setting up your study workspace...'],
  path: ['Building the trunk of your skill tree...', 'Mapping a calm opening progression...'],
  unlocks: ['Opening your first node sequence...', 'Preparing the first clear move...'],
  lesson: ['Designing your opening lesson...', 'Shaping a concrete starting point...'],
  examples: ['Gathering exemplar works...', 'Preparing concrete references for close observation...'],
  activities: ['Preparing your first practice prompts...', 'Crafting the first hands-on studio move...'],
  finalising: ['Connecting your notebook cue and milestones...', 'Final quality checks before launch...'],
  ready: ['Your first module is ready. Launching your workspace...'],
  preloading: ['Preparing extra lessons in the background...', 'Warming up likely next modules...'],
  complete: ['Topic fully prepared. Enjoy your learning path.'],
  failed: ['Setup hit an issue. You can retry safely.'],
};

const READY_PREVIEW = [
  {
    title: 'First lesson',
    description: 'A concrete opening lesson that leads with observation, interpretation, and a clear through-line.',
  },
  {
    title: 'First practice',
    description: 'A small, high-signal exercise so you can begin through doing instead of staying in setup mode.',
  },
  {
    title: 'Notebook cue',
    description: 'A reflective prompt to capture what changed, what you noticed, or what you want to follow next.',
  },
];

function stepFromStatus(status: TopicInitializationStatus | null): string {
  if (!status) return FALLBACK_STEPS[0];
  if (status.stage_label?.trim()) return status.stage_label;
  if (status.current_step?.trim()) return status.current_step;
  if (status.status === 'failed') return 'We could not finish setting up your topic';
  if (status.status === 'completed') return 'Topic ready';
  return 'Setting up your topic';
}

export default function TopicInitializingPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;
  const router = useRouter();

  const [status, setStatus] = useState<TopicInitializationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState('');
  const [pollNonce, setPollNonce] = useState(0);
  const [displayProgress, setDisplayProgress] = useState(0.08);
  const [clockTick, setClockTick] = useState(Date.now());
  const [hintIndex, setHintIndex] = useState(0);
  const stageKeyRef = useRef<string>('setup');
  const stageStartRef = useRef<number>(Date.now());

  const loadStatus = useCallback(async () => {
    try {
      const next = await getTopicInitializationStatus(topicId);
      setStatus(next);
      setError('');

      if (next.ready_for_entry) {
        router.replace(`/topics/${topicId}`);
        return next;
      }
      if ((next.status === 'completed' || next.status === 'ready') && !next.first_ready_skill_id) {
        router.replace(`/topics/${topicId}`);
      }
      return next;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'We could not check your topic progress right now.';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [router, topicId]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const next = await loadStatus();
      if (cancelled) return;

      const terminal =
        !next ||
        next.status === 'failed' ||
        next.status === 'completed' ||
        next.ready_for_entry;
      if (!terminal) {
        timer = window.setTimeout(poll, 1500);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [loadStatus, pollNonce]);

  const stageKey = status?.stage_key || 'setup';

  useEffect(() => {
    if (stageKeyRef.current === stageKey) return;
    stageKeyRef.current = stageKey;
    stageStartRef.current = Date.now();
    setHintIndex(0);
  }, [stageKey]);

  useEffect(() => {
    const timer = window.setInterval(() => setClockTick(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  const targetProgress = useMemo(() => {
    const serverProgress = status ? Math.max(0.04, Math.min(1, status.progress || 0)) : 0.08;
    if (!status || status.status === 'completed' || status.status === 'ready' || status.status === 'failed') {
      return serverProgress;
    }

    const bounds = STAGE_PROGRESS_BOUNDS[stageKey] || { min: serverProgress, max: Math.min(0.96, serverProgress + 0.12) };
    const elapsedMs = Math.max(0, clockTick - stageStartRef.current);
    const stageRatio = Math.min(1, elapsedMs / 16000);
    const softProgress = bounds.min + (bounds.max - bounds.min) * stageRatio;
    return Math.max(serverProgress, softProgress);
  }, [clockTick, stageKey, status]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setDisplayProgress((previous) => {
        const delta = targetProgress - previous;
        if (Math.abs(delta) < 0.003) return targetProgress;
        return previous + delta * 0.22;
      });
    }, 120);
    return () => window.clearInterval(timer);
  }, [targetProgress]);

  const progress = useMemo(() => Math.max(0.04, Math.min(1, displayProgress)), [displayProgress]);

  const messages = useMemo(() => {
    const fromStatus = status?.status_messages?.filter(Boolean).slice(-3) || [];
    const stageHints = STAGE_HINTS[stageKey] || FALLBACK_STEPS;
    const rotatingHint = stageHints[Math.min(hintIndex, stageHints.length - 1)];
    const combined = [rotatingHint, ...fromStatus].filter(Boolean);
    return combined.slice(0, 4);
  }, [hintIndex, stageKey, status]);

  useEffect(() => {
    const stageHints = STAGE_HINTS[stageKey] || [];
    if (stageHints.length <= 1) return;
    const timer = window.setInterval(() => {
      setHintIndex((value) => (value + 1) % stageHints.length);
    }, 2300);
    return () => window.clearInterval(timer);
  }, [stageKey]);

  async function handleRetry(force = false) {
    setRetrying(true);
    setError('');
    try {
      const next = await startTopicInitialization(topicId, force);
      setStatus(next);
      if (next.ready_for_entry) {
        router.replace(`/topics/${topicId}`);
        return;
      }
      if ((next.status === 'completed' || next.status === 'ready') && !next.first_ready_skill_id) {
        router.replace(`/topics/${topicId}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not restart setup. Please try again.');
    } finally {
      setRetrying(false);
      setPollNonce((value) => value + 1);
    }
  }

  const isFailed = status?.status === 'failed';

  return (
    <main className="mx-auto flex min-h-[72vh] max-w-4xl items-center p-6 md:p-10">
      <section className="panel w-full overflow-hidden">
        <div className="border-b border-black/10 bg-white/70 p-6 md:p-8">
          <p className="badge mb-3">Studio Setup</p>
          <h1 className="text-2xl md:text-3xl">Preparing your first study session in {PRODUCT_NAME}</h1>
          <p className="muted mt-2 max-w-2xl text-sm md:text-base">
            We&apos;re setting the trunk of your study, opening the first node, and preparing a concrete lesson, exemplar trail, and practice cue.
          </p>
        </div>

        <div className="space-y-5 p-6 md:p-8">
          <div className="rounded-xl border border-black/10 bg-white/75 p-4">
            <p className="text-xs uppercase tracking-[0.14em] text-black/55">What happens here</p>
            <p className="mt-2 text-sm text-black/75">
              No setup choices are needed now. We&apos;ll open your workspace as soon as the first study step is ready.
            </p>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {READY_PREVIEW.map((item) => (
                <article key={item.title} className="rounded-lg border border-black/10 bg-white p-3">
                  <p className="text-sm font-semibold text-black">{item.title}</p>
                  <p className="mt-1 text-xs text-black/65">{item.description}</p>
                </article>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between gap-3 text-xs text-black/65">
              <span>{stepFromStatus(status)}</span>
              <span>
                Step {Math.max(1, status?.stage_index || 1)} of {Math.max(1, status?.stage_total || 8)}
              </span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-black/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#4f7a63] via-[#3c879e] to-[#3557a8] transition-all duration-500"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          </div>

          <div className="grid gap-2">
            {messages.map((item, idx) => (
              <div key={`${item}-${idx}`} className="flex items-center gap-2 rounded-md border border-black/10 bg-white px-3 py-2 text-sm">
                <span className="inline-block h-2 w-2 rounded-full bg-[#4f7a63]" />
                <span>{item}</span>
              </div>
            ))}
          </div>

          {loading && <p className="text-sm text-black/70">Checking your setup progress...</p>}

          {status?.status === 'preloading' && status.ready_for_entry && (
            <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              Your first module is ready. Taking you there now while we prepare a few extra materials.
            </p>
          )}

          {isFailed && (
            <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-sm text-red-800">Initialization did not complete successfully.</p>
              {status?.error_text && <p className="text-xs text-red-700">{status.error_text}</p>}
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded-md bg-red-700 px-3 py-2 text-sm text-white disabled:opacity-60"
                  onClick={() => handleRetry(true)}
                  disabled={retrying}
                  type="button"
                >
                  {retrying ? 'Retrying...' : 'Try again'}
                </button>
                <button
                  className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                  onClick={() => router.replace('/topics')}
                  type="button"
                >
                  Back to topics
                </button>
              </div>
            </div>
          )}

          {!isFailed && error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-sm text-red-700">{error}</p>
              <button
                className="mt-3 rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                onClick={() => handleRetry(false)}
                disabled={retrying}
                type="button"
              >
                {retrying ? 'Retrying...' : 'Try again'}
              </button>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
