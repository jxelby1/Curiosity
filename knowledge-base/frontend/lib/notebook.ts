import { NoteType } from '@/lib/types';

export type NotebookLens =
  | 'reflection'
  | 'comparison'
  | 'exemplar'
  | 'interpretation'
  | 'view_shift'
  | 'next_thread';

export type NotebookLensOption = {
  tag: NotebookLens;
  label: string;
  shortLabel: string;
  noteType: NoteType;
  promptTitle: string;
  starter: string;
  description: string;
};

export const NOTEBOOK_LENS_OPTIONS: NotebookLensOption[] = [
  {
    tag: 'reflection',
    label: 'Reflection',
    shortLabel: 'Reflect',
    noteType: 'reflection',
    promptTitle: 'Reflection',
    starter: 'What became clearer today?\n- \nWhat still feels unresolved?\n- ',
    description: 'Capture what sharpened, what stayed unresolved, and what deserves a second look.',
  },
  {
    tag: 'comparison',
    label: 'Comparison',
    shortLabel: 'Compare',
    noteType: 'summary',
    promptTitle: 'Comparison',
    starter: 'Compare two works or interpretations:\n- Similarities:\n- Differences:\n- Why the contrast matters:',
    description: 'Set two works, interpretations, or styles beside each other and articulate the difference.',
  },
  {
    tag: 'exemplar',
    label: 'Saved Exemplar',
    shortLabel: 'Save exemplar',
    noteType: 'lesson',
    promptTitle: 'Exemplar',
    starter: 'Work or artifact:\nContext:\nWhat to study closely:\nWhy this is a reference point:',
    description: 'Save a work, artifact, or concrete example that deserves to become part of your taste library.',
  },
  {
    tag: 'interpretation',
    label: 'Interpretation',
    shortLabel: 'Interpret',
    noteType: 'summary',
    promptTitle: 'Interpretation',
    starter: 'My interpretation:\nEvidence from the work:\nAlternative reading worth considering:',
    description: 'State your reading clearly, ground it in evidence, and make room for alternative readings.',
  },
  {
    tag: 'view_shift',
    label: 'What Changed My View',
    shortLabel: 'View shift',
    noteType: 'reflection',
    promptTitle: 'View shift',
    starter: 'What changed my view:\nWhat triggered the shift:\nWhat I now notice differently:',
    description: 'Record the moments that reshaped your taste, attention, or interpretation.',
  },
  {
    tag: 'next_thread',
    label: 'Explore Next',
    shortLabel: 'Explore next',
    noteType: 'reminder',
    promptTitle: 'Explore next',
    starter: 'What I want to explore next:\nWhy this thread matters now:\nFirst concrete step:',
    description: 'Turn emerging curiosity into the next live thread without turning the notebook into a task list.',
  },
];

export function getNotebookLensOption(tag: NotebookLens | string | null | undefined): NotebookLensOption {
  return NOTEBOOK_LENS_OPTIONS.find((item) => item.tag === tag) || NOTEBOOK_LENS_OPTIONS[0];
}

