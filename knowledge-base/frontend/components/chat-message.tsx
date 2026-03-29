'use client';

import { ReactNode } from 'react';

import { MarkdownContent } from '@/components/markdown-content';
import { TutorStructuredAnswer } from '@/lib/types';

function RichText({ text }: { text: string }) {
  return (
    <MarkdownContent
      markdown={text}
      className="[&_li]:my-1 [&_ol]:space-y-1 [&_p]:my-2 [&_ul]:space-y-1"
    />
  );
}

export function AssistantMessage({
  text,
  structured,
  contextUsage,
  citations,
  actionSlot
}: {
  text: string;
  structured?: TutorStructuredAnswer | null;
  contextUsage?: { document_chunks: number; personal_notes: number; external_resources?: number } | null;
  citations?: Array<{ title: string; url: string; snippet?: string }> | null;
  actionSlot?: ReactNode;
}) {
  if (!structured) {
    return (
      <div className="max-w-3xl space-y-3 rounded-2xl border border-black/10 bg-paper/60 p-4">
        <RichText text={text} />
        {citations && citations.length > 0 && (
          <div className="rounded-lg border border-black/10 bg-white/80 p-3">
            <p className="text-xs uppercase tracking-[0.12em] text-black/60">Sources</p>
            <div className="mt-2 space-y-2">
              {citations.map((item) => (
                <a
                  key={item.url}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-md border border-black/10 bg-white px-2.5 py-2 text-xs hover:border-black/30"
                >
                  <p className="font-semibold text-black/85">{item.title}</p>
                  {item.snippet && <p className="mt-1 text-black/70">{item.snippet}</p>}
                  <p className="mt-1 truncate text-black/60">{item.url}</p>
                </a>
              ))}
            </div>
          </div>
        )}
        {contextUsage && (
          <p className="text-xs text-black/60">
            Context used: {contextUsage.document_chunks} source chunk(s)
            {contextUsage.personal_notes > 0 ? `, ${contextUsage.personal_notes} personal note(s)` : ''}
            {(contextUsage.external_resources ?? 0) > 0
              ? `, ${contextUsage.external_resources} web resource(s)`
              : ''}
          </p>
        )}
        {actionSlot}
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-3 rounded-2xl border border-black/10 bg-paper/60 p-4">
      <section>
        <p className="text-xs uppercase tracking-[0.12em] text-black/60">Overview</p>
        <p className="mt-1 text-sm leading-7 text-black/85">{structured.overview}</p>
      </section>

      <section className="rounded-lg border border-black/10 bg-white/70 p-3">
        <p className="text-xs uppercase tracking-[0.12em] text-black/60">Key Points</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-7">
          {structured.key_points.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-black/10 bg-white/70 p-3">
        <p className="text-xs uppercase tracking-[0.12em] text-black/60">Practical Steps</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-7">
          {structured.practical_steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      {structured.pitfalls.length > 0 && (
        <section className="rounded-lg border border-black/10 bg-white/70 p-3">
          <p className="text-xs uppercase tracking-[0.12em] text-black/60">Watch Outs</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-7">
            {structured.pitfalls.map((pitfall) => (
              <li key={pitfall}>{pitfall}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border border-black/10 bg-white p-3">
        <p className="text-xs uppercase tracking-[0.12em] text-black/60">Next Step</p>
        <p className="mt-1 text-sm font-medium leading-7">{structured.next_step}</p>
      </section>

      {contextUsage && (
        <p className="text-xs text-black/60">
          Context used: {contextUsage.document_chunks} source chunk(s)
          {contextUsage.personal_notes > 0 ? `, ${contextUsage.personal_notes} personal note(s)` : ''}
          {(contextUsage.external_resources ?? 0) > 0
            ? `, ${contextUsage.external_resources} web resource(s)`
            : ''}
        </p>
      )}
      {actionSlot}
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="inline-block max-w-[88%] rounded-xl bg-ink px-3 py-2 text-sm leading-relaxed text-white">
      {text}
    </div>
  );
}
