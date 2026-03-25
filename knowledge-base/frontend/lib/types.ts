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
  mastery_estimate: number;
  status: SkillStatus;
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

export interface NoteItem {
  id: number;
  filename: string;
  content_type: string;
  created_at: string;
}

export interface ChatReply {
  session_id: number;
  answer: string;
  used_chunks: string[];
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
