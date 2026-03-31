'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import {
  appendTutorResponseToExistingNote,
  chatTopic,
  getSkillTree,
  listNotes,
  saveTutorResponseToNotes,
} from '@/lib/api';
import { readSkillTreeCache, writeSkillTreeCache } from '@/lib/cache';
import { formatDisplayTag } from '@/lib/display-format';
import { getNotebookLensOption, NOTEBOOK_LENS_OPTIONS, NotebookLens } from '@/lib/notebook';
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
type SaveMode = 'excerpt' | 'summary' | 'append';

export default function TopicChatPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;
  const cachedTree = readSkillTreeCache(topicId);

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(cachedTree?.nodes?.[0]?.id ?? null);
  const [includeNotebookMemory, setIncludeNotebookMemory] = useState(true);
  const [allowWebSources, setAllowWebSources] = useState(false);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');
  const [topicNotes, setTopicNotes] = useState<PersonalNote[]>([]);

  const [activeSaveMessageId, setActiveSaveMessageId] = useState<number | null>(null);
  const [saveMode, setSaveMode] = useState<SaveMode>('summary');
  const [saveLens, setSaveLens] = useState<NotebookLens>('reflection');
  const [saveTitle, setSaveTitle] = useState('');
  const [saveBody, setSaveBody] = useState('');
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
      // keep dialogue usable even if notes fail to load
    }
  }, [topicId]);

  useEffect(() => {
    loadTopicNotes();
  }, [loadTopicNotes]);

  const selectedSkill = useMemo(() => {
    if (!tree || !selectedSkillId) return null;
    return tree.nodes.find((node) => node.id === selectedSkillId) || null;
  }, [tree, selectedSkillId]);

  const selectableNodes = useMemo(() => {
    if (!tree) return [];
    const unlocked = tree.nodes.filter((node) => node.status !== 'locked');
    return unlocked.length > 0 ? unlocked : tree.nodes;
  }, [tree]);

  const saveLensOption = useMemo(() => getNotebookLensOption(saveLens), [saveLens]);
  const promptStarters = useMemo(() => {
    const focus = selectedSkill?.name || tree?.topic.name || 'this study';
    return [
      `Help me interpret ${focus} more clearly.`,
      `What should I notice, compare, or practice next in ${focus}?`,
      `Give me grounded context for ${focus} without losing the main thread.`,
      `Turn the key insight from ${focus} into a notebook reflection.`,
    ];
  }, [selectedSkill?.name, tree?.topic.name]);

  const saveBodyPlaceholder =
    saveMode === 'append'
      ? 'Choose what to append, or leave the full passage as-is.'
      : `Optional: shape this capture in your own words.\n\n${saveLensOption.starter}`;

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
        include_personal_notes: includeNotebookMemory,
        include_web_resources: allowWebSources,
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
          contextUsage: reply.context_usage,
        },
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
    setSaveLens('reflection');
    setSaveTitle('');
    setSaveFeedback('');
    setAppendNoteId(topicNotes[0] ? String(topicNotes[0].id) : '');

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

  function applySaveLens(tag: NotebookLens) {
    const lens = getNotebookLensOption(tag);
    setSaveLens(tag);
    setSaveTitle((prev) => prev || lens.promptTitle);
  }

  async function onSaveTutorContent(item: ChatItem) {
    if (!item.messageId || !sessionId) {
      setError('Cannot save this message yet.');
      return;
    }

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
          tags: [],
        });
        setSaveFeedback(result.duplicate_warning || 'Dialogue response appended to notebook entry.');
      } else {
        const result = await saveTutorResponseToNotes({
          topic_id: Number(topicId),
          session_id: sessionId,
          message_id: item.messageId,
          mode: saveMode,
          title: saveTitle || saveLensOption.promptTitle,
          body: saveBody,
          tags: [saveLensOption.tag],
          note_type: saveLensOption.noteType,
          skill_node_id: selectedSkillId,
        });
        setSaveFeedback(result.duplicate_warning || 'Dialogue response saved to notebook.');
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
      <TopicHeader
        topicId={topicId}
        topicName={tree.topic.name}
        subtitle="Dialogue for interpretation, reflection, and notebook-ready insight"
      />

      <section className="panel grid min-h-[72vh] gap-0 overflow-hidden lg:grid-cols-[0.9fr_2fr]">
        <aside className="border-b border-black/10 bg-white p-4 lg:border-b-0 lg:border-r">
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-black/65">Dialogue Focus</h2>

          <div className="mt-3 rounded-2xl border border-black/10 bg-paper/35 p-4">
            <p className="text-[10px] uppercase tracking-[0.14em] text-black/50">Current focus</p>
            <p className="mt-2 text-base font-semibold text-black">{selectedSkill?.name || tree.topic.name}</p>
            <p className="mt-1 text-sm text-black/68">
              {selectedSkill?.description || 'Use dialogue to clarify meaning, test interpretation, and carry insight into the notebook.'}
            </p>
            {selectedSkill && (
              <p className="mt-2 text-xs text-black/58">
                {formatDisplayTag(selectedSkill.status)} · {formatDisplayTag(selectedSkill.progress_state)}
              </p>
            )}
          </div>

          <details className="mt-4 rounded-2xl border border-black/10 bg-white p-3">
            <summary className="cursor-pointer text-sm font-medium text-black">Switch focus</summary>
            <div className="mt-3 space-y-2">
              {selectableNodes.map((node) => (
                <button
                  key={node.id}
                  className={`w-full rounded-md border p-2 text-left text-sm ${
                    selectedSkillId === node.id ? 'border-ink bg-paper/60' : 'border-black/10 bg-white'
                  }`}
                  onClick={() => setSelectedSkillId(node.id)}
                  type="button"
                >
                  <p className="font-semibold">{node.name}</p>
                  <p className="muted mt-1 text-xs">
                    {formatDisplayTag(node.status)} · {formatDisplayTag(node.progress_state)}
                  </p>
                </button>
              ))}
            </div>
          </details>

          <details className="mt-4 rounded-2xl border border-black/10 bg-white p-3">
            <summary className="cursor-pointer text-sm font-medium text-black">Source scope</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs text-black/62">
                Study context stays primary. Expand the scope only when it genuinely helps interpretation or context.
              </p>
              <label className="flex items-start gap-3 rounded-lg border border-black/10 bg-paper/25 px-3 py-2">
                <input
                  type="checkbox"
                  checked={includeNotebookMemory}
                  onChange={(event) => setIncludeNotebookMemory(event.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-sm text-black/78">
                  Use notebook memory
                  <span className="mt-1 block text-xs text-black/58">
                    Keep prior notes and reflections in the conversation.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-lg border border-black/10 bg-paper/25 px-3 py-2">
                <input
                  type="checkbox"
                  checked={allowWebSources}
                  onChange={(event) => setAllowWebSources(event.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-sm text-black/78">
                  Allow current web sources
                  <span className="mt-1 block text-xs text-black/58">
                    Use this only when the topic needs fresh or external context beyond the study materials.
                  </span>
                </span>
              </label>
            </div>
          </details>
        </aside>

        <article className="flex flex-col p-4 md:p-6">
          <div className="mb-4 rounded-2xl border border-black/10 bg-[linear-gradient(165deg,rgba(255,255,255,0.96),rgba(247,252,244,0.92))] p-4 text-sm">
            <p className="text-xs uppercase tracking-[0.16em] text-black/55">Companion Prompt</p>
            <p className="mt-2 text-base font-medium text-black">
              Stay with {selectedSkill?.name || 'this study'} long enough to interpret it clearly, then carry the strongest insight into the notebook.
            </p>
            <p className="mt-2 text-sm text-black/65">
              Ask for interpretation, comparison, concrete context, or a notebook-worthy way to frame what changed.
            </p>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-black/10 bg-white p-4">
            {messages.length === 0 && (
              <div className="rounded-xl border border-dashed border-black/15 bg-paper/50 p-5">
                <p className="text-sm font-medium text-black">Begin with one clear prompt.</p>
                <p className="mt-1 text-sm text-black/62">
                  The companion is strongest when it stays close to the current study focus and helps you notice, compare, interpret, or capture.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {promptStarters.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      className="rounded-full border border-black/15 bg-white px-3 py-1.5 text-xs text-black/78 hover:bg-black/[0.03]"
                      onClick={() => setInput(starter)}
                    >
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
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
                              onClick={() =>
                                openSavePanel(
                                  item,
                                  typeof window !== 'undefined' && window.getSelection()?.toString().trim() ? 'excerpt' : 'summary'
                                )
                              }
                            >
                              Capture in notebook
                            </button>
                            {topicNotes.length > 0 && (
                              <button
                                type="button"
                                className="rounded-md border border-black/20 bg-white px-2.5 py-1 text-xs"
                                onClick={() => openSavePanel(item, 'append')}
                              >
                                Append to notebook
                              </button>
                            )}
                          </div>
                        ) : null
                      }
                    />
                    {activeSaveMessageId === item.messageId && (
                      <div className="max-w-3xl rounded-xl border border-black/15 bg-white p-3">
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                          <span className="badge">
                            {saveMode === 'append'
                              ? 'Append to notebook'
                              : saveMode === 'excerpt'
                                ? 'Capture excerpt'
                                : 'Capture note'}
                          </span>
                          <span className="text-black/60">
                            {topicNotes.length} notebook entr{topicNotes.length === 1 ? 'y' : 'ies'} in this study
                          </span>
                          <span className="text-black/60">
                            {selectedSkill ? `Linked to current focus: ${selectedSkill.name}` : 'Linked to study-level dialogue'}
                          </span>
                        </div>

                        {saveMode !== 'append' && (
                          <div className="mb-3 rounded-lg border border-black/10 bg-paper/40 p-3">
                            <p className="text-xs uppercase tracking-[0.12em] text-black/58">Notebook lens</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {NOTEBOOK_LENS_OPTIONS.map((lens) => (
                                <button
                                  key={`save-lens-${lens.tag}`}
                                  type="button"
                                  className={`rounded-full border px-3 py-1 text-xs hover:bg-black/[0.03] ${
                                    saveLens === lens.tag
                                      ? 'border-ink bg-ink text-white'
                                      : 'border-black/15 bg-white text-black/75'
                                  }`}
                                  onClick={() => applySaveLens(lens.tag)}
                                >
                                  {lens.label}
                                </button>
                              ))}
                            </div>
                            <p className="mt-2 text-[11px] text-black/78">{saveLensOption.description}</p>
                          </div>
                        )}

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

                        <textarea
                          value={saveBody}
                          onChange={(event) => setSaveBody(event.target.value)}
                          className="min-h-[120px] w-full rounded-md border border-black/15 bg-white p-3 text-sm"
                          placeholder={saveBodyPlaceholder}
                          maxLength={8000}
                        />

                        {saveMode !== 'append' && (
                          <details className="mt-2 rounded-lg border border-black/10 bg-paper/25 p-2.5">
                            <summary className="cursor-pointer text-xs font-medium text-black">Optional note details</summary>
                            <input
                              value={saveTitle}
                              onChange={(event) => setSaveTitle(event.target.value)}
                              className="mt-2 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
                              placeholder={`${saveLensOption.promptTitle} title (optional)`}
                              maxLength={120}
                            />
                          </details>
                        )}

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
                  <span>Composing studio response...</span>
                </div>
              </div>
            )}
          </div>

          <form className="mt-4 flex gap-2" onSubmit={onSend}>
            <div className="flex-1 space-y-1">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                className="min-h-[96px] w-full rounded-lg border border-black/15 bg-white px-3 py-3 text-sm"
                placeholder="Ask for interpretation, comparison, concrete context, or a notebook-worthy way to frame what changed..."
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
