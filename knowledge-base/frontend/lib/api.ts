import {
  ChatReply,
  ExternalResource,
  NoteItem,
  ProgressUpdateResult,
  Quiz,
  QuizSubmissionResult,
  RecommendationItem,
  Resource,
  SkillTree,
  Topic
} from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.headers || {})
    },
    cache: 'no-store'
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }

  return (await response.json()) as T;
}

export async function listTopics(userId = 1): Promise<Topic[]> {
  const data = await request<{ topics: Topic[] }>(`/topics?user_id=${userId}`);
  return data.topics;
}

export async function createTopic(input: {
  user_id?: number;
  name: string;
  description?: string;
  goal?: string;
}): Promise<Topic> {
  return request<Topic>('/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      name: input.name,
      description: input.description ?? '',
      goal: input.goal ?? ''
    })
  });
}

export async function getSkillTree(topicId: string | number, userId = 1): Promise<SkillTree> {
  return request<SkillTree>(`/topics/${topicId}/skill-tree?user_id=${userId}`);
}

export async function listNotes(topicId: string | number, userId = 1): Promise<NoteItem[]> {
  const data = await request<{ documents: NoteItem[] }>(`/topics/${topicId}/notes?user_id=${userId}`);
  return data.documents;
}

export async function uploadRawNote(topicId: string | number, rawText: string, userId = 1): Promise<void> {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('raw_text', rawText);

  await request(`/topics/${topicId}/notes/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function uploadFileNote(topicId: string | number, file: File, userId = 1): Promise<void> {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('file', file);

  await request(`/topics/${topicId}/notes/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function chatTopic(input: {
  topicId: string | number;
  message: string;
  user_id?: number;
  session_id?: number | null;
  skill_node_id?: number | null;
}): Promise<ChatReply> {
  return request<ChatReply>(`/topics/${input.topicId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      message: input.message,
      session_id: input.session_id ?? null,
      skill_node_id: input.skill_node_id ?? null
    })
  });
}

export async function getRecommendations(topicId: string | number, userId = 1): Promise<RecommendationItem[]> {
  const data = await request<{ recommendations: RecommendationItem[] }>(
    `/topics/${topicId}/recommendations?user_id=${userId}`
  );
  return data.recommendations;
}

export async function generateResource(input: {
  skillId: number;
  kind: 'lesson' | 'examples' | 'exercises';
  user_id?: number;
  regenerate?: boolean;
}): Promise<Resource> {
  const query = input.regenerate ? '?regenerate=true' : '';
  return request<Resource>(`/skills/${input.skillId}/resources/generate${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      kind: input.kind
    })
  });
}

export async function getExternalResources(skillId: number, userId = 1): Promise<ExternalResource[]> {
  const data = await request<{ resources: ExternalResource[] }>(
    `/skills/${skillId}/resources/external?user_id=${userId}`
  );
  return data.resources;
}

export async function generateQuiz(
  skillId: number,
  userId = 1,
  numQuestions = 3,
  regenerate = false
): Promise<Quiz> {
  const query = regenerate ? '?regenerate=true' : '';
  return request<Quiz>(`/skills/${skillId}/quiz/generate${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, num_questions: numQuestions })
  });
}

export async function submitQuiz(
  assessmentId: number,
  answers: number[],
  userId = 1
): Promise<QuizSubmissionResult> {
  return request<QuizSubmissionResult>(`/assessments/${assessmentId}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, answers })
  });
}

export async function updateProgress(input: {
  skillId: number;
  action: 'complete_lesson' | 'complete_exercises';
  user_id?: number;
}): Promise<ProgressUpdateResult> {
  return request<ProgressUpdateResult>(`/skills/${input.skillId}/progress/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      action: input.action
    })
  });
}
