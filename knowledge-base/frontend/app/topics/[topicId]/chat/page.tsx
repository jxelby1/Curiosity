'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import { chatTopic, getSkillTree } from '@/lib/api';
import { SkillTree } from '@/lib/types';
import { TopicHeader } from '@/components/topic-header';

type ChatItem = { role: 'user' | 'assistant'; content: string };

export default function TopicChatPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;

  const [tree, setTree] = useState<SkillTree | null>(null);
  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(null);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');

  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const loadTree = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getSkillTree(topicId);
      setTree(data);
      if (data.nodes.length) {
        const unlocked = data.nodes.find((node) => node.status !== 'locked') || data.nodes[0];
        setSelectedSkillId(unlocked.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topic context');
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const selectedSkill = useMemo(() => {
    if (!tree || !selectedSkillId) return null;
    return tree.nodes.find((node) => node.id === selectedSkillId) || null;
  }, [tree, selectedSkillId]);

  async function onSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim()) return;

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
        skill_node_id: selectedSkillId
      });
      setSessionId(reply.session_id);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl p-6 md:p-10">
        <p className="panel p-4 text-sm">Loading chat workspace...</p>
      </main>
    );
  }

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

      <section className="panel grid min-h-[70vh] gap-0 overflow-hidden lg:grid-cols-[0.85fr_2fr]">
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
                <p className="muted mt-1 text-xs">{node.status.replace('_', ' ')} · {(node.mastery_estimate * 100).toFixed(0)}%</p>
              </button>
            ))}
          </div>
        </aside>

        <article className="flex flex-col p-4 md:p-6">
          <div className="mb-3 rounded-md border border-black/10 bg-white p-3 text-sm">
            <p className="font-medium">Active context: {selectedSkill?.name || 'General topic context'}</p>
            <p className="muted mt-1 text-xs">The tutor adapts to this skill while using retrieved note chunks.</p>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-black/10 bg-white p-4">
            {messages.length === 0 && <p className="muted text-sm">Ask a question to start your tutoring session.</p>}
            {messages.map((item, index) => (
              <div key={index} className={item.role === 'user' ? 'text-right' : ''}>
                <div
                  className={`inline-block max-w-[88%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                    item.role === 'user' ? 'bg-ink text-white' : 'border border-black/10 bg-paper/60 text-black'
                  }`}
                >
                  {item.content}
                </div>
              </div>
            ))}
          </div>

          <form className="mt-4 flex gap-2" onSubmit={onSend}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              className="flex-1 rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Ask about debugging strategy, concept gaps, or next steps..."
            />
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
