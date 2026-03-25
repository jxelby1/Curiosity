export type SkillStatus = 'locked' | 'available' | 'in_progress' | 'mastered';
export type ProgressState = 'not_started' | 'learning' | 'completed' | 'verified';
export type NoteType = 'personal' | 'lesson' | 'summary' | 'reflection' | 'reminder';
export type AssessmentQuestionType =
  | 'multiple_choice'
  | 'short_answer'
  | 'explain'
  | 'scenario'
  | 'error_spotting'
  | 'reflection';

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  onboarding_state: string;
  subscription_tier: string;
  xp: number;
  level: number;
  preferences: Record<string, unknown>;
  current_goal_summary: string;
  created_at: string;
  updated_at: string;
}

export interface Topic {
  id: number;
  user_id: number;
  name: string;
  description: string;
  goal: string;
  created_at: string;
}

export type TopicInitializationStatusType =
  | 'queued'
  | 'running'
  | 'ready'
  | 'preloading'
  | 'completed'
  | 'failed';

export interface TopicInitializationStatus {
  topic_id: number;
  status: TopicInitializationStatusType;
  current_step: string;
  progress: number;
  ready_for_entry: boolean;
  background_complete: boolean;
  first_ready_skill_id: number | null;
  status_messages: string[];
  error_text: string;
  started_at: string | null;
  ready_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface TopicInitializationResult {
  topic: Topic;
  initialization: TopicInitializationStatus;
}

export interface SkillNode {
  id: number;
  topic_id: number;
  name: string;
  description: string;
  difficulty: number;
  node_kind: 'core' | 'optional_branch';
  branch_parent_skill_id: number | null;
  mastery_estimate: number;
  status: SkillStatus;
  lock_reason?: string | null;
  progress_state: ProgressState;
  lesson_completed: boolean;
  exercises_completed: boolean;
  quiz_taken: boolean;
  best_quiz_score?: number | null;
  prerequisites: number[];
  children: number[];
  recommended_next_action: string;
}

export interface SkillTree {
  topic: Topic;
  nodes: SkillNode[];
}

export interface DocumentItem {
  id: number;
  filename: string;
  content_type: string;
  created_at: string;
}

export interface PersonalNote {
  id: number;
  user_id: number;
  topic_id: number;
  skill_node_id: number | null;
  note_type: NoteType;
  tags: string[];
  source_type: 'user_authored' | 'tutor_generated' | 'external_resource';
  source_chat_session_id: number | null;
  source_message_id: number | null;
  created_from_skill_node_id: number | null;
  created_from_topic_id: number | null;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface TutorStructuredAnswer {
  overview: string;
  key_points: string[];
  practical_steps: string[];
  pitfalls: string[];
  next_step: string;
}

export interface ChatReply {
  session_id: number;
  assistant_message_id: number;
  answer: string;
  used_chunks: string[];
  citations: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
  structured_answer?: TutorStructuredAnswer | null;
  context_usage: {
    document_chunks: number;
    personal_notes: number;
    external_resources: number;
  };
}

export interface TutorNoteSaveResult {
  note: PersonalNote;
  duplicate_warning?: string | null;
  appended: boolean;
}

export interface RecommendationItem {
  skill_node_id: number;
  skill_name: string;
  rationale: string;
  action_type: string;
  resource_mode: 'generated' | 'external';
  confidence: number;
}

export interface Resource {
  id: number;
  skill_node_id: number;
  resource_type: string;
  title: string;
  url: string;
  summary: string;
  content: string;
  structured_content?: Record<string, unknown> | null;
  source: 'stored' | 'generated' | 'regenerated';
  version: number;
  relevance_reason: string;
}

export interface ExternalResource {
  id: number;
  title: string;
  url: string;
  summary: string;
  resource_type: string;
  relevance_reason: string;
}

export interface ProgressUpdateResult {
  skill_node_id: number;
  mastery: number;
  status: SkillStatus;
  progress_state: ProgressState;
}

export interface QuizQuestion {
  id: string;
  prompt: string;
  choices: string[];
}

export interface Quiz {
  assessment_id: number;
  title: string;
  questions: QuizQuestion[];
  source: 'stored' | 'generated' | 'regenerated';
  version: number;
}

export interface QuizSubmissionResult {
  score: number;
  feedback: Array<Record<string, unknown>>;
  updated_mastery: number;
  updated_status: SkillStatus;
  updated_progress_state: ProgressState;
}

export interface AssessmentQuestion {
  id: number;
  question_type: AssessmentQuestionType;
  prompt: string;
  choices: string[];
  expected_concepts: string[];
  rubric: Record<string, unknown>;
  difficulty: number;
  order_index: number;
}

export interface Assessment {
  id: number;
  topic_id: number;
  skill_node_id: number;
  title: string;
  difficulty: number;
  target_level: string;
  question_mix: Record<string, number>;
  version: number;
  source: 'stored' | 'generated' | 'regenerated';
  questions: AssessmentQuestion[];
  created_at: string;
}

export interface AssessmentResponseInput {
  question_id: number;
  selected_option_index?: number;
  answer_text?: string;
}

export interface AssessmentQuestionFeedback {
  question_id: number;
  question_type: AssessmentQuestionType;
  score: number;
  confidence_score?: number | null;
  feedback: string;
  missing_concepts: string[];
}

export interface AssessmentSubmissionResult {
  assessment_id: number;
  attempt_id: number;
  score: number;
  confidence_avg: number;
  mastery_delta: number;
  feedback: AssessmentQuestionFeedback[];
  strengths: string[];
  weaknesses: string[];
  review_next: string;
  recommended_follow_up: string;
  summary: string;
  updated_mastery: number;
  updated_status: SkillStatus;
  updated_progress_state: ProgressState;
  unlocked_skill_ids: number[];
}

export interface AssessmentAttempt {
  id: number;
  assessment_id: number;
  user_id: number;
  score: number;
  confidence_avg: number;
  mastery_delta: number;
  strengths: string[];
  weaknesses: string[];
  review_next: string;
  recommended_follow_up: string;
  feedback: AssessmentQuestionFeedback[];
  created_at: string;
}

export interface TopicProgressNode {
  skill_node_id: number;
  name: string;
  status: SkillStatus;
  progress_state: ProgressState;
  mastery: number;
  best_quiz_score: number;
  recommended_next_action: string;
}

export interface TopicProgress {
  topic_id: number;
  topic_name: string;
  total_nodes: number;
  verified_nodes: number;
  available_nodes: number;
  mastery_average: number;
  nodes: TopicProgressNode[];
}

export interface UserTopicProgressSummary {
  topic_id: number;
  topic_name: string;
  total_nodes: number;
  verified_nodes: number;
  mastery_average: number;
}

export interface UserProgressSummary {
  user_id: number;
  xp: number;
  level: number;
  topics_total: number;
  verified_nodes_total: number;
  mastery_average: number;
  topics: UserTopicProgressSummary[];
}
