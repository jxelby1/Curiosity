from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.branching import (
    CANONICAL_BRANCH_PURPOSES,
    branch_purpose_label,
    branch_purpose_summary,
    normalize_branch_purpose,
)
from app.core.course_preferences import (
    depth_node_bounds,
    level_prompt_guidance,
    normalize_course_depth,
    normalize_starting_skill_level,
    normalize_technical_depth,
    technical_depth_prompt_guidance,
)
from app.db.models import (
    BranchSuggestion,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    UserSkillState,
)
from app.schemas.llm import (
    BranchSuggestionPlan,
    DeepDiveBranchPlan,
    SkillGraphPlan,
    SkillNodeTitleRewritePlan,
    SkillPlanNode,
)
from app.services.llm import LLMService
from app.services.course_memory import CourseMemoryService
from app.services.course_research import CourseResearchService
from app.services.search import ExternalSearchService


logger = logging.getLogger(__name__)
MAX_PREREQUISITES_PER_NODE = 2
MAX_PENDING_BRANCH_SUGGESTIONS = 1
DEFAULT_OPTIONAL_BRANCH_NODE_COUNT = 1
_BUSINESS_TOPIC_HINTS = (
    'business',
    'marketing',
    'sales',
    'startup',
    'strategy',
    'operations',
    'finance',
    'management',
    'product',
    'go-to-market',
    'growth',
    'consulting',
    'mba',
)
_GENERIC_JARGON_TERMS = (
    'optimization',
    'optimisation',
    'framework',
    'synergy',
    'synergies',
    'best practice',
    'methodology',
    'techniques',
    'strategy',
    'strategies',
    'leverage',
    'value chain',
    'stakeholder',
    'roadmap',
)
_ABSTRACT_TITLE_PREFIXES = (
    'optimization',
    'optimisation',
    'strategic',
    'framework',
    'leveraging',
    'maximizing',
    'maximising',
    'advanced techniques',
)
_TITLE_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'from',
    'into',
    'your',
    'this',
    'that',
    'about',
    'using',
    'guide',
    'basics',
    'introduction',
    'overview',
}
_CONTENT_OVERLAP_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'from',
    'into',
    'that',
    'this',
    'about',
    'your',
    'node',
    'topic',
    'learning',
    'skill',
    'course',
    'lesson',
    'core',
    'path',
    'basics',
    'overview',
    'introduction',
}
_GENERIC_BRANCH_FOCUSES = {
    'more practice',
    'advanced practice',
    'deeper dive',
    'deep dive',
    'extra practice',
    'further study',
    'optional branch',
    'new branch',
}
_CORE_ROLE_FALLBACK_ORDER = (
    'foundational_concept',
    'conceptual_bridge',
    'practical_application',
    'comparison_contrast',
    'case_deepening',
    'assessment_preparation',
    'synthesis_review',
)


@dataclass
class BranchCurriculumState:
    taught_skill_lines: list[str] = field(default_factory=list)
    taught_concepts: list[str] = field(default_factory=list)
    used_examples: list[str] = field(default_factory=list)
    assessed_concepts: list[str] = field(default_factory=list)
    future_core_lines: list[str] = field(default_factory=list)
    existing_optional_lines: list[str] = field(default_factory=list)
    accepted_branch_focuses: list[str] = field(default_factory=list)
    pending_branch_focuses: list[str] = field(default_factory=list)
    weak_areas: list[str] = field(default_factory=list)
    strong_areas: list[str] = field(default_factory=list)


class SkillGraphAgent:
    def __init__(
        self,
        llm_service: LLMService,
        research_service: CourseResearchService | None = None,
        course_memory_service: CourseMemoryService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.course_memory_service = course_memory_service or CourseMemoryService()
        self.research_service = research_service or CourseResearchService(ExternalSearchService())

    def _learner_level(self, state: UserSkillState | None) -> str:
        if not state:
            return 'beginner'
        if state.progress_state == 'verified' or state.mastery >= 0.75:
            return 'advanced'
        if state.progress_state in ('learning', 'completed') or state.mastery >= 0.35:
            return 'intermediate'
        return 'beginner'

    @staticmethod
    def _normalize_branch_purpose(raw_purpose: str | None) -> str:
        return normalize_branch_purpose(raw_purpose)

    @staticmethod
    def _purpose_allows_revisit(purpose: str) -> bool:
        # Technique drills may intentionally revisit prior ideas in a narrower way.
        return purpose == 'style_technique_practice'

    @staticmethod
    def _text_tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or '').lower())
            if token not in _CONTENT_OVERLAP_STOPWORDS
        }

    @classmethod
    def _token_overlap_ratio(cls, left: str, right: str) -> float:
        left_tokens = cls._text_tokens(left)
        right_tokens = cls._text_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        return intersection / max(1, min(len(left_tokens), len(right_tokens)))

    @staticmethod
    def _text_similarity_ratio(left: str, right: str) -> float:
        left_clean = ' '.join((left or '').lower().split())
        right_clean = ' '.join((right or '').lower().split())
        if not left_clean or not right_clean:
            return 0.0
        return SequenceMatcher(None, left_clean, right_clean).ratio()

    @staticmethod
    def _dedupe_keep_order(items: list[str], *, limit: int) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = ' '.join((item or '').split()).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
            if len(deduped) >= limit:
                break
        return deduped

    @staticmethod
    def _trim_text(value: str | None, *, limit: int) -> str:
        text = ' '.join((value or '').split()).strip()
        if len(text) <= limit:
            return text
        trimmed = text[: limit - 1].rstrip(' ,;:-')
        if not trimmed:
            trimmed = text[: limit - 1].rstrip()
        return f'{trimmed}…'

    def _default_branch_focus(
        self,
        *,
        parent_node: SkillNode,
        purpose: str,
        state: BranchCurriculumState,
        requested_focus: str | None = None,
    ) -> str:
        requested = self._trim_text(requested_focus, limit=180)
        if requested and requested.lower() not in _GENERIC_BRANCH_FOCUSES:
            return requested

        if purpose == 'style_technique_practice':
            focus = state.weak_areas[0] if state.weak_areas else f'{parent_node.name} technique'
        elif purpose == 'creative_response':
            focus = state.strong_areas[0] if state.strong_areas else f'{parent_node.name} response study'
        elif purpose == 'study_exemplar':
            focus = requested or f'{parent_node.name} through one concrete exemplar'
        elif purpose == 'compare_contrast':
            focus = requested or f'{parent_node.name} across two contrasting examples'
        elif purpose == 'context_influence':
            focus = requested or f'{parent_node.name} in surrounding context'
        elif purpose == 'follow_lineage':
            focus = requested or f'lineage around {parent_node.name}'
        else:
            focus = requested or f'a deeper read of {parent_node.name}'
        return self._trim_text(focus, limit=180)

    def _format_branch_suggestion_title(
        self,
        *,
        topic: Topic,
        parent_node: SkillNode,
        purpose: str,
        focus: str,
        proposed_title: str | None,
    ) -> str:
        cleaned = self._trim_text(proposed_title, limit=160)
        issues = self._title_quality_issues(
            topic_name=topic.name,
            topic_description=topic.description or '',
            topic_goal=topic.goal or '',
            title=cleaned,
        )
        label = branch_purpose_label(purpose)
        focus_label = self._trim_text(focus, limit=120) or parent_node.name
        if not cleaned or issues:
            return self._trim_text(f'{label}: {focus_label}', limit=160)
        if cleaned.lower().startswith(label.lower()):
            return cleaned
        return self._trim_text(f'{label}: {focus_label}', limit=160)

    def _compose_branch_suggestion_rationale(
        self,
        *,
        parent_node: SkillNode,
        purpose: str,
        focus: str,
        state: BranchCurriculumState,
        trigger_event: str,
    ) -> str:
        if purpose == 'style_technique_practice' and state.weak_areas:
            why_now = f'recent work exposed a narrow weakness around {state.weak_areas[0]}'
        elif purpose == 'creative_response' and state.strong_areas:
            why_now = f'recent progress suggests you are ready to turn understanding into authorship around {state.strong_areas[0]}'
        elif trigger_event == 'completion':
            why_now = f'you have enough footing in {parent_node.name} to open one adjacent move without crowding the main path'
        elif trigger_event == 'interest':
            why_now = f'curiosity is pointing toward a distinct side path connected to {parent_node.name}'
        elif state.future_core_lines:
            why_now = 'there is room for one distinct side path without stepping on the upcoming core sequence'
        else:
            why_now = f'this adds a distinct way to study {parent_node.name} right now without replacing the main path'

        move = branch_purpose_summary(purpose)
        return self._trim_text(
            f'Why now: {why_now}. Study move: {move} Focus it on {focus}, and keep the core path primary.',
            limit=320,
        )

    def _build_curriculum_state(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
    ) -> BranchCurriculumState:
        snapshot = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=user_id,
            focus_skill_id=parent_node.id,
        )

        suggestions = db.scalars(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
                BranchSuggestion.parent_skill_id == parent_node.id,
            )
        ).all()
        accepted_branch_focuses = [item.focus for item in suggestions if item.status == 'accepted']
        pending_branch_focuses = [item.focus for item in suggestions if item.status == 'pending']

        return BranchCurriculumState(
            taught_skill_lines=self._dedupe_keep_order(snapshot.taught_node_lines + [f'{parent_node.name} — {parent_node.description}'], limit=14),
            taught_concepts=self._dedupe_keep_order(snapshot.taught_concepts, limit=18),
            used_examples=self._dedupe_keep_order(snapshot.used_examples, limit=10),
            assessed_concepts=self._dedupe_keep_order(snapshot.assessed_strengths + snapshot.assessed_weaknesses, limit=12),
            future_core_lines=self._dedupe_keep_order(snapshot.future_core_lines, limit=12),
            existing_optional_lines=self._dedupe_keep_order(snapshot.existing_branch_lines, limit=12),
            accepted_branch_focuses=self._dedupe_keep_order(accepted_branch_focuses, limit=8),
            pending_branch_focuses=self._dedupe_keep_order(pending_branch_focuses, limit=4),
            weak_areas=self._dedupe_keep_order(snapshot.assessed_weaknesses, limit=6),
            strong_areas=self._dedupe_keep_order(snapshot.assessed_strengths, limit=6),
        )

    def _curriculum_context_text(self, state: BranchCurriculumState) -> str:
        def _render(label: str, items: list[str], max_items: int = 6) -> str:
            if not items:
                return f'{label}: none'
            preview = '\n'.join(f'  - {item}' for item in items[:max_items])
            return f'{label}:\n{preview}'

        return '\n\n'.join(
            [
                _render('Already taught nodes', state.taught_skill_lines),
                _render('Taught concepts and terminology', state.taught_concepts),
                _render('Examples already used', state.used_examples),
                _render('Assessment strengths/weaknesses', state.assessed_concepts),
                _render('Planned future core nodes', state.future_core_lines),
                _render('Existing optional branches under this parent', state.existing_optional_lines),
                _render('Previously accepted branch focuses', state.accepted_branch_focuses),
                _render('Pending branch focuses', state.pending_branch_focuses, max_items=3),
                _render('Known weak areas', state.weak_areas, max_items=4),
                _render('Known strong areas', state.strong_areas, max_items=4),
            ]
        )

    def _is_redundant_branch_candidate(
        self,
        *,
        node_name: str,
        node_description: str,
        parent_node: SkillNode,
        purpose: str,
        state: BranchCurriculumState,
    ) -> bool:
        candidate = f'{node_name} {node_description}'.strip()
        if not candidate:
            return True

        title_issues = self._title_quality_issues(
            topic_name=parent_node.name,
            topic_description=parent_node.description or '',
            topic_goal='',
            title=node_name,
        )
        if 'empty' in title_issues or 'too_short' in title_issues:
            return True

        compare_sets: list[str] = []
        compare_sets.extend(state.existing_optional_lines)
        compare_sets.extend(state.future_core_lines)
        if not self._purpose_allows_revisit(purpose):
            compare_sets.extend(state.taught_skill_lines)
            compare_sets.extend(state.taught_concepts[:10])
            compare_sets.extend(state.used_examples[:8])

        for baseline in compare_sets:
            if self._text_similarity_ratio(candidate, baseline) >= 0.84:
                return True
            if self._token_overlap_ratio(candidate, baseline) >= 0.76:
                return True

        # Most branch moves should progress beyond the parent framing.
        if not self._purpose_allows_revisit(purpose):
            parent_signature = f'{parent_node.name} {parent_node.description}'
            if self._text_similarity_ratio(candidate, parent_signature) >= 0.84:
                return True
            if self._token_overlap_ratio(candidate, parent_signature) >= 0.8:
                return True

        return False

    def _is_redundant_branch_suggestion_candidate(
        self,
        *,
        title: str,
        focus: str,
        purpose: str,
        state: BranchCurriculumState,
    ) -> bool:
        candidate = f'{title} {focus}'.strip()
        compare_lines = (
            state.existing_optional_lines
            + state.future_core_lines
            + state.accepted_branch_focuses
            + state.pending_branch_focuses
        )
        if not self._purpose_allows_revisit(purpose):
            compare_lines += state.taught_skill_lines + state.taught_concepts
        focus_clean = ' '.join((focus or '').lower().split())
        title_clean = ' '.join((title or '').lower().split())
        for baseline in compare_lines:
            baseline_clean = ' '.join((baseline or '').lower().split())
            if focus_clean and focus_clean in baseline_clean:
                return True
            if title_clean and title_clean in baseline_clean:
                return True
            if self._text_similarity_ratio(candidate, baseline) >= 0.84:
                return True
            if self._token_overlap_ratio(candidate, baseline) >= 0.78:
                return True
        return False

    def _fallback_branch_node(
        self,
        *,
        topic: Topic,
        parent_node: SkillNode,
        focus: str | None,
        purpose: str,
        state: BranchCurriculumState,
    ) -> SkillPlanNode:
        focus_text = ' '.join((focus or '').split()).strip()
        weak_hint = state.weak_areas[0] if state.weak_areas else parent_node.name
        strong_hint = state.strong_areas[0] if state.strong_areas else parent_node.name

        if purpose == 'style_technique_practice':
            focus_label = focus_text or weak_hint
            name = f'Style and technique practice: {focus_label}'
            description = (
                f'Use guided drills to sharpen execution in {focus_label} while staying connected to {parent_node.name}. '
                'Revisit only the most relevant techniques and keep the practice targeted.'
            )
            role = 'remediation'
        elif purpose == 'compare_contrast':
            focus_label = focus_text or parent_node.name
            name = f'Compare and contrast: {focus_label}'
            description = (
                f'Place two works, interpretations, or methods side by side around {focus_label} to clarify differences in form, '
                'intent, and effect.'
            )
            role = 'comparison_contrast'
        elif purpose == 'context_influence':
            focus_label = focus_text or parent_node.name
            name = f'Context and influence: {focus_label}'
            description = (
                f'Study the cultural context around {focus_label}, including upstream influences and downstream impact, '
                f'anchored to {parent_node.name}.'
            )
            role = 'conceptual_bridge'
        elif purpose == 'study_exemplar':
            focus_label = focus_text or strong_hint
            name = f'Exemplar study: {focus_label}'
            description = (
                f'Use one concrete exemplar in {focus_label} to deepen understanding of {parent_node.name}, with close reading, '
                'structural breakdown, and interpretive reasoning.'
            )
            role = 'case_deepening'
        elif purpose == 'creative_response':
            focus_label = focus_text or parent_node.name
            name = f'Creative response: {focus_label}'
            description = (
                f'Create a short response piece inspired by {focus_label} to test your interpretation, taste, and decision-making '
                'in practice.'
            )
            role = 'practical_application'
        elif purpose == 'follow_lineage':
            focus_label = focus_text or parent_node.name
            name = f'Follow the lineage: {focus_label}'
            description = (
                f'Trace a clear lineage from earlier precedents into {focus_label}, then map how the line evolves in later works '
                'or movements.'
            )
            role = 'synthesis_review'
        else:
            focus_label = focus_text or parent_node.name
            name = f'Deepen theme: {focus_label}'
            description = (
                f'Extend a key idea from {parent_node.name} into {focus_label} with tighter analysis and richer interpretation, '
                'without duplicating upcoming core nodes.'
            )
            role = 'enrichment'

        harder_purposes = {'study_exemplar', 'creative_response', 'follow_lineage'}

        return SkillPlanNode(
            key='branch_focus_1',
            name=name[:180],
            description=description[:600],
            instructional_role=role,  # type: ignore[arg-type]
            difficulty=min(5, max(1, parent_node.difficulty + (1 if purpose in harder_purposes else 0))),
            prerequisites=['parent'],
        )

    @staticmethod
    def _limit_core_prerequisites(
        current_key: str,
        keys: list[str],
        key_position: dict[str, int],
    ) -> list[str]:
        unique: list[str] = []
        for key in keys:
            normalized = key.strip().lower()
            if (
                not normalized
                or normalized == current_key
                or normalized not in key_position
                or key_position[normalized] >= key_position[current_key]
                or normalized in unique
            ):
                continue
            unique.append(normalized)
        unique.sort(key=lambda item: key_position[item], reverse=True)
        return unique[:MAX_PREREQUISITES_PER_NODE]

    @staticmethod
    def _limit_branch_prerequisites(
        current_key: str,
        keys: list[str],
        key_position: dict[str, int],
    ) -> list[str]:
        wants_parent = any(item.strip().lower() == 'parent' for item in keys)
        siblings: list[str] = []
        for key in keys:
            normalized = key.strip().lower()
            if (
                normalized in ('', 'parent', current_key)
                or normalized not in key_position
                or key_position[normalized] >= key_position[current_key]
                or normalized in siblings
            ):
                continue
            siblings.append(normalized)
        siblings.sort(key=lambda item: key_position[item], reverse=True)

        selected: list[str] = []
        if wants_parent:
            selected.append('parent')
        for sibling in siblings:
            if len(selected) >= MAX_PREREQUISITES_PER_NODE:
                break
            selected.append(sibling)
        return selected[:MAX_PREREQUISITES_PER_NODE]

    @staticmethod
    def _build_progressive_branch_prereq_map(
        nodes: list[SkillPlanNode],
    ) -> dict[str, list[str]]:
        """
        Ensure every generated deep-dive branch reads like a real sub-path:
        first node anchors to parent, subsequent nodes progress downward by
        inheriting a prerequisite from the previous branch node.
        """
        if not nodes:
            return {}

        key_position = {node.key: idx for idx, node in enumerate(nodes)}
        prereq_map: dict[str, list[str]] = {}

        for index, node in enumerate(nodes):
            limited = SkillGraphAgent._limit_branch_prerequisites(
                current_key=node.key,
                keys=node.prerequisites,
                key_position=key_position,
            )
            sibling_prereqs = [key for key in limited if key != 'parent']
            wants_parent = 'parent' in limited

            if index == 0:
                prereq_map[node.key] = ['parent']
                continue

            previous_key = nodes[index - 1].key
            next_prereqs: list[str] = [previous_key]

            if wants_parent and len(next_prereqs) < MAX_PREREQUISITES_PER_NODE:
                next_prereqs.append('parent')

            for candidate in sibling_prereqs:
                if candidate == previous_key or candidate in next_prereqs:
                    continue
                if len(next_prereqs) >= MAX_PREREQUISITES_PER_NODE:
                    break
                next_prereqs.append(candidate)

            prereq_map[node.key] = next_prereqs[:MAX_PREREQUISITES_PER_NODE]

        return prereq_map

    @staticmethod
    def _resolve_effective_branch_size(*, requested_size: int, branch_purpose: str) -> int:
        # Optional branch creation is intentionally lightweight for now.
        # Keep exactly one immediately available node regardless of purpose.
        _ = requested_size, branch_purpose
        return DEFAULT_OPTIONAL_BRANCH_NODE_COUNT

    @staticmethod
    def _topic_anchor_tokens(topic_text: str) -> set[str]:
        tokens = {
            item
            for item in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", topic_text.lower())
            if item not in _TITLE_STOPWORDS
        }
        return tokens

    @staticmethod
    def _is_business_topic(*, topic_name: str, topic_description: str, topic_goal: str) -> bool:
        haystack = f'{topic_name} {topic_description} {topic_goal}'.lower()
        return any(token in haystack for token in _BUSINESS_TOPIC_HINTS)

    @classmethod
    def _title_quality_issues(
        cls,
        *,
        topic_name: str,
        topic_description: str,
        topic_goal: str,
        title: str,
    ) -> list[str]:
        cleaned = ' '.join((title or '').split()).strip()
        lowered = cleaned.lower()
        if not cleaned:
            return ['empty']

        issues: list[str] = []
        words = lowered.split()
        if len(words) < 2:
            issues.append('too_short')
        if len(cleaned) > 110:
            issues.append('too_long')
        if any(lowered.startswith(prefix) for prefix in _ABSTRACT_TITLE_PREFIXES):
            issues.append('abstract_prefix')

        has_jargon = any(term in lowered for term in _GENERIC_JARGON_TERMS)
        business_topic = cls._is_business_topic(
            topic_name=topic_name,
            topic_description=topic_description,
            topic_goal=topic_goal,
        )
        anchor_tokens = cls._topic_anchor_tokens(f'{topic_name} {topic_description}')
        has_topic_anchor = any(token in lowered for token in anchor_tokens)

        if has_jargon and (not business_topic or not has_topic_anchor):
            issues.append('generic_jargon')

        if not has_topic_anchor and any(token in lowered for token in ('process', 'approach', 'method', 'techniques')):
            issues.append('underspecified')

        return issues

    @staticmethod
    def _fallback_specific_title(*, topic_name: str, node_description: str, default_title: str) -> str:
        sentence = (node_description or '').split('.')[0].strip()
        candidate = ' '.join(sentence.split()[:9]).strip(' -:')
        if len(candidate) >= 8:
            return candidate[0].upper() + candidate[1:]
        base = ' '.join(default_title.split()[:7]).strip()
        if base:
            return base
        return f'{topic_name} focus area'

    @staticmethod
    def _normalize_instructional_role(raw_role: str | None, *, position: int) -> str:
        normalized = (raw_role or '').strip().lower().replace(' ', '_').replace('-', '_')
        alias = {
            'foundation': 'foundational_concept',
            'foundational': 'foundational_concept',
            'bridge': 'conceptual_bridge',
            'application': 'practical_application',
            'case_study': 'case_deepening',
            'comparison': 'comparison_contrast',
            'assessment_prep': 'assessment_preparation',
            'review': 'synthesis_review',
            'synthesis': 'synthesis_review',
            'remedial': 'remediation',
            'exploration': 'enrichment',
            'deepen_theme': 'enrichment',
            'compare_contrast': 'comparison_contrast',
            'context_influence': 'conceptual_bridge',
            'study_exemplar': 'case_deepening',
            'creative_response': 'practical_application',
            'style_technique_practice': 'remediation',
            'follow_lineage': 'synthesis_review',
        }
        candidate = alias.get(normalized, normalized)
        if candidate in _CORE_ROLE_FALLBACK_ORDER or candidate in {'remediation', 'enrichment', 'specialization'}:
            return candidate
        return _CORE_ROLE_FALLBACK_ORDER[position % len(_CORE_ROLE_FALLBACK_ORDER)]

    def _is_core_node_redundant(
        self,
        *,
        node: SkillPlanNode,
        accepted_nodes: list[SkillPlanNode],
        future_lines: list[str],
    ) -> bool:
        candidate = f'{node.name} {node.description}'
        for accepted in accepted_nodes:
            baseline = f'{accepted.name} {accepted.description}'
            if (
                node.instructional_role == accepted.instructional_role
                and self._token_overlap_ratio(candidate, baseline) >= 0.66
            ):
                return True
            if self._text_similarity_ratio(candidate, baseline) >= 0.86:
                return True
            if self._token_overlap_ratio(candidate, baseline) >= 0.8:
                return True
        for line in future_lines:
            if self._text_similarity_ratio(candidate, line) >= 0.88:
                return True
        return False

    def _coerce_core_roles(self, nodes: list[SkillPlanNode]) -> list[SkillPlanNode]:
        coerced: list[SkillPlanNode] = []
        used_roles: list[str] = []
        for index, node in enumerate(nodes):
            role = self._normalize_instructional_role(node.instructional_role, position=index)
            if index > 0 and role == used_roles[-1]:
                role = _CORE_ROLE_FALLBACK_ORDER[index % len(_CORE_ROLE_FALLBACK_ORDER)]
            used_roles.append(role)
            coerced.append(
                SkillPlanNode(
                    key=node.key,
                    name=node.name,
                    description=node.description,
                    instructional_role=role,  # type: ignore[arg-type]
                    difficulty=node.difficulty,
                    prerequisites=node.prerequisites,
                )
            )
        return coerced

    async def _improve_node_titles(
        self,
        *,
        topic: Topic,
        nodes: list[SkillPlanNode],
        parent_node_name: str | None = None,
    ) -> list[SkillPlanNode]:
        issues_by_key: dict[str, list[str]] = {}
        for node in nodes:
            issues = self._title_quality_issues(
                topic_name=topic.name,
                topic_description=topic.description or '',
                topic_goal=topic.goal or '',
                title=node.name,
            )
            if issues:
                issues_by_key[node.key] = issues

        if not issues_by_key:
            return nodes

        payload_lines = []
        for node in nodes:
            payload_lines.append(
                f'- key={node.key}; title={node.name}; description={node.description}; '
                f'issues={",".join(issues_by_key.get(node.key, [])) or "ok"}'
            )
        system_prompt = (
            'You rewrite learning node titles to sound natural, specific, and domain-appropriate. '
            'Avoid generic consulting/business jargon unless the topic is explicitly business-focused.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Description: {topic.description or "No description"}\n'
            f'Goal: {topic.goal or "No goal"}\n'
            f'Parent node context: {parent_node_name or "core path"}\n\n'
            'Rewrite only the low-quality titles while preserving each key.\n'
            'Title rules:\n'
            '- Concrete and specific, not abstract.\n'
            '- Natural human phrasing.\n'
            '- Avoid words like optimization/framework/strategy/techniques unless topic truly requires them.\n'
            '- Keep title length 3-80 chars.\n'
            '- Keep scope aligned to description.\n\n'
            f'Nodes:\n' + '\n'.join(payload_lines)
        )

        try:
            rewrite = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=SkillNodeTitleRewritePlan,
                temperature=0.1,
                max_tokens=900,
            )
            rewrite_map = {item.key: item.name.strip() for item in rewrite.nodes}
        except Exception as exc:  # noqa: BLE001
            logger.warning('skill_graph.title_rewrite_failed topic_id=%s error=%s', topic.id, exc)
            rewrite_map = {}

        improved: list[SkillPlanNode] = []
        for node in nodes:
            candidate = rewrite_map.get(node.key, node.name).strip()
            quality_issues = self._title_quality_issues(
                topic_name=topic.name,
                topic_description=topic.description or '',
                topic_goal=topic.goal or '',
                title=candidate,
            )
            if quality_issues:
                candidate = self._fallback_specific_title(
                    topic_name=topic.name,
                    node_description=node.description,
                    default_title=node.name,
                )

            improved.append(
                SkillPlanNode(
                    key=node.key,
                    name=' '.join(candidate.split()),
                    description=node.description,
                    instructional_role=node.instructional_role,
                    difficulty=node.difficulty,
                    prerequisites=node.prerequisites,
                )
            )

        return improved

    async def create_skill_tree(self, db: Session, topic: Topic) -> list[SkillNode]:
        course_depth = normalize_course_depth(topic.course_depth)
        starting_level = normalize_starting_skill_level(topic.starting_skill_level)
        technical_depth = normalize_technical_depth(topic.technical_depth)
        min_nodes, max_nodes = depth_node_bounds(course_depth)
        level_guidance = level_prompt_guidance(starting_level)
        technical_guidance = technical_depth_prompt_guidance(technical_depth)
        existing_blueprint = topic.curriculum_blueprint if isinstance(topic.curriculum_blueprint, dict) else {}
        existing_core_arc = existing_blueprint.get('core_arc') if isinstance(existing_blueprint, dict) else None
        future_guard_lines: list[str] = []
        if isinstance(existing_core_arc, list) and existing_core_arc:
            blueprint_context = '\n'.join(
                f"- {str(item.get('name') or '').strip()} ({str(item.get('instructional_role') or 'core')})"
                for item in existing_core_arc[:8]
                if isinstance(item, dict)
            )
            future_guard_lines = [
                f"{str(item.get('name') or '').strip()} {str(item.get('description') or '').strip()}".strip()
                for item in existing_core_arc
                if isinstance(item, dict) and str(item.get('name') or '').strip()
            ]
        else:
            blueprint_context = 'No prior blueprint available'

        research_insights = await self.research_service.gather_for_topic(topic=topic, limit=5)
        research_context = self.research_service.format_prompt_context(research_insights, max_items=5)

        system_prompt = (
            'You are SkillGraphAgent. Build a practical learning skill graph for a topic. '
            'Prefer atomic skills, clear prerequisite ordering, and realistic progression from fundamentals '
            'to applied practice. Keep graph acyclic and avoid redundant skills. '
            'For cultural and creative topics, prioritize exemplar study, taste development, and hands-on response work, '
            'with theory/history/context acting as support rather than the dominant mode.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Description: {topic.description or "No description"}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n\n'
            f'Course depth preference: {course_depth}\n'
            f'Starting skill level preference: {starting_level}\n'
            f'Technical depth preference: {technical_depth}\n'
            f'Guidance: {level_guidance}\n\n'
            f'Technical depth guidance: {technical_guidance}\n\n'
            f'Existing editorial spine to preserve where possible:\n{blueprint_context}\n\n'
            f'High-signal web research notes (optional grounding):\n{research_context or "None"}\n\n'
            f'Create between {min_nodes} and {max_nodes} skill nodes. '
            'Each node needs key, name, description, difficulty (1-5), '
            'instructional_role, and prerequisites (list of node keys). '
            'Use at most 2 prerequisites per node, and prefer 0-1 unless absolutely needed.\n'
            'Node title quality rules:\n'
            '- Use natural, specific, domain-grounded names.\n'
            '- Avoid vague jargon like optimization/framework/strategy/techniques unless topic is explicitly business.\n'
            '- Prefer concrete topic language over abstract process language.\n'
            'Balance rules for cultural and creative topics:\n'
            '- Ensure most nodes point toward doing, observing, comparing, or making, not only conceptual explanation.\n'
            '- Include at least one exemplar-focused node and one response/practice-focused node where relevant.\n'
            '- Keep theory/history/context nodes as grounding layers connected to practical interpretation or making.\n'
            'Instructional role rules:\n'
            '- Allowed instructional_role values: foundational_concept, conceptual_bridge, practical_application, '
            'case_deepening, comparison_contrast, assessment_preparation, synthesis_review, remediation, enrichment, specialization.\n'
            '- Every node must have a distinct instructional role rationale.\n'
            '- Avoid creating multiple nodes that teach the same role+concept combination.'
        )

        graph = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=SkillGraphPlan,
            temperature=0.2,
            max_tokens=2200,
        )

        unique_nodes = []
        seen_keys: set[str] = set()
        for node in graph.nodes:
            if node.key in seen_keys:
                continue
            seen_keys.add(node.key)
            unique_nodes.append(node)

        unique_nodes = unique_nodes[:max_nodes]
        unique_nodes = self._coerce_core_roles(unique_nodes)

        while len(unique_nodes) < min_nodes:
            idx = len(unique_nodes) + 1
            fallback_key = f'auto_skill_{idx}'
            fallback_prereq = [unique_nodes[-1].key] if unique_nodes else []
            unique_nodes.append(
                SkillPlanNode(
                    key=fallback_key,
                    name=f'{topic.name} skill {idx}',
                    description=f'Practical progression step {idx} for {topic.name}.',
                    instructional_role=_CORE_ROLE_FALLBACK_ORDER[idx % len(_CORE_ROLE_FALLBACK_ORDER)],  # type: ignore[arg-type]
                    difficulty=min(5, max(1, 1 + (idx // 3))),
                    prerequisites=fallback_prereq,
                )
            )
            seen_keys.add(fallback_key)

        unique_nodes = await self._improve_node_titles(topic=topic, nodes=unique_nodes)
        unique_nodes = self._coerce_core_roles(unique_nodes)
        filtered_nodes: list[SkillPlanNode] = []
        for node in unique_nodes:
            if self._is_core_node_redundant(
                node=node,
                accepted_nodes=filtered_nodes,
                future_lines=future_guard_lines,
            ):
                continue
            filtered_nodes.append(node)
        unique_nodes = filtered_nodes[:max_nodes]
        while len(unique_nodes) < min_nodes:
            idx = len(unique_nodes) + 1
            fallback_key = f'core_gap_{idx}'
            if fallback_key in seen_keys:
                fallback_key = f'core_gap_{idx}_{len(seen_keys)}'
            seen_keys.add(fallback_key)
            unique_nodes.append(
                SkillPlanNode(
                    key=fallback_key,
                    name=f'{topic.name} focus {idx}',
                    description=f'Curriculum bridge step {idx} to maintain coherent progression in {topic.name}.',
                    instructional_role=_CORE_ROLE_FALLBACK_ORDER[idx % len(_CORE_ROLE_FALLBACK_ORDER)],  # type: ignore[arg-type]
                    difficulty=min(5, max(1, 1 + (idx // 3))),
                    prerequisites=[unique_nodes[-1].key] if unique_nodes else [],
                )
            )

        key_position = {node.key: idx for idx, node in enumerate(unique_nodes)}
        prereq_map: dict[str, list[str]] = {}
        for node in unique_nodes:
            filtered_prereqs = [key for key in node.prerequisites if key in seen_keys and key != node.key]
            prereq_map[node.key] = self._limit_core_prerequisites(
                current_key=node.key,
                keys=filtered_prereqs,
                key_position=key_position,
            )

        has_root = any(len(prereq_map[node.key]) == 0 for node in unique_nodes)
        if not has_root:
            logger.warning('skill_graph.no_root topic_id=%s forcing first node as root', topic.id)
            prereq_map[unique_nodes[0].key] = []

        key_to_node: dict[str, SkillNode] = {}
        created_nodes: list[SkillNode] = []

        for node in unique_nodes:
            status = SkillStatus.available if len(prereq_map[node.key]) == 0 else SkillStatus.locked
            record = SkillNode(
                topic_id=topic.id,
                node_kind='core',
                branch_origin='core',
                branch_purpose='core_curriculum',
                instructional_role=node.instructional_role,
                branch_depth=0,
                branch_parent_skill_id=None,
                name=node.name,
                description=node.description,
                difficulty=node.difficulty,
                mastery_estimate=0.0,
                status=status,
                suggested_resources=[],
                generated_lessons=[],
            )
            db.add(record)
            db.flush()

            key_to_node[node.key] = record
            created_nodes.append(record)

        for child_key, parent_keys in prereq_map.items():
            child = key_to_node[child_key]
            for parent_key in parent_keys:
                parent = key_to_node[parent_key]
                db.add(
                    SkillEdge(
                        topic_id=topic.id,
                        parent_skill_id=parent.id,
                        child_skill_id=child.id,
                        edge_type='prerequisite',
                    )
                )

        spine = self.course_memory_service.build_editorial_spine(db, topic=topic)
        self.course_memory_service.persist_editorial_spine(
            db,
            topic=topic,
            spine={
                **spine,
                'research_signals': self.research_service.to_ledger_records(research_insights, limit=8),
                'technical_depth': technical_depth,
                'course_depth': course_depth,
            },
            reason='skill_graph_created',
        )
        initial_snapshot = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=topic.user_id,
            focus_skill_id=created_nodes[0].id if created_nodes else None,
        )
        self.course_memory_service.persist_snapshot(
            db,
            topic=topic,
            snapshot=initial_snapshot,
            reason='skill_graph_created',
        )

        db.commit()
        for node in created_nodes:
            db.refresh(node)

        logger.info('skill_graph.created topic_id=%s node_count=%s', topic.id, len(created_nodes))
        return created_nodes

    async def create_deep_dive_branch(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        focus: str | None = None,
        branch_size: int = 3,
        branch_origin: str = 'user_requested',
        branch_purpose: str = 'deepen_theme',
    ) -> list[SkillNode]:
        normalized_purpose = self._normalize_branch_purpose(branch_purpose)
        effective_branch_size = self._resolve_effective_branch_size(
            requested_size=branch_size,
            branch_purpose=normalized_purpose,
        )

        user_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == parent_node.id,
            )
        )
        learner_level = self._learner_level(user_state)
        technical_depth = normalize_technical_depth(topic.technical_depth)
        technical_guidance = technical_depth_prompt_guidance(technical_depth)
        curriculum_state = self._build_curriculum_state(
            db,
            topic=topic,
            parent_node=parent_node,
            user_id=user_id,
        )

        existing_branch_nodes = db.scalars(
            select(SkillNode)
            .where(
                SkillNode.topic_id == topic.id,
                SkillNode.branch_parent_skill_id == parent_node.id,
            )
            .order_by(SkillNode.created_at.desc())
            .limit(8)
        ).all()
        existing_branch_names = ', '.join(node.name for node in existing_branch_nodes) or 'None'

        system_prompt = (
            'You are SkillGraphAgent. Create optional deep-dive branch modules for a selected skill. '
            'Keep them narrow, relevant, and progression-friendly. Do not alter the core mandatory path.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Topic goal: {topic.goal or "No explicit goal"}\n'
            f'Parent skill: {parent_node.name}\n'
            f'Parent skill description: {parent_node.description}\n'
            f'Parent difficulty (1-5): {parent_node.difficulty}\n'
            f'Learner level at parent node: {learner_level}\n'
            f'Technical depth preference: {technical_depth}\n'
            f'Branch purpose (required): {normalized_purpose}\n'
            f'User focus request: {focus or "None"}\n'
            f'Existing optional branch nodes under this parent: {existing_branch_names}\n\n'
            f'Curriculum memory context:\n{self._curriculum_context_text(curriculum_state)}\n\n'
            f'Generate {effective_branch_size} optional branch nodes.\n'
            'Requirements:\n'
            '- The branch must be clearly optional.\n'
            '- Keep branch-level rationale concise (about 1-2 sentences, <= 280 characters).\n'
            '- Keep scope tightly tied to the parent node.\n'
            '- Use key, name, description, instructional_role, difficulty, prerequisites.\n'
            "- In prerequisites, use either sibling node keys or 'parent'.\n"
            '- Use no more than 2 prerequisites per node (including parent).\n'
            '- Shape the node to the required branch purpose:\n'
            '  deepen_theme: deepen one core theme with richer interpretation.\n'
            '  compare_contrast: stage a clear comparison between two works, styles, or interpretations.\n'
            '  context_influence: map context, influence, and downstream impact.\n'
            '  study_exemplar: focus on one concrete exemplar and analyze it closely.\n'
            '  creative_response: produce an original response grounded in the studied material.\n'
            '  style_technique_practice: run targeted style or technique drills.\n'
            '  follow_lineage: trace lineage from precursors to later developments.\n'
            '- Keep beginner learners on foundational depth, not advanced capstone tasks.\n'
            f'- Match technical rigor to this guidance: {technical_guidance}\n'
            '- Avoid duplicate or overlapping node names.\n'
            '- Titles must be specific and natural; avoid generic strategy/optimization jargon.\n'
            '- Branch nodes must add distinct value relative to already taught nodes/examples.\n'
            '- Favor branch nodes that lead to concrete observation, comparison, making, or response.\n'
            '- If adding theory/history/context, explicitly tie it to a concrete interpretation or practice move.\n'
            '- For all branch purposes except style_technique_practice: avoid repeating taught concepts and avoid duplicating planned future core nodes.\n'
            '- For style_technique_practice: revisit only targeted weak areas, not broad repetition.'
        )

        plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=DeepDiveBranchPlan,
            temperature=0.3,
            max_tokens=1800,
        )

        existing_names_lower = {
            node.name.strip().lower()
            for node in db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
        }
        unique_nodes = []
        seen_keys: set[str] = set()
        for node in plan.nodes:
            normalized_name = node.name.strip().lower()
            if node.key in seen_keys:
                continue
            if normalized_name in existing_names_lower:
                continue
            if self._is_redundant_branch_candidate(
                node_name=node.name,
                node_description=node.description,
                parent_node=parent_node,
                purpose=normalized_purpose,
                state=curriculum_state,
            ):
                continue
            seen_keys.add(node.key)
            unique_nodes.append(node)
            if len(unique_nodes) >= effective_branch_size:
                break

        if len(unique_nodes) < 1:
            unique_nodes = [
                self._fallback_branch_node(
                    topic=topic,
                    parent_node=parent_node,
                    focus=focus,
                    purpose=normalized_purpose,
                    state=curriculum_state,
                )
            ]
        if len(unique_nodes) < effective_branch_size:
            unique_nodes = unique_nodes[:1]

        unique_nodes = await self._improve_node_titles(
            topic=topic,
            nodes=unique_nodes,
            parent_node_name=parent_node.name,
        )

        prereq_map = self._build_progressive_branch_prereq_map(unique_nodes)

        key_to_node: dict[str, SkillNode] = {}
        created_nodes: list[SkillNode] = []

        parent_depth = parent_node.branch_depth or 0
        for index, node in enumerate(unique_nodes):
            has_internal_prereq = any(item != 'parent' for item in prereq_map[node.key])
            status = SkillStatus.locked if has_internal_prereq else SkillStatus.available
            record = SkillNode(
                topic_id=topic.id,
                node_kind='optional_branch',
                branch_origin=branch_origin,
                branch_purpose=normalized_purpose,
                instructional_role=self._normalize_instructional_role(node.instructional_role, position=index),
                branch_depth=max(1, parent_depth + index + 1),
                branch_parent_skill_id=parent_node.id,
                name=node.name,
                description=node.description,
                difficulty=min(5, max(parent_node.difficulty, min(parent_node.difficulty + 1, node.difficulty))),
                mastery_estimate=0.0,
                status=status,
                suggested_resources=[],
                generated_lessons=[],
            )
            db.add(record)
            db.flush()

            key_to_node[node.key] = record
            created_nodes.append(record)

        parent_linked_children: set[int] = set()
        for child_key, parent_keys in prereq_map.items():
            child = key_to_node[child_key]
            for parent_key in parent_keys:
                if parent_key == 'parent':
                    db.add(
                        SkillEdge(
                            topic_id=topic.id,
                            parent_skill_id=parent_node.id,
                            child_skill_id=child.id,
                            edge_type='optional_branch',
                        )
                    )
                    parent_linked_children.add(child.id)
                    continue

                parent = key_to_node.get(parent_key)
                if not parent:
                    continue
                db.add(
                    SkillEdge(
                        topic_id=topic.id,
                        parent_skill_id=parent.id,
                        child_skill_id=child.id,
                        edge_type='prerequisite',
                    )
                )

        root_keys = [node.key for node in unique_nodes if len(prereq_map.get(node.key, [])) == 0]
        for root_key in root_keys:
            root_id = key_to_node[root_key].id
            if root_id in parent_linked_children:
                continue
            db.add(
                SkillEdge(
                    topic_id=topic.id,
                    parent_skill_id=parent_node.id,
                    child_skill_id=root_id,
                    edge_type='optional_branch',
                )
            )
            parent_linked_children.add(root_id)

        if not parent_linked_children:
            db.add(
                SkillEdge(
                    topic_id=topic.id,
                    parent_skill_id=parent_node.id,
                    child_skill_id=created_nodes[0].id,
                    edge_type='optional_branch',
                )
            )

        db.commit()
        for node in created_nodes:
            db.refresh(node)
        snapshot_after = self.course_memory_service.build_snapshot(
            db,
            topic=topic,
            user_id=user_id,
            focus_skill_id=parent_node.id,
        )
        self.course_memory_service.persist_snapshot(
            db,
            topic=topic,
            snapshot=snapshot_after,
            reason='branch_created',
        )
        self.course_memory_service.persist_editorial_spine(
            db,
            topic=topic,
            spine=self.course_memory_service.build_editorial_spine(db, topic=topic),
            reason='branch_created',
        )
        db.commit()

        logger.info(
            (
                'skill_graph.deep_dive_created topic_id=%s parent_skill_id=%s node_count=%s '
                'origin=%s purpose=%s requested_size=%s effective_size=%s'
            ),
            topic.id,
            parent_node.id,
            len(created_nodes),
            branch_origin,
            normalized_purpose,
            branch_size,
            effective_branch_size,
        )
        return created_nodes

    async def suggest_branch_paths(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        limit: int = 1,
        trigger_event: str = 'manual',
    ) -> list[BranchSuggestion]:
        _ = limit
        limit = MAX_PENDING_BRANCH_SUGGESTIONS

        pending = db.scalars(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
                BranchSuggestion.parent_skill_id == parent_node.id,
                BranchSuggestion.status == 'pending',
            )
            .order_by(desc(BranchSuggestion.created_at))
        ).all()
        if len(pending) > limit:
            for stale in pending[limit:]:
                stale.status = 'rejected'
                stale.updated_at = datetime.utcnow()
            db.commit()
            pending = pending[:limit]
        if pending:
            return pending[:limit]

        learner_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == parent_node.id,
            )
        )
        learner_level = self._learner_level(learner_state)
        curriculum_state = self._build_curriculum_state(
            db,
            topic=topic,
            parent_node=parent_node,
            user_id=user_id,
        )

        system_prompt = (
            'You are SkillGraphAgent. Suggest optional branch pathways for a selected learning node. '
            'Suggestions must be specific, useful, and clearly optional.'
        )
        user_prompt = (
            f'Topic: {topic.name}\n'
            f'Goal: {topic.goal or "No explicit goal"}\n'
            f'Parent node: {parent_node.name}\n'
            f'Parent description: {parent_node.description}\n'
            f'Learner level: {learner_level}\n'
            f'Trigger event: {trigger_event}\n'
            f'Curriculum memory context:\n{self._curriculum_context_text(curriculum_state)}\n'
            f'Provide exactly {limit} optional branch suggestion.\n'
            'Each suggestion must include: title, focus, rationale, purpose.\n'
            'purpose must be one of: deepen_theme, compare_contrast, context_influence, '
            'study_exemplar, creative_response, style_technique_practice, follow_lineage.\n'
            'Suggestion quality rules:\n'
            '- Must declare why this branch exists now.\n'
            '- Must clearly match the selected branch move type.\n'
            '- Must reference learner context (strength, weakness, or progression signal).\n'
            '- Focus should name a concrete work, question, technique, contrast, or response move instead of a generic deep dive.\n'
            '- Prefer actionable moves: try this, compare this, study one exemplar, or make a response.\n'
            '- If proposing context/influence, tie it to a concrete seeing/listening/writing/making action.\n'
            '- Must avoid duplicating already taught content unless the move is style_technique_practice.\n'
            '- Must avoid overlapping obvious upcoming core nodes.\n'
            '- Only suggest one high-signal path.'
        )
        plan = await self.llm_service.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=BranchSuggestionPlan,
            temperature=0.3,
            max_tokens=1200,
        )

        existing_focuses = {
            row.focus.strip().lower()
            for row in db.scalars(
                select(BranchSuggestion).where(
                    BranchSuggestion.topic_id == topic.id,
                    BranchSuggestion.user_id == user_id,
                    BranchSuggestion.parent_skill_id == parent_node.id,
                )
            ).all()
        }
        existing_focuses.update(item.lower() for item in curriculum_state.pending_branch_focuses)
        existing_focuses.update(item.lower() for item in curriculum_state.accepted_branch_focuses)

        created: list[BranchSuggestion] = []
        for item in plan.suggestions:
            normalized_purpose = self._normalize_branch_purpose(item.purpose)
            normalized_focus = self._default_branch_focus(
                parent_node=parent_node,
                purpose=normalized_purpose,
                state=curriculum_state,
                requested_focus=item.focus,
            )
            normalized_title = self._format_branch_suggestion_title(
                topic=topic,
                parent_node=parent_node,
                purpose=normalized_purpose,
                focus=normalized_focus,
                proposed_title=item.title,
            )
            rationale = self._compose_branch_suggestion_rationale(
                parent_node=parent_node,
                purpose=normalized_purpose,
                focus=normalized_focus,
                state=curriculum_state,
                trigger_event=trigger_event,
            )
            focus_key = normalized_focus.strip().lower()
            if not focus_key or focus_key in existing_focuses:
                continue
            if self._is_redundant_branch_suggestion_candidate(
                title=normalized_title,
                focus=normalized_focus,
                purpose=normalized_purpose,
                state=curriculum_state,
            ):
                continue
            existing_focuses.add(focus_key)
            record = BranchSuggestion(
                topic_id=topic.id,
                user_id=user_id,
                parent_skill_id=parent_node.id,
                title=normalized_title,
                focus=normalized_focus,
                rationale=rationale,
                purpose=normalized_purpose,
                origin='system_suggested',
                trigger_event=trigger_event,
                status='pending',
            )
            db.add(record)
            db.flush()
            created.append(record)
            if len(created) >= limit:
                break

        if not created:
            fallback_purpose = (
                'style_technique_practice'
                if curriculum_state.weak_areas
                else 'creative_response'
                if curriculum_state.strong_areas
                else 'context_influence'
            )
            fallback_focus = (
                curriculum_state.weak_areas[0]
                if fallback_purpose == 'style_technique_practice' and curriculum_state.weak_areas
                else curriculum_state.strong_areas[0]
                if fallback_purpose == 'creative_response' and curriculum_state.strong_areas
                else parent_node.name
            )
            if fallback_focus.lower() not in existing_focuses:
                fallback_focus = self._default_branch_focus(
                    parent_node=parent_node,
                    purpose=fallback_purpose,
                    state=curriculum_state,
                    requested_focus=fallback_focus,
                )
                fallback_rationale = self._compose_branch_suggestion_rationale(
                    parent_node=parent_node,
                    purpose=fallback_purpose,
                    focus=fallback_focus,
                    state=curriculum_state,
                    trigger_event=trigger_event,
                )
                fallback_title = self._format_branch_suggestion_title(
                    topic=topic,
                    parent_node=parent_node,
                    purpose=fallback_purpose,
                    focus=fallback_focus,
                    proposed_title=f'{branch_purpose_label(fallback_purpose)}: {fallback_focus}',
                )
                record = BranchSuggestion(
                    topic_id=topic.id,
                    user_id=user_id,
                    parent_skill_id=parent_node.id,
                    title=fallback_title[:255],
                    focus=fallback_focus[:255],
                    rationale=fallback_rationale,
                    purpose=fallback_purpose,
                    origin='system_suggested',
                    trigger_event=trigger_event,
                    status='pending',
                )
                db.add(record)
                db.flush()
                created.append(record)

        db.commit()
        for row in created:
            db.refresh(row)

        return created

    def create_performance_branch_suggestion(
        self,
        db: Session,
        *,
        topic: Topic,
        parent_node: SkillNode,
        user_id: int,
        score: float,
    ) -> BranchSuggestion | None:
        purpose = None
        title = ''
        rationale = ''
        focus = ''
        if score <= 0.45:
            purpose = 'style_technique_practice'
            focus = f'Targeted technique drills for {parent_node.name}'
        elif score >= 0.85:
            purpose = 'creative_response'
            focus = f'Original response work inspired by {parent_node.name}'

        if not purpose:
            return None

        existing_pending = db.scalar(
            select(BranchSuggestion).where(
                BranchSuggestion.topic_id == topic.id,
                BranchSuggestion.user_id == user_id,
                BranchSuggestion.parent_skill_id == parent_node.id,
                BranchSuggestion.status == 'pending',
            )
            .order_by(desc(BranchSuggestion.created_at))
        )
        if existing_pending:
            return existing_pending

        curriculum_state = self._build_curriculum_state(
            db,
            topic=topic,
            parent_node=parent_node,
            user_id=user_id,
        )
        focus = self._default_branch_focus(
            parent_node=parent_node,
            purpose=purpose,
            state=curriculum_state,
            requested_focus=focus,
        )
        title = self._format_branch_suggestion_title(
            topic=topic,
            parent_node=parent_node,
            purpose=purpose,
            focus=focus,
            proposed_title=f'{branch_purpose_label(purpose)}: {focus}',
        )
        rationale = self._compose_branch_suggestion_rationale(
            parent_node=parent_node,
            purpose=purpose,
            focus=focus,
            state=curriculum_state,
            trigger_event='assessment_performance',
        )
        if self._is_redundant_branch_suggestion_candidate(
            title=title,
            focus=focus,
            purpose=purpose,
            state=curriculum_state,
        ):
            return None

        suggestion = BranchSuggestion(
            topic_id=topic.id,
            user_id=user_id,
            parent_skill_id=parent_node.id,
            title=title,
            focus=focus,
            rationale=rationale,
            purpose=purpose,
            origin='system_suggested',
            trigger_event='assessment_performance',
            status='pending',
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)
        return suggestion
