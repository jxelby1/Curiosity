from __future__ import annotations

from typing import Literal


CourseDepth = Literal['light', 'standard', 'deep_dive']
StartingSkillLevel = Literal['beginner', 'intermediate', 'advanced']
TechnicalDepth = Literal['beginner', 'intermediate', 'advanced', 'degree', 'masters', 'phd']
AssessmentStyle = Literal[
    'open_text',
    'short_answer',
    'multiple_choice',
    'flashcard',
    'scenario',
    'coding',
    'debugging',
    'code_completion',
    'code_interpretation',
    'math_problem',
]

COURSE_DEPTH_VALUES: tuple[CourseDepth, ...] = ('light', 'standard', 'deep_dive')
STARTING_SKILL_LEVEL_VALUES: tuple[StartingSkillLevel, ...] = ('beginner', 'intermediate', 'advanced')
TECHNICAL_DEPTH_VALUES: tuple[TechnicalDepth, ...] = (
    'beginner',
    'intermediate',
    'advanced',
    'degree',
    'masters',
    'phd',
)
ASSESSMENT_STYLE_VALUES: tuple[AssessmentStyle, ...] = (
    'open_text',
    'short_answer',
    'multiple_choice',
    'flashcard',
    'scenario',
    'coding',
    'debugging',
    'code_completion',
    'code_interpretation',
    'math_problem',
)

DEFAULT_ASSESSMENT_STYLES: list[AssessmentStyle] = [
    'short_answer',
    'multiple_choice',
    'flashcard',
]
DEFAULT_TECHNICAL_DEPTH: TechnicalDepth = 'intermediate'

# Maps user-facing assessment styles to internal grading categories.
ASSESSMENT_STYLE_TO_QUESTION_TYPE: dict[AssessmentStyle, str] = {
    'open_text': 'explain',
    'short_answer': 'short_answer',
    'multiple_choice': 'multiple_choice',
    'flashcard': 'short_answer',
    'scenario': 'scenario',
    'coding': 'scenario',
    'debugging': 'error_spotting',
    'code_completion': 'short_answer',
    'code_interpretation': 'explain',
    'math_problem': 'short_answer',
}


def normalize_course_depth(value: str | None) -> CourseDepth:
    if value in COURSE_DEPTH_VALUES:
        return value
    return 'standard'


def normalize_starting_skill_level(value: str | None) -> StartingSkillLevel:
    if value in STARTING_SKILL_LEVEL_VALUES:
        return value
    return 'beginner'


def normalize_technical_depth(value: str | None) -> TechnicalDepth:
    if value in TECHNICAL_DEPTH_VALUES:
        return value
    return DEFAULT_TECHNICAL_DEPTH


def normalize_assessment_styles(values: list[str] | None) -> list[AssessmentStyle]:
    if not values:
        return DEFAULT_ASSESSMENT_STYLES.copy()

    seen: set[str] = set()
    normalized: list[AssessmentStyle] = []
    for raw in values:
        if raw not in ASSESSMENT_STYLE_VALUES:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        normalized.append(raw)

    return normalized or DEFAULT_ASSESSMENT_STYLES.copy()


def depth_node_bounds(depth: CourseDepth) -> tuple[int, int]:
    if depth == 'light':
        return (6, 8)
    if depth == 'deep_dive':
        return (12, 16)
    return (8, 12)


def assessment_question_count_for_depth(depth: CourseDepth) -> int:
    if depth == 'light':
        return 5
    if depth == 'deep_dive':
        return 8
    return 6


def starting_level_mastery_floor(level: StartingSkillLevel, difficulty: int) -> float:
    base = 0.0
    if level == 'intermediate':
        base = 0.18
    elif level == 'advanced':
        base = 0.34
    penalty = max(0, difficulty - 1) * 0.06
    return max(0.0, min(1.0, base - penalty))


def level_prompt_guidance(level: StartingSkillLevel) -> str:
    if level == 'advanced':
        return (
            'Assume strong prior familiarity. Compress basics, focus quickly on advanced application, '
            'edge cases, optimization, and synthesis.'
        )
    if level == 'intermediate':
        return (
            'Assume partial familiarity. Keep foundations concise and move quickly into practical application.'
        )
    return (
        'Assume beginner familiarity. Include foundational concepts, prerequisites, and gradual ramp-up.'
    )


def technical_depth_prompt_guidance(depth: TechnicalDepth) -> str:
    if depth == 'phd':
        return (
            'Use research-grade depth: high conceptual density, careful uncertainty handling, explicit competing '
            'interpretations, edge cases, and rigorous analytical framing. Avoid filler.'
        )
    if depth == 'masters':
        return (
            'Use advanced graduate depth: nuanced analysis, synthesis across perspectives, stronger tradeoff reasoning, '
            'and explicit ambiguity handling where relevant.'
        )
    if depth == 'degree':
        return (
            'Use undergraduate degree-level rigor: formal conceptual framing, disciplinary vocabulary, and structured '
            'argumentation with concrete examples.'
        )
    if depth == 'advanced':
        return (
            'Use advanced depth: dense explanations, prior-knowledge assumptions, and deeper causal/comparative reasoning.'
        )
    if depth == 'intermediate':
        return (
            'Use intermediate depth: compact explanations with some assumed familiarity, plus practical synthesis.'
        )
    return (
        'Use beginner depth: strong scaffolding, explicit terminology explanations, and stepwise concept build-up.'
    )


def technical_depth_lesson_targets(depth: TechnicalDepth) -> dict[str, int]:
    """
    Target complexity settings for lesson generation quality constraints.
    Values are tuned to encourage richer output without forcing verbosity.
    """
    if depth == 'phd':
        return {'section_min_chars': 320, 'min_sections': 4, 'max_tokens': 2600}
    if depth == 'masters':
        return {'section_min_chars': 280, 'min_sections': 4, 'max_tokens': 2400}
    if depth == 'degree':
        return {'section_min_chars': 240, 'min_sections': 4, 'max_tokens': 2200}
    if depth == 'advanced':
        return {'section_min_chars': 210, 'min_sections': 3, 'max_tokens': 2000}
    if depth == 'intermediate':
        return {'section_min_chars': 180, 'min_sections': 3, 'max_tokens': 1800}
    return {'section_min_chars': 140, 'min_sections': 3, 'max_tokens': 1600}


def _domain_flags(text: str) -> dict[str, bool]:
    lowered = text.lower()
    coding_keywords = (
        'python',
        'javascript',
        'java',
        'debug',
        'coding',
        'code',
        'algorithm',
        'software',
        'api',
        'programming',
        'sql',
    )
    math_keywords = (
        'math',
        'mathematics',
        'algebra',
        'calculus',
        'probability',
        'statistics',
        'equation',
        'quant',
        'numeric',
        'geometry',
    )
    applied_keywords = (
        'case',
        'decision',
        'strategy',
        'tradeoff',
        'interview',
        'customer',
        'policy',
        'scenario',
        'real-world',
    )
    return {
        'code': any(token in lowered for token in coding_keywords),
        'math': any(token in lowered for token in math_keywords),
        'applied': any(token in lowered for token in applied_keywords),
    }


def style_weight(
    *,
    style: AssessmentStyle,
    topic_text: str,
    skill_text: str,
    learner_level: StartingSkillLevel | str,
) -> float:
    flags = _domain_flags(f'{topic_text} {skill_text}')
    level = learner_level if learner_level in STARTING_SKILL_LEVEL_VALUES else 'beginner'

    base = 1.0
    if style == 'multiple_choice':
        base = 1.2 if level == 'beginner' else 0.9
    elif style in {'short_answer', 'open_text'}:
        base = 1.0 if level == 'beginner' else 1.2
    elif style == 'flashcard':
        base = 1.25 if level == 'beginner' else 0.8
    elif style == 'scenario':
        base = 1.2 if flags['applied'] else 1.0
    elif style in {'coding', 'debugging', 'code_completion', 'code_interpretation'}:
        base = 1.45 if flags['code'] else 0.35
    elif style == 'math_problem':
        base = 1.45 if flags['math'] else 0.35

    return base


def build_assessment_style_sequence(
    *,
    allowed_styles: list[str] | None,
    question_count: int,
    topic_text: str,
    skill_text: str,
    learner_level: StartingSkillLevel | str,
) -> list[AssessmentStyle]:
    allowed = normalize_assessment_styles(allowed_styles)
    question_count = max(4, min(12, int(question_count)))

    ranked = sorted(
        allowed,
        key=lambda item: style_weight(
            style=item,
            topic_text=topic_text,
            skill_text=skill_text,
            learner_level=learner_level,
        ),
        reverse=True,
    )

    if not ranked:
        ranked = DEFAULT_ASSESSMENT_STYLES.copy()

    sequence: list[AssessmentStyle] = []
    # First pass: coverage/diversity.
    for style in ranked:
        if len(sequence) >= question_count:
            break
        sequence.append(style)

    if len(sequence) >= question_count:
        return sequence[:question_count]

    # Second pass: fill remaining by weighted preference.
    weighted = []
    for style in ranked:
        weight = style_weight(
            style=style,
            topic_text=topic_text,
            skill_text=skill_text,
            learner_level=learner_level,
        )
        repeats = max(1, int(round(weight * 2)))
        weighted.extend([style] * repeats)

    idx = 0
    while len(sequence) < question_count:
        sequence.append(weighted[idx % len(weighted)])
        idx += 1

    return sequence
