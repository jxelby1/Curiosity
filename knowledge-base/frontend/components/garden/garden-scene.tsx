'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useMemo } from 'react';

import { treeStageAsset, treeStageLabel } from '@/lib/tree-growth';
import { UserTopicProgressSummary } from '@/lib/types';

type GardenNode = {
  topic: UserTopicProgressSummary;
  x: number;
  y: number;
  scale: number;
  row: number;
  z: number;
};

type BedBand = {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
};

function parseLatestActivity(value: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function activityWeight(value: string | null): number {
  const latest = parseLatestActivity(value);
  if (!latest) return 0;
  const hours = (Date.now() - latest.getTime()) / (1000 * 60 * 60);
  if (hours <= 36) return 40;
  if (hours <= 120) return 24;
  if (hours <= 336) return 12;
  return 4;
}

function momentumMeta(topic: UserTopicProgressSummary): {
  label: string;
  badgeClass: string;
  glow: string;
  glowOpacity: number;
} {
  const latest = parseLatestActivity(topic.latest_activity_at);
  if (!latest) {
    return {
      label: 'Just planted',
      badgeClass: 'border-stone-300 bg-stone-100 text-stone-700',
      glow: 'radial-gradient(circle, rgba(184,170,152,0.35), rgba(184,170,152,0) 68%)',
      glowOpacity: 0.14,
    };
  }
  const hours = (Date.now() - latest.getTime()) / (1000 * 60 * 60);
  if (hours <= 36) {
    return {
      label: 'Recently tended',
      badgeClass: 'border-emerald-300 bg-emerald-100 text-emerald-800',
      glow: 'radial-gradient(circle, rgba(110,231,183,0.5), rgba(110,231,183,0) 68%)',
      glowOpacity: 0.32,
    };
  }
  if (hours <= 120) {
    return {
      label: 'In motion',
      badgeClass: 'border-cyan-300 bg-cyan-100 text-cyan-800',
      glow: 'radial-gradient(circle, rgba(125,211,252,0.42), rgba(125,211,252,0) 68%)',
      glowOpacity: 0.24,
    };
  }
  if (hours <= 336) {
    return {
      label: 'Resting',
      badgeClass: 'border-amber-300 bg-amber-100 text-amber-800',
      glow: 'radial-gradient(circle, rgba(253,230,138,0.38), rgba(253,230,138,0) 68%)',
      glowOpacity: 0.18,
    };
  }
  return {
    label: 'Ready to revisit',
    badgeClass: 'border-violet-300 bg-violet-100 text-violet-800',
    glow: 'radial-gradient(circle, rgba(196,181,253,0.4), rgba(196,181,253,0) 68%)',
    glowOpacity: 0.18,
  };
}

function layeringLine(topic: UserTopicProgressSummary): string {
  if (topic.notes_count > 0 && topic.branch_count > 0) {
    return `${topic.notes_count} notebook note${topic.notes_count === 1 ? '' : 's'} · ${topic.branch_count} branch path${topic.branch_count === 1 ? '' : 's'}`;
  }
  if (topic.notes_count > 0) {
    return `${topic.notes_count} notebook note${topic.notes_count === 1 ? '' : 's'} gathered here`;
  }
  if (topic.branch_count > 0) {
    return `${topic.branch_count} branch path${topic.branch_count === 1 ? '' : 's'} opened here`;
  }
  return 'Core path still taking shape';
}

function buildGardenLayout(topics: UserTopicProgressSummary[]): { nodes: GardenNode[]; width: number; height: number; rows: number } {
  const ranked = [...topics].sort((a, b) => {
    const activityDelta = activityWeight(b.latest_activity_at) - activityWeight(a.latest_activity_at);
    if (activityDelta !== 0) return activityDelta;
    if (a.tree_stage !== b.tree_stage) return b.tree_stage - a.tree_stage;
    if (a.mastery_average !== b.mastery_average) return b.mastery_average - a.mastery_average;
    return a.topic_id - b.topic_id;
  });

  const columns = Math.max(2, Math.min(4, Math.ceil(Math.sqrt(Math.max(1, ranked.length)))));
  const rows = Math.max(1, Math.ceil(ranked.length / columns));
  const colGap = 240;
  const rowGap = 192;
  const rowOffset = 112;
  const width = columns * colGap + rowOffset + 260;
  const height = rows * rowGap + 260;

  const nodes: GardenNode[] = ranked.map((topic, index) => {
    const row = Math.floor(index / columns);
    const col = index % columns;
    const x = 170 + col * colGap + (row % 2 === 0 ? 0 : rowOffset);
    const y = 132 + row * rowGap;
    const scale = Math.min(1.1, 0.86 + row * 0.08 + Math.max(0, topic.tree_stage - 1) * 0.02);

    return {
      topic,
      x,
      y,
      scale,
      row,
      z: 30 + row * 10 + topic.tree_stage,
    };
  });

  return { nodes, width, height, rows };
}

function buildBedBands(layout: { width: number; rows: number }): BedBand[] {
  const bands: BedBand[] = [];
  for (let row = 0; row < layout.rows; row += 1) {
    bands.push({
      id: `row-bed-${row}`,
      x: layout.width * 0.5,
      y: 150 + row * 192,
      width: layout.width * 0.82,
      height: 136,
      opacity: Math.max(0.16, 0.32 - row * 0.04),
    });
  }
  return bands;
}

export function GardenScene({ topics }: { topics: UserTopicProgressSummary[] }) {
  const layout = useMemo(() => buildGardenLayout(topics), [topics]);
  const bedBands = useMemo(() => buildBedBands(layout), [layout]);

  return (
    <section className="panel relative overflow-hidden rounded-3xl p-0">
      <div className="border-b border-black/10 px-5 py-4 md:px-6">
        <h2 className="text-xl font-semibold">Living grove</h2>
        <p className="mt-1 text-sm text-black/65">
          Each plot carries its own rhythm. Warmer trees mark recent attention; notebook trails and branch paths show where a study has become more layered.
        </p>
      </div>

      <div className="relative overflow-auto px-2 pb-6 pt-3 md:px-4">
        <div
          className="relative rounded-3xl border border-black/10"
          style={{
            width: `${layout.width}px`,
            minHeight: `${layout.height}px`,
            background:
              'radial-gradient(circle at 14% 14%, rgba(125,211,252,0.16), transparent 36%), radial-gradient(circle at 82% 12%, rgba(110,231,183,0.18), transparent 38%), linear-gradient(180deg, #f8fcff 0%, #eef7ec 45%, #d9e9d5 100%)',
          }}
        >
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_86%,rgba(58,109,71,0.11),transparent_48%)]" />

          {bedBands.map((band) => (
            <div
              key={band.id}
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-[999px]"
              style={{
                left: `${band.x}px`,
                top: `${band.y}px`,
                width: `${band.width}px`,
                height: `${band.height}px`,
                background: 'radial-gradient(circle at 50% 42%, rgba(111,170,105,0.2), rgba(75,120,77,0.05) 66%, transparent 100%)',
                opacity: band.opacity,
              }}
            />
          ))}

          {layout.nodes.map(({ topic, x, y, scale, row, z }) => {
            const stageLabel = treeStageLabel(topic.tree_stage);
            const momentum = momentumMeta(topic);
            const memoryLine = layeringLine(topic);
            const glowOpacity = Math.min(0.42, momentum.glowOpacity + Math.min(topic.notes_count, 4) * 0.03);

            return (
              <Link
                key={topic.topic_id}
                href={`/topics/${topic.topic_id}`}
                className="group absolute -translate-x-1/2"
                style={{ left: `${x}px`, top: `${y}px`, zIndex: z }}
              >
                <div className="pointer-events-none relative">
                  <span
                    className="absolute left-1/2 top-[18px] h-[116px] w-[116px] -translate-x-1/2 rounded-full blur-2xl"
                    style={{ background: momentum.glow, opacity: glowOpacity }}
                  />
                  <span className="absolute bottom-4 left-1/2 h-7 w-[122px] -translate-x-1/2 rounded-[999px] bg-black/20 blur-[9px]" />
                  <span
                    className="absolute bottom-5 left-1/2 h-6 w-[120px] -translate-x-1/2 rotate-[-2deg] rounded-[999px] border border-emerald-900/20"
                    style={{
                      background:
                        row % 2 === 0
                          ? 'linear-gradient(180deg,#d9ccac,#c3aa85)'
                          : 'linear-gradient(180deg,#d6c5a1,#b99b72)',
                    }}
                  />
                  <div
                    className="relative mx-auto h-[124px] w-[124px] transition duration-200 group-hover:scale-[1.04]"
                    style={{ transform: `scale(${scale})` }}
                  >
                    <Image
                      src={treeStageAsset(topic.tree_stage)}
                      alt={`${topic.topic_name} tree stage ${topic.tree_stage}`}
                      fill
                      sizes="124px"
                      className="garden-tree-sway object-contain drop-shadow-[0_8px_16px_rgba(24,39,21,0.24)]"
                    />
                  </div>
                </div>

                <div className="mt-1.5 w-48 rounded-xl border border-black/10 bg-white/92 px-3 py-2 shadow-[0_10px_20px_rgba(16,19,33,0.12)] backdrop-blur">
                  <p className="line-clamp-1 text-sm font-semibold text-black">{topic.topic_name}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] ${momentum.badgeClass}`}>
                      {momentum.label}
                    </span>
                    <span className="text-[10px] uppercase tracking-[0.12em] text-black/55">{stageLabel}</span>
                  </div>
                  <p className="mt-1 text-xs text-black/62">{memoryLine}</p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}
