'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';

import { getSkillTree, listNotes, uploadFileNote, uploadRawNote } from '@/lib/api';
import { NoteItem, SkillTree } from '@/lib/types';
import { TopicHeader } from '@/components/topic-header';

export default function TopicNotesPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;

  const [tree, setTree] = useState<SkillTree | null>(null);
  const [notes, setNotes] = useState<NoteItem[]>([]);

  const [rawText, setRawText] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const loadNotesPage = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [treeData, noteData] = await Promise.all([getSkillTree(topicId), listNotes(topicId)]);
      setTree(treeData);
      setNotes(noteData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notes page');
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadNotesPage();
  }, [loadNotesPage]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rawText.trim() && !file) return;

    setSaving(true);
    setError('');
    try {
      if (rawText.trim()) {
        await uploadRawNote(topicId, rawText.trim());
        setRawText('');
      }
      if (file) {
        await uploadFileNote(topicId, file);
        setFile(null);
      }
      await loadNotesPage();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload notes');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl p-6 md:p-10">
        <p className="panel p-4 text-sm">Loading notes workspace...</p>
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
      <TopicHeader topicId={topicId} topicName={tree.topic.name} subtitle="Ingest your notes and build retrieval context" />

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <article className="panel p-6">
          <h2 className="text-xl font-semibold">Upload Notes</h2>
          <p className="muted mt-2 text-sm">
            Paste text or upload files (`.txt`, `.md`, `.pdf`). Ingested content is chunked and embedded for retrieval.
          </p>

          <form className="mt-4 space-y-3" onSubmit={onSubmit}>
            <textarea
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              className="min-h-44 w-full rounded-lg border border-black/15 bg-white p-3 text-sm"
              placeholder="Paste study notes, concepts, examples, or debugging logs..."
            />
            <input
              type="file"
              accept=".txt,.md,.markdown,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              className="text-sm"
            />
            <button className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60" disabled={saving}>
              {saving ? 'Ingesting...' : 'Ingest Notes'}
            </button>
          </form>
        </article>

        <article className="panel p-6">
          <h2 className="text-xl font-semibold">Uploaded Notes</h2>
          <div className="mt-4 space-y-2">
            {notes.map((note) => (
              <div key={note.id} className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                <p className="font-semibold">{note.filename}</p>
                <p className="muted mt-1 text-xs">{new Date(note.created_at).toLocaleString()}</p>
              </div>
            ))}
            {notes.length === 0 && (
              <p className="muted rounded-lg border border-dashed border-black/15 bg-white p-4 text-sm">
                No notes uploaded yet.
              </p>
            )}
          </div>
        </article>
      </section>

      {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
