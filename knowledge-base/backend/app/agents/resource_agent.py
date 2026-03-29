from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import LearningResource, ResourceType, SkillEdge, SkillNode, Topic, UserSkillState
from app.core.exceptions import ConfigurationError, ProviderError
from app.core.config import get_settings
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
    'wikipedia.org',
    'wikimedia.org',
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
    'painting',
    'diagram',
    'map',
    'illustration',
    'chart',
    'timeline',
    'figure',
    'satellite',
    'atlas',
)
_STRICT_MEDIA_SCORE_THRESHOLD = 0.28
_RELAXED_MEDIA_SCORE_THRESHOLD = 0.2
_BROAD_MEDIA_SCORE_THRESHOLD = 0.1
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
        self.settings = get_settings()

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
            '- Include at least one concrete example anchored to the node scope.\n'
            '- Include at least one misconception or failure mode and how to avoid it.\n'
            '- Avoid generic filler, broad motivational language, and repetitive transition phrases.\n'
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
        if kind not in {'lesson', 'deep_lesson'}:
            return []
        text_parts: list[str] = []
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
        if blob.count('example') == 0 and blob.count('for instance') == 0:
            issues.append('missing_specific_examples')
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
        if not any(token in section_blob for token in ('for example', 'consider', 'e.g.', 'for instance')):
            issues.append('missing_concrete_example')
        if not any(
            token in section_blob
            for token in ('common mistake', 'misconception', 'pitfall', 'avoid this', 'failure mode')
        ):
            issues.append('missing_misconception_handling')
        if not any(token in section_blob for token in ('because', 'therefore', 'whereas', 'however', 'trade-off')):
            issues.append('missing_reasoning_connectors')

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
                f'A concise introduction to {skill_node.name} for {learner_level} learners in {topic.name}.',
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
            ],
            'sections': [
                {
                    'heading': 'What this skill is for',
                    'content': _truncate_text_cleanly(
                        f'{skill_node.name} helps you make reliable progress inside {topic.name}. '
                        'Focus on one clear concept at a time before adding complexity.',
                        800,
                    ),
                },
                {
                    'heading': 'How to practice this node',
                    'content': _truncate_text_cleanly(
                        'Use short focused practice rounds. Run one attempt, review what happened, and repeat with '
                        'a single adjustment so progress is measurable.',
                        800,
                    ),
                },
            ],
            'takeaways': [
                f'You should be able to describe {skill_node.name} in plain language.',
                'Small, repeatable drills build faster mastery than broad unfocused practice.',
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
                f'These examples show practical, beginner-safe uses of {skill_node.name} in {topic.name}.',
                420,
            ),
            'examples': [
                {
                    'name': 'Baseline example',
                    'explanation': _truncate_text_cleanly(
                        f'Start with a minimal case where {skill_node.name} is applied once with clear inputs and outputs.',
                        500,
                    ),
                    'why_it_matters': _truncate_text_cleanly(
                        'This anchors the core concept before adding edge cases.',
                        280,
                    ),
                },
                {
                    'name': 'Common mistake and correction',
                    'explanation': _truncate_text_cleanly(
                        f'Show a frequent mistake in {skill_node.name}, then demonstrate the corrected approach.',
                        500,
                    ),
                    'why_it_matters': _truncate_text_cleanly(
                        'Seeing failure modes early improves retention and confidence.',
                        280,
                    ),
                },
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
                f'A deeper lesson on {skill_node.name} with historical context, technical detail, and structured study prompts '
                f'for {topic.name}.',
                420,
            ),
            'essential_questions': [
                f'What is the core historical or conceptual significance of {skill_node.name}?',
                f'How does {skill_node.name} influence later developments inside {topic.name}?',
            ],
            'sections': [
                {
                    'heading': 'Context and background',
                    'content': (
                        f'Start by situating {skill_node.name} in the broader timeline of {topic.name}. '
                        'Identify what came before it, which constraints shaped it, and what immediate problems it addressed. '
                        'Use this context to avoid memorizing isolated facts without understanding why they mattered.'
                    ),
                },
                {
                    'heading': 'Detailed analysis',
                    'content': (
                        f'Break {skill_node.name} into component ideas, methods, and trade-offs. '
                        'For each component, describe its purpose, strengths, and limitations with one concrete example. '
                        'Where possible, compare two interpretations and explain how evidence supports or challenges each one.'
                    ),
                },
                {
                    'heading': 'Implications and transfer',
                    'content': (
                        f'Conclude by connecting {skill_node.name} to downstream learning. '
                        'Highlight what a learner should now be able to explain, critique, and apply. '
                        'This turns the lesson into reusable understanding rather than a one-off reading exercise.'
                    ),
                },
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

    def _extract_media_keywords(self, *, topic: Topic, skill_node: SkillNode, deep_lesson: dict[str, Any]) -> list[str]:
        base_terms = [
            topic.name,
            skill_node.name,
            *(str(item) for item in deep_lesson.get('essential_questions', []) if str(item).strip()),
            *(str(item.get('heading')) for item in deep_lesson.get('sections', []) if isinstance(item, dict)),
            *(str(item.get('term')) for item in deep_lesson.get('key_terms', []) if isinstance(item, dict)),
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
            if len(keywords) >= 10:
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
            if len(parts) >= 4:
                break

        seed = ' '.join(parts).strip()
        # Keep search queries compact to avoid provider-side parse errors.
        return seed[:120]

    def _media_relevance_score(self, *, title: str, summary: str, url: str, keywords: list[str], skill_name: str) -> float:
        haystack = f'{title} {summary} {url}'.lower()
        if not haystack.strip():
            return 0.0

        matches = sum(1 for keyword in keywords if keyword in haystack)
        score = matches / max(1, len(keywords))
        if skill_name.lower() in haystack:
            score += 0.2
        if any(token in haystack for token in ('museum', 'archive', 'artwork', 'primary source', 'documentary', 'lecture')):
            score += 0.08
        if any(token in haystack for token in _VISUAL_MEDIA_HINTS):
            score += 0.08
        if any(token in haystack for token in ('history', 'geography', 'culture', 'politics', 'science', 'education')):
            score += 0.05
        return min(score, 1.0)

    def _is_trusted_media_candidate(self, *, domain: str, title: str, summary: str, kind: str) -> bool:
        if not domain:
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
            if kind != 'external_video':
                return False
            return any(hint in lowered_meta for hint in _TRUSTED_YOUTUBE_HINTS)

        return True

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
        if url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg')):
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
            'Quality constraints:\n'
            '- Avoid formulaic filler phrases and generic transitions.\n'
            '- Prefer concrete distinctions, trade-offs, and specific examples.\n'
            '- Do not repeat examples already used in the course memory unless clearly marked as remediation.'
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
            writing_issues = self._writing_slop_issues(structured_content, kind='deep_lesson')
            writing_issues.extend(
                self._repetition_issues(
                    kind='deep_lesson',
                    structured_content=structured_content,
                    memory=memory_snapshot,
                )
            )
            if writing_issues:
                refine_prompt = (
                    f'Topic: {topic.name}\n'
                    f'Skill: {skill_node.name}\n'
                    f'Technical depth: {technical_depth}\n'
                    f'Quality issues to fix: {", ".join(sorted(set(writing_issues)))}\n\n'
                    f'Course memory ledger:\n{memory_context}\n\n'
                    f'Deep lesson draft JSON:\n{json.dumps(structured_content, indent=2)}'
                )
                try:
                    refined_model = await self.llm_service.generate_structured(
                        system_prompt=(
                            'You are ResourceAgent. Rewrite this deep lesson to remove formulaic writing and '
                            'content repetition while keeping the same scope and factual grounding.'
                        ),
                        user_prompt=refine_prompt,
                        schema_model=DeepLessonPlan,
                        temperature=0.15,
                        max_tokens=2400,
                    )
                    structured_content = self._polish_structured_snippets(
                        kind='deep_lesson',
                        structured_content=refined_model.model_dump(),
                    )
                except ProviderError:
                    pass
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
            return structured_content, 'fallback'

    async def fetch_strict_supporting_media(
        self,
        *,
        topic: Topic,
        skill_node: SkillNode,
        deep_lesson: dict[str, Any],
        limit: int = 2,
    ) -> list[dict[str, str]]:
        keywords = self._extract_media_keywords(topic=topic, skill_node=skill_node, deep_lesson=deep_lesson)
        query_seed = self._compact_media_query_seed(topic=topic, skill_node=skill_node, keywords=keywords)
        query = f'{query_seed} map diagram photo documentary educational video'

        try:
            search_results = await self.search_service.search(
                topic.name,
                skill_node.name,
                query=query,
                limit=max(8, limit * 4),
                source_policy='strict_media',
            )
        except (ConfigurationError, ProviderError) as exc:
            logger.info(
                'resource.deep_lesson_media_skipped topic_id=%s skill_id=%s reason=%s',
                topic.id,
                skill_node.id,
                exc,
            )
            return []

        def rank_candidates(
            candidates: list[Any],
            *,
            threshold: float,
            require_visual_hint: bool,
            selected_urls: set[str],
            enforce_trusted_sources: bool,
            allow_article_fallback: bool,
            reason_text: str,
        ) -> list[tuple[float, dict[str, str]]]:
            ranked: list[tuple[float, dict[str, str]]] = []
            for candidate in candidates:
                if candidate.url in selected_urls:
                    continue

                domain = self._domain_for_url(candidate.url)
                if any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_SOCIAL_MEDIA_DOMAINS):
                    continue
                if any(domain == blocked or domain.endswith(f'.{blocked}') for blocked in _BLOCKED_STOCK_MEDIA_DOMAINS):
                    continue
                if enforce_trusted_sources:
                    if not self._is_trusted_media_candidate(
                        domain=domain,
                        title=candidate.title,
                        summary=candidate.summary,
                        kind=candidate.kind,
                    ):
                        continue

                lowered_meta = f'{candidate.title} {candidate.summary}'.lower()
                media_type = self._infer_media_type(
                    kind=candidate.kind,
                    url=candidate.url,
                    lowered_meta=lowered_meta,
                    allow_article_fallback=allow_article_fallback,
                )
                if media_type is None:
                    continue

                if require_visual_hint and media_type == 'image':
                    if not any(token in lowered_meta for token in _VISUAL_MEDIA_HINTS):
                        continue

                score = self._media_relevance_score(
                    title=candidate.title,
                    summary=candidate.summary,
                    url=candidate.url,
                    keywords=keywords,
                    skill_name=skill_node.name,
                )
                if score < threshold:
                    continue

                selected_urls.add(candidate.url)
                ranked.append(
                    (
                        score,
                        {
                            'title': candidate.title,
                            'url': candidate.url,
                            'media_type': media_type,
                            'source_domain': domain,
                            'relevance_reason': reason_text,
                        },
                    )
                )
            return ranked

        selected_urls: set[str] = set()
        scored = rank_candidates(
            search_results,
            threshold=_STRICT_MEDIA_SCORE_THRESHOLD,
            require_visual_hint=False,
            selected_urls=selected_urls,
            enforce_trusted_sources=True,
            allow_article_fallback=True,
            reason_text='Selected because it directly supports this deep-dive node and comes from a trusted source.',
        )
        strict_count = len(scored)

        if len(scored) < limit:
            fallback_query = (
                f'{query_seed} map diagram archival image educational video '
                'site:wikipedia.org site:wikimedia.org site:britannica.com site:khanacademy.org'
            )[:220]
            try:
                fallback_results = await self.search_service.search(
                    topic.name,
                    skill_node.name,
                    query=fallback_query,
                    limit=max(8, limit * 4),
                    source_policy='strict_media',
                )
            except (ConfigurationError, ProviderError):
                fallback_results = []

            scored.extend(
                rank_candidates(
                    fallback_results,
                    threshold=_RELAXED_MEDIA_SCORE_THRESHOLD,
                    require_visual_hint=True,
                    selected_urls=selected_urls,
                    enforce_trusted_sources=True,
                    allow_article_fallback=True,
                    reason_text='Selected as a trusted supplemental reference that is likely helpful for this deep-dive topic.',
                )
            )
        fallback_count = max(0, len(scored) - strict_count)
        broad_count = 0
        if len(scored) < limit and len(scored) == 0:
            broad_results = search_results
            scored.extend(
                rank_candidates(
                    broad_results,
                    threshold=_BROAD_MEDIA_SCORE_THRESHOLD,
                    require_visual_hint=False,
                    selected_urls=selected_urls,
                    enforce_trusted_sources=False,
                    allow_article_fallback=True,
                    reason_text='Selected from non-social public sources as a high-relevance fallback for this lesson.',
                )
            )
            broad_count = max(0, len(scored) - strict_count - fallback_count)
        emergency_count = 0

        logger.info(
            'resource.deep_lesson_media_selected topic_id=%s skill_id=%s selected=%s strict=%s fallback=%s broad=%s emergency=%s requested_limit=%s environment=%s',
            topic.id,
            skill_node.id,
            len(scored),
            strict_count,
            fallback_count,
            broad_count,
            emergency_count,
            limit,
            self.settings.environment,
        )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[:limit]]

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
    ) -> tuple[LearningResource, dict[str, Any] | None, ResourceSource]:
        resource_type = self._resource_type_for_kind(kind)
        existing = self._get_active_generated_resource(
            db,
            user_id=user_id,
            skill_node_id=skill_node.id,
            resource_type=resource_type,
        )

        if existing and not regenerate:
            structured = self._extract_structured_content(existing)
            logger.info(
                'resource.loaded_from_store topic_id=%s skill_id=%s kind=%s version=%s',
                topic.id,
                skill_node.id,
                kind,
                existing.version,
            )
            return existing, structured, 'stored'

        technical_depth = self._technical_depth(topic)
        lesson_targets = technical_depth_lesson_targets(normalize_technical_depth(technical_depth))

        prompts = {
            'lesson': (
                LessonPlan,
                (
                    'Create a high-quality lesson that is conceptually rich, specific, and pedagogically structured. '
                    'Prioritize explanation quality, precision, and node-specific examples over generic summary language.'
                ),
                int(lesson_targets['max_tokens']),
            ),
            'examples': (
                ExamplesPlan,
                (
                    'Create concrete examples that build from simple to challenging and explain the reasoning. '
                    f'Adjust example rigor to this technical depth: {technical_depth_prompt_guidance(technical_depth)} '
                    'while keeping intro concise (roughly 2-3 sentences).'
                ),
                1000,
            ),
            'exercises': (
                ExercisesPlan,
                (
                    'Create exercises for short practice sessions with clear expected outcomes. '
                    f'Adjust cognitive complexity to this technical depth: {technical_depth_prompt_guidance(technical_depth)} '
                    'while keeping intro concise (roughly 2-3 sentences).'
                ),
                1100,
            ),
        }
        schema_model, instruction, max_tokens = prompts[kind]

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
            f'Editorial spine excerpt (preserve coherence):\n{editorial_spine_context}\n\n'
            f'Course memory ledger:\n{memory_context}\n\n'
            f'Stable completed coverage guidance:\n{stable_coverage_context}\n\n'
            f'Retrieved learner notes:\n{notes_context or "No notes available"}\n\n'
            f'Curated web grounding references (optional; use only if directly relevant):\n'
            f'{web_grounding_context or "None"}\n\n'
            f'Alignment rules:\n{alignment_rules}\n'
            f'Formatting constraints:\n{field_length_rules}\n'
            f'Instruction: {instruction}\n\n'
            'If web references are present, use them selectively for specific examples and context. '
            'Do not force web facts when relevance is weak. Never produce a link dump.\n'
            'Anti-slop rules:\n'
            '- Avoid filler transitions, motivational fluff, and generic consulting language.\n'
            '- Add concrete distinctions and context-specific details.\n'
            '- Do not repeat examples already used unless remediation is explicitly required.'
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
        if kind == 'lesson' and not used_fallback:
            _is_high_quality, quality_issues = self._lesson_quality_signals(
                structured_content,
                technical_depth=technical_depth,
            )
            quality_issues.extend(self._writing_slop_issues(structured_content, kind='lesson'))
            quality_issues.extend(
                self._repetition_issues(
                    kind='lesson',
                    structured_content=structured_content,
                    memory=memory_snapshot,
                )
            )
            if quality_issues:
                logger.info(
                    'resource.lesson_quality_refine topic_id=%s skill_id=%s technical_depth=%s issues=%s',
                    topic.id,
                    skill_node.id,
                    technical_depth,
                    quality_issues,
                )
                refine_prompt = (
                    f'Topic: {topic.name}\n'
                    f'Skill: {skill_node.name}\n'
                    f'Skill description: {skill_node.description}\n'
                    f'Technical depth: {technical_depth}\n'
                    f'Quality issues to fix: {", ".join(quality_issues)}\n\n'
                    'Refine this draft lesson into a higher-quality teaching artifact. '
                    'Do not change scope or invent unsupported claims. Strengthen conceptual depth, examples, and nuance.\n\n'
                    f'Draft lesson JSON:\n{json.dumps(structured_content, indent=2)}'
                )
                try:
                    refined_model = await self.llm_service.generate_structured(
                        system_prompt=(
                            'You are ResourceAgent. Improve lesson quality while staying accurate, structured, and '
                            'strictly scoped to the same skill node.'
                        ),
                        user_prompt=refine_prompt,
                        schema_model=LessonPlan,
                        temperature=0.2,
                        max_tokens=max_tokens,
                    )
                    structured_content = refined_model.model_dump()
                except ProviderError as exc:
                    logger.warning(
                        'resource.lesson_quality_refine_failed topic_id=%s skill_id=%s error=%s',
                        topic.id,
                        skill_node.id,
                        exc,
                    )
        elif kind == 'examples' and not used_fallback:
            quality_issues = self._repetition_issues(
                kind='examples',
                structured_content=structured_content,
                memory=memory_snapshot,
            )
            if quality_issues:
                refine_prompt = (
                    f'Topic: {topic.name}\n'
                    f'Skill: {skill_node.name}\n'
                    f'Issues: {", ".join(sorted(set(quality_issues)))}\n\n'
                    f'Course memory ledger:\n{memory_context}\n\n'
                    f'Current examples JSON:\n{json.dumps(structured_content, indent=2)}'
                )
                try:
                    refined_model = await self.llm_service.generate_structured(
                        system_prompt=(
                            'You are ResourceAgent. Rewrite examples to remove repetition and improve specificity '
                            'while keeping scope tied to the same skill.'
                        ),
                        user_prompt=refine_prompt,
                        schema_model=ExamplesPlan,
                        temperature=0.2,
                        max_tokens=max_tokens,
                    )
                    structured_content = refined_model.model_dump()
                except ProviderError:
                    pass
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
