'use client';

import { useMemo } from 'react';

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInlineMarkdown(input: string): string {
  const escaped = escapeHtml(input);
  return escaped
    .replace(/`([^`\n]+?)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+?)__/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/_([^_\n]+?)_/g, '<em>$1</em>');
}

function normalizeMarkdownSource(input: string): string {
  return (input || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\([*_`~-])/g, '$1');
}

export function markdownToPlainText(markdown: string): string {
  const normalized = normalizeMarkdownSource(markdown)
    .replace(/`{1,3}([\s\S]*?)`{1,3}/g, '$1')
    .replace(/\*\*([\s\S]*?)\*\*/g, '$1')
    .replace(/__([\s\S]*?)__/g, '$1')
    .replace(/\*([\s\S]*?)\*/g, '$1')
    .replace(/_([\s\S]*?)_/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\r\n?/g, '\n')
    .replace(/\n+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return normalized;
}

export function markdownToHtml(markdown: string): string {
  const lines = normalizeMarkdownSource(markdown).replace(/\r\n?/g, '\n').split('\n');
  const blocks: string[] = [];
  let paragraphLines: string[] = [];
  let unorderedItems: string[] = [];
  let orderedItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    blocks.push(`<p>${paragraphLines.map((line) => renderInlineMarkdown(line)).join('<br />')}</p>`);
    paragraphLines = [];
  };

  const flushUnordered = () => {
    if (!unorderedItems.length) return;
    blocks.push(`<ul>${unorderedItems.map((item) => `<li>${item}</li>`).join('')}</ul>`);
    unorderedItems = [];
  };

  const flushOrdered = () => {
    if (!orderedItems.length) return;
    blocks.push(`<ol>${orderedItems.map((item) => `<li>${item}</li>`).join('')}</ol>`);
    orderedItems = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      let nextNonEmpty = '';
      for (let lookahead = index + 1; lookahead < lines.length; lookahead += 1) {
        const candidate = lines[lookahead].trim();
        if (candidate) {
          nextNonEmpty = candidate;
          break;
        }
      }
      const continuesUnordered = unorderedItems.length > 0 && /^[-*]\s+/.test(nextNonEmpty);
      const continuesOrdered = orderedItems.length > 0 && /^\d+[.)]\s+/.test(nextNonEmpty);
      if (continuesUnordered || continuesOrdered) {
        continue;
      }
      flushParagraph();
      flushUnordered();
      flushOrdered();
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushUnordered();
      flushOrdered();
      const level = Math.min(3, headingMatch[1].length);
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (unorderedMatch) {
      flushParagraph();
      flushOrdered();
      unorderedItems.push(renderInlineMarkdown(unorderedMatch[1].trim()));
      continue;
    }

    const orderedMatch = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      flushUnordered();
      orderedItems.push(renderInlineMarkdown(orderedMatch[1].trim()));
      continue;
    }

    flushUnordered();
    flushOrdered();
    paragraphLines.push(trimmed);
  }

  flushParagraph();
  flushUnordered();
  flushOrdered();

  return blocks.join('\n');
}

export function MarkdownContent({ markdown, className = '' }: { markdown: string; className?: string }) {
  const html = useMemo(() => markdownToHtml(markdown), [markdown]);
  return (
    <div
      className={`text-sm leading-relaxed text-black/85 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_ol]:ml-5 [&_ol]:list-decimal [&_p]:my-2 [&_strong]:font-semibold [&_ul]:ml-5 [&_ul]:list-disc [&_code]:rounded [&_code]:bg-black/5 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
