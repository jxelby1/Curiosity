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
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.16em] text-black/60">
          <Link href="/topics" className="underline underline-offset-4">
            Topics
          </Link>
          <span>/</span>
          <span>{topicName}</span>
        </div>
        <h1 className="text-3xl font-semibold md:text-4xl">{topicName}</h1>
        {subtitle && <p className="muted max-w-3xl text-sm md:text-base">{subtitle}</p>}
      </div>

      <div className="flex flex-wrap gap-2">
        <Link href={`/topics/${topicId}`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
          Overview
        </Link>
        <Link href={`/topics/${topicId}/notes`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
          Notes
        </Link>
        <Link href={`/topics/${topicId}/chat`} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
          Tutor Chat
        </Link>
        {rightSlot}
      </div>
    </header>
  );
}
