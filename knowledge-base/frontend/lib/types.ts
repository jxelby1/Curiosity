export type SkillStatus = 'locked' | 'available' | 'in_progress' | 'mastered';

export interface Topic {
  id: number;
  user_id: number;
  name: string;
  description: string;
  goal: string;
  created_at: string;
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
  progress_state: 'not_started' | 'learning' | 'completed' | 'verified';
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

export type NoteType = 'personal' | 'lesson' | 'summary' | 'reflection' | 'reminder';

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
  feedback: Array<{
    question_id: string;
    correct: boolean;
    expected_index: number;
    user_index: number;
    explanation: string;
  }>;
  updated_mastery: number;
  updated_status: SkillStatus;
  updated_progress_state: 'not_started' | 'learning' | 'completed' | 'verified';
}

export interface ProgressUpdateResult {
  skill_node_id: number;
  mastery: number;
  status: SkillStatus;
  progress_state: 'not_started' | 'learning' | 'completed' | 'verified';
}
