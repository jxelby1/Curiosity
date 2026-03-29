from __future__ import annotations

from typing import Final


CANONICAL_BRANCH_PURPOSES: Final[tuple[str, ...]] = (
    'deepen_theme',
    'compare_contrast',
    'context_influence',
    'study_exemplar',
    'creative_response',
    'style_technique_practice',
    'follow_lineage',
)

BRANCH_PURPOSE_LABELS: Final[dict[str, str]] = {
    'deepen_theme': 'Deepen Theme',
    'compare_contrast': 'Compare & Contrast',
    'context_influence': 'Context & Influence',
    'study_exemplar': 'Study an Exemplar',
    'creative_response': 'Creative Response',
    'style_technique_practice': 'Style / Technique Practice',
    'follow_lineage': 'Follow the Lineage',
}

_BRANCH_PURPOSE_ALIASES: Final[dict[str, str]] = {
    # Canonical values
    'deepen_theme': 'deepen_theme',
    'compare_contrast': 'compare_contrast',
    'context_influence': 'context_influence',
    'study_exemplar': 'study_exemplar',
    'creative_response': 'creative_response',
    'style_technique_practice': 'style_technique_practice',
    'follow_lineage': 'follow_lineage',
    # Human-readable variants
    'deepen theme': 'deepen_theme',
    'compare contrast': 'compare_contrast',
    'compare and contrast': 'compare_contrast',
    'context influence': 'context_influence',
    'context and influence': 'context_influence',
    'study exemplar': 'study_exemplar',
    'study an exemplar': 'study_exemplar',
    'creative response': 'creative_response',
    'style technique practice': 'style_technique_practice',
    'style and technique practice': 'style_technique_practice',
    'follow lineage': 'follow_lineage',
    'follow the lineage': 'follow_lineage',
    # Backwards-compatible legacy values
    'exploration': 'context_influence',
    'enrichment': 'deepen_theme',
    'specialization': 'study_exemplar',
    'remediation': 'style_technique_practice',
    'assessment_prep': 'style_technique_practice',
    'project': 'creative_response',
    'curiosity': 'context_influence',
}


def normalize_branch_purpose(raw_purpose: str | None, *, default: str = 'deepen_theme') -> str:
    cleaned = (raw_purpose or '').strip().lower()
    cleaned = cleaned.replace('&', ' and ')
    cleaned = cleaned.replace('/', ' ')
    cleaned = cleaned.replace('-', '_').replace(' ', '_')
    cleaned = '_'.join(segment for segment in cleaned.split('_') if segment)
    alias_key = cleaned.replace('_', ' ')
    resolved = _BRANCH_PURPOSE_ALIASES.get(cleaned) or _BRANCH_PURPOSE_ALIASES.get(alias_key)
    if resolved:
        return resolved
    return default if default in CANONICAL_BRANCH_PURPOSES else 'deepen_theme'


def branch_purpose_label(raw_purpose: str | None) -> str:
    canonical = normalize_branch_purpose(raw_purpose)
    return BRANCH_PURPOSE_LABELS.get(canonical, BRANCH_PURPOSE_LABELS['deepen_theme'])
