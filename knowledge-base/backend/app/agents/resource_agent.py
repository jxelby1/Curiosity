from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any, Literal
from urllib.parse import quote, unquote, urlparse

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import LearningResource, ResourceType, SkillEdge, SkillNode, Topic, UserSkillState
from app.core.exceptions import ConfigurationError, ProviderError
from app.core.course_preferences import (
    normalize_technical_depth,
    technical_depth_lesson_targets,
    technical_depth_prompt_guidance,
)
from app.schemas.llm import (
    ExamplesPlan,
    ExercisesPlan,
    ExternalResourceReasoningPlan,
    DeepLessonPlan,
    LessonPlan,
)
from app.services.llm import LLMService
from app.services.course_memory import CourseMemoryService, CourseMemorySnapshot
from app.services.course_research import CourseResearchService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService


logger = logging.getLogger(__name__)
ResourceSource = Literal['stored', 'generated', 'regenerated']

_TRUSTED_MEDIA_DOMAINS = (
    'worldhistory.org',
    'britannica.com',
    'history.state.gov',
    'state.gov',
    'un.org',
    'unesco.org',
    'worldbank.org',
    'imf.org',
    'oecd.org',
    'cia.gov',
    'ourworldindata.org',
    'nasa.gov',
    'noaa.gov',
    'usgs.gov',
    'openstax.org',
    'encyclopedia.com',
    'metmuseum.org',
    'moma.org',
    'tate.org.uk',
    'si.edu',
    'loc.gov',
    'archives.gov',
    'khanacademy.org',
    'bbc.com',
    'bbc.co.uk',
    'reuters.com',
    'apnews.com',
    'nytimes.com',
    'washingtonpost.com',
    'theguardian.com',
    'economist.com',
    'bloomberg.com',
    'wsj.com',
    'ft.com',
    'medium.com',
    'nationalgeographic.com',
    'pbs.org',
    'history.com',
    'youtube.com',
    'youtu.be',
)
_DEEMPHASIZED_MEDIA_DOMAINS = (
    'wikipedia.org',
    'wikimedia.org',
)
_TRUSTED_YOUTUBE_HINTS = (
    'khan academy',
    'crashcourse',
    'ted-ed',
    'ted ed',
    'mit opencourseware',
    'smarthistory',
    'bbc',
    'pbs',
    'national geographic',
)
_BLOCKED_SOCIAL_MEDIA_DOMAINS = (
    'facebook.com',
    'fb.watch',
    'instagram.com',
    'tiktok.com',
    'x.com',
    'twitter.com',
    'threads.net',
    'snapchat.com',
    'pinterest.com',
    'reddit.com',
)
_BLOCKED_STOCK_MEDIA_DOMAINS = (
    'gettyimages.com',
    'istockphoto.com',
    'shutterstock.com',
    'stock.adobe.com',
    'adobestock.com',
    'dreamstime.com',
    'alamy.com',
    'depositphotos.com',
    '123rf.com',
)
_VISUAL_MEDIA_HINTS = (
    'image',
    'photo',
    'photograph',
    'painting',
    'drawing',
    'sketch',
    'diagram',
    'map',
    'illustration',
    'chart',
    'timeline',
    'figure',
    'satellite',
    'atlas',
    'scene',
    'still',
    'frame',
    'poster',
    'facade',
    'plan',
    'blueprint',
    'layout',
    'typography',
    'composition',
    'gallery',
    'museum collection',
    'artifact',
    'object',
    'archive image',
    'visual analysis',
)
_VISUAL_DISCIPLINE_HINTS = (
    'art',
    'painting',
    'drawing',
    'illustration',
    'design',
    'typography',
    'poster',
    'architecture',
    'building',
    'city',
    'urban',
    'film',
    'cinema',
    'scene',
    'director',
    'photography',
    'photo',
    'visual',
    'music',
    'dj',
    'curation',
    'writing',
    'essay',
    'poetry',
    'literature',
    'culture',
    'history',
)
_STRICT_MEDIA_SCORE_THRESHOLD = 0.24
_RELAXED_MEDIA_SCORE_THRESHOLD = 0.16
_BROAD_MEDIA_SCORE_THRESHOLD = 0.1
_DIRECT_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif')
_DIRECT_VIDEO_EXTENSIONS = ('.mp4', '.webm', '.ogg', '.mov', '.m4v')
_VIDEO_TITLE_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'from',
    'this',
    'that',
    'your',
    'into',
    'guide',
    'lesson',
    'study',
    'overview',
    'introduction',
    'part',
    'episode',
    'official',
    'video',
}
_AI_SLOP_PHRASES = (
    'in this section',
    'it is important to note',
    'in today',
    'this highlights the importance',
    'let us explore',
    'overall,',
    'in conclusion,',
    'delve into',
    'leveraging',
    'optimization strategy',
)
_GENERIC_WAFFLE_TERMS = (
    'optimization',
    'optimisation',
    'framework',
    'strategy',
    'synergy',
    'best practice',
    'methodology',
    'stakeholder',
    'roadmap',
    'leverage',
)
_OBSERVATION_SPINE_HINTS = (
    'notice',
    'observe',
    'look at',
    'listen for',
    'watch for',
    'read closely',
    'detail',
    'scene',
    'shot',
    'line',
    'passage',
    'example',
    'exemplar',
    'artifact',
    'object',
    'work',
    'choice',
    'composition',
)
_RESPONSE_SPINE_HINTS = (
    'respond',
    'response',
    'practice',
    'try',
    'draft',
    'write',
    'make',
    'sketch',
    'shoot',
    'edit',
    'test',
    'attempt',
    'revise',
    'apply',
)
_CONTEXT_SPINE_HINTS = (
    'context',
    'history',
    'historical',
    'influence',
    'movement',
    'lineage',
    'cultural',
    'social',
    'political',
)
_EVIDENCE_DENSITY_HINTS = (
    'for example',
    'for instance',
    'such as',
    'consider ',
    'look at ',
    'take ',
    'imagine ',
    'one concrete example',
    'a concrete example',
    'in this scene',
    'in the passage',
    'in this passage',
    'in the sentence',
    'in this sentence',
    'in the experiment',
    'in this experiment',
    'in the policy',
    'in this policy',
    'the data shows',
    'the data reveal',
)
_EVIDENCE_OBJECT_HINTS = (
    'scene',
    'passage',
    'policy',
    'experiment',
    'sentence',
    'equation',
    'artifact',
    'data',
    'document',
    'diagram',
    'map',
)
_NEGATED_EVIDENCE_HINTS = (
    'without evidence',
    'without further evidence',
    'no evidence',
    'no concrete example',
    'no concrete case',
    'has not been taught yet',
    'not been taught yet',
)
_WORKED_EXPLANATION_HINTS = (
    'because',
    'therefore',
    'which means',
    'so that',
    'this matters because',
    'as a result',
    'which changes',
    'which shows',
    'this leads to',
)
_COMPARISON_DETAIL_HINTS = (
    'compare',
    'contrast',
    'whereas',
    'unlike',
    'by contrast',
    'in contrast',
    'variation',
    'alternative',
    'different',
)
_ASSUMED_FAMILIARITY_HINTS = (
    'as you already know',
    'as discussed above',
    'as we saw earlier',
    'if you know',
    'if you have seen',
    'if you have read',
    'if you are familiar',
    'already familiar',
)
_SCAFFOLD_LANGUAGE_HINTS = (
    'notice',
    'compare',
    'respond',
    'try',
    'reflect',
    'apply',
    'practice',
)
_GENERIC_EXAMPLE_NAME_PATTERN = re.compile(r'^(example|case study|sample|scenario)\s*(?:[0-9]+|[a-z])?$', re.IGNORECASE)
_GENERIC_SECTION_HEADINGS = {
    'overview',
    'introduction',
    'summary',
    'wrap-up',
    'conclusion',
    'reflect',
    'reflection',
    'respond',
    'try it',
    'practice',
    'section 1',
    'section 2',
    'section 3',
}
_CRITICAL_QUALITY_ISSUES = {
    'schema_invalid',
    'low_evidence_density',
    'examples_lack_concrete_evidence',
    'weak_worked_explanation',
    'examples_need_worked_explanation',
    'practice_before_proof',
    'assumes_outside_familiarity',
    'exemplar_not_operationalized',
    'missing_concrete_example',
    'missing_response_transfer',
    'examples_need_response_transfer',
    'missing_clear_contrast',
    'examples_need_clear_contrast',
    'compare_mode_needs_clear_contrast',
    'repetitive_explanations',
    'low_instructional_distinctiveness',
    'generic_section_headings',
}


@dataclass
class LessonQualityReport:
    kind: str
    passed: bool
    issue_groups: dict[str, list[str]]
    all_issues: list[str]
    schema_errors: list[str]
    decision: Literal['accept', 'rewrite', 'strict_rewrite', 'fallback']
    metrics: dict[str, Any]


def _truncate_text_cleanly(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    if max_len <= 1:
        return value[:max_len]
    if max_len <= 4:
        return value[:max_len]

    budget = max_len - 1  # reserve room for ellipsis
    window = value[:budget]

    sentence_matches = list(re.finditer(r'[.!?](?=(?:["\')\]]|\s|$))', window))
    cut_idx: int | None = None
    if sentence_matches:
        candidate = sentence_matches[-1].end()
        if candidate >= int(budget * 0.55):
            cut_idx = candidate

    if cut_idx is None:
        candidate = max(window.rfind(' '), window.rfind('\n'), window.rfind('\t'))
        if candidate >= int(budget * 0.65):
            cut_idx = candidate

    if cut_idx is None:
        cut_idx = budget

    trimmed = window[:cut_idx].rstrip(' ,;:-')
    if not trimmed:
        trimmed = window.rstrip()
    if len(trimmed) >= max_len:
        trimmed = trimmed[: max_len - 1].rstrip()
    return f'{trimmed}…'


def _extract_terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or '').lower())


def _clean_clipped_fragment(value: Any, *, max_len: int) -> str:
    raw_text = ' '.join(str(value or '').split()).strip()
    text = raw_text
    if not text:
        return ''
    had_ellipsis = re.search(r'(?:\u2026|\.{3})\s*$', text) is not None
    text = re.sub(r'(?:\u2026|\.{3})\s*$', '', text).strip()

    def _ensure_sentence_closure(snippet: str) -> str:
        snippet = snippet.strip()
        if not snippet:
            return ''
        if re.search(r'[.!?](?:["\')\]]*)$', snippet):
            return snippet[:max_len].rstrip() if len(snippet) > max_len else snippet
        if max_len <= 1:
            return snippet[:max_len]
        if len(snippet) + 1 <= max_len:
            return f'{snippet}.'
        return f'{snippet[: max_len - 1].rstrip()}.'

    def _truncate_complete_sentence(snippet: str) -> str:
        if max_len <= 1:
            return snippet[:max_len]
        window = snippet[:max_len].rstrip()
        if not window:
            return ''

        sentence_matches = list(re.finditer(r'[.!?](?=(?:["\')\]]|\s|$))', window))
        if sentence_matches:
            candidate = sentence_matches[-1].end()
            if candidate >= int(max_len * 0.45):
                return window[:candidate].rstrip()

        clause_matches = list(re.finditer(r'[,;:](?=\s|$)', window))
        if clause_matches:
            candidate = clause_matches[-1].start()
            if candidate >= int(max_len * 0.45):
                return _ensure_sentence_closure(window[:candidate].rstrip(' ,;:-'))

        soft_break_matches = list(
            re.finditer(r'\b(and|with|which|that|including|while|where|when|because|since)\b', window, flags=re.IGNORECASE)
        )
        if soft_break_matches:
            candidate = soft_break_matches[-1].start()
            if candidate >= int(max_len * 0.55):
                return _ensure_sentence_closure(window[:candidate].rstrip(' ,;:-'))

        word_break = max(window.rfind(' '), window.rfind('\n'), window.rfind('\t'))
        if word_break >= int(max_len * 0.6):
            return _ensure_sentence_closure(window[:word_break].rstrip(' ,;:-'))
        return _ensure_sentence_closure(window.rstrip(' ,;:-'))

    if had_ellipsis:
        return _truncate_complete_sentence(text)
    if len(text) > max_len:
        return _truncate_complete_sentence(text)
    closed_sentence = re.search(r'[.!?](?:["\')\]]*)$', text) is not None
    if len(text) >= max_len - 1 and not closed_sentence:
        return _truncate_complete_sentence(text)
    if not closed_sentence and len(text) >= 90:
        return _ensure_sentence_closure(text)
    return text


class ResourceAgent:
    def __init__(
        self,
        llm_service: LLMService,
        search_service: ExternalSearchService,
        retrieval_service: RetrievalService,
        course_memory_service: CourseMemoryService | None = None,
        course_research_service: CourseResearchService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.search_service = search_service
        self.retrieval_service = retrieval_service
        self.course_memory_service = course_memory_service or CourseMemoryService()
        self.course_research_service = course_research_service or CourseResearchService(search_service)

    def _difficulty_band(self, difficulty: int) -> str:
        if difficulty <= 2:
            return 'foundation'
        if difficulty == 3:
            return 'intermediate'
        return 'advanced'

    def _learner_level(self, state: UserSkillState | None) -> str:
        if not state:
            return 'beginner'
        if state.progress_state == 'verified' or state.mastery >= 0.75:
            return 'advanced'
        if state.progress_state in ('learning', 'completed') or state.mastery >= 0.35:
            return 'intermediate'
        return 'beginner'

    def _technical_depth(self, topic: Topic) -> str:
        return normalize_technical_depth(getattr(topic, 'technical_depth', None))

    def _teaching_quality_rules(self, *, technical_depth: str) -> str:
        return (
            'Teaching quality requirements:\n'
            '- Explain why each concept matters, not only what it is.\n'
            '- Include causal/comparative reasoning where appropriate.\n'
            '- No concept without evidence: support claims with a concrete example, worked explanation, comparison, source-grounded detail, or short case.\n'
            '- No exemplar without operationalization: if you name a work, event, thinker, principle, place, or technique, teach through it instead of only mentioning it.\n'
            '- Include at least one misconception or failure mode and how to avoid it.\n'
            '- Open from something observable, comparable, or directly actionable before abstract explanation.\n'
            '- Make the lesson self-contained enough that a learner does not need outside familiarity to benefit.\n'
            '- Do not move into practice, response, or reflection until the learner has at least one strong grounded example and a clear explanation of what is happening.\n'
            '- If you add theory, history, or context, make it answer what the learner should notice, compare, or try next.\n'
            '- Prefer proof, distinctions, and worked explanation over scaffold-heavy language.\n'
            '- Avoid generic filler, broad motivational language, repetitive transition phrases, and vague AI-teacher tone.\n'
            f'- Technical depth guidance: {technical_depth_prompt_guidance(technical_depth)}\n'
        )

    def _course_memory_context(self, snapshot: CourseMemorySnapshot) -> str:
        return snapshot.to_prompt_context()

    def _editorial_spine_context(self, topic: Topic) -> str:
        blueprint = topic.curriculum_blueprint if isinstance(topic.curriculum_blueprint, dict) else {}
        core_arc = blueprint.get('core_arc')
        if not isinstance(core_arc, list) or not core_arc:
            return 'No editorial spine available yet.'
        lines: list[str] = []
        for item in core_arc[:10]:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name') or '').strip()
            role = str(item.get('instructional_role') or 'core').strip()
            if name:
                lines.append(f'- {name} ({role})')
        return '\n'.join(lines) if lines else 'No editorial spine available yet.'

    def _stable_coverage_context(self, snapshot: CourseMemorySnapshot) -> str:
        if not snapshot.taught_node_lines:
            return 'No completed/stable coverage yet.'
        lines = '\n'.join(f'- {line}' for line in snapshot.taught_node_lines[:8])
        return (
            f'{lines}\n'
            'Treat completed coverage as stable. Avoid re-teaching the same concepts at the same depth unless remediation is explicit.'
        )

    def _writing_slop_issues(self, structured_content: dict[str, Any], *, kind: str) -> list[str]:
        if kind not in {'lesson', 'deep_lesson', 'examples'}:
            return []
        text_parts: list[str] = []
        if kind == 'examples':
            text_parts.append(str(structured_content.get('intro') or ''))
            examples = structured_content.get('examples')
            if isinstance(examples, list):
                for item in examples:
                    if isinstance(item, dict):
                        text_parts.append(str(item.get('explanation') or ''))
                        text_parts.append(str(item.get('why_it_matters') or ''))
        else:
            text_parts.append(str(structured_content.get('summary') or ''))
            sections = structured_content.get('sections')
            if isinstance(sections, list):
                for item in sections:
                    if isinstance(item, dict):
                        text_parts.append(str(item.get('content') or ''))
        blob = ' '.join(text_parts).lower()
        issues: list[str] = []
        hit_count = sum(1 for phrase in _AI_SLOP_PHRASES if phrase in blob)
        if hit_count >= 2:
            issues.append('formulaic_phrasing')
        waffle_hits = sum(1 for term in _GENERIC_WAFFLE_TERMS if term in blob)
        if waffle_hits >= 3:
            issues.append('generic_abstract_language')
        if blob.count('important') >= 4:
            issues.append('padding_language')
        if not self._has_evidence_signal(blob):
            issues.append('missing_specific_examples')
        if self._contains_any_hint(blob, _ASSUMED_FAMILIARITY_HINTS):
            issues.append('assumes_outside_familiarity')
        return issues

    @staticmethod
    def _contains_any_hint(text: str, hints: tuple[str, ...]) -> bool:
        lowered = (text or '').lower()
        return any(hint in lowered for hint in hints)

    @staticmethod
    def _has_evidence_signal(text: str) -> bool:
        lowered = (text or '').lower()
        strong_hits = sum(1 for hint in _EVIDENCE_DENSITY_HINTS if hint in lowered)
        object_hits = sum(1 for hint in _EVIDENCE_OBJECT_HINTS if re.search(rf'\b{re.escape(hint)}s?\b', lowered))
        negated = any(hint in lowered for hint in _NEGATED_EVIDENCE_HINTS)
        if strong_hits >= 1:
            return True
        if object_hits >= 2 and not negated:
            return True
        return False

    @staticmethod
    def _dedupe_issues(issues: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for issue in issues:
            token = str(issue or '').strip()
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered

    @staticmethod
    def _schema_model_for_kind(kind: str):  # type: ignore[no-untyped-def]
        mapping = {
            'lesson': LessonPlan,
            'examples': ExamplesPlan,
            'deep_lesson': DeepLessonPlan,
        }
        return mapping.get(kind)

    def _schema_validation_issues(self, *, kind: str, structured_content: dict[str, Any]) -> tuple[list[str], list[str]]:
        schema_model = self._schema_model_for_kind(kind)
        if schema_model is None:
            return [], []

        try:
            schema_model.model_validate(structured_content)
            return [], []
        except ValidationError as exc:
            details: list[str] = []
            for error in exc.errors():
                location = '.'.join(str(part) for part in error.get('loc', ()))
                message = str(error.get('msg') or '').strip()
                if location:
                    details.append(f'{location}: {message}')
                elif message:
                    details.append(message)
            details = self._dedupe_issues(details)
            return ['schema_invalid'], details

    def _distinctiveness_issues(self, *, kind: str, structured_content: dict[str, Any]) -> list[str]:
        issues: list[str] = []

        if kind in {'lesson', 'deep_lesson'}:
            sections = structured_content.get('sections')
            section_items = [item for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []
            headings = [str(item.get('heading') or '').strip().lower() for item in section_items if str(item.get('heading') or '').strip()]
            generic_heading_hits = sum(1 for heading in headings if heading in _GENERIC_SECTION_HEADINGS)
            if generic_heading_hits >= max(2, len(headings) - 1) and headings:
                issues.append('generic_section_headings')

            content_blobs = [' '.join(str(item.get('content') or '').lower().split()) for item in section_items]
            for idx, left in enumerate(content_blobs):
                left_tokens = set(_extract_terms(left))
                if len(left_tokens) < 10:
                    continue
                for right in content_blobs[idx + 1 :]:
                    right_tokens = set(_extract_terms(right))
                    if len(right_tokens) < 10:
                        continue
                    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
                    if overlap >= 0.72:
                        issues.append('repetitive_explanations')
                        break
                if 'repetitive_explanations' in issues:
                    break

            unique_heading_ratio = len(set(headings)) / max(1, len(headings))
            if headings and unique_heading_ratio < 0.75:
                issues.append('low_instructional_distinctiveness')

        if kind == 'examples':
            examples = structured_content.get('examples')
            example_items = [item for item in examples if isinstance(item, dict)] if isinstance(examples, list) else []
            names = [str(item.get('name') or '').strip().lower() for item in example_items if str(item.get('name') or '').strip()]
            if names and len(set(names)) / max(1, len(names)) < 0.75:
                issues.append('low_instructional_distinctiveness')
            explanation_blobs = [' '.join(str(item.get('explanation') or '').lower().split()) for item in example_items]
            for idx, left in enumerate(explanation_blobs):
                left_tokens = set(_extract_terms(left))
                if len(left_tokens) < 10:
                    continue
                for right in explanation_blobs[idx + 1 :]:
                    right_tokens = set(_extract_terms(right))
                    if len(right_tokens) < 10:
                        continue
                    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
                    if overlap >= 0.72:
                        issues.append('repetitive_explanations')
                        break
                if 'repetitive_explanations' in issues:
                    break

        return self._dedupe_issues(issues)

    def _quality_gate_report(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        study_mode: str,
        memory: CourseMemorySnapshot,
        technical_depth: str | None = None,
    ) -> LessonQualityReport:
        schema_issues, schema_errors = self._schema_validation_issues(kind=kind, structured_content=structured_content)
        issue_groups: dict[str, list[str]] = {'schema': schema_issues}

        if kind == 'lesson' and technical_depth is not None:
            _is_high_quality, quality_issues = self._lesson_quality_signals(
                structured_content,
                technical_depth=technical_depth,
            )
            issue_groups['quality'] = quality_issues
        else:
            issue_groups['quality'] = []

        issue_groups['spine'] = self._teaching_spine_issues(
            kind=kind,
            structured_content=structured_content,
            study_mode=study_mode,
        )
        issue_groups['evidence'] = self._evidence_density_issues(
            kind=kind,
            structured_content=structured_content,
            study_mode=study_mode,
        )
        issue_groups['writing'] = self._writing_slop_issues(structured_content, kind=kind)
        issue_groups['repetition'] = self._repetition_issues(
            kind=kind,
            structured_content=structured_content,
            memory=memory,
        )
        issue_groups['distinctiveness'] = self._distinctiveness_issues(kind=kind, structured_content=structured_content)

        all_issues = self._dedupe_issues(
            [issue for issues in issue_groups.values() for issue in issues]
        )
        critical_issue_count = sum(1 for issue in all_issues if issue in _CRITICAL_QUALITY_ISSUES)

        metrics: dict[str, Any] = {}
        if kind in {'lesson', 'deep_lesson'}:
            sections = structured_content.get('sections')
            section_items = [item for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []
            section_lengths = [len(str(item.get('content') or '').strip()) for item in section_items if str(item.get('content') or '').strip()]
            metrics = {
                'section_count': len(section_items),
                'avg_section_chars': round(sum(section_lengths) / max(1, len(section_lengths)), 1) if section_lengths else 0,
                'section_roles': [str(item.get('role') or '') for item in section_items],
                'has_evidence_signal': self._has_evidence_signal(
                    ' '.join(str(item.get('content') or '') for item in section_items)
                ),
            }
        elif kind == 'examples':
            examples = structured_content.get('examples')
            example_items = [item for item in examples if isinstance(item, dict)] if isinstance(examples, list) else []
            explanation_lengths = [len(str(item.get('explanation') or '').strip()) for item in example_items if str(item.get('explanation') or '').strip()]
            metrics = {
                'example_count': len(example_items),
                'avg_explanation_chars': round(sum(explanation_lengths) / max(1, len(explanation_lengths)), 1) if explanation_lengths else 0,
                'example_roles': [str(item.get('role') or '') for item in example_items],
                'has_evidence_signal': self._has_evidence_signal(
                    ' '.join(str(item.get('explanation') or '') for item in example_items)
                ),
            }

        if not all_issues:
            decision: Literal['accept', 'rewrite', 'strict_rewrite', 'fallback'] = 'accept'
        elif schema_issues or critical_issue_count >= 3 or len(all_issues) >= 6:
            decision = 'strict_rewrite'
        else:
            decision = 'rewrite'

        return LessonQualityReport(
            kind=kind,
            passed=not all_issues,
            issue_groups=issue_groups,
            all_issues=all_issues,
            schema_errors=schema_errors,
            decision=decision,
            metrics=metrics,
        )

    def _repair_structured_content(self, *, kind: str, structured_content: dict[str, Any]) -> dict[str, Any]:
        if kind in {'lesson', 'deep_lesson'}:
            sections = structured_content.get('sections')
            if isinstance(sections, list):
                order = {
                    'core_concept': 0,
                    'context': 1,
                    'example': 2,
                    'analysis': 3,
                    'comparison': 4,
                    'transfer': 5,
                }
                sortable = [item for item in sections if isinstance(item, dict)]
                if sortable and all(str(item.get('role') or '').strip() for item in sortable):
                    structured_content['sections'] = sorted(
                        sortable,
                        key=lambda item: order.get(str(item.get('role') or '').strip(), 99),
                    )
        if kind == 'examples':
            examples = structured_content.get('examples')
            if isinstance(examples, list):
                order = {
                    'anchor': 0,
                    'contrast': 1,
                    'variation': 2,
                    'transfer': 3,
                }
                sortable = [item for item in examples if isinstance(item, dict)]
                if sortable and all(str(item.get('role') or '').strip() for item in sortable):
                    structured_content['examples'] = sorted(
                        sortable,
                        key=lambda item: order.get(str(item.get('role') or '').strip(), 99),
                    )
        return structured_content

    def _log_quality_gate_report(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        report: LessonQualityReport,
        study_mode: str,
        technical_depth: str,
        attempt: str,
    ) -> None:
        logger.info(
            'resource.lesson_quality_gate topic_id=%s skill_id=%s kind=%s study_mode=%s technical_depth=%s attempt=%s decision=%s issues=%s schema_errors=%s metrics=%s issue_groups=%s',
            topic.id,
            skill_node.id,
            report.kind,
            study_mode,
            technical_depth,
            attempt,
            report.decision,
            report.all_issues,
            report.schema_errors,
            report.metrics,
            report.issue_groups,
        )

    def _quality_rewrite_system_prompt(self, *, kind: str, strict: bool) -> str:
        base = (
            'You are ResourceAgent. Rewrite this learning material so it becomes concrete, self-contained, and evidence-based while staying accurate and scoped to the same skill node. '
            'Keep practice after proof, reduce generic filler, and teach through worked explanation rather than broad summary.'
        )
        if kind == 'examples':
            base += ' Keep the set sequenced as anchor -> contrast or variation -> transfer.'
        if kind == 'deep_lesson':
            base += ' Preserve depth, but keep the deep lesson tied to an anchor exemplar, analysis, comparison, and transfer.'
        if strict:
            base += ' Strict rewrite mode: if the draft is still shallow, rebuild the structure instead of lightly editing the wording.'
        return base

    def _quality_rewrite_prompt(
        self,
        *,
        kind: str,
        topic: Topic,
        skill_node: SkillNode,
        technical_depth: str,
        study_mode: str,
        memory_context: str,
        report: LessonQualityReport,
        structured_content: dict[str, Any],
        strict: bool,
    ) -> str:
        return (
            f'Topic: {topic.name}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Kind: {kind}\n'
            f'Technical depth: {technical_depth}\n'
            f'Study mode: {study_mode}\n'
            f'Strict rewrite mode: {"on" if strict else "off"}\n'
            f'Quality issues to fix: {", ".join(report.all_issues) or "None"}\n'
            f'Schema validation notes: {json.dumps(report.schema_errors, indent=2) if report.schema_errors else "None"}\n'
            f'Quality diagnostics: {json.dumps(report.issue_groups, indent=2)}\n'
            f'Metrics: {json.dumps(report.metrics, indent=2)}\n\n'
            f'Course memory ledger:\n{memory_context}\n\n'
            'Repair strategy:\n'
            '- strengthen concrete examples or evidence\n'
            '- expand worked explanation and causal logic\n'
            '- make the lesson self-contained\n'
            '- ensure practice comes after explanation and transfer\n'
            '- remove repetition, generic headings, and circular phrasing\n'
            '- keep structure domain-sensitive rather than template-like\n\n'
            f'Current draft JSON:\n{json.dumps(structured_content, indent=2)}'
        )

    async def _quality_control_structured_content(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        topic: Topic,
        skill_node: SkillNode,
        study_mode: str,
        technical_depth: str,
        memory_snapshot: CourseMemorySnapshot,
        memory_context: str,
        max_tokens: int,
        fallback_builder,
    ) -> tuple[dict[str, Any], bool, LessonQualityReport]:
        schema_model = self._schema_model_for_kind(kind)
        used_fallback = False

        structured_content = self._polish_structured_snippets(kind=kind, structured_content=structured_content)
        if kind in {'lesson', 'examples', 'deep_lesson'}:
            structured_content = self._ensure_studio_balance_fields(
                kind=kind,
                structured_content=structured_content,
                skill_node=skill_node,
                study_mode=study_mode,
            )
        structured_content = self._repair_structured_content(kind=kind, structured_content=structured_content)
        if kind in {'lesson', 'examples', 'deep_lesson'}:
            structured_content = self._clear_legacy_supporting_media_fields(
                topic=topic,
                skill_node=skill_node,
                structured_content=structured_content,
                kind=kind,
            )

        report = self._quality_gate_report(
            kind=kind,
            structured_content=structured_content,
            study_mode=study_mode,
            memory=memory_snapshot,
            technical_depth=technical_depth,
        )
        self._log_quality_gate_report(
            topic=topic,
            skill_node=skill_node,
            report=report,
            study_mode=study_mode,
            technical_depth=technical_depth,
            attempt='initial',
        )
        if report.passed or schema_model is None:
            return structured_content, used_fallback, report

        for attempt_index in range(2):
            strict = attempt_index == 1 or report.decision == 'strict_rewrite'
            rewrite_prompt = self._quality_rewrite_prompt(
                kind=kind,
                topic=topic,
                skill_node=skill_node,
                technical_depth=technical_depth,
                study_mode=study_mode,
                memory_context=memory_context,
                report=report,
                structured_content=structured_content,
                strict=strict,
            )
            try:
                refined_model = await self.llm_service.generate_structured(
                    system_prompt=self._quality_rewrite_system_prompt(kind=kind, strict=strict),
                    user_prompt=rewrite_prompt,
                    schema_model=schema_model,
                    temperature=0.15 if strict else 0.2,
                    max_tokens=max_tokens,
                )
                structured_content = refined_model.model_dump()
            except ProviderError as exc:
                logger.warning(
                    'resource.lesson_quality_rewrite_failed topic_id=%s skill_id=%s kind=%s attempt=%s strict=%s error=%s',
                    topic.id,
                    skill_node.id,
                    kind,
                    attempt_index + 1,
                    strict,
                    exc,
                )
                continue

            structured_content = self._polish_structured_snippets(kind=kind, structured_content=structured_content)
            if kind in {'lesson', 'examples', 'deep_lesson'}:
                structured_content = self._ensure_studio_balance_fields(
                    kind=kind,
                    structured_content=structured_content,
                    skill_node=skill_node,
                    study_mode=study_mode,
                )
            structured_content = self._repair_structured_content(kind=kind, structured_content=structured_content)
            if kind in {'lesson', 'examples', 'deep_lesson'}:
                structured_content = self._clear_legacy_supporting_media_fields(
                    topic=topic,
                    skill_node=skill_node,
                    structured_content=structured_content,
                    kind=kind,
                )

            report = self._quality_gate_report(
                kind=kind,
                structured_content=structured_content,
                study_mode=study_mode,
                memory=memory_snapshot,
                technical_depth=technical_depth,
            )
            self._log_quality_gate_report(
                topic=topic,
                skill_node=skill_node,
                report=report,
                study_mode=study_mode,
                technical_depth=technical_depth,
                attempt=f'rewrite_{attempt_index + 1}',
            )
            if report.passed:
                return structured_content, used_fallback, report
            remaining_critical = [
                issue for issue in report.all_issues if issue in _CRITICAL_QUALITY_ISSUES or issue == 'schema_invalid'
            ]
            if not remaining_critical and len(report.all_issues) <= 2:
                logger.info(
                    'resource.lesson_quality_accept_minor topic_id=%s skill_id=%s kind=%s issues=%s',
                    topic.id,
                    skill_node.id,
                    kind,
                    report.all_issues,
                )
                return structured_content, used_fallback, report

        remaining_critical = [issue for issue in report.all_issues if issue in _CRITICAL_QUALITY_ISSUES or issue == 'schema_invalid']
        if not remaining_critical and len(report.all_issues) <= 2:
            logger.info(
                'resource.lesson_quality_accept_minor topic_id=%s skill_id=%s kind=%s issues=%s',
                topic.id,
                skill_node.id,
                kind,
                report.all_issues,
            )
            return structured_content, used_fallback, report

        logger.warning(
            'resource.lesson_quality_fallback topic_id=%s skill_id=%s kind=%s issues=%s schema_errors=%s',
            topic.id,
            skill_node.id,
            kind,
            report.all_issues,
            report.schema_errors,
        )
        structured_content = fallback_builder()
        used_fallback = True
        structured_content = self._polish_structured_snippets(kind=kind, structured_content=structured_content)
        if kind in {'lesson', 'examples', 'deep_lesson'}:
            structured_content = self._ensure_studio_balance_fields(
                kind=kind,
                structured_content=structured_content,
                skill_node=skill_node,
                study_mode=study_mode,
            )
        structured_content = self._repair_structured_content(kind=kind, structured_content=structured_content)
        if kind in {'lesson', 'examples', 'deep_lesson'}:
            structured_content = self._clear_legacy_supporting_media_fields(
                topic=topic,
                skill_node=skill_node,
                structured_content=structured_content,
                kind=kind,
            )
        report = self._quality_gate_report(
            kind=kind,
            structured_content=structured_content,
            study_mode=study_mode,
            memory=memory_snapshot,
            technical_depth=technical_depth,
        )
        self._log_quality_gate_report(
            topic=topic,
            skill_node=skill_node,
            report=report,
            study_mode=study_mode,
            technical_depth=technical_depth,
            attempt='fallback',
        )
        return structured_content, used_fallback, report

    def _teaching_spine_issues(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        study_mode: str,
    ) -> list[str]:
        issues: list[str] = []

        observation_prompts = self._normalize_string_list(structured_content.get('observation_prompts'), limit=5)
        comparison_prompts = self._normalize_string_list(structured_content.get('comparison_prompts'), limit=4)
        response_prompts = self._normalize_string_list(structured_content.get('response_prompts'), limit=4)
        practice_hooks = self._normalize_string_list(structured_content.get('practice_hooks'), limit=4)
        exemplar_focus = self._normalize_string_list(structured_content.get('exemplar_focus'), limit=3)

        if kind in {'lesson', 'deep_lesson'}:
            sections = structured_content.get('sections')
            if isinstance(sections, list) and sections:
                first_section = sections[0] if isinstance(sections[0], dict) else {}
                first_blob = ' '.join(
                    [
                        str(first_section.get('heading') or ''),
                        str(first_section.get('content') or ''),
                        ' '.join(exemplar_focus),
                    ]
                )
                if not self._contains_any_hint(first_blob, _OBSERVATION_SPINE_HINTS):
                    issues.append('weak_concrete_opening')

                all_sections_blob = ' '.join(
                    ' '.join(
                        [
                            str(item.get('heading') or ''),
                            str(item.get('content') or ''),
                        ]
                    )
                    for item in sections
                    if isinstance(item, dict)
                )
                prompt_blob = ' '.join(response_prompts + practice_hooks)
                if not self._contains_any_hint(f'{all_sections_blob} {prompt_blob}', _RESPONSE_SPINE_HINTS):
                    issues.append('missing_response_transfer')
                if kind == 'deep_lesson' and not self._contains_any_hint(all_sections_blob, _CONTEXT_SPINE_HINTS):
                    issues.append('missing_contextual_reading')

        if kind == 'examples':
            examples = structured_content.get('examples')
            example_items = [item for item in examples if isinstance(item, dict)] if isinstance(examples, list) else []
            if any(_GENERIC_EXAMPLE_NAME_PATTERN.match(str(item.get('name') or '').strip()) for item in example_items):
                issues.append('generic_example_labels')
            explanation_blob = ' '.join(
                ' '.join(
                    [
                        str(item.get('name') or ''),
                        str(item.get('explanation') or ''),
                        str(item.get('why_it_matters') or ''),
                    ]
                )
                for item in example_items
            )
            if not self._contains_any_hint(f'{explanation_blob} {" ".join(observation_prompts)}', _OBSERVATION_SPINE_HINTS):
                issues.append('examples_need_observation_detail')
            if study_mode == 'compare' and not self._contains_any_hint(
                f'{explanation_blob} {" ".join(comparison_prompts)}',
                ('compare', 'contrast', 'difference', 'whereas', 'versus'),
            ):
                issues.append('compare_mode_needs_clear_contrast')
            if not self._contains_any_hint(
                f'{explanation_blob} {" ".join(response_prompts)} {" ".join(practice_hooks)}',
                _RESPONSE_SPINE_HINTS,
            ):
                issues.append('examples_need_response_transfer')

        return issues

    def _evidence_density_issues(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        study_mode: str,
    ) -> list[str]:
        issues: list[str] = []

        observation_prompts = self._normalize_string_list(structured_content.get('observation_prompts'), limit=5)
        comparison_prompts = self._normalize_string_list(structured_content.get('comparison_prompts'), limit=4)
        response_prompts = self._normalize_string_list(structured_content.get('response_prompts'), limit=4)
        practice_hooks = self._normalize_string_list(structured_content.get('practice_hooks'), limit=4)
        exemplar_focus = self._normalize_string_list(structured_content.get('exemplar_focus'), limit=3)

        if kind == 'examples':
            examples = structured_content.get('examples')
            example_items = [item for item in examples if isinstance(item, dict)] if isinstance(examples, list) else []
            explanation_blob = ' '.join(
                ' '.join(
                    [
                        str(item.get('name') or ''),
                        str(item.get('explanation') or ''),
                        str(item.get('why_it_matters') or ''),
                    ]
                )
                for item in example_items
            ).lower()
            avg_explanation_len = (
                sum(len(str(item.get('explanation') or '').strip()) for item in example_items) / max(1, len(example_items))
                if example_items
                else 0
            )
            if len(example_items) < 3:
                issues.append('too_few_worked_examples')
            if not self._has_evidence_signal(explanation_blob):
                issues.append('examples_lack_concrete_evidence')
            if not self._contains_any_hint(explanation_blob, _WORKED_EXPLANATION_HINTS) or avg_explanation_len < 120:
                issues.append('examples_need_worked_explanation')
            if not self._contains_any_hint(
                f'{explanation_blob} {" ".join(comparison_prompts).lower()}',
                _COMPARISON_DETAIL_HINTS,
            ):
                issues.append('examples_need_clear_contrast')
            if self._contains_any_hint(explanation_blob, _ASSUMED_FAMILIARITY_HINTS):
                issues.append('assumes_outside_familiarity')
            if (response_prompts or practice_hooks) and not self._has_evidence_signal(explanation_blob):
                issues.append('practice_before_proof')
            return issues

        sections = structured_content.get('sections')
        section_items = [item for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []
        section_blob = ' '.join(
            ' '.join([str(item.get('heading') or ''), str(item.get('content') or '')])
            for item in section_items
        ).lower()
        opening_blob = ' '.join(str(item.get('content') or '') for item in section_items[:2]).lower()
        avg_section_len = (
            sum(len(str(item.get('content') or '').strip()) for item in section_items) / max(1, len(section_items))
            if section_items
            else 0
        )
        prompt_blob = ' '.join(observation_prompts + comparison_prompts + response_prompts + practice_hooks).lower()

        if not self._has_evidence_signal(section_blob):
            issues.append('low_evidence_density')
        if not self._contains_any_hint(section_blob, _WORKED_EXPLANATION_HINTS) or avg_section_len < 150:
            issues.append('weak_worked_explanation')
        if study_mode == 'compare' or kind == 'deep_lesson':
            if not self._contains_any_hint(f'{section_blob} {prompt_blob}', _COMPARISON_DETAIL_HINTS):
                issues.append('missing_clear_contrast')
        if exemplar_focus and not self._has_evidence_signal(section_blob):
            issues.append('exemplar_not_operationalized')
        if self._contains_any_hint(section_blob, _ASSUMED_FAMILIARITY_HINTS):
            issues.append('assumes_outside_familiarity')
        scaffold_hits = sum(1 for hint in _SCAFFOLD_LANGUAGE_HINTS if hint in prompt_blob)
        if scaffold_hits >= 2 and (
            len(opening_blob) < 220 or not self._has_evidence_signal(opening_blob)
        ):
            issues.append('practice_before_proof')

        return issues

    def _repetition_issues(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        memory: CourseMemorySnapshot,
    ) -> list[str]:
        issues: list[str] = []
        if kind == 'examples':
            examples = structured_content.get('examples')
            if isinstance(examples, list):
                existing = {item.lower() for item in memory.used_examples}
                overlap = 0
                for item in examples:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get('name') or '').strip().lower()
                    if name and name in existing:
                        overlap += 1
                if overlap >= 1:
                    issues.append('reused_examples')

        if kind in {'lesson', 'deep_lesson'}:
            summary = str(structured_content.get('summary') or '')
            candidate_tokens = set(_extract_terms(summary))
            taught_tokens = set(_extract_terms(' '.join(memory.taught_concepts[:16])))
            if candidate_tokens and taught_tokens:
                overlap_ratio = len(candidate_tokens & taught_tokens) / max(1, min(len(candidate_tokens), len(taught_tokens)))
                if overlap_ratio >= 0.85:
                    issues.append('summary_overlaps_prior_teaching')
            future_tokens = set(_extract_terms(' '.join(memory.future_core_lines[:10])))
            if candidate_tokens and future_tokens:
                overlap_ratio = len(candidate_tokens & future_tokens) / max(1, min(len(candidate_tokens), len(future_tokens)))
                if overlap_ratio >= 0.82:
                    issues.append('premature_future_overlap')

        return issues

    def _lesson_quality_signals(
        self,
        structured_content: dict[str, Any],
        *,
        technical_depth: str,
    ) -> tuple[bool, list[str]]:
        targets = technical_depth_lesson_targets(normalize_technical_depth(technical_depth))
        sections = structured_content.get('sections')
        key_concepts = structured_content.get('key_concepts')
        issues: list[str] = []

        if not isinstance(sections, list) or len(sections) < int(targets['min_sections']):
            issues.append('too_few_sections')

        section_lengths: list[int] = []
        section_blob_parts: list[str] = []
        for section in sections if isinstance(sections, list) else []:
            if not isinstance(section, dict):
                continue
            content = str(section.get('content') or '').strip()
            if not content:
                continue
            section_lengths.append(len(content))
            section_blob_parts.append(content.lower())

        if section_lengths:
            avg_len = sum(section_lengths) / max(1, len(section_lengths))
            if avg_len < int(targets['section_min_chars']):
                issues.append('sections_too_shallow')
        else:
            issues.append('missing_section_content')

        if not isinstance(key_concepts, list) or len(key_concepts) < 3:
            issues.append('too_few_key_concepts')

        section_blob = ' '.join(section_blob_parts)
        if not self._has_evidence_signal(section_blob):
            issues.append('missing_concrete_example')
        if not any(
            token in section_blob
            for token in ('common mistake', 'misconception', 'pitfall', 'avoid this', 'failure mode')
        ):
            issues.append('missing_misconception_handling')
        if not self._contains_any_hint(section_blob, _WORKED_EXPLANATION_HINTS + _COMPARISON_DETAIL_HINTS):
            issues.append('missing_reasoning_connectors')
        if self._contains_any_hint(section_blob, _ASSUMED_FAMILIARITY_HINTS):
            issues.append('assumes_outside_familiarity')

        return len(issues) == 0, issues

    def _polish_structured_snippets(self, *, kind: str, structured_content: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(structured_content, dict):
            return structured_content

        if kind == 'lesson':
            structured_content['summary'] = _clean_clipped_fragment(structured_content.get('summary'), max_len=300)
            concepts = structured_content.get('key_concepts')
            if isinstance(concepts, list):
                for item in concepts:
                    if isinstance(item, dict):
                        item['description'] = _clean_clipped_fragment(item.get('description'), max_len=260)
            return structured_content

        if kind == 'examples':
            structured_content['intro'] = _clean_clipped_fragment(structured_content.get('intro'), max_len=420)
            examples = structured_content.get('examples')
            if isinstance(examples, list):
                for item in examples:
                    if isinstance(item, dict):
                        item['explanation'] = _clean_clipped_fragment(item.get('explanation'), max_len=500)
                        item['why_it_matters'] = _clean_clipped_fragment(item.get('why_it_matters'), max_len=280)
            return structured_content

        if kind == 'exercises':
            structured_content['intro'] = _clean_clipped_fragment(structured_content.get('intro'), max_len=420)
            exercises = structured_content.get('exercises')
            if isinstance(exercises, list):
                for item in exercises:
                    if isinstance(item, dict):
                        item['task'] = _clean_clipped_fragment(item.get('task'), max_len=500)
                        item['expected_outcome'] = _clean_clipped_fragment(item.get('expected_outcome'), max_len=300)
            return structured_content

        if kind == 'deep_lesson':
            structured_content['summary'] = _clean_clipped_fragment(structured_content.get('summary'), max_len=420)
            key_terms = structured_content.get('key_terms')
            if isinstance(key_terms, list):
                for item in key_terms:
                    if isinstance(item, dict):
                        item['description'] = _clean_clipped_fragment(item.get('description'), max_len=260)
            return structured_content

        return structured_content

    def _alignment_rules(self, difficulty: int, learner_level: str, kind: str, technical_depth: str) -> str:
        base = (
            '- Stay strictly scoped to this node title and description.\n'
            '- Assume only prerequisite knowledge, not downstream skills.\n'
            '- Do not include capstone or multi-skill project tasks unless node difficulty is advanced.\n'
            f'- Match technical depth target: {technical_depth_prompt_guidance(technical_depth)}\n'
        )

        if difficulty <= 2 or learner_level == 'beginner':
            beginner = (
                '- Treat learner as beginner/foundation for this node.\n'
                '- Use plain language, short steps, and foundational concepts.\n'
                '- Exercises must be short micro-practice tasks (5-15 minutes each).\n'
                '- Do NOT ask for full sets, long performances, or complex end-to-end production workflows.\n'
            )
            return base + beginner

        if kind == 'exercises':
            return (
                base
                + '- Use applied tasks that are realistic for node scope.\n'
                '- Prefer progressive tasks from easier to harder.\n'
            )
        if kind == 'lesson':
            return base + self._teaching_quality_rules(technical_depth=technical_depth)
        return base

    def _field_length_rules(self, kind: str, technical_depth: str) -> str:
        if kind == 'lesson':
            targets = technical_depth_lesson_targets(normalize_technical_depth(technical_depth))
            return (
                '- Keep summary under 280 characters.\n'
                f'- Use at least {targets["min_sections"]} sections when possible.\n'
                f'- Target average section depth of at least {targets["section_min_chars"]} characters.\n'
            )
        if kind == 'examples':
            return (
                '- Keep intro under 260 characters.\n'
                '- Keep each explanation concise and practical.\n'
            )
        if kind == 'exercises':
            return (
                '- Keep intro under 260 characters.\n'
                '- Keep each task scoped to one focused activity.\n'
            )
        return ''

    def _normalize_string_list(self, value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = ' '.join(str(item or '').split()).strip()
            if len(cleaned) < 4:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            result.append(cleaned)
            if len(result) >= limit:
                break
        return result

    def _is_creative_or_visual_topic(self, *, topic: Topic, skill_node: SkillNode) -> bool:
        haystack = ' '.join(
            [
                str(topic.name or ''),
                str(topic.description or ''),
                str(topic.goal or ''),
                str(skill_node.name or ''),
                str(skill_node.description or ''),
            ]
        ).lower()
        return any(token in haystack for token in _VISUAL_DISCIPLINE_HINTS)

    def _practice_balance_rules(self, *, kind: str, study_mode: str) -> str:
        base = (
            'Universal pedagogy rules:\n'
            '- Lead with concrete examples, cases, artifacts, sentences, scenarios, mechanisms, or observable choices.\n'
            '- Keep theory/history/context as support for explanation, comparison, and transfer.\n'
            '- No practice before proof: give the learner enough evidence and explanation before asking for response or application.\n'
            '- Keep language grounded and specific; avoid abstract explanation-only flow.\n'
            '- Reduce scaffold-heavy phrasing unless it is backed by real teaching content.\n'
        )
        if kind == 'lesson':
            base += (
                '- Build the lesson body in this order when possible: core concept -> minimal context -> concrete example or evidence -> close explanation -> comparison or contrast -> worked transfer -> practice.\n'
                '- When possible, move through this study spine: anchor exemplar -> close observation -> interpretation or context -> response or practice transfer.\n'
            )
        if kind in {'lesson', 'examples'}:
            base += '- Ensure response or practice prompts come after enough teaching to make transfer possible.\n'
        if kind == 'examples':
            base += (
                '- Sequence examples as an intentional set: anchor example first, then variation or contrast, then transfer or response.\n'
                '- Avoid placeholder labels such as Example 1 or generic case study naming.\n'
            )
        if kind == 'deep_lesson':
            base += (
                '- Use the deep dive to move from close reading into richer context, then back into interpretation, contrast, and transfer.\n'
                '- Every section should stay tied to a concrete artifact, passage, scene, object, mechanism, or observable decision.\n'
            )
        if study_mode == 'exemplar':
            base += '- Stay anchored to one exemplar so ideas remain concrete and observable.\n'
        if study_mode == 'compare':
            base += '- Include explicit comparison criteria and a clear contrast task.\n'
        return base

    def _ensure_studio_balance_fields(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        skill_node: SkillNode,
        study_mode: str,
    ) -> dict[str, Any]:
        if not isinstance(structured_content, dict):
            return structured_content

        exemplar_focus = self._normalize_string_list(structured_content.get('exemplar_focus'), limit=3)
        comparison_prompts = self._normalize_string_list(structured_content.get('comparison_prompts'), limit=4)
        observation_prompts = self._normalize_string_list(structured_content.get('observation_prompts'), limit=5)
        response_prompts = self._normalize_string_list(structured_content.get('response_prompts'), limit=4)
        practice_hooks = self._normalize_string_list(structured_content.get('practice_hooks'), limit=4)

        if not exemplar_focus:
            exemplar_focus = [
                f'Anchor the lesson in one concrete {skill_node.name} case before moving into broader explanation.',
            ]
        if not observation_prompts:
            observation_prompts = [
                f'Identify one specific detail in the {skill_node.name} example and explain what it changes or reveals.',
            ]
        if study_mode == 'compare' and not comparison_prompts:
            comparison_prompts = [
                'Compare two concrete cases side-by-side using one explicit lens, then justify the most important difference.',
            ]
        elif study_mode != 'compare' and not comparison_prompts:
            comparison_prompts = [
                'Contrast this example with a nearby variation, weaker case, or alternate interpretation to sharpen the distinction.',
            ]
        if not response_prompts and kind in {'lesson', 'examples', 'deep_lesson'}:
            response_prompts = [
                'Respond only after the evidence is clear: interpret one specific detail and support your reading with what the lesson showed.',
            ]
        if not practice_hooks and kind != 'deep_lesson':
            practice_hooks = [
                'Apply the pattern in one small worked attempt, then explain what changed between attempt one and two.',
            ]
        elif not practice_hooks and kind == 'deep_lesson':
            practice_hooks = [
                'Translate this deep reading into one concrete practice or observation task, using the lesson evidence as your guide.',
            ]

        structured_content['exemplar_focus'] = exemplar_focus[:3]
        structured_content['comparison_prompts'] = comparison_prompts[:4]
        structured_content['observation_prompts'] = observation_prompts[:5]
        structured_content['response_prompts'] = response_prompts[:4]
        structured_content['practice_hooks'] = practice_hooks[:4]
        return structured_content

    def _clear_legacy_supporting_media_fields(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        structured_content: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        if kind not in {'lesson', 'examples', 'deep_lesson'}:
            return structured_content
        if not isinstance(structured_content, dict):
            return structured_content
        prior_media = structured_content.get('supporting_media')
        prior_count = len(prior_media) if isinstance(prior_media, list) else 0
        removed_keys = (
            'supporting_media',
            'visual_support_needed',
            'visual_priority',
            'visual_support_reason',
            'visual_support_selected_count',
        )
        removed_any = prior_count > 0 or any(key in structured_content for key in removed_keys[1:])
        for key in removed_keys:
            structured_content.pop(key, None)
        if removed_any:
            logger.info(
                'resource.legacy_media_fields_cleared topic_id=%s skill_id=%s kind=%s cleared_existing=%s',
                topic.id,
                skill_node.id,
                kind,
                prior_count,
            )
        return structured_content

    def _contains_advanced_pattern(self, text: str) -> bool:
        lowered = text.lower()
        patterns = (
            '5-minute set',
            '5 minute set',
            'full set',
            'live set',
            'perform a set',
            'end-to-end',
            'end to end',
            'full production workflow',
            'release-ready',
            'mastering chain',
        )
        return any(pattern in lowered for pattern in patterns)

    def _exercise_signature(self, title: str, task: str) -> str:
        compact = f'{title.strip().lower()}::{task.strip().lower()}'
        compact = compact.replace('\n', ' ')
        return ' '.join(compact.split())

    def _normalize_exercise_collection(self, structured_content: dict[str, Any]) -> dict[str, Any]:
        exercises = structured_content.get('exercises')
        if not isinstance(exercises, list):
            return structured_content

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in exercises:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get('title') or '').strip()
            task = str(raw.get('task') or '').strip()
            if not title or not task:
                continue
            signature = self._exercise_signature(title, task)
            if signature in seen:
                continue
            seen.add(signature)
            difficulty_raw = str(raw.get('difficulty') or 'medium').strip().lower()
            difficulty = difficulty_raw if difficulty_raw in {'easy', 'medium', 'hard'} else 'medium'
            hints_raw = raw.get('hints')
            hints = (
                [str(item).strip() for item in hints_raw if str(item).strip()]
                if isinstance(hints_raw, list)
                else []
            )[:4]
            if not hints:
                hints = ['Break the task into one small focused step.', 'Validate one result before moving on.']
            expected_outcome = str(raw.get('expected_outcome') or '').strip()
            if not expected_outcome:
                expected_outcome = 'You complete one focused attempt and identify one concrete improvement.'

            normalized.append(
                {
                    'title': _truncate_text_cleanly(title, 120),
                    'task': _truncate_text_cleanly(task, 500),
                    'hints': hints,
                    'expected_outcome': _truncate_text_cleanly(expected_outcome, 300),
                    'difficulty': difficulty,
                }
            )

        if len(normalized) > 2:
            selected: list[dict[str, Any]] = []
            used_indexes: set[int] = set()
            for target in ('easy', 'medium', 'hard'):
                for idx, item in enumerate(normalized):
                    if idx in used_indexes or item.get('difficulty') != target:
                        continue
                    selected.append(item)
                    used_indexes.add(idx)
                    break
                if len(selected) >= 2:
                    break
            if len(selected) < 2:
                for idx, item in enumerate(normalized):
                    if idx in used_indexes:
                        continue
                    selected.append(item)
                    used_indexes.add(idx)
                    if len(selected) >= 2:
                        break
            normalized = selected[:2]

        if len(normalized) == 1:
            first = normalized[0]
            normalized.append(
                {
                    'title': _truncate_text_cleanly(f'{first["title"]} (variation)', 120),
                    'task': _truncate_text_cleanly(
                        f'{first["task"]}\n\nVariation: repeat with one controlled change and compare outcomes.',
                        500,
                    ),
                    'hints': (
                        list(first.get('hints') or [])[:2]
                        + ['Change only one variable so you can compare results clearly.']
                    )[:4],
                    'expected_outcome': _truncate_text_cleanly(
                        str(first.get('expected_outcome') or '')
                        + ' You can explain the difference between attempt A and attempt B.',
                        300,
                    ),
                    'difficulty': first.get('difficulty') if first.get('difficulty') in {'easy', 'medium', 'hard'} else 'medium',
                }
            )
        elif len(normalized) == 0:
            normalized = [
                {
                    'title': 'Focused practice drill',
                    'task': 'Complete one short focused practice attempt on the core concept.',
                    'hints': ['Keep scope narrow.', 'Check one outcome at the end.'],
                    'expected_outcome': 'You can explain one thing that improved after this drill.',
                    'difficulty': 'easy',
                },
                {
                    'title': 'Apply and compare',
                    'task': 'Run a second attempt with one controlled change and compare results.',
                    'hints': ['Change one variable only.', 'Write down the before/after difference.'],
                    'expected_outcome': 'You can describe which change improved the outcome and why.',
                    'difficulty': 'medium',
                },
            ]

        structured_content['exercises'] = normalized[:2]
        return structured_content

    def _enforce_foundation_scope(
        self,
        *,
        kind: str,
        structured_content: dict[str, Any],
        skill_name: str,
    ) -> dict[str, Any]:
        if kind != 'exercises':
            return structured_content

        exercises = structured_content.get('exercises')
        if not isinstance(exercises, list):
            return structured_content

        normalized_exercises: list[dict[str, Any]] = []
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue

            text = ' '.join(
                [
                    str(exercise.get('title', '')),
                    str(exercise.get('task', '')),
                    str(exercise.get('expected_outcome', '')),
                ]
            )
            if self._contains_advanced_pattern(text):
                exercise['task'] = (
                    f'In a short 10-minute practice, focus on one core "{skill_name}" technique only. '
                    'Repeat the same simple pattern until timing and control are stable.'
                )
                exercise['expected_outcome'] = (
                    'You can demonstrate one foundational pattern cleanly for 30-60 seconds and explain what improved.'
                )
                hints = exercise.get('hints')
                if isinstance(hints, list):
                    exercise['hints'] = (hints[:2] + ['Keep the scope small: one pattern, one technique.'])[:4]
                else:
                    exercise['hints'] = [
                        'Start with one simple pattern.',
                        'Keep the drill short and repeatable.',
                    ]
                exercise['difficulty'] = 'easy'

            normalized_exercises.append(exercise)

        if normalized_exercises:
            structured_content['exercises'] = normalized_exercises
        return structured_content

    def _resource_type_for_kind(self, kind: str) -> ResourceType:
        mapping = {
            'lesson': ResourceType.generated_lesson,
            'examples': ResourceType.generated_examples,
            'exercises': ResourceType.generated_exercises,
        }
        if kind not in mapping:
            raise ValueError('Unsupported resource kind.')
        return mapping[kind]

    def _fallback_lesson_content(self, *, topic: Topic, skill_node: SkillNode, learner_level: str) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Starter lesson',
            'summary': _truncate_text_cleanly(
                f'A focused introduction to {skill_node.name} for {learner_level} learners in {topic.name}, anchored in concrete examples and short practice.',
                300,
            ),
            'learning_objectives': [
                f'Explain the core purpose of {skill_node.name}.',
                'Apply one foundational method correctly in a small example.',
            ],
            'key_concepts': [
                {
                    'term': skill_node.name[:100],
                    'description': 'The core concept this node teaches and why it matters in practice.',
                },
                {
                    'term': 'Foundational workflow',
                    'description': 'A repeatable sequence of steps for basic execution and review.',
                },
                {
                    'term': 'Worked contrast',
                    'description': 'A side-by-side comparison between a stronger and weaker case that reveals the deciding difference.',
                },
            ],
            'sections': [
                {
                    'role': 'example',
                    'heading': 'Start with one grounded case',
                    'content': _truncate_text_cleanly(
                        f'Start from one concrete {skill_node.name} case. Describe what is happening in plain language, '
                        'name one specific detail, and explain why that detail is the right place to begin.',
                        800,
                    ),
                },
                {
                    'role': 'analysis',
                    'heading': 'Explain the mechanism, not just the label',
                    'content': _truncate_text_cleanly(
                        'Walk step by step through what the detail is doing, why it matters, and what would change if it were missing or handled poorly. '
                        'Use a short cause-and-effect explanation rather than summary language.',
                        800,
                    ),
                },
                {
                    'role': 'comparison',
                    'heading': 'Add contrast and a common failure mode',
                    'content': _truncate_text_cleanly(
                        'Compare the anchor case with a weaker variant, nearby alternative, or common mistake. '
                        'Use that contrast to show the boundary of the concept instead of relying on broad definition alone.',
                        800,
                    ),
                },
                {
                    'role': 'transfer',
                    'heading': 'Transfer the idea into one worked attempt',
                    'content': _truncate_text_cleanly(
                        'Only after the explanation is clear, run one small worked attempt. State what to try, what result to watch for, and how to tell whether the concept actually transferred.',
                        800,
                    ),
                },
            ],
            'takeaways': [
                f'You should be able to explain {skill_node.name} through one concrete case rather than a vague definition.',
                'Contrast and failure cases make the concept more trustworthy and easier to transfer.',
            ],
            'exemplar_focus': [
                f'Choose one concrete {skill_node.name} exemplar and use it as your anchor.',
            ],
            'comparison_prompts': [
                'Compare your anchor exemplar with one alternative and name the clearest difference.',
            ],
            'observation_prompts': [
                f'Notice one specific formal choice in the {skill_node.name} exemplar and explain its effect.',
            ],
            'response_prompts': [
                'Write a short interpretation grounded in one observed detail rather than summary language.',
            ],
            'practice_hooks': [
                'Run one short practical attempt, then document one change you would test next.',
            ],
            'next_steps': [
                'Open examples to see the concept applied in context.',
                'Move to exercises and complete one short task end-to-end.',
            ],
        }

    def _fallback_examples_content(self, *, topic: Topic, skill_node: SkillNode) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Worked examples',
            'intro': _truncate_text_cleanly(
                f'These examples foreground concrete works and practical moves for {skill_node.name} in {topic.name}.',
                420,
            ),
            'examples': [
                {
                    'role': 'anchor',
                    'name': 'Anchor case: clean execution',
                    'explanation': _truncate_text_cleanly(
                        f'Start with a minimal case where {skill_node.name} is applied once with clear inputs, a visible decision, and a clear outcome. '
                        'Explain each step so the learner can see what makes the example work.',
                        500,
                    ),
                    'why_it_matters': _truncate_text_cleanly(
                        'This gives the learner one reliable worked model before any contrast or variation is introduced.',
                        280,
                    ),
                },
                {
                    'role': 'contrast',
                    'name': 'Contrast case: weak move and correction',
                    'explanation': _truncate_text_cleanly(
                        f'Show a frequent mistake in {skill_node.name}, explain why it fails, and then demonstrate the corrected approach with one precise change.',
                        500,
                    ),
                    'why_it_matters': _truncate_text_cleanly(
                        'Seeing a wrong move beside a better one helps the learner understand the real boundary of the concept.',
                        280,
                    ),
                },
                {
                    'role': 'transfer',
                    'name': 'Transfer case: same principle in a new setting',
                    'explanation': _truncate_text_cleanly(
                        f'Apply the same {skill_node.name} principle in a new but closely related situation. Show what stays the same, what changes, and how the learner should adapt the move.',
                        500,
                    ),
                    'why_it_matters': _truncate_text_cleanly(
                        'This demonstrates transfer, so the learner sees how to use the concept beyond the anchor example.',
                        280,
                    ),
                },
            ],
            'exemplar_focus': [
                f'Anchor this set around one strong {skill_node.name} exemplar before broad comparisons.',
            ],
            'comparison_prompts': [
                'Stage one side-by-side comparison and explain the meaningful difference in outcome.',
            ],
            'observation_prompts': [
                'Notice one detail first, then interpret why it matters.',
            ],
            'response_prompts': [
                'Draft a short response that applies one observed choice from the exemplar.',
            ],
            'practice_hooks': [
                'Try one constrained variation and capture what changed.',
            ],
        }

    def _fallback_exercises_content(self, *, topic: Topic, skill_node: SkillNode) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Starter exercises',
            'intro': _truncate_text_cleanly(
                f'Complete these short drills to build confidence in {skill_node.name} within {topic.name}.',
                420,
            ),
            'exercises': [
                {
                    'title': 'Quick concept drill',
                    'task': _truncate_text_cleanly(
                        f'Spend 10 minutes applying one core {skill_node.name} technique in a minimal practice setup.',
                        500,
                    ),
                    'hints': [
                        'Keep the task narrow and repeatable.',
                        'Check one variable at a time.',
                    ],
                    'expected_outcome': _truncate_text_cleanly(
                        'You can perform one clean attempt and explain what worked and what to improve next.',
                        300,
                    ),
                    'difficulty': 'easy',
                },
                {
                    'title': 'Error-spotting mini task',
                    'task': _truncate_text_cleanly(
                        f'Review a flawed {skill_node.name} attempt, identify one mistake, and produce a corrected version.',
                        500,
                    ),
                    'hints': [
                        'Write down the mistake before fixing it.',
                        'Validate the correction with one quick re-test.',
                    ],
                    'expected_outcome': _truncate_text_cleanly(
                        'You can identify a common error pattern and apply a targeted correction.',
                        300,
                    ),
                    'difficulty': 'medium',
                },
            ],
        }

    def _fallback_structured_content(
        self,
        *,
        kind: str,
        topic: Topic,
        skill_node: SkillNode,
        learner_level: str,
    ) -> dict[str, Any]:
        if kind == 'lesson':
            return self._fallback_lesson_content(topic=topic, skill_node=skill_node, learner_level=learner_level)
        if kind == 'examples':
            return self._fallback_examples_content(topic=topic, skill_node=skill_node)
        if kind == 'exercises':
            return self._fallback_exercises_content(topic=topic, skill_node=skill_node)
        raise ValueError('Unsupported resource kind for fallback.')

    def _fallback_deep_lesson_content(self, *, topic: Topic, skill_node: SkillNode) -> dict[str, Any]:
        return {
            'title': f'{skill_node.name}: Deep dive',
            'summary': _truncate_text_cleanly(
                f'A deeper lesson on {skill_node.name} that moves from exemplar observation to interpretation, comparison, and applied response in {topic.name}.',
                420,
            ),
            'essential_questions': [
                f'Which concrete exemplar best reveals the core logic of {skill_node.name}?',
                f'How does context deepen interpretation without replacing close observation?',
            ],
            'sections': [
                {
                    'role': 'example',
                    'heading': 'Start from one anchor exemplar',
                    'content': (
                        f'Start with one concrete {skill_node.name} exemplar. '
                        'Identify what you can observe directly before introducing abstract terms. '
                        'Use concrete detail as the base layer for interpretation, and include enough description that the learner does not need prior familiarity.'
                    ),
                },
                {
                    'role': 'analysis',
                    'heading': 'Interpret the details before broad context',
                    'content': (
                        'Explain what the most revealing details are doing and why they matter. '
                        'Keep interpretation tied to evidence rather than broad summary language, and walk through the logic step by step.'
                    ),
                },
                {
                    'role': 'comparison',
                    'heading': 'Context, influence, and comparison',
                    'content': (
                        f'Add historical and cultural context to explain why the exemplar takes this shape. '
                        'Compare at least one adjacent work, movement, or interpretation. '
                        'Use evidence to explain differences instead of broad labels, and make the comparison criteria explicit.'
                    ),
                },
                {
                    'role': 'transfer',
                    'heading': 'Response and transfer',
                    'content': (
                        f'Convert understanding into action with a short response task tied to {skill_node.name}. '
                        'Describe what to try, what to notice, and how to reflect on changes in judgment or taste.'
                    ),
                },
            ],
            'exemplar_focus': [
                f'Choose one defining {skill_node.name} exemplar and keep returning to it through the lesson.',
            ],
            'comparison_prompts': [
                'Compare your anchor exemplar with one related work and justify the key contrast with evidence.',
            ],
            'observation_prompts': [
                'List three concrete details before writing your interpretation.',
            ],
            'response_prompts': [
                'Write or make a short response that applies one technique or interpretive lens from this lesson.',
            ],
            'practice_hooks': [
                'Schedule one focused 15-minute practice session and log what changed in your next note.',
            ],
            'key_terms': [
                {
                    'term': skill_node.name[:100],
                    'description': 'The focal concept of this deep lesson and its defining characteristics.',
                },
                {
                    'term': 'Primary evidence',
                    'description': 'First-hand sources or direct artifacts used to support historical or technical claims.',
                },
                {
                    'term': 'Interpretive lens',
                    'description': 'A framework used to analyze evidence and reach a defensible conclusion.',
                },
            ],
            'study_prompts': [
                f'Explain {skill_node.name} in your own words using one concrete example.',
                'Identify one common misunderstanding and correct it with evidence.',
                'Write a short comparison between two interpretations and justify your conclusion.',
            ],
        }

    def _domain_for_url(self, url: str) -> str:
        host = urlparse(url).netloc.lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _is_direct_image_url(self, url: str) -> bool:
        if '/api/media-cache/proxy/' in (url or '').lower():
            return True
        lowered = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        if '/wiki/file:' in lowered:
            return False
        return lowered.endswith(_DIRECT_IMAGE_EXTENSIONS)

    def _wikimedia_preview_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith('www.'):
            host = host[4:]
        if host not in {'commons.wikimedia.org', 'wikipedia.org', 'en.wikipedia.org'}:
            return None

        path = parsed.path or ''
        marker = '/wiki/File:'
        if marker not in path:
            return None
        raw_file_name = path.split(marker, 1)[1].strip()
        if not raw_file_name:
            return None

        decoded = unquote(raw_file_name)
        if not self._is_direct_image_url(decoded):
            return None
        return f'https://commons.wikimedia.org/wiki/Special:FilePath/{quote(decoded)}'

    def _resolve_image_preview_url(
        self,
        *,
        url: str,
        kind: str,
        lowered_meta: str,
        existing_preview_url: str = '',
    ) -> str | None:
        preview_candidate = existing_preview_url.strip()
        if preview_candidate and self._is_direct_image_url(preview_candidate):
            return preview_candidate
        if self._is_direct_image_url(url):
            return url
        wikimedia_preview = self._wikimedia_preview_url(url)
        if wikimedia_preview:
            return wikimedia_preview
        # Allow article/source URLs to flow into the media-cache proxy, which can extract
        # og:image/twitter:image and first renderable inline assets.
        if kind == 'external_image' and (url.startswith('http://') or url.startswith('https://')):
            return url
        return None

    def _extract_media_keywords(self, *, topic: Topic, skill_node: SkillNode, deep_lesson: dict[str, Any]) -> list[str]:
        base_terms = [
            topic.name,
            topic.description or '',
            topic.goal or '',
            skill_node.name,
            skill_node.description or '',
            str(deep_lesson.get('title') or ''),
            str(deep_lesson.get('summary') or ''),
            *(str(item) for item in deep_lesson.get('essential_questions', []) if str(item).strip()),
            *(str(item) for item in deep_lesson.get('learning_objectives', []) if str(item).strip()),
            *(str(item) for item in deep_lesson.get('exemplar_focus', []) if str(item).strip()),
            *(str(item) for item in deep_lesson.get('comparison_prompts', []) if str(item).strip()),
            *(str(item) for item in deep_lesson.get('observation_prompts', []) if str(item).strip()),
            *(str(item.get('heading')) for item in deep_lesson.get('sections', []) if isinstance(item, dict)),
            *(str(item.get('term')) for item in deep_lesson.get('key_terms', []) if isinstance(item, dict)),
            *(str(item.get('term')) for item in deep_lesson.get('key_concepts', []) if isinstance(item, dict)),
            *(str(item.get('name')) for item in deep_lesson.get('examples', []) if isinstance(item, dict)),
        ]
        keywords: list[str] = []
        seen: set[str] = set()
        for term in base_terms:
            normalized = ' '.join(term.lower().split())
            if len(normalized) < 3:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            keywords.append(normalized)
            if len(keywords) >= 14:
                break
        return keywords

    def _compact_media_query_seed(self, *, topic: Topic, skill_node: SkillNode, keywords: list[str]) -> str:
        parts: list[str] = []
        for seed in (topic.name, skill_node.name):
            cleaned = ' '.join(str(seed or '').split()).strip()
            if cleaned and cleaned.lower() not in {item.lower() for item in parts}:
                parts.append(cleaned[:64])

        for keyword in keywords:
            cleaned = ' '.join(keyword.split()).strip()
            if not cleaned:
                continue
            if len(cleaned) > 48:
                continue
            lowered = cleaned.lower()
            if lowered in {item.lower() for item in parts}:
                continue
            parts.append(cleaned)
            if len(parts) >= 5:
                break

        seed = ' '.join(parts).strip()
        # Keep search queries compact to avoid provider-side parse errors.
        return seed[:160]

    def _media_relevance_score(self, *, title: str, summary: str, url: str, keywords: list[str], skill_name: str) -> float:
        haystack = f'{title} {summary} {url}'.lower()
        if not haystack.strip():
            return 0.0

        matches = sum(1 for keyword in keywords if keyword in haystack)
        score = matches / max(1, len(keywords))
        if skill_name.lower() in haystack:
            score += 0.2
        if any(
            token in haystack
            for token in (
                'museum',
                'archive',
                'artwork',
                'primary source',
                'documentary',
                'lecture',
                'gallery',
                'collection',
                'scene',
                'still',
                'visual analysis',
            )
        ):
            score += 0.08
        if any(token in haystack for token in _VISUAL_MEDIA_HINTS):
            score += 0.08
        if any(token in haystack for token in ('history', 'geography', 'culture', 'politics', 'science', 'education')):
            score += 0.05
        return min(score, 1.0)

    def _title_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r'[a-z0-9]{3,}', (text or '').lower())
            if token not in _VIDEO_TITLE_STOPWORDS
        }

    def _video_title_similarity(self, *, node_title: str, candidate_title: str) -> float:
        node_tokens = self._title_tokens(node_title)
        candidate_tokens = self._title_tokens(candidate_title)
        if not node_tokens or not candidate_tokens:
            return 0.0
        overlap = node_tokens.intersection(candidate_tokens)
        if not overlap:
            return 0.0
        coverage = len(overlap) / max(1, len(node_tokens))
        concentration = len(overlap) / max(1, len(candidate_tokens))
        return min(1.0, (coverage * 0.7) + (concentration * 0.3))

    def _is_embeddable_video_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        host = (parsed.netloc or '').lower()
        if host.startswith('www.'):
            host = host[4:]
        if host in {'youtube.com', 'm.youtube.com', 'youtu.be', 'vimeo.com', 'player.vimeo.com'}:
            return True
        normalized = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        return normalized.endswith(_DIRECT_VIDEO_EXTENSIONS)

    def _is_trusted_media_candidate(self, *, domain: str, title: str, summary: str, kind: str) -> bool:
        if not domain:
            return False
        if self._is_deemphasized_media_domain(domain):
            return False
        if any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_SOCIAL_MEDIA_DOMAINS):
            return False
        if any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_STOCK_MEDIA_DOMAINS):
            return False
        trusted_domain = domain.endswith('.edu') or any(domain == allowed or domain.endswith(f'.{allowed}') for allowed in _TRUSTED_MEDIA_DOMAINS)
        if not trusted_domain:
            return False

        lowered_meta = f'{title} {summary}'.lower()
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return kind == 'external_video' and bool(lowered_meta.strip())

        return True

    def _is_deemphasized_media_domain(self, domain: str) -> bool:
        if not domain:
            return False
        return any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _DEEMPHASIZED_MEDIA_DOMAINS)

    def _infer_media_type(
        self,
        *,
        kind: str,
        url: str,
        lowered_meta: str,
        allow_article_fallback: bool = False,
    ) -> str | None:
        if kind == 'external_video':
            return 'video'
        normalized_url = (url or '').lower().split('?', 1)[0].split('#', 1)[0]
        if normalized_url.endswith(_DIRECT_VIDEO_EXTENSIONS):
            return 'video'
        if kind == 'external_image':
            return 'image'
        if self._is_direct_image_url(url):
            return 'image'
        if any(token in lowered_meta for token in _VISUAL_MEDIA_HINTS):
            return 'image'
        if allow_article_fallback and kind in {'external_article', 'external_documentation'}:
            return 'image'
        return None

    async def generate_deep_lesson_material(
        self,
        db: Session,
        *,
        user_id: int,
        topic: Topic,
        skill_node: SkillNode,
    ) -> tuple[dict[str, Any], Literal['generated', 'fallback']]:
        technical_depth = self._technical_depth(topic)
        memory_snapshot = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=user_id,
            focus_skill_id=skill_node.id,
        )
        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{topic.name} {skill_node.name} deep explanation',
            top_k=5,
        )
        notes_context = '\n\n'.join(f'- {item.text[:360]}' for item in retrieved)
        research_insights = await self.course_research_service.gather_for_skill(
            topic=topic,
            skill_node=skill_node,
            kind='deep_lesson',
            memory=memory_snapshot,
            retrieval_hits=len(retrieved),
            limit=4,
        )
        web_grounding_context = self.course_research_service.format_prompt_context(research_insights, max_items=4)
        memory_context = self._course_memory_context(memory_snapshot)
        editorial_spine_context = self._editorial_spine_context(topic)

        concise_lesson = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=ResourceType.generated_lesson,
        )
        concise_examples = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=ResourceType.generated_examples,
        )
        concise_lesson_context = ''
        if concise_lesson and isinstance(concise_lesson.content_json, dict):
            concise_lesson_context = json.dumps(concise_lesson.content_json)[:1600]
        concise_examples_context = ''
        if concise_examples and isinstance(concise_examples.content_json, dict):
            concise_examples_context = json.dumps(concise_examples.content_json)[:1600]

        system_prompt = (
            'You are a senior tutor writing a high-quality deep-dive lesson. '
            'Teach thoroughly, stay accurate, and keep the structure clear for self-study.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Difficulty: {skill_node.difficulty}\n\n'
            f'Technical depth preference: {technical_depth}\n'
            f'Technical depth guidance: {technical_depth_prompt_guidance(technical_depth)}\n\n'
            'Produce a richer, textbook-style deep lesson on this exact skill. '
            'Do not repeat generic overview text. Go deeper with context, reasoning, and concrete explanations.\n\n'
            f'Editorial spine (keep coherence with this sequence):\n{editorial_spine_context}\n\n'
            f'Course memory ledger:\n{memory_context}\n\n'
            f'Existing concise lesson context (if available):\n{concise_lesson_context or "None"}\n\n'
            f'Existing examples context (if available):\n{concise_examples_context or "None"}\n\n'
            f'Retrieved learner context:\n{notes_context or "No learner context available"}\n\n'
            f'Curated web grounding context (only include if directly relevant):\n'
            f'{web_grounding_context or "No high-signal web grounding selected"}\n\n'
            'Output structured content only and stay tightly scoped to this skill node.\n'
            f'{self._practice_balance_rules(kind="deep_lesson", study_mode="standard")}\n'
            'Quality constraints:\n'
            '- No concept without evidence. Support claims with cases, source-grounded detail, mechanisms, or worked explanation.\n'
            '- No exemplar without operationalization. If you name a work, event, thinker, principle, or place, teach through it.\n'
            '- Make the lesson self-contained; do not assume outside familiarity with the topic.\n'
            '- Do not move into response or practice before enough teaching has happened.\n'
            '- Avoid formulaic filler phrases and generic transitions.\n'
            '- Prefer concrete distinctions, trade-offs, and specific examples.\n'
            '- Do not repeat examples already used in the course memory unless clearly marked as remediation.\n'
            '- Make the first section concretely observable, the middle sections interpretive and comparative, and the later section transfer-oriented.\n'
            '- Let context or history deepen the reading; do not let it take over the lesson body.\n'
            '- Populate exemplar_focus, comparison_prompts, observation_prompts, response_prompts, and practice_hooks.'
        )

        try:
            structured_model = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=DeepLessonPlan,
                temperature=0.25,
                max_tokens=2400,
            )
            structured_content = self._polish_structured_snippets(
                kind='deep_lesson',
                structured_content=structured_model.model_dump(),
            )
            structured_content, used_fallback, _quality_report = await self._quality_control_structured_content(
                kind='deep_lesson',
                structured_content=structured_content,
                topic=topic,
                skill_node=skill_node,
                study_mode='standard',
                technical_depth=technical_depth,
                memory_snapshot=memory_snapshot,
                memory_context=memory_context,
                max_tokens=2400,
                fallback_builder=lambda: self._fallback_deep_lesson_content(topic=topic, skill_node=skill_node),
            )
            snapshot_after = self.course_memory_service.build_snapshot(
                db,
                topic=topic,
                user_id=user_id,
                focus_skill_id=skill_node.id,
            )
            self.course_memory_service.persist_snapshot(
                db,
                topic=topic,
                snapshot=snapshot_after,
                reason='generated_deep_lesson',
            )
            ledger_payload = topic.curriculum_ledger if isinstance(topic.curriculum_ledger, dict) else {}
            ledger_payload['latest_deep_lesson_research'] = self.course_research_service.to_ledger_records(
                research_insights,
                limit=6,
            )
            topic.curriculum_ledger = ledger_payload
            db.commit()
            return structured_content, 'generated'
        except ProviderError as exc:
            logger.warning(
                'resource.deep_lesson_fallback topic_id=%s skill_id=%s error=%s',
                topic.id,
                skill_node.id,
                exc,
            )
            structured_content = self._polish_structured_snippets(
                kind='deep_lesson',
                structured_content=self._fallback_deep_lesson_content(topic=topic, skill_node=skill_node),
            )
            structured_content = self._ensure_studio_balance_fields(
                kind='deep_lesson',
                structured_content=structured_content,
                skill_node=skill_node,
                study_mode='standard',
            )
            structured_content = self._clear_legacy_supporting_media_fields(
                topic=topic,
                skill_node=skill_node,
                structured_content=structured_content,
                kind='deep_lesson',
            )
            return structured_content, 'fallback'

    def _get_active_generated_resource(
        self,
        db: Session,
        *,
        user_id: int,
        skill_node_id: int,
        resource_type: ResourceType,
    ) -> LearningResource | None:
        return db.scalar(
            select(LearningResource)
            .where(
                LearningResource.skill_node_id == skill_node_id,
                LearningResource.resource_type == resource_type,
                LearningResource.is_active.is_(True),
                (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
            )
            .order_by(LearningResource.version.desc(), LearningResource.created_at.desc())
        )

    def _extract_structured_content(self, resource: LearningResource) -> dict[str, Any] | None:
        if resource.content_json:
            return resource.content_json

        content = (resource.content or '').strip()
        if not content:
            return None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    async def generate_material(
        self,
        db: Session,
        *,
        user_id: int,
        topic: Topic,
        skill_node: SkillNode,
        kind: str,
        regenerate: bool = False,
        study_mode: str = 'standard',
        exemplar_title: str | None = None,
        exemplar_context: str | None = None,
        comparison_left: str | None = None,
        comparison_right: str | None = None,
        comparison_axis: str | None = None,
    ) -> tuple[LearningResource, dict[str, Any] | None, ResourceSource]:
        resource_type = self._resource_type_for_kind(kind)
        normalized_study_mode = (study_mode or 'standard').strip().lower()
        existing = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
        )

        if existing and not regenerate:
            structured = self._extract_structured_content(existing)
            if isinstance(structured, dict) and kind in {'lesson', 'examples'}:
                before_structured = dict(structured)
                structured = self._clear_legacy_supporting_media_fields(
                    topic=topic,
                    skill_node=skill_node,
                    structured_content=structured,
                    kind=kind,
                )
                legacy_media_cleared = structured != before_structured
                if legacy_media_cleared:
                    existing.content_json = structured
                    existing.content = json.dumps(structured, indent=2)
                    existing.summary = _clean_clipped_fragment(
                        structured.get('summary') or structured.get('intro') or existing.content,
                        max_len=320,
                    )
                    db.add(existing)
                    db.commit()
                    db.refresh(existing)
            else:
                legacy_media_cleared = False
            logger.info(
                'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s legacy_media_cleared=%s',
                topic.id,
                skill_node.id,
                kind,
                existing.version,
                legacy_media_cleared,
            )
            return existing, structured, 'stored'

        technical_depth = self._technical_depth(topic)
        lesson_targets = technical_depth_lesson_targets(normalize_technical_depth(technical_depth))

        prompts = {
            'lesson': (
                LessonPlan,
                (
                    'Create a high-quality lesson that is conceptually rich, specific, and pedagogically structured. '
                    'Prioritize exemplar-first teaching, evidence density, worked explanation, and response-oriented understanding over generic summary language.'
                ),
                int(lesson_targets['max_tokens']),
            ),
            'examples': (
                ExamplesPlan,
                (
                    'Create worked examples that build from simple to challenging, foreground visible/audible details, and explain the reasoning. '
                    f'Adjust example rigor to this technical depth: {technical_depth_prompt_guidance(technical_depth)} '
                    'while keeping intro concise (roughly 2-3 sentences). Include at least one contrast or transfer case.'
                ),
                1000,
            ),
            'exercises': (
                ExercisesPlan,
                (
                    'Create exercises for short practice sessions with clear expected outcomes and concrete creative action. '
                    f'Adjust cognitive complexity to this technical depth: {technical_depth_prompt_guidance(technical_depth)} '
                    'while keeping intro concise (roughly 2-3 sentences).'
                ),
                1100,
            ),
        }
        schema_model, instruction, max_tokens = prompts[kind]

        mode_instruction = ''
        mode_context_lines: list[str] = []
        if normalized_study_mode == 'exemplar':
            anchor_title = (exemplar_title or skill_node.name).strip()
            anchor_context = (exemplar_context or '').strip()
            mode_instruction = (
                'Exemplar-first mode is active. Teach through one concrete artifact and keep explanations anchored to it. '
                'Prioritize close reading/listening/viewing observations over abstraction.'
            )
            mode_context_lines = [
                f'Exemplar anchor: {anchor_title}',
                f'Exemplar context from learner: {anchor_context or "Not provided"}',
            ]
        elif normalized_study_mode == 'compare':
            left = (comparison_left or '').strip()
            right = (comparison_right or '').strip()
            axis = (comparison_axis or '').strip() or 'form, context, interpretation, and effect'
            mode_instruction = (
                'Compare mode is active. Structure material around contrasts and convergences between the two targets. '
                'Make comparison criteria explicit and avoid vague summaries.'
            )
            mode_context_lines = [
                f'Comparison target A: {left}',
                f'Comparison target B: {right}',
                f'Comparison lens: {axis}',
            ]
        else:
            normalized_study_mode = 'standard'
            mode_instruction = (
                'Studio standard mode is active. Teach through concrete examples and observable details, then connect to context and theory.'
            )

        memory_snapshot = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=user_id,
            focus_skill_id=skill_node.id,
        )
        memory_context = self._course_memory_context(memory_snapshot)
        stable_coverage_context = self._stable_coverage_context(memory_snapshot)
        editorial_spine_context = self._editorial_spine_context(topic)

        retrieved = await self.retrieval_service.retrieve_chunks(
            db,
            topic_id=topic.id,
            query=f'{topic.name} {skill_node.name}',
            top_k=3,
        )
        notes_context = '\n\n'.join(f'- {item.text[:320]}' for item in retrieved)
        research_insights = await self.course_research_service.gather_for_skill(
            topic=topic,
            skill_node=skill_node,
            kind=kind,
            memory=memory_snapshot,
            retrieval_hits=len(retrieved),
            limit=3,
        )
        web_grounding_context = self.course_research_service.format_prompt_context(research_insights, max_items=3)
        user_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill_node.id,
            )
        )
        prerequisite_ids = db.scalars(
            select(SkillEdge.parent_skill_id).where(
                SkillEdge.topic_id == topic.id,
                SkillEdge.child_skill_id == skill_node.id,
            )
        ).all()
        prerequisite_names: list[str] = []
        if prerequisite_ids:
            prerequisite_nodes = db.scalars(select(SkillNode).where(SkillNode.id.in_(prerequisite_ids))).all()
            prerequisite_names = [node.name for node in prerequisite_nodes]

        difficulty_band = self._difficulty_band(skill_node.difficulty)
        learner_level = self._learner_level(user_state)
        alignment_rules = self._alignment_rules(skill_node.difficulty, learner_level, kind, technical_depth)
        field_length_rules = self._field_length_rules(kind, technical_depth)

        system_prompt = (
            'You are ResourceAgent. Produce high-quality learning material that is technically correct and '
            'tailored to learner context.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n\n'
            f'Skill difficulty (1-5): {skill_node.difficulty} ({difficulty_band})\n'
            f'Learner level for this node: {learner_level}\n'
            f'Technical depth preference: {technical_depth}\n'
            f'Learner progress state: {user_state.progress_state if user_state else "not_started"}\n'
            f'Instructional role for this node: {skill_node.instructional_role}\n'
            f'Prerequisites for this node: {", ".join(prerequisite_names) if prerequisite_names else "None"}\n\n'
            f'Study mode: {normalized_study_mode}\n'
            f'Study mode context:\n{chr(10).join(f"- {line}" for line in mode_context_lines) if mode_context_lines else "- None"}\n\n'
            f'Editorial spine excerpt (preserve coherence):\n{editorial_spine_context}\n\n'
            f'Course memory ledger:\n{memory_context}\n\n'
            f'Stable completed coverage guidance:\n{stable_coverage_context}\n\n'
            f'Retrieved learner notes:\n{notes_context or "No notes available"}\n\n'
            f'Curated web grounding references (optional; use only if directly relevant):\n'
            f'{web_grounding_context or "None"}\n\n'
            f'Alignment rules:\n{alignment_rules}\n'
            f'Formatting constraints:\n{field_length_rules}\n'
            f'{self._practice_balance_rules(kind=kind, study_mode=normalized_study_mode)}\n'
            f'Instruction: {instruction}\n\n'
            f'Study mode instruction: {mode_instruction or "No special mode. Use standard teaching flow."}\n\n'
            'If web references are present, use them selectively for specific examples and context. '
            'Do not force web facts when relevance is weak. Never produce a link dump.\n'
            'Anti-slop rules:\n'
            '- No concept without evidence. Back claims with cases, examples, mechanisms, worked explanation, or source-grounded detail.\n'
            '- No exemplar without operationalization. Teach through named examples rather than merely mentioning them.\n'
            '- Make the lesson self-contained enough that a learner can benefit without outside familiarity.\n'
            '- Do not ask the learner to reflect, compare, create, solve, or apply until the lesson has provided enough proof and explanation.\n'
            '- Avoid filler transitions, motivational fluff, and generic consulting language.\n'
            '- Add concrete distinctions and context-specific details.\n'
            '- Do not repeat examples already used unless remediation is explicitly required.\n'
            '- Do not let theory or background dominate the material before the learner has something concrete to observe or compare.\n'
            '- For lesson/examples, populate exemplar_focus, comparison_prompts, observation_prompts, response_prompts, and practice_hooks.'
        )

        used_fallback = False
        try:
            structured_model = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=schema_model,
                temperature=0.3,
                max_tokens=max_tokens,
            )
            structured_content = structured_model.model_dump()
        except ProviderError as exc:
            used_fallback = True
            logger.warning(
                'resource.generation_fallback kind=%s topic_id=%s skill_id=%s error=%s',
                kind,
                topic.id,
                skill_node.id,
                exc,
            )
            structured_content = self._fallback_structured_content(
                kind=kind,
                topic=topic,
                skill_node=skill_node,
                learner_level=learner_level,
            )
        if kind == 'examples' and isinstance(structured_content, dict):
            if normalized_study_mode == 'exemplar' and (exemplar_title or '').strip():
                anchor_title = (exemplar_title or '').strip()
                structured_content['title'] = f'Exemplar Study: {anchor_title}'
                intro = str(structured_content.get('intro') or '').strip()
                structured_content['intro'] = (
                    f'This set is anchored in "{anchor_title}" so each example stays concrete and interpretable. '
                    f'{intro}'.strip()
                )[:600]
            elif normalized_study_mode == 'compare' and (comparison_left or '').strip() and (comparison_right or '').strip():
                left = (comparison_left or '').strip()
                right = (comparison_right or '').strip()
                axis = (comparison_axis or '').strip() or 'form, context, interpretation, and effect'
                structured_content['title'] = f'Compare: {left} vs {right}'
                intro = str(structured_content.get('intro') or '').strip()
                structured_content['intro'] = (
                    f'This comparison set maps contrasts between "{left}" and "{right}" through {axis}. '
                    f'{intro}'.strip()
                )[:600]
        if kind in {'lesson', 'examples'}:
            fallback_builder = (
                (lambda: self._fallback_lesson_content(topic=topic, skill_node=skill_node, learner_level=learner_level))
                if kind == 'lesson'
                else (lambda: self._fallback_examples_content(topic=topic, skill_node=skill_node))
            )
            structured_content, quality_used_fallback, _quality_report = await self._quality_control_structured_content(
                kind=kind,
                structured_content=structured_content,
                topic=topic,
                skill_node=skill_node,
                study_mode=normalized_study_mode,
                technical_depth=technical_depth,
                memory_snapshot=memory_snapshot,
                memory_context=memory_context,
                max_tokens=max_tokens,
                fallback_builder=fallback_builder,
            )
            used_fallback = used_fallback or quality_used_fallback
        if skill_node.difficulty <= 2 or learner_level == 'beginner':
            structured_content = self._enforce_foundation_scope(
                kind=kind,
                structured_content=structured_content,
                skill_name=skill_node.name,
            )
        if kind == 'exercises':
            structured_content = self._normalize_exercise_collection(structured_content)
        structured_content = self._polish_structured_snippets(kind=kind, structured_content=structured_content)
        content = json.dumps(structured_content, indent=2)
        summary = _clean_clipped_fragment(
            structured_content.get('summary') or structured_content.get('intro') or content,
            max_len=320,
        )

        next_version = 1
        if existing:
            next_version = existing.version + 1
            db.execute(
                update(LearningResource)
                .where(
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.resource_type == resource_type,
                    LearningResource.is_active.is_(True),
                    (LearningResource.user_id == user_id) | (LearningResource.user_id.is_(None)),
                )
                .values(is_active=False)
            )

        resource = LearningResource(
            user_id=user_id,
            topic_id=topic.id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
            version=next_version,
            is_active=True,
            title=structured_content.get('title') or f'{skill_node.name} {kind.title()}',
            summary=summary,
            content_json=structured_content,
            content=content,
            url='',
            relevance_reason='Generated to match learner progression, selected skill, and uploaded note context.',
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        source: ResourceSource = 'regenerated' if existing else 'generated'
        snapshot_after = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=user_id,
            focus_skill_id=skill_node.id,
        )
        self.course_memory_service.persist_snapshot(
            db,
            topic=topic,
            snapshot=snapshot_after,
            reason=f'generated_{kind}',
        )
        ledger_payload = topic.curriculum_ledger if isinstance(topic.curriculum_ledger, dict) else {}
        ledger_payload[f'latest_{kind}_research'] = self.course_research_service.to_ledger_records(
            research_insights,
            limit=6,
        )
        topic.curriculum_ledger = ledger_payload
        db.commit()
        db.refresh(resource)
        logger.info(
            'resource.generated topic_id=%s skill_id=%s kind=%s version=%s source=%s fallback=%s',
            topic.id,
            skill_node.id,
            kind,
            resource.version,
            source,
            used_fallback,
        )
        return resource, structured_content, source

    async def fetch_external_resources(
        self,
        db: Session,
        *,
        topic: Topic,
        skill_node: SkillNode,
        limit: int = 3,
    ) -> list[LearningResource]:
        search_results = await self.search_service.search(
            topic.name,
            skill_node.name,
            limit=max(6, limit * 2),
            source_policy='grounding',
        )
        if not search_results:
            return []

        result_payload = [
            {
                'title': item.title,
                'url': item.url,
                'kind': item.kind,
                'summary': item.summary,
            }
            for item in search_results
        ]

        system_prompt = (
            'You are ResourceAgent. Select the most relevant external resources for a learner and provide concise '
            'relevance reasons tied to the selected skill.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Skill: {skill_node.name}\n'
            f'Skill description: {skill_node.description}\n'
            f'Select up to {limit} resources from these candidates:\n{json.dumps(result_payload, indent=2)}'
        )

        reasoning = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=ExternalResourceReasoningPlan,
            temperature=0.2,
            max_tokens=1200,
        )

        candidate_map = {item.url: item for item in search_results}
        selected_urls: list[str] = []
        reasons_by_url: dict[str, str] = {}

        for item in reasoning.resources:
            if item.url not in candidate_map:
                continue
            if item.url in reasons_by_url:
                continue
            reasons_by_url[item.url] = item.relevance_reason
            selected_urls.append(item.url)
            if len(selected_urls) >= limit:
                break

        if not selected_urls:
            selected_urls = [item.url for item in search_results[:limit]]
            for url in selected_urls:
                reasons_by_url[url] = 'Relevant to the selected skill path and current learning objective.'

        created: list[LearningResource] = []
        for url in selected_urls:
            source = candidate_map[url]
            existing = db.scalar(
                select(LearningResource).where(
                    LearningResource.topic_id == topic.id,
                    LearningResource.skill_node_id == skill_node.id,
                    LearningResource.url == source.url,
                )
            )
            if existing:
                created.append(existing)
                continue

            resource = LearningResource(
                user_id=None,
                topic_id=topic.id,
                skill_node_id=skill_node.id,
                resource_type=ResourceType(source.kind),
                title=source.title,
                url=source.url,
                summary=source.summary,
                content_json=None,
                content='',
                relevance_reason=reasons_by_url.get(source.url, 'Relevant to current skill progression.'),
            )
            db.add(resource)
            db.flush()
            created.append(resource)

        db.commit()
        for item in created:
            db.refresh(item)

        logger.info('resource.external topic_id=%s skill_id=%s count=%s', topic.id, skill_node.id, len(created))
        return created
