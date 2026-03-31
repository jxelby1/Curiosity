'use client';

import { formatDisplayTag } from '@/lib/display-format';
import { MarkdownContent } from '@/components/markdown-content';

type LessonShape = {
  title: string;
  summary: string;
  learning_objectives: string[];
  key_concepts: Array<{ term: string; description: string }>;
  sections: Array<{ heading: string; content: string }>;
  exemplar_focus: string[];
  comparison_prompts: string[];
  observation_prompts: string[];
  response_prompts: string[];
  practice_hooks: string[];
  takeaways: string[];
  next_steps: string[];
};

type ExamplesShape = {
  title: string;
  intro: string;
  examples: Array<{ name: string; explanation: string; why_it_matters: string }>;
  exemplar_focus: string[];
  comparison_prompts: string[];
  observation_prompts: string[];
  response_prompts: string[];
  practice_hooks: string[];
};

type ExercisesShape = {
  title: string;
  intro: string;
  exercises: Array<{
    title: string;
    task: string;
    hints: string[];
    expected_outcome: string;
    difficulty: 'easy' | 'medium' | 'hard';
  }>;
};

type DeepLessonShape = {
  title: string;
  summary: string;
  essential_questions: string[];
  sections: Array<{ heading: string; content: string }>;
  exemplar_focus: string[];
  comparison_prompts: string[];
  observation_prompts: string[];
  response_prompts: string[];
  practice_hooks: string[];
  key_terms: Array<{ term: string; description: string }>;
  study_prompts: string[];
};

const LESSON_SUMMARY_MAX = 300;
const LESSON_KEY_CONCEPT_DESC_MAX = 260;
const EXAMPLES_INTRO_MAX = 420;
const EXAMPLES_TEXT_MAX = 500;
const EXAMPLES_WHY_MAX = 280;
const EXERCISES_INTRO_MAX = 420;
const EXERCISE_TASK_MAX = 500;
const EXERCISE_OUTCOME_MAX = 300;
const DEEP_LESSON_SUMMARY_MAX = 420;
const DEEP_LESSON_TERM_DESC_MAX = 260;

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || '').trim()).filter(Boolean);
}

function toObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

function hasSentenceClosure(text: string): boolean {
  return /[.!?…](?:["')\]]*)$/.test(text);
}

function ensureSentenceClosure(text: string, maxLen: number): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  if (/[.!?](?:["')\]]*)$/.test(trimmed)) return trimmed;
  if (maxLen <= 1) return trimmed.slice(0, maxLen);
  if (trimmed.length + 1 <= maxLen) return `${trimmed}.`;
  return `${trimmed.slice(0, Math.max(0, maxLen - 1)).trim()}.`;
}

function truncateToCompleteSentence(text: string, maxLen: number): string {
  if (!text) return '';
  if (maxLen <= 1) return text.slice(0, maxLen);

  const budget = maxLen;
  const window = text.slice(0, budget).trimEnd();
  if (!window) return '';

  const sentenceMatches = [...window.matchAll(/[.!?](?=(?:["')\]]|\s|$))/g)];
  const sentenceCandidate = sentenceMatches.at(-1);
  if (sentenceCandidate && sentenceCandidate.index !== undefined) {
    const end = sentenceCandidate.index + sentenceCandidate[0].length;
    if (end >= Math.floor(budget * 0.45)) {
      return window.slice(0, end).trim();
    }
  }

  const clauseMatches = [...window.matchAll(/[,;:](?=\s|$)/g)];
  const clauseCandidate = clauseMatches.at(-1);
  if (clauseCandidate && clauseCandidate.index !== undefined) {
    const cut = clauseCandidate.index;
    if (cut >= Math.floor(budget * 0.45)) {
      return ensureSentenceClosure(window.slice(0, cut).replace(/[,\-:;]+$/, ''), maxLen);
    }
  }

  const softBreakPattern = /\b(and|with|which|that|including|while|where|when|because|since)\b/gi;
  let softBreakIndex = -1;
  let match: RegExpExecArray | null = softBreakPattern.exec(window);
  while (match) {
    softBreakIndex = match.index;
    match = softBreakPattern.exec(window);
  }
  if (softBreakIndex >= Math.floor(budget * 0.55)) {
    return ensureSentenceClosure(window.slice(0, softBreakIndex), maxLen);
  }

  const wordBreak = Math.max(window.lastIndexOf(' '), window.lastIndexOf('\n'), window.lastIndexOf('\t'));
  const trimmed = (wordBreak >= Math.floor(budget * 0.6) ? window.slice(0, wordBreak) : window)
    .replace(/[,\-:;]+$/, '')
    .trim();
  const base = trimmed || window.trim();
  return ensureSentenceClosure(base, maxLen);
}

function normalizeCardSnippet(value: unknown, maxLen: number): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  const endsWithEllipsis = /(?:\u2026|\.{3})$/.test(text);
  const withoutEllipsis = endsWithEllipsis ? text.replace(/(?:\u2026|\.{3})\s*$/, '').trim() : text;

  if (withoutEllipsis.length > maxLen) {
    return truncateToCompleteSentence(withoutEllipsis, maxLen);
  }

  const likelyHardCutAtBoundary =
    withoutEllipsis.length >= maxLen - 1 && /[A-Za-z0-9]$/.test(withoutEllipsis) && !hasSentenceClosure(withoutEllipsis);
  if (endsWithEllipsis || likelyHardCutAtBoundary) {
    return truncateToCompleteSentence(withoutEllipsis, maxLen);
  }

  if (!hasSentenceClosure(withoutEllipsis) && withoutEllipsis.length >= 90) {
    return ensureSentenceClosure(withoutEllipsis, maxLen);
  }

  return withoutEllipsis;
}

export function parseLessonContent(value: unknown): LessonShape | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;

  const keyConcepts = toObjectArray(input.key_concepts)
    .map((item) => ({
      term: String(item.term || '').trim(),
      description: normalizeCardSnippet(item.description, LESSON_KEY_CONCEPT_DESC_MAX)
    }))
    .filter((item) => item.term && item.description);

  const sections = toObjectArray(input.sections)
    .map((item) => ({
      heading: String(item.heading || '').trim(),
      content: String(item.content || '').trim()
    }))
    .filter((item) => item.heading && item.content);

  const result: LessonShape = {
    title: String(input.title || '').trim(),
    summary: normalizeCardSnippet(input.summary, LESSON_SUMMARY_MAX),
    learning_objectives: toStringArray(input.learning_objectives),
    key_concepts: keyConcepts,
    sections,
    exemplar_focus: toStringArray(input.exemplar_focus),
    comparison_prompts: toStringArray(input.comparison_prompts),
    observation_prompts: toStringArray(input.observation_prompts),
    response_prompts: toStringArray(input.response_prompts),
    practice_hooks: toStringArray(input.practice_hooks),
    takeaways: toStringArray(input.takeaways),
    next_steps: toStringArray(input.next_steps)
  };

  if (!result.title || !result.summary || result.sections.length === 0) return null;
  return result;
}

export function parseExamplesContent(value: unknown): ExamplesShape | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;

  const examples = toObjectArray(input.examples)
    .map((item) => ({
      name: String(item.name || '').trim(),
      explanation: normalizeCardSnippet(item.explanation, EXAMPLES_TEXT_MAX),
      why_it_matters: normalizeCardSnippet(item.why_it_matters, EXAMPLES_WHY_MAX)
    }))
    .filter((item) => item.name && item.explanation);

  const result: ExamplesShape = {
    title: String(input.title || '').trim(),
    intro: normalizeCardSnippet(input.intro, EXAMPLES_INTRO_MAX),
    examples,
    exemplar_focus: toStringArray(input.exemplar_focus),
    comparison_prompts: toStringArray(input.comparison_prompts),
    observation_prompts: toStringArray(input.observation_prompts),
    response_prompts: toStringArray(input.response_prompts),
    practice_hooks: toStringArray(input.practice_hooks),
  };

  if (!result.title || result.examples.length === 0) return null;
  return result;
}

export function parseExercisesContent(value: unknown): ExercisesShape | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;

  const exercises = toObjectArray(input.exercises)
    .map((item) => {
      const difficultyRaw = String(item.difficulty || 'medium').toLowerCase();
      const difficulty: 'easy' | 'medium' | 'hard' =
        difficultyRaw === 'easy' || difficultyRaw === 'hard' ? (difficultyRaw as 'easy' | 'hard') : 'medium';

      return {
        title: String(item.title || '').trim(),
        task: normalizeCardSnippet(item.task, EXERCISE_TASK_MAX),
        hints: toStringArray(item.hints),
        expected_outcome: normalizeCardSnippet(item.expected_outcome, EXERCISE_OUTCOME_MAX),
        difficulty
      };
    })
    .filter((item) => item.title && item.task)
    .slice(0, 2);

  const result: ExercisesShape = {
    title: String(input.title || '').trim(),
    intro: normalizeCardSnippet(input.intro, EXERCISES_INTRO_MAX),
    exercises
  };

  if (!result.title || result.exercises.length === 0) return null;
  return result;
}

export function parseDeepLessonContent(value: unknown): DeepLessonShape | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;

  const sections = toObjectArray(input.sections)
    .map((item) => ({
      heading: String(item.heading || '').trim(),
      content: String(item.content || '').trim()
    }))
    .filter((item) => item.heading && item.content);

  const keyTerms = toObjectArray(input.key_terms)
    .map((item) => ({
      term: String(item.term || '').trim(),
      description: normalizeCardSnippet(item.description, DEEP_LESSON_TERM_DESC_MAX)
    }))
    .filter((item) => item.term && item.description);

  const result: DeepLessonShape = {
    title: String(input.title || '').trim(),
    summary: normalizeCardSnippet(input.summary, DEEP_LESSON_SUMMARY_MAX),
    essential_questions: toStringArray(input.essential_questions),
    sections,
    exemplar_focus: toStringArray(input.exemplar_focus),
    comparison_prompts: toStringArray(input.comparison_prompts),
    observation_prompts: toStringArray(input.observation_prompts),
    response_prompts: toStringArray(input.response_prompts),
    practice_hooks: toStringArray(input.practice_hooks),
    key_terms: keyTerms,
    study_prompts: toStringArray(input.study_prompts),
  };

  if (!result.title || result.sections.length === 0) return null;
  return result;
}

function StudioPromptPanel({
  title,
  items,
  markerClass,
}: {
  title: string;
  items: string[];
  markerClass: string;
}) {
  if (items.length === 0) return null;
  return (
    <article className="rounded-xl border border-black/10 bg-white p-4">
      <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">{title}</h4>
      <ul className="mt-3 space-y-2 text-sm">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className={`mt-1 h-1.5 w-1.5 rounded-full ${markerClass}`} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

function StudySequenceSection({
  title,
  subtitle,
  exemplarFocus,
  observationPrompts,
  comparisonPrompts,
  responsePrompts,
  practiceHooks,
}: {
  title: string;
  subtitle: string;
  exemplarFocus: string[];
  observationPrompts: string[];
  comparisonPrompts: string[];
  responsePrompts: string[];
  practiceHooks: string[];
}) {
  const hasContent =
    exemplarFocus.length > 0 ||
    observationPrompts.length > 0 ||
    comparisonPrompts.length > 0 ||
    responsePrompts.length > 0 ||
    practiceHooks.length > 0;

  if (!hasContent) return null;

  return (
    <section className="rounded-xl border border-black/10 bg-white p-5">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">{title}</h3>
        <p className="muted text-sm leading-relaxed">{subtitle}</p>
      </div>

      {exemplarFocus.length > 0 && (
        <div className="mt-4 rounded-xl border border-black/10 bg-paper/45 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-black/60">Anchor Exemplar</p>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed">
            {exemplarFocus.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-ink" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <StudioPromptPanel title="Notice" items={observationPrompts} markerClass="bg-ink" />
        <StudioPromptPanel title="Compare" items={comparisonPrompts} markerClass="bg-moss" />
        <StudioPromptPanel title="Respond" items={responsePrompts} markerClass="bg-brass" />
        <StudioPromptPanel title="Try" items={practiceHooks} markerClass="bg-emerald-500" />
      </div>
    </section>
  );
}

export function LessonRenderer({ content }: { content: LessonShape }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold leading-tight">{content.title}</h2>
        <p className="muted max-w-3xl text-sm leading-relaxed">{content.summary}</p>
      </div>

      <section className="rounded-xl border border-black/10 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Learning Objectives</h3>
        <ul className="mt-3 space-y-2 text-sm leading-relaxed">
          {content.learning_objectives.map((objective) => (
            <li key={objective} className="flex gap-2">
              <span className="mt-1 h-1.5 w-1.5 rounded-full bg-ink" />
              <span>{objective}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        {content.key_concepts.map((concept) => (
          <article key={concept.term} className="rounded-xl border border-black/10 bg-white p-4">
            <h4 className="text-base font-semibold">{concept.term}</h4>
            <p className="muted mt-2 text-sm leading-relaxed">{concept.description}</p>
          </article>
        ))}
      </section>

      <section className="space-y-3">
        {content.sections.map((section) => (
          <article key={section.heading} className="rounded-xl border border-black/10 bg-white p-5">
            <h4 className="text-lg font-semibold">{section.heading}</h4>
            <p className="muted mt-3 text-sm leading-7">{section.content}</p>
          </article>
        ))}
      </section>

      <StudySequenceSection
        title="Study Sequence"
        subtitle="Use the lesson first, then move from observation to interpretation, comparison, and transfer with evidence in view."
        exemplarFocus={content.exemplar_focus}
        observationPrompts={content.observation_prompts}
        comparisonPrompts={content.comparison_prompts}
        responsePrompts={content.response_prompts}
        practiceHooks={content.practice_hooks}
      />

      <section className="grid gap-4 md:grid-cols-2">
        <article className="rounded-xl border border-black/10 bg-white p-4">
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Takeaways</h4>
          <ul className="mt-3 space-y-2 text-sm">
            {content.takeaways.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-moss" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-xl border border-black/10 bg-white p-4">
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Next Steps</h4>
          <ul className="mt-3 space-y-2 text-sm">
            {content.next_steps.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brass" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </div>
  );
}

export function ExamplesRenderer({ content }: { content: ExamplesShape }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{content.title}</h2>
        <p className="muted mt-2 max-w-3xl text-sm leading-relaxed">{content.intro}</p>
      </div>

      <div className="space-y-3">
        {content.examples.map((example) => (
          <article key={example.name} className="rounded-xl border border-black/10 bg-white p-5">
            <h3 className="text-lg font-semibold">{example.name}</h3>
            <p className="muted mt-3 text-sm leading-7">{example.explanation}</p>
            <div className="mt-4 rounded-lg border border-black/10 bg-paper/70 p-3 text-sm">
              <p className="font-medium">Why it matters</p>
              <p className="muted mt-1 leading-relaxed">{example.why_it_matters}</p>
            </div>
          </article>
        ))}
      </div>

      <StudySequenceSection
        title="Example Sequence"
        subtitle="Read the examples as a progression: anchor case, contrast case, then transfer. Use the prompts only after the examples have done real teaching work."
        exemplarFocus={content.exemplar_focus}
        observationPrompts={content.observation_prompts}
        comparisonPrompts={content.comparison_prompts}
        responsePrompts={content.response_prompts}
        practiceHooks={content.practice_hooks}
      />
    </div>
  );
}

export function ExercisesRenderer({ content }: { content: ExercisesShape }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{content.title}</h2>
        <p className="muted mt-2 max-w-3xl text-sm leading-relaxed">{content.intro}</p>
      </div>

      <div className="space-y-3">
        {content.exercises.map((exercise) => (
          <article key={exercise.title} className="rounded-xl border border-black/10 bg-white p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-lg font-semibold">{exercise.title}</h3>
              <span className="badge">{formatDisplayTag(exercise.difficulty)}</span>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-black/65">Task</p>
                <p className="muted mt-2 leading-7">{exercise.task}</p>
              </div>

              <div>
                <p className="text-xs uppercase tracking-[0.14em] text-black/65">Hints</p>
                <ul className="mt-2 space-y-2">
                  {exercise.hints.map((hint) => (
                    <li key={hint} className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-ink" />
                      <span className="muted">{hint}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-lg border border-black/10 bg-paper/70 p-3">
                <p className="font-medium">Expected outcome</p>
                <p className="muted mt-1 leading-relaxed">{exercise.expected_outcome}</p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export function DeepLessonRenderer({ content }: { content: DeepLessonShape }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold leading-tight">{content.title}</h2>
        <p className="muted max-w-4xl text-sm leading-relaxed">{content.summary}</p>
      </div>

      <section className="rounded-xl border border-black/10 bg-white p-5">
        <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Essential Questions</h3>
        <ul className="mt-3 space-y-2 text-sm leading-relaxed">
          {content.essential_questions.map((question) => (
            <li key={question} className="flex gap-2">
              <span className="mt-1 h-1.5 w-1.5 rounded-full bg-ink" />
              <span>{question}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        {content.sections.map((section) => (
          <article key={section.heading} className="rounded-xl border border-black/10 bg-white p-5">
            <h4 className="text-lg font-semibold">{section.heading}</h4>
            <MarkdownContent markdown={section.content} className="mt-3 text-sm leading-7" />
          </article>
        ))}
      </section>

      <StudySequenceSection
        title="How to Read This Deep Dive"
        subtitle="Keep the evidence in view first, then move through close reading, context, comparison, and transfer."
        exemplarFocus={content.exemplar_focus}
        observationPrompts={content.observation_prompts}
        comparisonPrompts={content.comparison_prompts}
        responsePrompts={content.response_prompts}
        practiceHooks={content.practice_hooks}
      />

      <section className="grid gap-4 md:grid-cols-2">
        <article className="rounded-xl border border-black/10 bg-white p-4">
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Key Terms</h4>
          <div className="mt-3 space-y-2">
            {content.key_terms.map((term) => (
              <div key={term.term} className="rounded-lg border border-black/10 bg-paper/60 p-3">
                <p className="text-sm font-semibold">{term.term}</p>
                <p className="muted mt-1 text-sm">{term.description}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-xl border border-black/10 bg-white p-4">
          <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Study Prompts</h4>
          <ul className="mt-3 space-y-2 text-sm">
            {content.study_prompts.map((prompt) => (
              <li key={prompt} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brass" />
                <span>{prompt}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </div>
  );
}
