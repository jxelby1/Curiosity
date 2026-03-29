'use client';

import Image from 'next/image';

import { treeStageAsset, treeStageLabel } from '@/lib/tree-growth';

export function TopicTreeStage({
  stage,
  className = '',
  compact = false
}: {
  stage: number;
  className?: string;
  compact?: boolean;
}) {
  const label = treeStageLabel(stage);
  const src = treeStageAsset(stage);

  return (
    <div className={`rounded-xl border border-black/10 bg-white p-3 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-[0.14em] text-black/60">Growth stage</p>
        <span className="badge">Stage {stage}</span>
      </div>
      <div className={`relative mx-auto mt-2 ${compact ? 'h-28 w-28' : 'h-44 w-44'}`}>
        <Image
          src={src}
          alt={`Tree growth stage ${stage}: ${label}`}
          fill
          className="object-contain"
          sizes={compact ? '112px' : '176px'}
        />
      </div>
      <p className="mt-1 text-center text-sm font-medium">{label}</p>
    </div>
  );
}
