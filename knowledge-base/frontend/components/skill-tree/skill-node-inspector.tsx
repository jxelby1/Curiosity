'use client';

import Link from 'next/link';
import { useState } from 'react';

import {
  BRANCH_PURPOSE_OPTIONS,
  BranchPurpose,
  getBranchPurposeMeta,
} from '@/lib/branch-purpose';
import { derivePrimaryNodeNextStep } from '@/lib/next-step';
import { BranchSuggestion, SkillNode } from '@/lib/types';

function statusLabel(node: SkillNode): string {
  if (node.status === 'locked') return 'Locked';
  if (node.progress_state === 'verified' || node.status === 'mastered') return 'Verified';
  if (node.progress_state === 'learning' || node.status === 'in_progress') return 'In Progress';
  return 'Available';
}

function statusTone(node: SkillNode): string {
  if (node.status === 'locked') return 'border-zinc-300 bg-zinc-100 text-zinc-700';
  if (node.progress_state === 'verified' || node.status === 'mastered') {
    return 'border-emerald-300 bg-emerald-100 text-emerald-800';
  }
  if (node.progress_state === 'learning' || node.status === 'in_progress') {
    return 'border-amber-300 bg-amber-100 text-amber-800';
  }
  return 'border-sky-300 bg-sky-100 text-sky-800';
}

function pct(value: number | null | undefined): string {
  if (typeof value !== 'number') return '--';
  return `${Math.round(value * 100)}%`;
}

function CompactStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-black/10 bg-white px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-[0.14em] text-black/48">{label}</p>
      <p className="mt-0.5 text-xs font-semibold text-black">{value}</p>
    </div>
  );
}

export function SkillNodeInspector({
  topicId,
  node,
  prerequisites,
  branchSuggestions,
  branchSuggestionsLoading,
  branchActionLoading,
  branchError,
  onCreateBranch,
  onGenerateSuggestions,
  onAcceptSuggestion,
  onRejectSuggestion,
  canForceUnlock,
  forcingUnlock,
  onForceUnlock,
}: {
  topicId: string;
  node: SkillNode | null;
  prerequisites: SkillNode[];
  branchSuggestions: BranchSuggestion[];
  branchSuggestionsLoading: boolean;
  branchActionLoading: boolean;
  branchError?: string;
  onCreateBranch: (input: {
    focus?: string;
    purpose: BranchPurpose;
  }) => void;
  onGenerateSuggestions: () => void;
  onAcceptSuggestion: (suggestionId: number) => void;
  onRejectSuggestion: (suggestionId: number) => void;
  canForceUnlock: boolean;
  forcingUnlock: boolean;
  onForceUnlock: (skillNodeId: number) => void;
}) {
  const [branchFocus, setBranchFocus] = useState('');
  const [branchPurpose, setBranchPurpose] = useState<BranchPurpose>('deepen_theme');

  if (!node) {
    return (
      <aside className="rounded-2xl border border-black/10 bg-white/85 p-5 text-sm text-black/70 shadow-[0_10px_26px_rgba(16,19,33,0.08)]">
        Select a node to inspect context, open study materials, or add a focused branch.
      </aside>
    );
  }

  const status = statusLabel(node);
  const isLocked = node.status === 'locked';
  const branchDisabled = isLocked || branchActionLoading || forcingUnlock;
  const primaryAction = derivePrimaryNodeNextStep(topicId, node);
  const selectedPurposeMeta = getBranchPurposeMeta(branchPurpose);

  return (
    <aside className="rounded-2xl border border-black/10 bg-[linear-gradient(165deg,rgba(255,255,255,0.96),rgba(247,252,244,0.92))] p-4 text-black shadow-[0_16px_38px_rgba(16,19,33,0.12)]">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] ${statusTone(node)}`}>{status}</span>
        <span className="rounded-full border border-black/15 bg-white px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-black/70">
          {node.node_kind === 'optional_branch'
            ? node.branch_origin === 'system_suggested'
              ? 'Suggested branch (active)'
              : 'Branch path (active)'
            : 'Core study path'}
        </span>
      </div>

      <h3 className="mt-3 text-lg font-semibold leading-tight">{node.name}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-black/72">{node.description}</p>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <CompactStat label="Difficulty" value={String(node.difficulty)} />
        <CompactStat label="Mastery" value={pct(node.mastery_estimate)} />
        <CompactStat label="Best score" value={pct(node.best_quiz_score)} />
      </div>

      <section className="mt-3 rounded-xl border border-black/10 bg-white p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Connections</p>
          <span className="text-[10px] uppercase tracking-[0.14em] text-black/40">{prerequisites.length} prerequisite(s)</span>
        </div>

        {prerequisites.length > 0 ? (
          <ul className="mt-2 space-y-1.5 text-xs text-black/80">
            {prerequisites.slice(0, 4).map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2 rounded-md border border-black/10 bg-paper/40 px-2 py-1.5">
                <span className="line-clamp-1">{item.name}</span>
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] ${
                    item.progress_state === 'verified'
                      ? 'border-emerald-300 bg-emerald-100 text-emerald-800'
                      : 'border-zinc-300 bg-zinc-100 text-zinc-600'
                  }`}
                >
                  {item.progress_state === 'verified' ? 'Ready' : 'Pending'}
                </span>
              </li>
            ))}
            {prerequisites.length > 4 && <li className="text-[11px] text-black/58">+{prerequisites.length - 4} more prerequisites</li>}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-black/68">No prerequisites required.</p>
        )}

        {isLocked && node.lock_reason && <p className="mt-2 text-xs text-amber-700">{node.lock_reason}</p>}
      </section>

      <section className="mt-3 rounded-xl border border-black/10 bg-white p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Next move</p>
          <span className="text-[10px] uppercase tracking-[0.14em] text-black/40">
            {node.progress_state === 'verified' ? 'Keep sharp' : 'Move forward'}
          </span>
        </div>
        <div className="mt-2 grid gap-2">
          <Link
            href={primaryAction.href}
            className="rounded-md bg-ink px-3 py-2 text-center text-sm font-semibold text-white hover:opacity-90"
          >
            {primaryAction.label}
          </Link>
          {primaryAction.tab !== 'overview' && (
            <Link
              href={`/topics/${topicId}/skills/${node.id}?tab=overview`}
              className="rounded-md border border-black/15 bg-white px-3 py-2 text-center text-sm text-black/80 hover:bg-black/[0.03]"
            >
              View overview
            </Link>
          )}
        </div>
        <p className="mt-2 text-xs text-black/64">
          {primaryAction.reason || node.recommended_next_action || (isLocked ? 'Complete prerequisites to unlock this node.' : 'Continue to keep momentum.')}
        </p>
      </section>

      <section className="mt-3 rounded-xl border border-black/10 bg-white p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] uppercase tracking-[0.14em] text-black/52">Branch move</p>
          <button
            type="button"
            className="rounded-md border border-black/15 bg-white px-2 py-1 text-[11px] disabled:opacity-60"
            onClick={onGenerateSuggestions}
            disabled={branchDisabled}
          >
            {branchSuggestionsLoading ? 'Loading...' : 'Suggest one'}
          </button>
        </div>
        <p className="mt-1 text-[11px] text-black/64">
          Open a focused branch when it deepens your study. Keep branch decisions sparse and intentional.
        </p>
        <p className="mt-1 text-[11px] text-black/56">
          Each branch type is a distinct study move with a clear intent.
        </p>

        <div className="mt-2.5 grid gap-2">
          <input
            value={branchFocus}
            onChange={(event) => setBranchFocus(event.target.value)}
            className="w-full rounded-md border border-black/15 bg-white px-2.5 py-2 text-xs"
            placeholder="Branch focus (work, question, technique)"
            maxLength={180}
            disabled={branchDisabled}
          />
          <div className="flex gap-2">
            <select
              value={branchPurpose}
              onChange={(event) => setBranchPurpose(event.target.value as BranchPurpose)}
              className="min-w-0 flex-1 rounded-md border border-black/15 bg-white px-2.5 py-2 text-xs"
              disabled={branchDisabled}
            >
              {BRANCH_PURPOSE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
              onClick={() => {
                onCreateBranch({
                  focus: branchFocus.trim() || undefined,
                  purpose: branchPurpose,
                });
                setBranchFocus('');
              }}
              disabled={branchDisabled}
            >
              Create
            </button>
          </div>
          <p className="text-[11px] text-black/56">{selectedPurposeMeta.summary}</p>
        </div>

        {branchError && <p className="mt-2 text-xs text-red-700">{branchError}</p>}

        <div className="mt-2.5 space-y-2">
          {branchSuggestions.map((suggestion) => {
            const suggestionMeta = getBranchPurposeMeta(suggestion.purpose);
            return (
              <article key={suggestion.id} className="rounded-md border border-black/10 bg-paper/35 p-2.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold leading-tight">{suggestion.title}</p>
                  <span className="rounded-full border border-black/15 bg-white px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-black/60">
                    {suggestionMeta.label}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-black/68">{suggestion.rationale}</p>
                <p className="mt-1 text-[11px] text-black/58">{suggestionMeta.summary}</p>
                <p className="mt-1 text-[11px] text-black/58">
                  Suggested path. Accept to activate it inside your study tree.
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded-md bg-ink px-2 py-1 text-[11px] text-white disabled:opacity-60"
                    onClick={() => onAcceptSuggestion(suggestion.id)}
                    disabled={branchDisabled}
                  >
                    Activate path
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-black/15 bg-white px-2 py-1 text-[11px] text-black/70 disabled:opacity-60"
                    onClick={() => onRejectSuggestion(suggestion.id)}
                    disabled={branchDisabled}
                  >
                    Not now
                  </button>
                </div>
              </article>
            );
          })}
          {branchSuggestions.length === 0 && !branchSuggestionsLoading && (
            <p className="text-[11px] text-black/58">No recommended branch opportunity right now.</p>
          )}
        </div>
      </section>

      {canForceUnlock && isLocked && (
        <div className="mt-3 rounded-xl border border-fuchsia-300/70 bg-fuchsia-50 p-3">
          <p className="text-[11px] text-fuchsia-800">Developer override</p>
          <button
            type="button"
            className="mt-1.5 rounded-md border border-fuchsia-300 bg-fuchsia-100 px-3 py-1.5 text-xs text-fuchsia-800 disabled:opacity-60"
            onClick={() => onForceUnlock(node.id)}
            disabled={forcingUnlock}
          >
            {forcingUnlock ? 'Unlocking...' : 'Force unlock node'}
          </button>
        </div>
      )}

      {node.force_unlocked && <p className="mt-2 text-[11px] text-fuchsia-700">Dev override active for this node.</p>}
    </aside>
  );
}
