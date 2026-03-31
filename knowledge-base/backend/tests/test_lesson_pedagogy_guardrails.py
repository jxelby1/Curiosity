from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.resource_agent import ResourceAgent
from app.schemas.llm import DeepLessonPlan, ExamplesPlan, LessonPlan


def _agent() -> ResourceAgent:
    return ResourceAgent(  # type: ignore[arg-type]
        llm_service=object(),
        search_service=object(),
        retrieval_service=object(),
    )


def test_lesson_plan_rejects_scaffold_before_grounding() -> None:
    with pytest.raises(ValidationError, match='example section|ground'):
        LessonPlan.model_validate(
            {
                'title': 'Photosynthesis basics',
                'summary': 'A short lesson on how plants make energy.',
                'learning_objectives': ['Define photosynthesis.', 'Apply the idea to plant growth.'],
                'key_concepts': [
                    {'term': 'Photosynthesis', 'description': 'A process plants use to make energy-rich compounds.'},
                    {'term': 'Chlorophyll', 'description': 'A pigment associated with light capture in plants.'},
                    {'term': 'Glucose', 'description': 'An energy-rich sugar plants produce through photosynthesis.'},
                ],
                'sections': [
                    {
                        'role': 'core_concept',
                        'heading': 'Overview',
                        'content': 'Photosynthesis is a process plants use to make food. It is important in biology and matters for ecosystems overall.',
                    },
                    {
                        'role': 'analysis',
                        'heading': 'Reflect',
                        'content': 'Notice what stands out in the process and respond with your own interpretation of why it matters in the natural world.',
                    },
                    {
                        'role': 'transfer',
                        'heading': 'Try it',
                        'content': 'Apply the idea to a plant you know and explain what you think is happening without using further evidence or worked explanation.',
                    },
                ],
                'exemplar_focus': ['Use one plant example as an anchor.'],
                'observation_prompts': ['Notice what stands out first.'],
                'response_prompts': ['Write a quick response.'],
                'practice_hooks': ['Try applying the idea immediately.'],
                'takeaways': ['Photosynthesis matters.', 'Plants make food.'],
                'next_steps': ['Try a practice prompt.'],
            }
        )


def test_lesson_plan_accepts_grounded_self_contained_teaching() -> None:
    plan = LessonPlan.model_validate(
        {
            'title': 'Photosynthesis basics',
            'summary': 'Learn how plants convert light into stored chemical energy through one concrete leaf-level example.',
            'learning_objectives': ['Explain the core process.', 'Apply the idea to a simple plant case.'],
                'key_concepts': [
                    {'term': 'Photosynthesis', 'description': 'The process by which plants convert light, water, and carbon dioxide into glucose and oxygen.'},
                    {'term': 'Chlorophyll', 'description': 'The pigment that absorbs light energy, especially in leaf cells.'},
                    {'term': 'Glucose', 'description': 'The sugar produced when the leaf stores energy in chemical form.'},
                ],
            'sections': [
                {
                    'role': 'example',
                    'heading': 'Start from one leaf-level case',
                    'content': 'Consider a basil leaf placed in sunlight for a school lab. For example, the leaf takes in light and carbon dioxide while water moves upward through the stem. This specific case gives us evidence for what the process is trying to accomplish.',
                },
                {
                    'role': 'analysis',
                    'heading': 'Explain the mechanism',
                    'content': 'The light matters because chlorophyll captures energy that helps rearrange water and carbon dioxide into glucose. This matters because the plant needs stored chemical energy, which means the leaf is not just green decoration but an energy-conversion site.',
                },
                {
                    'role': 'comparison',
                    'heading': 'Contrast with low-light conditions',
                    'content': 'By contrast, a basil plant kept in dim light grows more weakly because the same mechanism has less energy available. Compare the two conditions and the difference becomes visible in leaf color, growth rate, and sugar production.',
                },
                {
                    'role': 'transfer',
                    'heading': 'Transfer to a new plant case',
                    'content': 'Apply the same reasoning to a mint plant on a shaded windowsill. Explain what you would predict, which observable details matter first, and how the lower-light case changes the interpretation.',
                },
            ],
            'exemplar_focus': ['Keep the basil leaf example in view as the anchor case.'],
            'observation_prompts': ['Identify one visible detail in the basil-leaf case and connect it to the mechanism.'],
            'comparison_prompts': ['Compare the basil leaf in strong light with one in weak light and explain the key difference.'],
            'response_prompts': ['Explain one detail from the basil example using evidence from the lesson.'],
            'practice_hooks': ['Apply the pattern to one houseplant and predict what would change in lower light.'],
            'takeaways': ['Photosynthesis is an evidence-based energy conversion process.', 'Comparison clarifies why light conditions matter.'],
            'next_steps': ['Apply the same reasoning to plant growth in shade.'],
        }
    )

    assert len(plan.sections) == 4


def test_examples_plan_rejects_placeholder_example_names() -> None:
    with pytest.raises(ValidationError, match='specific'):
        ExamplesPlan.model_validate(
            {
                'title': 'Worked examples for comma splices',
                'intro': 'These examples show how comma splices work in real sentences before you try correcting them yourself.',
                'examples': [
                    {
                        'role': 'anchor',
                        'name': 'Example 1',
                        'explanation': 'For example, the sentence joins two independent clauses with only a comma, which means the reader gets a grammatical collision instead of a clear boundary.',
                        'why_it_matters': 'This matters because the error weakens control over sentence structure.',
                    },
                    {
                        'role': 'contrast',
                        'name': 'Example 2',
                        'explanation': 'For instance, another sentence shows the same problem in a different register, and the comparison helps the learner see the recurring pattern.',
                        'why_it_matters': 'This matters because repeated contrast makes the rule more usable.',
                    },
                    {
                        'role': 'transfer',
                        'name': 'Example 3',
                        'explanation': 'Consider a corrected version where the writer uses a semicolon instead, because the clauses need a stronger bridge than a comma alone can provide.',
                        'why_it_matters': 'This matters because the learner can compare the broken and fixed sentence side by side.',
                    },
                ],
                'comparison_prompts': ['Compare the incorrect sentence with the corrected one.'],
                'observation_prompts': ['Notice which punctuation choice changes the sentence boundary.'],
                'response_prompts': ['Explain why the corrected sentence works.'],
                'practice_hooks': ['Correct one new sentence of your own.'],
            }
        )


def test_deep_lesson_plan_rejects_assumed_familiarity() -> None:
    with pytest.raises(ValidationError, match='prior familiarity'):
        DeepLessonPlan.model_validate(
            {
                'title': 'Machiavelli and civic power',
                'summary': 'A deeper look at how civic power operates in Machiavelli.',
                'essential_questions': ['How does civic power work?', 'Why does context matter?'],
                'sections': [
                    {
                        'role': 'example',
                        'heading': 'Opening',
                        'content': 'If you are already familiar with The Prince, the basic argument is obvious. We can move quickly into what you already know about fear, power, and civic order without restating the text.',
                    },
                    {
                        'role': 'analysis',
                        'heading': 'Interpretation',
                        'content': 'Because the ruler is balancing instability, the argument matters, and therefore we can interpret the passage as a response to crisis rather than a general moral teaching.',
                    },
                    {
                        'role': 'comparison',
                        'heading': 'Comparison',
                        'content': 'Compare the ruler-centered argument with a civic-republican argument, and by contrast the role of institutions becomes clearer for the reader.',
                    },
                    {
                        'role': 'transfer',
                        'heading': 'Transfer',
                        'content': 'Apply the contrast to a new historical case and justify the comparison with evidence from the lesson rather than assumed familiarity.',
                    },
                ],
                'exemplar_focus': ['Use one passage from The Prince as the anchor.'],
                'comparison_prompts': ['Compare the ruler-centered argument with a civic-republican alternative.'],
                'observation_prompts': ['Read one passage closely before interpreting it.'],
                'response_prompts': ['Write a short response to the argument.'],
                'practice_hooks': ['Apply the argument to a new historical case.'],
                'key_terms': [
                    {'term': 'Civic power', 'description': 'Power exercised through or against shared institutions.'},
                    {'term': 'Republicanism', 'description': 'A political tradition centered on civic participation and constraint.'},
                    {'term': 'Legitimacy', 'description': 'The perceived rightfulness of a political order or ruling arrangement.'},
                ],
                'study_prompts': ['Explain the main argument.', 'Compare Machiavelli with another position.'],
            }
        )


def test_resource_agent_flags_low_evidence_and_practice_before_proof() -> None:
    agent = _agent()
    issues = agent._evidence_density_issues(  # type: ignore[attr-defined]
        kind='lesson',
        study_mode='standard',
        structured_content={
            'sections': [
                {'heading': 'Overview', 'content': 'This lesson introduces the concept in broad terms and explains that it is important for many situations overall.'},
                {'heading': 'Respond', 'content': 'Reflect on the concept and try applying it to your own case immediately, even though no concrete case has been taught yet.'},
                {'heading': 'Summary', 'content': 'The concept remains important because it matters in many contexts and should be kept in mind generally.'},
            ],
            'response_prompts': ['Write a quick response.'],
            'practice_hooks': ['Try the concept right away.'],
            'observation_prompts': ['Notice what stands out.'],
            'comparison_prompts': [],
            'exemplar_focus': ['Use one anchor example.'],
        },
    )

    assert 'low_evidence_density' in issues
    assert 'practice_before_proof' in issues


def test_lesson_plan_requires_example_analysis_and_transfer_roles() -> None:
    with pytest.raises(ValidationError, match='explicit example section'):
        LessonPlan.model_validate(
            {
                'title': 'Thermodynamics basics',
                'summary': 'A short lesson on heat and energy.',
                'learning_objectives': ['Define heat transfer.', 'Apply the idea to a simple case.'],
                'key_concepts': [
                    {'term': 'Heat transfer', 'description': 'The movement of thermal energy from one place to another.'},
                    {'term': 'Conduction', 'description': 'Heat transfer through direct contact between materials.'},
                    {'term': 'Thermal equilibrium', 'description': 'A state in which connected systems stop exchanging heat overall.'},
                ],
                'sections': [
                    {
                        'role': 'core_concept',
                        'heading': 'Concept',
                        'content': 'Heat transfer matters because temperature differences lead energy to move until conditions change and an observable balance becomes possible.',
                    },
                    {
                        'role': 'analysis',
                        'heading': 'Explain the idea',
                        'content': 'Because the hotter object has more thermal energy available, energy moves toward the cooler one, which means the temperature gap begins to shrink.',
                    },
                    {
                        'role': 'transfer',
                        'heading': 'Apply it',
                        'content': 'Apply the concept to a mug on a table and explain what would happen next in ordinary conditions.',
                    },
                ],
                'exemplar_focus': ['Use one metal spoon example as the anchor.'],
                'observation_prompts': ['Notice one detail from the worked case.'],
                'response_prompts': ['Explain the change in your own words.'],
                'practice_hooks': ['Apply the idea to a kitchen example.'],
                'takeaways': ['Heat transfer depends on difference.', 'Mechanism matters more than vocabulary alone.'],
                'next_steps': ['Try a simple conduction example.'],
            }
        )
