export type BranchPurpose =
  | 'deepen_theme'
  | 'compare_contrast'
  | 'context_influence'
  | 'study_exemplar'
  | 'creative_response'
  | 'style_technique_practice'
  | 'follow_lineage';

type BranchPurposeMeta = {
  value: BranchPurpose;
  label: string;
  summary: string;
};

const BRANCH_PURPOSE_META: Record<BranchPurpose, BranchPurposeMeta> = {
  deepen_theme: {
    value: 'deepen_theme',
    label: 'Deepen Theme',
    summary: 'Go deeper on a central idea without widening scope.',
  },
  compare_contrast: {
    value: 'compare_contrast',
    label: 'Compare & Contrast',
    summary: 'Set two works, styles, or interpretations side by side.',
  },
  context_influence: {
    value: 'context_influence',
    label: 'Context & Influence',
    summary: 'Study surrounding context, influence, and downstream impact.',
  },
  study_exemplar: {
    value: 'study_exemplar',
    label: 'Study an Exemplar',
    summary: 'Use one concrete work as a close study anchor.',
  },
  creative_response: {
    value: 'creative_response',
    label: 'Creative Response',
    summary: 'Create an original response grounded in what you studied.',
  },
  style_technique_practice: {
    value: 'style_technique_practice',
    label: 'Style / Technique Practice',
    summary: 'Run focused drills to sharpen execution and craft.',
  },
  follow_lineage: {
    value: 'follow_lineage',
    label: 'Follow the Lineage',
    summary: 'Trace precedents and later developments across a lineage.',
  },
};

const BRANCH_PURPOSE_ALIASES: Record<string, BranchPurpose> = {
  deepen_theme: 'deepen_theme',
  compare_contrast: 'compare_contrast',
  context_influence: 'context_influence',
  study_exemplar: 'study_exemplar',
  creative_response: 'creative_response',
  style_technique_practice: 'style_technique_practice',
  follow_lineage: 'follow_lineage',
  exploration: 'context_influence',
  enrichment: 'deepen_theme',
  specialization: 'study_exemplar',
  remediation: 'style_technique_practice',
  assessment_prep: 'style_technique_practice',
  project: 'creative_response',
  curiosity: 'context_influence',
};

export const BRANCH_PURPOSE_OPTIONS: BranchPurposeMeta[] = [
  BRANCH_PURPOSE_META.deepen_theme,
  BRANCH_PURPOSE_META.compare_contrast,
  BRANCH_PURPOSE_META.context_influence,
  BRANCH_PURPOSE_META.study_exemplar,
  BRANCH_PURPOSE_META.creative_response,
  BRANCH_PURPOSE_META.style_technique_practice,
  BRANCH_PURPOSE_META.follow_lineage,
];

export function normalizeBranchPurpose(rawValue: string | null | undefined): BranchPurpose {
  const token = String(rawValue || '')
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[/-]+/g, ' ')
    .replace(/\s+/g, '_');
  const normalized = token.replace(/_+/g, '_');
  return BRANCH_PURPOSE_ALIASES[normalized] || 'deepen_theme';
}

export function getBranchPurposeMeta(rawValue: string | null | undefined): BranchPurposeMeta {
  const canonical = normalizeBranchPurpose(rawValue);
  return BRANCH_PURPOSE_META[canonical];
}
