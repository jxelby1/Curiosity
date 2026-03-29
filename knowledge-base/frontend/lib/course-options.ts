import { AssessmentStyle, CourseDepth, StartingSkillLevel, TechnicalDepth } from '@/lib/types';

export const COURSE_DEPTH_OPTIONS: Array<{
  value: CourseDepth;
  label: string;
  description: string;
}> = [
  {
    value: 'light',
    label: 'Light course',
    description: 'Fast, compact path with essential skills.',
  },
  {
    value: 'standard',
    label: 'Standard',
    description: 'Balanced scope for most learning goals.',
  },
  {
    value: 'deep_dive',
    label: 'Deep dive',
    description: 'Broader and more detailed progression map.',
  },
];

export const STARTING_SKILL_LEVEL_OPTIONS: Array<{
  value: StartingSkillLevel;
  label: string;
  description: string;
}> = [
  {
    value: 'beginner',
    label: 'Beginner',
    description: 'Includes foundations and gradual ramp-up.',
  },
  {
    value: 'intermediate',
    label: 'Intermediate',
    description: 'Assumes some familiarity and moves faster.',
  },
  {
    value: 'advanced',
    label: 'Advanced',
    description: 'Compresses basics and emphasizes high-order practice.',
  },
];

export const TECHNICAL_DEPTH_OPTIONS: Array<{
  value: TechnicalDepth;
  label: string;
  description: string;
}> = [
  {
    value: 'beginner',
    label: 'Beginner depth',
    description: 'Highly scaffolded, minimal assumptions, concept-first explanations.',
  },
  {
    value: 'intermediate',
    label: 'Intermediate depth',
    description: 'Balanced rigor with practical synthesis and moderate complexity.',
  },
  {
    value: 'advanced',
    label: 'Advanced depth',
    description: 'Dense explanations with stronger assumptions and edge-case handling.',
  },
  {
    value: 'degree',
    label: 'Degree level',
    description: 'Undergraduate-style framing with formal conceptual structure.',
  },
  {
    value: 'masters',
    label: 'Masters level',
    description: 'Graduate-level nuance, synthesis, and analytical interpretation.',
  },
  {
    value: 'phd',
    label: 'PhD level',
    description: 'Research-style rigor, ambiguity handling, and high conceptual density.',
  },
];

export const ASSESSMENT_STYLE_OPTIONS: Array<{
  value: AssessmentStyle;
  label: string;
  category: 'Core' | 'Applied' | 'Code' | 'Quant';
  description: string;
}> = [
  {
    value: 'open_text',
    label: 'Open text',
    category: 'Core',
    description: 'Long-form written reasoning and synthesis.',
  },
  {
    value: 'short_answer',
    label: 'Short answer',
    category: 'Core',
    description: 'Concise explanation and concept recall.',
  },
  {
    value: 'multiple_choice',
    label: 'Multiple choice',
    category: 'Core',
    description: 'Single best-answer checks.',
  },
  {
    value: 'flashcard',
    label: 'Flashcard recall',
    category: 'Core',
    description: 'Fast recall for definitions and facts.',
  },
  {
    value: 'scenario',
    label: 'Scenario reasoning',
    category: 'Applied',
    description: 'Case-based judgment and tradeoffs.',
  },
  {
    value: 'coding',
    label: 'Coding assessment',
    category: 'Code',
    description: 'Applied coding decisions and implementation.',
  },
  {
    value: 'debugging',
    label: 'Debugging',
    category: 'Code',
    description: 'Locate faults and propose fixes.',
  },
  {
    value: 'code_completion',
    label: 'Code completion',
    category: 'Code',
    description: 'Fill missing code and finish snippets.',
  },
  {
    value: 'code_interpretation',
    label: 'Code interpretation',
    category: 'Code',
    description: 'Explain behavior and intent of code.',
  },
  {
    value: 'math_problem',
    label: 'Math problem solving',
    category: 'Quant',
    description: 'Quantitative and numeric reasoning.',
  },
];

export const DEFAULT_ASSESSMENT_STYLES: AssessmentStyle[] = [
  'short_answer',
  'multiple_choice',
  'flashcard',
];
