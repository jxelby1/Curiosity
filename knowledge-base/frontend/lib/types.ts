export type SkillStatus = 'locked' | 'available' | 'in_progress' | 'mastered';
export type ProgressState = 'not_started' | 'learning' | 'completed' | 'verified';
export type NoteType = 'personal' | 'lesson' | 'summary' | 'reflection' | 'reminder';
export type CourseDepth = 'light' | 'standard' | 'deep_dive';
export type StartingSkillLevel = 'beginner' | 'intermediate' | 'advanced';
export type TechnicalDepth = 'beginner' | 'intermediate' | 'advanced' | 'degree' | 'masters' | 'phd';
export type TopicMode = 'factual' | 'fictional' | 'hypothetical' | 'creative';
export type AssessmentStyle =
  | 'open_text'
  | 'short_answer'
  | 'multiple_choice'
  | 'flashcard'
  | 'scenario'
  | 'coding'
  | 'debugging'
  | 'code_completion'
  | 'code_interpretation'
  | 'math_problem';
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
  dev_tools_enabled: boolean;
  xp: number;
  level: number;
  preferences: Record<string, unknown>;
  current_goal_summary: string;
  created_at: string;
  updated_at: string;
}

export interface ForgotPasswordResult {
  message: string;
  debug_reset_token?: string | null;
}

export interface ResetPasswordResult {
  message: string;
}

export interface Topic {
  id: number;
  user_id: number;
  name: string;
  description: string;
  goal: string;
  course_depth: CourseDepth;
  starting_skill_level: StartingSkillLevel;
  technical_depth: TechnicalDepth;
  assessment_styles: AssessmentStyle[];
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
  stage_key: string;
  stage_label: string;
  stage_index: number;
  stage_total: number;
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

export interface TopicPlausibilityCheck {
  status: 'pass' | 'clarify' | 'needs_context' | 'block';
  confidence: number;
  reason: string;
  suggested_reframe: string;
  suggested_mode: TopicMode;
  requires_source_material: boolean;
  context_hint: string;
}

export interface SkillNode {
  id: number;
  topic_id: number;
  name: string;
  description: string;
  difficulty: number;
  node_kind: 'core' | 'optional_branch';
  branch_origin: string;
  branch_purpose: string;
  instructional_role: string;
  branch_depth: number;
  branch_parent_skill_id: number | null;
  mastery_estimate: number;
  status: SkillStatus;
  force_unlocked?: boolean;
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

export interface DeepLesson {
  skill_node_id: number;
  title: string;
  summary: string;
  structured_content: Record<string, unknown>;
  source: 'generated' | 'fallback';
}

export interface ExerciseCompletion {
  id: number;
  topic_id: number;
  skill_node_id: number;
  resource_id: number | null;
  exercise_index: number;
  exercise_title: string;
  completed_at: string;
  proof_filename: string | null;
  proof_content_type: string | null;
  proof_size_bytes: number | null;
  proof_url: string | null;
}

export interface ExerciseCompletionList {
  skill_node_id: number;
  total_exercises: number;
  completed_count: number;
  completion_ratio: number;
  completions: ExerciseCompletion[];
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
  assessment_style: AssessmentStyle | string;
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
  answers_revealed: boolean;
  mastery_eligible: boolean;
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
  assessment_style?: AssessmentStyle | string;
  score: number | null;
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
  mastery_eligible: boolean;
  mastery_applied: boolean;
  practice_mode: boolean;
  outcome_message: string;
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
  mastery_eligible: boolean;
  practice_mode: boolean;
  strengths: string[];
  weaknesses: string[];
  review_next: string;
  recommended_follow_up: string;
  feedback: AssessmentQuestionFeedback[];
  created_at: string;
}

export interface AssessmentAnswerReveal {
  question_id: number;
  question_type: AssessmentQuestionType;
  assessment_style: AssessmentStyle | string;
  answer: string;
  key_points: string[];
}

export interface AssessmentRevealResult {
  assessment_id: number;
  answers_revealed: boolean;
  mastery_eligible: boolean;
  warning: string;
  question_reveals: AssessmentAnswerReveal[];
}

export interface BranchSuggestion {
  id: number;
  topic_id: number;
  parent_skill_id: number;
  title: string;
  focus: string;
  rationale: string;
  purpose: string;
  origin: string;
  status: string;
  accepted_branch_root_skill_id: number | null;
  created_at: string;
  updated_at: string;
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
  tree_stage: number;
  nodes: TopicProgressNode[];
}

export type LearningTab = 'overview' | 'lesson' | 'examples' | 'exercises' | 'quiz' | 'resources';

export interface TopicActionItem {
  skill_node_id: number | null;
  skill_name: string;
  action_type: string;
  title: string;
  description: string;
  tab: LearningTab;
}

export interface UnlockAnticipation {
  skill_node_id: number;
  skill_name: string;
  status_label: string;
  why_locked: string;
  steps: string[];
  next_step_skill_node_id: number | null;
  next_step_tab: LearningTab;
}

export interface TopicReminder {
  id: number;
  reminder_type: string;
  title: string;
  message: string;
  action_skill_node_id: number | null;
  action_tab: LearningTab;
  created_at: string;
}

export interface MilestoneEvent {
  id: number;
  milestone_type: string;
  title: string;
  message: string;
  skill_node_id: number | null;
  created_at: string;
}

export interface TopicRetentionLoop {
  topic_id: number;
  topic_name: string;
  cadence: 'daily' | 'weekly';
  plan_summary: string;
  next_actions: TopicActionItem[];
  learning_plan: TopicActionItem[];
  unlock_anticipation: UnlockAnticipation | null;
  reminder: TopicReminder | null;
  milestones: MilestoneEvent[];
  total_nodes: number;
  available_nodes: number;
  verified_nodes: number;
  completed_nodes: number;
  lessons_completed: number;
  assessments_taken: number;
  mastery_average: number;
  tree_stage: number;
  streak_days: number;
  activity_days_last_14: number;
  latest_activity_at: string | null;
  notebook_memory: NotebookMemorySignal;
  dev_unlock_enabled: boolean;
}

export interface NotebookMemorySignal {
  notes_count: number;
  reflections_logged: number;
  comparisons_logged: number;
  exemplars_saved: number;
  interpretations_logged: number;
  view_shifts_logged: number;
  next_threads_logged: number;
  prompt: string;
  growth_signal: string;
  recommended_lens: 'reflection' | 'comparison' | 'exemplar' | 'interpretation' | 'view_shift' | 'next_thread';
  recommended_lens_label: string;
  recommended_lens_reason: string;
  latest_note_title: string;
  latest_note_at: string | null;
  latest_note_skill_name: string | null;
}

export interface TopicJournalEntry {
  id: string;
  entry_type: 'note' | 'exercise' | 'module' | 'assessment' | 'milestone' | 'branch';
  title: string;
  description: string;
  skill_node_id: number | null;
  skill_name: string | null;
  occurred_at: string;
  importance: 'high' | 'medium' | 'low';
  evidence_strength: 'direct' | 'derived' | 'contextual';
  metadata: Record<string, unknown>;
}

export interface TopicJournalChapter {
  id: string;
  label: string;
  started_at: string;
  ended_at: string;
  entry_count: number;
  evidence_count: number;
  focus: string;
}

export interface TopicJournalSummary {
  total_entries: number;
  evidence_entries: number;
  notes_count: number;
  notes_created: number;
  notes_updated: number;
  lessons_completed: number;
  exercises_completed: number;
  artifacts_uploaded: number;
  assessments_taken: number;
  assessments_passed: number;
  milestones_reached: number;
  branches_accepted: number;
  branches_rejected: number;
  reflections_logged: number;
  comparisons_logged: number;
  exemplars_saved: number;
  interpretations_logged: number;
  view_shifts_logged: number;
  next_threads_logged: number;
  verified_nodes: number;
  total_nodes: number;
  mastery_average: number;
  latest_activity_at: string | null;
  reflection_prompt: string;
  growth_signal: string;
  recommended_lens: 'reflection' | 'comparison' | 'exemplar' | 'interpretation' | 'view_shift' | 'next_thread';
  recommended_lens_label: string;
  recommended_lens_reason: string;
  latest_note_title: string;
  latest_note_at: string | null;
  latest_note_skill_name: string | null;
}

export interface TopicJournal {
  topic_id: number;
  topic_name: string;
  summary: TopicJournalSummary;
  chapters: TopicJournalChapter[];
  entries: TopicJournalEntry[];
}

export interface UserTopicProgressSummary {
  topic_id: number;
  topic_name: string;
  total_nodes: number;
  verified_nodes: number;
  mastery_average: number;
  tree_stage: number;
  branch_count: number;
  notes_count: number;
  latest_activity_at: string | null;
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
