'use client';

import { formatDisplayTag } from '@/lib/display-format';

type LessonShape = {
  title: string;
  summary: string;
  learning_objectives: string[];
  key_concepts: Array<{ term: string; description: string }>;
  sections: Array<{ heading: string; content: string }>;
  takeaways: string[];
  next_steps: string[];
};

type ExamplesShape = {
  title: string;
  intro: string;
  examples: Array<{ name: string; explanation: string; why_it_matters: string }>;
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

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || '').trim()).filter(Boolean);
}

function toObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

export function parseLessonContent(value: unknown): LessonShape | null {
  if (!value || typeof value !== 'object') return null;
  const input = value as Record<string, unknown>;

  const keyConcepts = toObjectArray(input.key_concepts)
    .map((item) => ({
      term: String(item.term || '').trim(),
      description: String(item.description || '').trim()
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
    summary: String(input.summary || '').trim(),
    learning_objectives: toStringArray(input.learning_objectives),
    key_concepts: keyConcepts,
    sections,
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
      explanation: String(item.explanation || '').trim(),
      why_it_matters: String(item.why_it_matters || '').trim()
    }))
    .filter((item) => item.name && item.explanation);

  const result: ExamplesShape = {
    title: String(input.title || '').trim(),
    intro: String(input.intro || '').trim(),
    examples
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
        task: String(item.task || '').trim(),
        hints: toStringArray(item.hints),
        expected_outcome: String(item.expected_outcome || '').trim(),
        difficulty
      };
    })
    .filter((item) => item.title && item.task)
    .slice(0, 2);

  const result: ExercisesShape = {
    title: String(input.title || '').trim(),
    intro: String(input.intro || '').trim(),
    exercises
  };

  if (!result.title || result.exercises.length === 0) return null;
  return result;
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
