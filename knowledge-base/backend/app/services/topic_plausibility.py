from __future__ import annotations

import logging
import re

from app.schemas.api import TopicPlausibilityCheckResponse
from app.schemas.llm import TopicPlausibilityPlan
from app.services.llm import LLMService


logger = logging.getLogger(__name__)

EXPLICIT_CREATIVE_MARKERS = (
    'fictional',
    'imagined',
    'imagining',
    'hypothetical',
    'alternate history',
    'alternate universe',
    'what if',
    'creative',
    'satirical',
    'parody',
)

HIGH_RISK_FACTUAL_PHRASES = (
    'professional football career',
    'six nations appearances',
    'olympic swimming medals',
    'formula 1 driving career',
    'machine learning research',
    'music compositions',
    'snooker career',
)

FACTUAL_CLAIM_MARKERS = (
    'career',
    'appearances',
    'medals',
    'compositions',
    'research',
    'record',
    'championship',
    'titles',
    'awards',
)
PERSON_ENTITY_HINTS = (
    'person',
    'individual',
    'figure',
    'leader',
    'politician',
    'founder',
    'artist',
    'writer',
    'scientist',
)
PRIVATE_SUBJECT_MARKERS = (
    'my friend',
    'my colleague',
    'my coworker',
    'my classmate',
    'my teacher',
    'my mentor',
    'my manager',
    'my boss',
    'my dad',
    'my mom',
    'my mother',
    'my father',
    'my brother',
    'my sister',
    'my partner',
    'my husband',
    'my wife',
    'our friend',
)
UNDER_SPECIFIED_MARKERS = (
    'about my friend',
    'life and career',
    'everything about',
    'complete biography',
    'story of',
)
GENERIC_PERSON_REQUEST_MARKERS = (
    'about him',
    'about her',
    'his life',
    'her life',
    'his career',
    'her career',
    'learn about him',
    'learn about her',
    'biography',
    'background',
)
GROUNDING_HINT_MARKERS = (
    'timeline',
    'source',
    'document',
    'citation',
    'published',
    'known for',
    'worked at',
    'role',
    'project',
    'research',
    'book',
    'paper',
    'article',
    'archive',
)

PERSON_POSSESSIVE_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}'s\b")
PERSON_OF_RE = re.compile(r"\b(?:career|legacy|biography|history)\s+of\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b")
PERSON_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
PERSON_PSEUDO_POSSESSIVE_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}s\b")
BARE_TITLECASE_NAME_RE = re.compile(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$')

NON_PERSON_TITLECASE_TOKENS = {
    'History',
    'Science',
    'Art',
    'Physics',
    'Chemistry',
    'Biology',
    'Mathematics',
    'Economics',
    'Politics',
    'Culture',
    'Design',
    'Programming',
    'Learning',
    'Engineering',
    'Mechanics',
    'Theory',
    'Systems',
    'Analysis',
    'Fundamentals',
    'Basics',
    'Overview',
    'Introduction',
    'Methods',
    'Practice',
    'Policy',
    'Trade',
    'Communication',
    'Literature',
}


class TopicPlausibilityService:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service

    def _is_explicitly_creative(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in EXPLICIT_CREATIVE_MARKERS)

    def _contains_phrase(self, text: str, phrase: str) -> bool:
        return bool(re.search(rf'\b{re.escape(phrase)}\b', text))

    def _looks_like_bare_person_name_topic(self, *, name: str) -> bool:
        name_clean = name.strip()
        if not BARE_TITLECASE_NAME_RE.fullmatch(name_clean):
            return False

        tokens = name_clean.split()
        if any(token in NON_PERSON_TITLECASE_TOKENS for token in tokens):
            return False

        return True

    def _grounding_strength(self, *, description: str, goal: str) -> float:
        details = ' '.join(part.strip() for part in (description, goal) if part and part.strip())
        lowered = details.lower()
        if not lowered:
            return 0.0
        score = min(0.6, len(lowered) / 900)
        marker_hits = sum(1 for marker in GROUNDING_HINT_MARKERS if marker in lowered)
        score += min(0.35, marker_hits * 0.07)
        if any(token.isdigit() for token in lowered):
            score += 0.08
        return min(score, 1.0)

    def _is_private_or_unknown_person_topic(self, *, name: str, description: str, goal: str) -> bool:
        name_clean = name.strip()
        text = ' '.join(part.strip() for part in (name, description, goal) if part and part.strip()).lower()
        if any(self._contains_phrase(text, marker) for marker in PRIVATE_SUBJECT_MARKERS):
            return True
        if any(self._contains_phrase(text, marker) for marker in UNDER_SPECIFIED_MARKERS):
            return True

        person_like = bool(
            PERSON_POSSESSIVE_RE.search(name_clean)
            or PERSON_PSEUDO_POSSESSIVE_RE.search(name_clean)
            or PERSON_OF_RE.search(name_clean)
            or PERSON_NAME_RE.search(name_clean)
        )
        if not person_like:
            return False

        has_contextual_domain_anchor = any(
            token in text
            for token in (
                'policy',
                'literary',
                'novel',
                'history',
                'economics',
                'trade',
                'art',
                'science',
                'communication',
                'philosophy',
                'music theory',
            )
        )
        has_biography_claim = any(marker in text for marker in FACTUAL_CLAIM_MARKERS) or 'biography' in text
        return has_biography_claim and not has_contextual_domain_anchor

    def _heuristic_clarification(self, text: str) -> TopicPlausibilityCheckResponse | None:
        lowered = text.lower()
        phrase_hits = [item for item in HIGH_RISK_FACTUAL_PHRASES if item in lowered]
        if phrase_hits:
            hit = phrase_hits[0]
            return TopicPlausibilityCheckResponse(
                status='clarify',
                confidence=0.88,
                reason=(
                    f'This appears to make a concrete factual claim ("{hit}") that may not be real as stated.'
                ),
                suggested_reframe=(
                    'If you intended a creative scenario, reframe it explicitly as fictional, hypothetical, or alternate history.'
                ),
                suggested_mode='hypothetical',
                requires_source_material=False,
                context_hint='',
            )

        looks_like_person_claim = bool(
            PERSON_POSSESSIVE_RE.search(text)
            or PERSON_PSEUDO_POSSESSIVE_RE.search(text)
            or PERSON_OF_RE.search(text)
        )
        if looks_like_person_claim and any(marker in lowered for marker in FACTUAL_CLAIM_MARKERS):
            return TopicPlausibilityCheckResponse(
                status='clarify',
                confidence=0.72,
                reason=(
                    'This topic looks like a factual biographical claim and may need clarification to avoid invented premises.'
                ),
                suggested_reframe='You can revise to a verifiable factual angle, or mark it as fictional/hypothetical.',
                suggested_mode='hypothetical',
                requires_source_material=False,
                context_hint='',
            )

        return None

    async def _llm_assess(self, *, name: str, description: str, goal: str) -> TopicPlausibilityCheckResponse | None:
        if self.llm_service is None:
            return None

        system_prompt = (
            'You are a topic plausibility guardrail for a learning platform. '
            'Detect likely fabricated factual premises while avoiding false positives. '
            'Do not penalize niche but plausible topics. '
            'If a topic is clearly framed as fictional/hypothetical, prefer pass. '
            'If a topic appears to target a private/unknown individual without sufficient grounding, return needs_context.'
        )
        user_prompt = (
            f'Topic name: {name}\n'
            f'Description: {description or "None"}\n'
            f'Goal: {goal or "None"}\n\n'
            'Classify:\n'
            '- pass: plausible or ambiguous but acceptable without friction\n'
            '- clarify: likely fabricated factual premise; ask user to revise or reframe\n'
            '- needs_context: likely private/unknown subject or under-grounded factual premise; require source context first\n'
            '- block: only for extremely clear fabricated factual premises\n\n'
            'Return concise reason and suggested_reframe.'
        )

        try:
            assessment = await self.llm_service.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_model=TopicPlausibilityPlan,
                temperature=0.0,
                max_tokens=500,
                retries=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning('topic_plausibility.llm_fallback error=%s', exc)
            return None

        return TopicPlausibilityCheckResponse(
            status=assessment.status,
            confidence=assessment.confidence,
            reason=assessment.reason,
            suggested_reframe=assessment.suggested_reframe,
            suggested_mode='hypothetical' if assessment.status in {'clarify', 'block'} else 'factual',
            requires_source_material=assessment.status == 'needs_context',
            context_hint=(
                'Provide source notes, timeline facts, and key context to create a grounded factual course.'
                if assessment.status == 'needs_context'
                else ''
            ),
        )

    async def evaluate(
        self,
        *,
        name: str,
        description: str = '',
        goal: str = '',
        topic_mode: str = 'factual',
        technical_depth: str = 'intermediate',
    ) -> TopicPlausibilityCheckResponse:
        text = ' '.join(part.strip() for part in (name, description, goal) if part and part.strip())
        lowered = text.lower()
        if not text:
            return TopicPlausibilityCheckResponse(
                status='block',
                confidence=0.99,
                reason='Topic name is required.',
                suggested_reframe='Add a clear topic name to continue.',
                suggested_mode='factual',
                requires_source_material=False,
                context_hint='',
            )

        if topic_mode in {'fictional', 'hypothetical', 'creative'}:
            return TopicPlausibilityCheckResponse(
                status='pass',
                confidence=0.95,
                reason='Creative/hypothetical framing is explicit, so this topic is allowed.',
                suggested_reframe='',
                suggested_mode=topic_mode,  # type: ignore[arg-type]
                requires_source_material=False,
                context_hint='',
            )

        if self._is_explicitly_creative(text):
            return TopicPlausibilityCheckResponse(
                status='pass',
                confidence=0.9,
                reason='The topic is explicitly framed as fictional or hypothetical.',
                suggested_reframe='',
                suggested_mode='creative',
                requires_source_material=False,
                context_hint='',
            )

        if any(self._contains_phrase(lowered, marker) for marker in PRIVATE_SUBJECT_MARKERS):
            return TopicPlausibilityCheckResponse(
                status='needs_context',
                confidence=0.93,
                reason=(
                    'This appears to be a factual topic about a private individual, and there is not enough grounding '
                    'to generate a reliable course without source context.'
                ),
                suggested_reframe=(
                    'Add source notes (timeline, roles, projects, key facts), or reframe as fictional/hypothetical.'
                ),
                suggested_mode='factual',
                requires_source_material=True,
                context_hint='Provide source notes or background context before generating a factual course.',
            )

        heuristic = self._heuristic_clarification(text)
        if heuristic and heuristic.confidence >= 0.86:
            return heuristic

        looks_like_person_name = self._looks_like_bare_person_name_topic(name=name)
        context_text = ' '.join(part.strip() for part in (description, goal) if part and part.strip()).lower()
        generic_person_request = (
            not context_text
            or any(self._contains_phrase(context_text, marker) for marker in GENERIC_PERSON_REQUEST_MARKERS)
        )
        if looks_like_person_name and generic_person_request and self._grounding_strength(description=description, goal=goal) < 0.55:
            return TopicPlausibilityCheckResponse(
                status='needs_context',
                confidence=0.94,
                reason=(
                    'This topic looks like a private or under-specified person-focused request. '
                    'Without concrete context, generating a factual course would likely produce generic filler.'
                ),
                suggested_reframe=(
                    'Add source notes (timeline, roles, major events, references), or reframe to a specific theme '
                    '(for example, writing style, policy decisions, or historical impact).'
                ),
                suggested_mode='factual',
                requires_source_material=True,
                context_hint='Provide source-backed context before creating a factual person-focused course.',
            )

        grounding_strength = self._grounding_strength(description=description, goal=goal)
        private_or_unknown_subject = self._is_private_or_unknown_person_topic(
            name=name,
            description=description,
            goal=goal,
        )
        high_rigor_request = technical_depth in {'masters', 'phd'}
        named_person_with_factual_claim = bool(PERSON_NAME_RE.search(name)) and any(
            marker in text.lower() for marker in FACTUAL_CLAIM_MARKERS
        )
        under_grounded_personal_claim = bool(
            re.search(r'\b(history|biography|career|legacy)\s+of\b', lowered)
            and any(hint in lowered for hint in PERSON_ENTITY_HINTS)
        )
        if private_or_unknown_subject and grounding_strength < 0.62:
            return TopicPlausibilityCheckResponse(
                status='needs_context',
                confidence=0.9,
                reason=(
                    'This appears to be a factual topic about a private or insufficiently grounded individual. '
                    'Creating a course now would likely produce generic or invented filler.'
                ),
                suggested_reframe=(
                    'Add concrete source context (timeline, roles, projects, key facts), or reframe as fictional/hypothetical.'
                ),
                suggested_mode='factual',
                requires_source_material=True,
                context_hint='Provide source notes or background context before generating a factual course.',
            )

        if high_rigor_request and grounding_strength < 0.25 and (
            named_person_with_factual_claim or under_grounded_personal_claim
        ):
            return TopicPlausibilityCheckResponse(
                status='needs_context',
                confidence=0.82,
                reason=(
                    'High technical-depth generation needs stronger grounding. Current topic details are too thin for '
                    'masters/PhD-level content.'
                ),
                suggested_reframe='Add specific scope, supporting context, or choose a lower depth level.',
                suggested_mode='factual',
                requires_source_material=True,
                context_hint='Add concrete context or reduce technical depth to avoid ungrounded advanced output.',
            )

        has_factual_claim_marker = any(marker in lowered for marker in FACTUAL_CLAIM_MARKERS)
        contains_named_person = bool(PERSON_NAME_RE.search(name))
        looks_like_personal_factual_claim = (
            (
                bool(PERSON_POSSESSIVE_RE.search(name))
                or bool(PERSON_PSEUDO_POSSESSIVE_RE.search(name))
                or bool(PERSON_OF_RE.search(name))
            )
            and has_factual_claim_marker
        )
        person_claim_needing_check = contains_named_person and has_factual_claim_marker
        needs_llm_check = bool(heuristic) or looks_like_personal_factual_claim
        if not needs_llm_check and person_claim_needing_check:
            needs_llm_check = True
        if needs_llm_check:
            llm_result = await self._llm_assess(name=name, description=description, goal=goal)
            if llm_result and (
                llm_result.status == 'block'
                or llm_result.status == 'needs_context'
                or (llm_result.status == 'clarify' and llm_result.confidence >= 0.68)
            ):
                return llm_result

        if heuristic:
            return heuristic

        return TopicPlausibilityCheckResponse(
            status='pass',
            confidence=0.82,
            reason='No strong fabricated-factual signals detected.',
            suggested_reframe='',
            suggested_mode='factual',
            requires_source_material=False,
            context_hint='',
        )
