import { RecommendationItem, SkillNode, SkillTree, TopicActionItem, TopicRetentionLoop } from '@/lib/types';

export type LearningLoopStep = 'learn' | 'practice' | 'verify' | 'reflect' | 'continue_or_branch';

export type PrimaryNextStep = {
  label: string;
  reason: string;
  href: string;
  tab?: string;
  skillNodeId: number | null;
  source: 'retention' | 'recommendation' | 'skill_state' | 'fallback';
  loopStep: LearningLoopStep;
};

export const LEARNING_LOOP_LABELS: Array<{ id: LearningLoopStep; label: string }> = [
  { id: 'learn', label: 'Study' },
  { id: 'practice', label: 'Practice' },
  { id: 'verify', label: 'Verify' },
  { id: 'reflect', label: 'Reflect' },
  { id: 'continue_or_branch', label: 'Continue or Branch' },
];

function actionHref(topicId: string, action: TopicActionItem): string {
  if (!action.skill_node_id) return `/topics/${topicId}`;
  return `/topics/${topicId}/skills/${action.skill_node_id}?tab=${action.tab}`;
}

function stepFromTab(tab: string | undefined): LearningLoopStep {
  if (tab === 'lesson') return 'learn';
  if (tab === 'examples' || tab === 'exercises') return 'practice';
  if (tab === 'quiz') return 'verify';
  if (tab === 'resources') return 'reflect';
  return 'continue_or_branch';
}

function stepFromRecommendationType(actionType: string): LearningLoopStep {
  if (actionType === 'practice_quiz') return 'verify';
  if (actionType === 'study_external') return 'practice';
  return 'learn';
}

function preferredTabForNode(node: SkillNode): string {
  if (node.status === 'locked') return 'overview';
  if (!node.lesson_completed) return 'lesson';
  if (!node.exercises_completed) return 'exercises';
  if (!node.quiz_taken || node.progress_state !== 'verified') return 'quiz';
  return 'overview';
}

export function derivePrimaryNodeNextStep(topicId: string, node: SkillNode): PrimaryNextStep {
  if (node.status === 'locked') {
    return {
      label: 'View unlock sequence',
      reason: node.lock_reason || 'Complete prerequisite nodes first to continue this path.',
      href: `/topics/${topicId}/skills/${node.id}?tab=overview`,
      tab: 'overview',
      skillNodeId: node.id,
      source: 'skill_state',
      loopStep: 'continue_or_branch',
    };
  }

  if (!node.lesson_completed) {
    return {
      label: 'Study this node',
      reason: 'Start with the lesson before practice or verification so your interpretation is grounded.',
      href: `/topics/${topicId}/skills/${node.id}?tab=lesson`,
      tab: 'lesson',
      skillNodeId: node.id,
      source: 'skill_state',
      loopStep: 'learn',
    };
  }

  if (!node.exercises_completed) {
    return {
      label: 'Practice this node',
      reason: 'Practice now to turn understanding into concrete skill before verification.',
      href: `/topics/${topicId}/skills/${node.id}?tab=exercises`,
      tab: 'exercises',
      skillNodeId: node.id,
      source: 'skill_state',
      loopStep: 'practice',
    };
  }

  if (!node.quiz_taken || node.progress_state !== 'verified') {
    return {
      label: 'Verify understanding',
      reason: 'A verified result unlocks progression and confirms mastery for this node.',
      href: `/topics/${topicId}/skills/${node.id}?tab=quiz`,
      tab: 'quiz',
      skillNodeId: node.id,
      source: 'skill_state',
      loopStep: 'verify',
    };
  }

  return {
    label: 'Reflect in notebook',
    reason: 'Capture what shifted in your understanding, then continue the core path or branch.',
    href: `/topics/${topicId}/notes`,
    tab: 'notes',
    skillNodeId: node.id,
    source: 'skill_state',
    loopStep: 'reflect',
  };
}

export function derivePrimaryTopicNextStep({
  topicId,
  retention,
  recommendations,
  tree,
}: {
  topicId: string;
  retention: TopicRetentionLoop | null;
  recommendations: RecommendationItem[];
  tree: SkillTree | null;
}): PrimaryNextStep {
  const firstRetentionAction = retention?.next_actions?.[0];
  if (firstRetentionAction) {
    const label = firstRetentionAction.title || `Continue ${firstRetentionAction.skill_name}`;
    return {
      label,
      reason:
        firstRetentionAction.description ||
        'Recommended from your current progression state.',
      href: actionHref(topicId, firstRetentionAction),
      tab: firstRetentionAction.tab,
      skillNodeId: firstRetentionAction.skill_node_id,
      source: 'retention',
      loopStep: stepFromTab(firstRetentionAction.tab),
    };
  }

  const firstRecommendation = recommendations[0];
  if (firstRecommendation) {
    const node = tree?.nodes.find((item) => item.id === firstRecommendation.skill_node_id);
    const tab = node ? preferredTabForNode(node) : 'overview';
    return {
      label: `Continue ${firstRecommendation.skill_name}`,
      reason: firstRecommendation.rationale || 'Recommended based on your current momentum.',
      href: `/topics/${topicId}/skills/${firstRecommendation.skill_node_id}?tab=${tab}`,
      tab,
      skillNodeId: firstRecommendation.skill_node_id,
      source: 'recommendation',
      loopStep: stepFromRecommendationType(firstRecommendation.action_type),
    };
  }

  const fallbackNode = tree?.nodes.find((item) => item.status !== 'locked') || tree?.nodes[0];
  if (fallbackNode) {
    const fallback = derivePrimaryNodeNextStep(topicId, fallbackNode);
    return {
      ...fallback,
      label: `Continue ${fallbackNode.name}`,
      source: 'fallback',
      loopStep: fallbackNode.status === 'locked' ? 'continue_or_branch' : fallback.loopStep,
    };
  }

  return {
    label: 'Start your first study',
    reason: 'Start one study to begin your core learning loop.',
    href: '/topics',
    tab: 'overview',
    skillNodeId: null,
    source: 'fallback',
    loopStep: 'learn',
  };
}
