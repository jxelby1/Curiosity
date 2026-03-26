import { clearAuthToken, getAuthToken, setAuthToken } from '@/lib/auth';
import {
  Assessment,
  AssessmentRevealResult,
  AssessmentAttempt,
  AssessmentResponseInput,
  AssessmentSubmissionResult,
  AssessmentStyle,
  BranchSuggestion,
  AuthUser,
  CourseDepth,
  ChatReply,
  DocumentItem,
  ExternalResource,
  ForgotPasswordResult,
  NoteType,
  PersonalNote,
  ProgressUpdateResult,
  Quiz,
  QuizSubmissionResult,
  RecommendationItem,
  Resource,
  SkillTree,
  Topic,
  TopicInitializationResult,
  TopicInitializationStatus,
  TopicProgress,
  TutorNoteSaveResult,
  ResetPasswordResult,
  StartingSkillLevel,
  TopicRetentionLoop,
  UserProgressSummary
} from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api';

type RequestOptions = RequestInit & {
  auth?: boolean;
};

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const authEnabled = options?.auth !== false;
  const token = authEnabled ? getAuthToken() : null;
  const headers = new Headers(options?.headers || {});

  if (authEnabled && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: 'no-store'
  });

  if (!response.ok) {
    const detail = await response.text();
    const message = detail || `Request failed (${response.status})`;
    if (response.status === 401) {
      throw new Error(`Unauthorized: ${message}`);
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function register(input: {
  email: string;
  password: string;
  display_name: string;
}): Promise<string> {
  const data = await request<{ access_token: string }>('/auth/register', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  setAuthToken(data.access_token);
  return data.access_token;
}

export async function login(input: { email: string; password: string }): Promise<string> {
  const data = await request<{ access_token: string }>('/auth/login', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  setAuthToken(data.access_token);
  return data.access_token;
}

export async function logout(): Promise<void> {
  try {
    await request('/auth/logout', { method: 'POST' });
  } catch {
    // ignore logout request failures and always clear local token
  }
  clearAuthToken();
}

export async function getMe(): Promise<AuthUser> {
  return request<AuthUser>('/auth/me');
}

export async function forgotPassword(email: string): Promise<ForgotPasswordResult> {
  return request<ForgotPasswordResult>('/auth/forgot-password', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
}

export async function resetPassword(input: { token: string; new_password: string }): Promise<ResetPasswordResult> {
  return request<ResetPasswordResult>('/auth/reset-password', {
    method: 'POST',
    auth: false,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
}

export async function listTopics(): Promise<Topic[]> {
  const data = await request<{ topics: Topic[] }>('/topics');
  return data.topics;
}

export async function createTopic(input: {
  name: string;
  description?: string;
  goal?: string;
  course_depth?: CourseDepth;
  starting_skill_level?: StartingSkillLevel;
  assessment_styles?: AssessmentStyle[];
}): Promise<Topic> {
  return request<Topic>('/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name,
      description: input.description ?? '',
      goal: input.goal ?? '',
      course_depth: input.course_depth ?? 'standard',
      starting_skill_level: input.starting_skill_level ?? 'beginner',
      assessment_styles: input.assessment_styles ?? []
    })
  });
}

export async function createTopicAndInitialize(input: {
  name: string;
  description?: string;
  goal?: string;
  course_depth?: CourseDepth;
  starting_skill_level?: StartingSkillLevel;
  assessment_styles?: AssessmentStyle[];
}): Promise<TopicInitializationResult> {
  return request<TopicInitializationResult>('/topics/create-and-initialize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name,
      description: input.description ?? '',
      goal: input.goal ?? '',
      course_depth: input.course_depth ?? 'standard',
      starting_skill_level: input.starting_skill_level ?? 'beginner',
      assessment_styles: input.assessment_styles ?? []
    })
  });
}

export async function getTopicInitializationStatus(topicId: string | number): Promise<TopicInitializationStatus> {
  return request<TopicInitializationStatus>(`/topics/${topicId}/initialization-status`);
}

export async function startTopicInitialization(
  topicId: string | number,
  force = false
): Promise<TopicInitializationStatus> {
  const query = force ? '?force=true' : '';
  return request<TopicInitializationStatus>(`/topics/${topicId}/initialize${query}`, {
    method: 'POST'
  });
}

export async function deleteTopic(topicId: string | number): Promise<void> {
  await request(`/topics/${topicId}?confirm=true`, {
    method: 'DELETE'
  });
}

export async function getSkillTree(topicId: string | number): Promise<SkillTree> {
  return request<SkillTree>(`/topics/${topicId}/skill-tree`);
}

export async function listDocuments(topicId: string | number): Promise<DocumentItem[]> {
  const data = await request<{ documents: DocumentItem[] }>(`/topics/${topicId}/documents`);
  return data.documents;
}

export async function deleteDocument(topicId: string | number, documentId: number): Promise<void> {
  await request(`/topics/${topicId}/documents/${documentId}`, {
    method: 'DELETE'
  });
}

export async function uploadRawNote(topicId: string | number, rawText: string): Promise<void> {
  const formData = new FormData();
  formData.append('raw_text', rawText);

  await request(`/topics/${topicId}/documents/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function uploadFileNote(topicId: string | number, file: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);

  await request(`/topics/${topicId}/documents/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function listNotes(
  topicId: string | number,
  input?: { skill_node_id?: number; query?: string }
): Promise<PersonalNote[]> {
  const params = new URLSearchParams();
  if (typeof input?.skill_node_id === 'number') params.set('skill_node_id', String(input.skill_node_id));
  if (input?.query?.trim()) params.set('query', input.query.trim());
  const query = params.toString();
  const suffix = query ? `?${query}` : '';

  const data = await request<{ notes: PersonalNote[] }>(`/topics/${topicId}/notes${suffix}`);
  return data.notes;
}

export async function createNote(input: {
  topic_id: number;
  title?: string;
  body: string;
  note_type?: NoteType;
  skill_node_id?: number | null;
  tags?: string[];
}): Promise<PersonalNote> {
  return request<PersonalNote>(`/topics/${input.topic_id}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title ?? '',
      body: input.body,
      note_type: input.note_type ?? 'personal',
      skill_node_id: input.skill_node_id ?? null,
      tags: input.tags ?? []
    })
  });
}

export async function updateNote(input: {
  note_id: number;
  title?: string;
  body?: string;
  note_type?: NoteType;
  skill_node_id?: number | null;
  tags?: string[];
}): Promise<PersonalNote> {
  return request<PersonalNote>(`/notes/${input.note_id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      body: input.body,
      note_type: input.note_type,
      skill_node_id: input.skill_node_id ?? null,
      tags: input.tags
    })
  });
}

export async function deleteNote(noteId: number): Promise<void> {
  await request(`/notes/${noteId}`, {
    method: 'DELETE'
  });
}

export async function chatTopic(input: {
  topicId: string | number;
  message: string;
  session_id?: number | null;
  skill_node_id?: number | null;
  include_personal_notes?: boolean;
  include_web_resources?: boolean;
}): Promise<ChatReply> {
  return request<ChatReply>(`/topics/${input.topicId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: input.message,
      session_id: input.session_id ?? null,
      skill_node_id: input.skill_node_id ?? null,
      include_personal_notes: input.include_personal_notes ?? false,
      include_web_resources: input.include_web_resources ?? false
    })
  });
}

export async function getRecommendations(topicId: string | number, refresh = false): Promise<RecommendationItem[]> {
  const data = await request<{ recommendations: RecommendationItem[] }>(
    `/topics/${topicId}/recommendations${refresh ? '?refresh=true' : ''}`
  );
  return data.recommendations;
}

export async function generateResource(input: {
  skillId: number;
  kind: 'lesson' | 'examples' | 'exercises';
  regenerate?: boolean;
}): Promise<Resource> {
  const query = input.regenerate ? '?regenerate=true' : '';
  return request<Resource>(`/skills/${input.skillId}/resources/generate${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind: input.kind
    })
  });
}

export async function getExternalResources(skillId: number): Promise<ExternalResource[]> {
  const data = await request<{ resources: ExternalResource[] }>(`/skills/${skillId}/resources/external`);
  return data.resources;
}

export async function generateAssessment(input: {
  topic_id: number;
  skill_node_id: number;
  question_count?: number;
  regenerate?: boolean;
  assessment_styles?: AssessmentStyle[];
}): Promise<Assessment> {
  const payload: Record<string, unknown> = {
    topic_id: input.topic_id,
    skill_node_id: input.skill_node_id,
    regenerate: input.regenerate ?? false
  };
  if (typeof input.question_count === 'number') {
    payload.question_count = input.question_count;
  }
  if (input.assessment_styles && input.assessment_styles.length > 0) {
    payload.assessment_styles = input.assessment_styles;
  }
  return request<Assessment>('/assessments/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function getAssessment(assessmentId: number): Promise<Assessment> {
  return request<Assessment>(`/assessments/${assessmentId}`);
}

export async function revealAssessmentAnswers(assessmentId: number): Promise<AssessmentRevealResult> {
  return request<AssessmentRevealResult>(`/assessments/${assessmentId}/reveal-answers`, {
    method: 'POST',
  });
}

export async function submitAssessment(
  assessmentId: number,
  responses: AssessmentResponseInput[]
): Promise<AssessmentSubmissionResult> {
  return request<AssessmentSubmissionResult>(`/assessments/${assessmentId}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ responses })
  });
}

export async function getAssessmentAttempt(attemptId: number): Promise<AssessmentAttempt> {
  return request<AssessmentAttempt>(`/assessment-attempts/${attemptId}`);
}

export async function getTopicProgress(topicId: number | string): Promise<TopicProgress> {
  return request<TopicProgress>(`/topics/${topicId}/progress`);
}

export async function getMyProgressSummary(): Promise<UserProgressSummary> {
  return request<UserProgressSummary>('/users/me/progress-summary');
}

export async function getTopicRetentionLoop(topicId: number | string): Promise<TopicRetentionLoop> {
  return request<TopicRetentionLoop>(`/topics/${topicId}/retention-loop`);
}

export async function markMilestoneSeen(topicId: number | string, milestoneId: number): Promise<void> {
  await request(`/topics/${topicId}/milestones/${milestoneId}/seen`, {
    method: 'POST'
  });
}

export async function dismissTopicReminder(topicId: number | string, reminderId: number): Promise<void> {
  await request(`/topics/${topicId}/reminders/${reminderId}/dismiss`, {
    method: 'POST'
  });
}

export async function generateQuiz(
  skillId: number,
  numQuestions = 6,
  regenerate = false
): Promise<Quiz> {
  const query = regenerate ? '?regenerate=true' : '';
  return request<Quiz>(`/skills/${skillId}/quiz/generate${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num_questions: numQuestions })
  });
}

export async function submitQuiz(assessmentId: number, answers: number[]): Promise<QuizSubmissionResult> {
  return request<QuizSubmissionResult>(`/assessments/${assessmentId}/submit-quiz`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers })
  });
}

export async function updateProgress(input: {
  skillId: number;
  action: 'complete_lesson' | 'complete_exercises';
}): Promise<ProgressUpdateResult> {
  return request<ProgressUpdateResult>(`/skills/${input.skillId}/progress/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: input.action
    })
  });
}

export async function forceUnlockSkill(skillId: number): Promise<ProgressUpdateResult> {
  return request<ProgressUpdateResult>(`/skills/${skillId}/force-unlock`, {
    method: 'POST'
  });
}

export async function createDeepDiveBranch(input: {
  skillId: number;
  focus?: string;
  branch_size?: number;
  purpose?: 'exploration' | 'specialization' | 'enrichment' | 'remediation' | 'assessment_prep' | 'project';
}): Promise<SkillTree> {
  return request<SkillTree>(`/skills/${input.skillId}/deep-dive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      focus: input.focus ?? '',
      branch_size: input.branch_size ?? 3,
      purpose: input.purpose ?? 'exploration'
    })
  });
}

export async function listBranchSuggestions(
  skillId: number,
  statusFilter: 'pending' | 'accepted' | 'rejected' | 'all' = 'pending'
): Promise<BranchSuggestion[]> {
  const data = await request<{ suggestions: BranchSuggestion[] }>(
    `/skills/${skillId}/branch-suggestions?status_filter=${statusFilter}`
  );
  return data.suggestions;
}

export async function generateBranchSuggestions(input: {
  skillId: number;
  limit?: number;
  trigger_event?: 'manual' | 'assessment_performance' | 'completion' | 'interest';
}): Promise<BranchSuggestion[]> {
  const data = await request<{ suggestions: BranchSuggestion[] }>(`/skills/${input.skillId}/branch-suggestions/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      limit: input.limit ?? 2,
      trigger_event: input.trigger_event ?? 'manual',
    }),
  });
  return data.suggestions;
}

export async function acceptBranchSuggestion(input: {
  suggestionId: number;
  branch_size?: number;
}): Promise<SkillTree> {
  const query = `?branch_size=${input.branch_size ?? 3}`;
  return request<SkillTree>(`/branch-suggestions/${input.suggestionId}/accept${query}`, {
    method: 'POST',
  });
}

export async function rejectBranchSuggestion(suggestionId: number): Promise<BranchSuggestion> {
  return request<BranchSuggestion>(`/branch-suggestions/${suggestionId}/reject`, {
    method: 'POST',
  });
}

export async function saveTutorResponseToNotes(input: {
  topic_id: number;
  session_id: number;
  message_id: number;
  mode: 'full' | 'excerpt' | 'summary';
  title?: string;
  body?: string;
  tags?: string[];
  note_type?: NoteType;
  skill_node_id?: number | null;
}): Promise<TutorNoteSaveResult> {
  return request<TutorNoteSaveResult>(
    `/topics/${input.topic_id}/chat/${input.session_id}/messages/${input.message_id}/save-note`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: input.mode,
        title: input.title ?? '',
        body: input.body ?? '',
        tags: input.tags ?? [],
        note_type: input.note_type ?? 'summary',
        skill_node_id: input.skill_node_id ?? null
      })
    }
  );
}

export async function appendTutorResponseToExistingNote(input: {
  note_id: number;
  session_id: number;
  message_id: number;
  mode: 'full' | 'excerpt' | 'summary';
  body?: string;
  tags?: string[];
}): Promise<TutorNoteSaveResult> {
  return request<TutorNoteSaveResult>(`/notes/${input.note_id}/append-tutor-response`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: input.session_id,
      message_id: input.message_id,
      mode: input.mode,
      body: input.body ?? '',
      tags: input.tags ?? []
    })
  });
}
