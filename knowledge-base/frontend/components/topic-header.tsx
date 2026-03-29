'use client';

import Link from 'next/link';

export function TopicHeader({
  topicId,
  topicName,
  subtitle,
  rightSlot
}: {
  topicId: string;
  topicName: string;
  subtitle?: string;
  rightSlot?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-black/10 bg-white/70 p-4 shadow-[0_14px_34px_rgba(20,26,24,0.08)] backdrop-blur-sm md:p-5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.16em] text-black/60">
          <Link href="/topics" className="underline underline-offset-4">
            Studies
          </Link>
          <span>/</span>
          <span>{topicName}</span>
        </div>
        <h1 className="text-3xl md:text-4xl">{topicName}</h1>
        {subtitle && <p className="muted max-w-3xl text-sm md:text-base">{subtitle}</p>}
      </div>

      <div className="flex flex-wrap gap-2">
        <Link href="/garden" className="studio-button-secondary px-3 py-2 text-sm">
          Garden
        </Link>
        <Link href={`/topics/${topicId}`} className="studio-button-secondary px-3 py-2 text-sm">
          Overview
        </Link>
        <Link href={`/topics/${topicId}/notes`} className="studio-button-secondary px-3 py-2 text-sm">
          Notebook
        </Link>
        <Link href={`/topics/${topicId}/chat`} className="studio-button-secondary px-3 py-2 text-sm">
          Dialogue
        </Link>
        {rightSlot}
      </div>
    </header>
  );
}
