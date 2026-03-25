import {
  ChatReply,
  DocumentItem,
  ExternalResource,
  NoteType,
  PersonalNote,
  ProgressUpdateResult,
  Quiz,
  QuizSubmissionResult,
  RecommendationItem,
  Resource,
  SkillTree,
  Topic,
  TutorNoteSaveResult
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

  if (response.status === 204) {
    return undefined as T;
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

export async function deleteTopic(topicId: string | number, userId = 1): Promise<void> {
  await request(`/topics/${topicId}?user_id=${userId}&confirm=true`, {
    method: 'DELETE'
  });
}

export async function getSkillTree(topicId: string | number, userId = 1): Promise<SkillTree> {
  return request<SkillTree>(`/topics/${topicId}/skill-tree?user_id=${userId}`);
}

export async function listDocuments(topicId: string | number, userId = 1): Promise<DocumentItem[]> {
  const data = await request<{ documents: DocumentItem[] }>(`/topics/${topicId}/documents?user_id=${userId}`);
  return data.documents;
}

export async function deleteDocument(
  topicId: string | number,
  documentId: number,
  userId = 1
): Promise<void> {
  await request(`/topics/${topicId}/documents/${documentId}?user_id=${userId}`, {
    method: 'DELETE'
  });
}

export async function uploadRawNote(topicId: string | number, rawText: string, userId = 1): Promise<void> {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('raw_text', rawText);

  await request(`/topics/${topicId}/documents/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function uploadFileNote(topicId: string | number, file: File, userId = 1): Promise<void> {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('file', file);

  await request(`/topics/${topicId}/documents/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function listNotes(
  topicId: string | number,
  input?: { user_id?: number; skill_node_id?: number; query?: string }
): Promise<PersonalNote[]> {
  const params = new URLSearchParams();
  params.set('user_id', String(input?.user_id ?? 1));
  if (typeof input?.skill_node_id === 'number') params.set('skill_node_id', String(input.skill_node_id));
  if (input?.query?.trim()) params.set('query', input.query.trim());

  const data = await request<{ notes: PersonalNote[] }>(`/topics/${topicId}/notes?${params.toString()}`);
  return data.notes;
}

export async function createNote(input: {
  topic_id: number;
  user_id?: number;
  title?: string;
  body: string;
  note_type?: NoteType;
  skill_node_id?: number | null;
}): Promise<PersonalNote> {
  const query = `?user_id=${input.user_id ?? 1}`;
  return request<PersonalNote>(`/topics/${input.topic_id}/notes${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title ?? '',
      body: input.body,
      note_type: input.note_type ?? 'personal',
      skill_node_id: input.skill_node_id ?? null
    })
  });
}

export async function updateNote(input: {
  note_id: number;
  user_id?: number;
  title?: string;
  body?: string;
  note_type?: NoteType;
  skill_node_id?: number | null;
}): Promise<PersonalNote> {
  const query = `?user_id=${input.user_id ?? 1}`;
  return request<PersonalNote>(`/notes/${input.note_id}${query}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      body: input.body,
      note_type: input.note_type,
      skill_node_id: input.skill_node_id ?? null
    })
  });
}

export async function deleteNote(noteId: number, userId = 1): Promise<void> {
  await request(`/notes/${noteId}?user_id=${userId}`, {
    method: 'DELETE'
  });
}

export async function chatTopic(input: {
  topicId: string | number;
  message: string;
  user_id?: number;
  session_id?: number | null;
  skill_node_id?: number | null;
  include_personal_notes?: boolean;
  include_web_resources?: boolean;
}): Promise<ChatReply> {
  return request<ChatReply>(`/topics/${input.topicId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      message: input.message,
      session_id: input.session_id ?? null,
      skill_node_id: input.skill_node_id ?? null,
      include_personal_notes: input.include_personal_notes ?? false,
      include_web_resources: input.include_web_resources ?? false
    })
  });
}

export async function getRecommendations(
  topicId: string | number,
  userId = 1,
  refresh = false
): Promise<RecommendationItem[]> {
  const data = await request<{ recommendations: RecommendationItem[] }>(
    `/topics/${topicId}/recommendations?user_id=${userId}${refresh ? '&refresh=true' : ''}`
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

export async function createDeepDiveBranch(input: {
  skillId: number;
  user_id?: number;
  focus?: string;
  branch_size?: number;
}): Promise<SkillTree> {
  return request<SkillTree>(`/skills/${input.skillId}/deep-dive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      focus: input.focus ?? '',
      branch_size: input.branch_size ?? 3
    })
  });
}

export async function saveTutorResponseToNotes(input: {
  topic_id: number;
  session_id: number;
  message_id: number;
  user_id?: number;
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
        user_id: input.user_id ?? 1,
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
  user_id?: number;
  mode: 'full' | 'excerpt' | 'summary';
  body?: string;
  tags?: string[];
}): Promise<TutorNoteSaveResult> {
  return request<TutorNoteSaveResult>(`/notes/${input.note_id}/append-tutor-response`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: input.user_id ?? 1,
      session_id: input.session_id,
      message_id: input.message_id,
      mode: input.mode,
      body: input.body ?? '',
      tags: input.tags ?? []
    })
  });
}
