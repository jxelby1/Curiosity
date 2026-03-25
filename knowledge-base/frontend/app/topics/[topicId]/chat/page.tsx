'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import {
  appendTutorResponseToExistingNote,
  chatTopic,
  getSkillTree,
  listNotes,
  saveTutorResponseToNotes
} from '@/lib/api';
import { readSkillTreeCache, writeSkillTreeCache } from '@/lib/cache';
import { PersonalNote, SkillTree, TutorStructuredAnswer } from '@/lib/types';
import { AssistantMessage, UserMessage } from '@/components/chat-message';
import { TopicHeader } from '@/components/topic-header';
import { ChatWorkspaceSkeleton } from '@/components/page-skeletons';

type ChatItem = {
  role: 'user' | 'assistant';
  content: string;
  messageId?: number;
  structured?: TutorStructuredAnswer | null;
  citations?: Array<{ title: string; url: string; snippet: string }>;
  contextUsage?: { document_chunks: number; personal_notes: number; external_resources: number } | null;
};

const CHAT_MESSAGE_MAX = 600;
type RetrievalMode = 'knowledge_base' | 'knowledge_plus_web';
type SaveMode = 'full' | 'excerpt' | 'summary' | 'append';

export default function TopicChatPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;
  const cachedTree = readSkillTreeCache(topicId);

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(cachedTree?.nodes?.[0]?.id ?? null);
  const [includePersonalNotes, setIncludePersonalNotes] = useState(false);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>('knowledge_base');

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');
  const [topicNotes, setTopicNotes] = useState<PersonalNote[]>([]);

  const [activeSaveMessageId, setActiveSaveMessageId] = useState<number | null>(null);
  const [saveMode, setSaveMode] = useState<SaveMode>('full');
  const [saveTitle, setSaveTitle] = useState('');
  const [saveBody, setSaveBody] = useState('');
  const [saveTagsInput, setSaveTagsInput] = useState('');
  const [appendNoteId, setAppendNoteId] = useState<string>('');

  const [loadingTree, setLoadingTree] = useState(!cachedTree);
  const [sending, setSending] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState('');
  const [error, setError] = useState('');

  const loadTree = useCallback(async () => {
    try {
      const data = await getSkillTree(topicId);
      setTree(data);
      writeSkillTreeCache(topicId, data);

      if (!selectedSkillId && data.nodes.length) {
        const unlocked = data.nodes.find((node) => node.status !== 'locked') || data.nodes[0];
        setSelectedSkillId(unlocked.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topic context');
    } finally {
      setLoadingTree(false);
    }
  }, [selectedSkillId, topicId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const loadTopicNotes = useCallback(async () => {
    try {
      const notes = await listNotes(topicId);
      setTopicNotes(notes);
    } catch {
      // keep chat usable even if notes list fails
    }
  }, [topicId]);

  useEffect(() => {
    loadTopicNotes();
  }, [loadTopicNotes]);

  const selectedSkill = useMemo(() => {
    if (!tree || !selectedSkillId) return null;
    return tree.nodes.find((node) => node.id === selectedSkillId) || null;
  }, [tree, selectedSkillId]);

  async function onSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim()) return;
    if (input.trim().length > CHAT_MESSAGE_MAX) {
      setError(`Message must be ${CHAT_MESSAGE_MAX} characters or less.`);
      return;
    }

    const message = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setSending(true);
    setError('');

    try {
      const reply = await chatTopic({
        topicId,
        message,
        session_id: sessionId,
        skill_node_id: selectedSkillId,
        include_personal_notes: includePersonalNotes,
        include_web_resources: retrievalMode === 'knowledge_plus_web'
      });

      setSessionId(reply.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          messageId: reply.assistant_message_id,
          content: reply.answer,
          structured: reply.structured_answer,
          citations: reply.citations,
          contextUsage: reply.context_usage
        }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  }

  function openSavePanel(item: ChatItem, nextMode: SaveMode) {
    if (!item.messageId) return;
    const selectedText = typeof window !== 'undefined' ? window.getSelection()?.toString().trim() || '' : '';
    setActiveSaveMessageId(item.messageId);
    setSaveMode(nextMode);
    setSaveTitle('');
    setSaveTagsInput('');
    setSaveFeedback('');
    setAppendNoteId(topicNotes[0] ? String(topicNotes[0].id) : '');

    if (nextMode === 'full') {
      setSaveBody(item.content);
      return;
    }
    if (nextMode === 'excerpt') {
      setSaveBody(selectedText);
      return;
    }
    if (nextMode === 'append') {
      setSaveBody(selectedText || item.content);
      return;
    }
    setSaveBody('');
  }

  async function onSaveTutorContent(item: ChatItem) {
    if (!item.messageId || !sessionId) {
      setError('Cannot save this message yet.');
      return;
    }

    const tags = saveTagsInput
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);

    setSavingNote(true);
    setError('');
    setSaveFeedback('');
    try {
      if (saveMode === 'append') {
        if (!appendNoteId) {
          setError('Select a note to append to.');
          return;
        }
        const result = await appendTutorResponseToExistingNote({
          note_id: Number(appendNoteId),
          session_id: sessionId,
          message_id: item.messageId,
          mode: saveBody.trim() ? 'excerpt' : 'summary',
          body: saveBody,
          tags
        });
        setSaveFeedback(result.duplicate_warning || 'Tutor content appended to note.');
      } else {
        const mode = saveMode === 'summary' ? 'summary' : saveMode;
        const result = await saveTutorResponseToNotes({
          topic_id: Number(topicId),
          session_id: sessionId,
          message_id: item.messageId,
          mode,
          title: saveTitle,
          body: saveBody,
          tags,
          note_type: saveMode === 'summary' ? 'summary' : 'lesson',
          skill_node_id: selectedSkillId
        });
        setSaveFeedback(result.duplicate_warning || 'Tutor response saved to notes.');
      }

      await loadTopicNotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save tutor content');
    } finally {
      setSavingNote(false);
    }
  }

  if (!tree && loadingTree) return <ChatWorkspaceSkeleton />;

  if (!tree) {
    return (
      <main className="mx-auto max-w-6xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Topic not found.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-6 md:p-10">
      <TopicHeader topicId={topicId} topicName={tree.topic.name} subtitle="Focused tutoring chat workspace" />

      <section className="panel grid min-h-[72vh] gap-0 overflow-hidden lg:grid-cols-[0.85fr_2fr]">
        <aside className="border-b border-black/10 bg-white p-4 lg:border-b-0 lg:border-r">
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Context Skill</h2>
          <div className="mt-3 space-y-2">
            {tree.nodes.map((node) => (
              <button
                key={node.id}
                className={`w-full rounded-md border p-2 text-left text-sm ${
                  selectedSkillId === node.id ? 'border-ink bg-paper/60' : 'border-black/10 bg-white'
                }`}
                onClick={() => setSelectedSkillId(node.id)}
                type="button"
              >
                <p className="font-semibold">{node.name}</p>
                <p className="muted mt-1 text-xs">{node.status.replace('_', ' ')} · {node.progress_state.replace('_', ' ')}</p>
              </button>
            ))}
          </div>
        </aside>

        <article className="flex flex-col p-4 md:p-6">
          <div className="mb-3 rounded-md border border-black/10 bg-white p-3 text-sm">
            <p className="font-medium">Active context: {selectedSkill?.name || 'General topic context'}</p>
            <div className="mt-2 space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <button
                  type="button"
                  className={`rounded-md border px-2.5 py-1 ${
                    retrievalMode === 'knowledge_base'
                      ? 'border-ink bg-ink text-white'
                      : 'border-black/15 bg-white text-black'
                  }`}
                  onClick={() => setRetrievalMode('knowledge_base')}
                >
                  Learn from my knowledge base
                </button>
                <button
                  type="button"
                  className={`rounded-md border px-2.5 py-1 ${
                    retrievalMode === 'knowledge_plus_web'
                      ? 'border-ink bg-ink text-white'
                      : 'border-black/15 bg-white text-black'
                  }`}
                  onClick={() => setRetrievalMode('knowledge_plus_web')}
                >
                  Include current web resources
                </button>
              </div>
              <div className="flex items-center justify-between gap-3">
                <p className="muted text-xs">
                  Internal knowledge (documents, skill graph, history, generated lessons) is always used first.
                </p>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={includePersonalNotes}
                    onChange={(event) => setIncludePersonalNotes(event.target.checked)}
                  />
                  <span>Use personal notes</span>
                </label>
              </div>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-black/10 bg-white p-4">
            {messages.length === 0 && (
              <p className="muted rounded-md border border-dashed border-black/15 bg-paper/50 p-4 text-sm">
                Ask a question to start your tutoring session.
              </p>
            )}

            {messages.map((item, index) => (
              <div key={index} className={item.role === 'user' ? 'text-right' : ''}>
                {item.role === 'user' ? (
                  <UserMessage text={item.content} />
                ) : (
                  <div className="space-y-2">
                    <AssistantMessage
                      text={item.content}
                      structured={item.structured}
                      citations={item.citations}
                      contextUsage={item.contextUsage}
                      actionSlot={
                        item.messageId ? (
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="rounded-md border border-black/20 bg-white px-2.5 py-1 text-xs"
                              onClick={() => openSavePanel(item, 'full')}
                            >
                              Save to notes
                            </button>
                            <button
                              type="button"
                              className="rounded-md border border-black/20 bg-white px-2.5 py-1 text-xs"
                              onClick={() => openSavePanel(item, 'excerpt')}
                            >
                              Save selected excerpt
                            </button>
                            <button
                              type="button"
                              className="rounded-md border border-black/20 bg-white px-2.5 py-1 text-xs"
                              onClick={() => openSavePanel(item, 'summary')}
                            >
                              Save summary to notes
                            </button>
                            <button
                              type="button"
                              className="rounded-md border border-black/20 bg-white px-2.5 py-1 text-xs"
                              onClick={() => openSavePanel(item, 'append')}
                            >
                              Append to existing note
                            </button>
                          </div>
                        ) : null
                      }
                    />
                    {activeSaveMessageId === item.messageId && (
                      <div className="max-w-3xl rounded-xl border border-black/15 bg-white p-3">
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                          <span className="badge">Save mode: {saveMode}</span>
                          <span className="text-black/60">Notes in topic: {topicNotes.length}</span>
                        </div>

                        {saveMode === 'append' && (
                          <select
                            value={appendNoteId}
                            onChange={(event) => setAppendNoteId(event.target.value)}
                            className="mb-2 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                          >
                            <option value="">Select note to append</option>
                            {topicNotes.map((note) => (
                              <option key={note.id} value={note.id}>
                                #{note.id} {note.title}
                              </option>
                            ))}
                          </select>
                        )}

                        {saveMode !== 'append' && (
                          <input
                            value={saveTitle}
                            onChange={(event) => setSaveTitle(event.target.value)}
                            className="mb-2 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                            placeholder="Note title (optional)"
                            maxLength={120}
                          />
                        )}

                        <textarea
                          value={saveBody}
                          onChange={(event) => setSaveBody(event.target.value)}
                          className="min-h-[120px] w-full rounded-md border border-black/15 bg-white p-3 text-sm"
                          placeholder={
                            saveMode === 'summary'
                              ? 'Optional: edit/add summary text, or leave blank to auto-generate summary.'
                              : 'Edit content before saving.'
                          }
                          maxLength={8000}
                        />

                        <input
                          value={saveTagsInput}
                          onChange={(event) => setSaveTagsInput(event.target.value)}
                          className="mt-2 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                          placeholder="Tags (comma separated)"
                        />

                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className="rounded-md bg-ink px-3 py-1.5 text-xs text-white disabled:opacity-60"
                            onClick={() => onSaveTutorContent(item)}
                            disabled={savingNote}
                          >
                            {savingNote ? 'Saving...' : saveMode === 'append' ? 'Append now' : 'Save now'}
                          </button>
                          <button
                            type="button"
                            className="rounded-md border border-black/20 bg-white px-3 py-1.5 text-xs"
                            onClick={() => setActiveSaveMessageId(null)}
                          >
                            Cancel
                          </button>
                          {saveFeedback && <p className="text-xs text-emerald-700">{saveFeedback}</p>}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {sending && (
              <div>
                <div className="inline-flex items-center gap-2 rounded-2xl border border-black/10 bg-paper/60 px-3 py-2 text-xs text-black/70">
                  <span className="inline-block h-2 w-2 rounded-full bg-ink/70" />
                  <span>Composing tutor response...</span>
                </div>
              </div>
            )}
          </div>

          <form className="mt-4 flex gap-2" onSubmit={onSend}>
            <div className="flex-1 space-y-1">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
                placeholder="Ask about concept gaps, debugging strategy, or next step..."
                maxLength={CHAT_MESSAGE_MAX}
              />
              <p className="text-right text-xs text-black/60">
                {input.length}/{CHAT_MESSAGE_MAX}
              </p>
            </div>
            <button className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60" disabled={sending}>
              {sending ? 'Sending...' : 'Send'}
            </button>
          </form>
        </article>
      </section>

      {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
