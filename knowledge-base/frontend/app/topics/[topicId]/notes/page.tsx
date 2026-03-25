'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

import {
  createNote,
  deleteDocument,
  deleteNote,
  getSkillTree,
  listDocuments,
  listNotes,
  updateNote,
  uploadFileNote
} from '@/lib/api';
import { readSkillTreeCache, writeSkillTreeCache } from '@/lib/cache';
import { DocumentItem, NoteType, PersonalNote, SkillTree } from '@/lib/types';
import { TopicHeader } from '@/components/topic-header';
import { NotesWorkspaceSkeleton } from '@/components/page-skeletons';

const NOTE_TYPE_OPTIONS: Array<{ value: NoteType; label: string }> = [
  { value: 'personal', label: 'Personal note' },
  { value: 'lesson', label: 'Lesson note' },
  { value: 'summary', label: 'Summary' },
  { value: 'reflection', label: 'Reflection' },
  { value: 'reminder', label: 'Reminder' }
];
const NOTE_TITLE_MAX = 120;
const NOTE_BODY_MAX = 8000;

export default function TopicNotesPage({ params }: { params: { topicId: string } }) {
  const topicId = params.topicId;
  const cachedTree = readSkillTreeCache(topicId);

  const [tree, setTree] = useState<SkillTree | null>(cachedTree);
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const [selectedNoteId, setSelectedNoteId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [noteType, setNoteType] = useState<NoteType>('personal');
  const [linkedSkillId, setLinkedSkillId] = useState<string>('');

  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [loadingTree, setLoadingTree] = useState(!cachedTree);
  const [loadingNotes, setLoadingNotes] = useState(true);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [savingNote, setSavingNote] = useState(false);
  const [uploadingDocument, setUploadingDocument] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const selectedNote = useMemo(
    () => (selectedNoteId ? notes.find((note) => note.id === selectedNoteId) || null : null),
    [notes, selectedNoteId]
  );

  const loadTree = useCallback(async () => {
    try {
      const treeData = await getSkillTree(topicId);
      setTree(treeData);
      writeSkillTreeCache(topicId, treeData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topic context');
    } finally {
      setLoadingTree(false);
    }
  }, [topicId]);

  const loadNotes = useCallback(async () => {
    setLoadingNotes(true);
    try {
      const noteData = await listNotes(topicId, { query: searchQuery });
      setNotes(noteData);
      if (noteData.length === 0) {
        setSelectedNoteId(null);
      } else if (selectedNoteId && !noteData.some((note) => note.id === selectedNoteId)) {
        setSelectedNoteId(noteData[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notes');
    } finally {
      setLoadingNotes(false);
    }
  }, [searchQuery, selectedNoteId, topicId]);

  const loadDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    try {
      const docs = await listDocuments(topicId);
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      setLoadingDocuments(false);
    }
  }, [topicId]);

  useEffect(() => {
    loadTree();
    loadNotes();
    loadDocuments();
  }, [loadDocuments, loadNotes, loadTree]);

  useEffect(() => {
    if (!selectedNote) return;
    setTitle(selectedNote.title);
    setBody(selectedNote.body);
    setNoteType(selectedNote.note_type);
    setLinkedSkillId(selectedNote.skill_node_id ? String(selectedNote.skill_node_id) : '');
  }, [selectedNote]);

  function resetEditorForNewNote() {
    setSelectedNoteId(null);
    setTitle('');
    setBody('');
    setNoteType('personal');
    setLinkedSkillId('');
  }

  async function onSaveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!body.trim()) {
      setError('Note body cannot be empty.');
      return;
    }
    if (body.trim().length > NOTE_BODY_MAX) {
      setError(`Note body must be ${NOTE_BODY_MAX} characters or less.`);
      return;
    }

    setSavingNote(true);
    setError('');
    try {
      const payload = {
        title: title.trim(),
        body: body.trim(),
        note_type: noteType,
        skill_node_id: linkedSkillId ? Number(linkedSkillId) : null
      };

      if (selectedNoteId) {
        await updateNote({ note_id: selectedNoteId, ...payload });
      } else {
        const created = await createNote({ topic_id: Number(topicId), ...payload });
        setSelectedNoteId(created.id);
      }
      await loadNotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save note');
    } finally {
      setSavingNote(false);
    }
  }

  async function onDeleteNote() {
    if (!selectedNoteId) return;
    setSavingNote(true);
    setError('');
    try {
      await deleteNote(selectedNoteId);
      resetEditorForNewNote();
      await loadNotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete note');
    } finally {
      setSavingNote(false);
    }
  }

  async function onUploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadFile) return;

    setUploadingDocument(true);
    setError('');
    try {
      await uploadFileNote(topicId, uploadFile);
      setUploadFile(null);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload document');
    } finally {
      setUploadingDocument(false);
    }
  }

  async function onDeleteDocument(document: DocumentItem) {
    const confirmed = window.confirm(
      `Delete source document "${document.filename}"?\n\nThis removes its retrieval context for this topic.`
    );
    if (!confirmed) return;

    setDeletingDocumentId(document.id);
    setError('');
    try {
      await deleteDocument(topicId, document.id);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete document');
    } finally {
      setDeletingDocumentId(null);
    }
  }

  if (!tree && loadingTree) return <NotesWorkspaceSkeleton />;

  if (!tree) {
    return (
      <main className="mx-auto max-w-6xl p-6 md:p-10">
        <p className="panel p-4 text-sm text-red-700">Topic not found.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl p-6 md:p-10">
      <TopicHeader topicId={topicId} topicName={tree.topic.name} subtitle="Personal notes and learning materials" />

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.25fr_0.95fr]">
        <article className="panel p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">My Notes</h2>
            <button className="text-xs underline underline-offset-4" onClick={resetEditorForNewNote}>
              New note
            </button>
          </div>

          <div className="flex gap-2">
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              onBlur={() => setSearchQuery(searchInput.trim())}
              className="w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Search notes..."
            />
            <button
              className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs"
              onClick={() => setSearchQuery(searchInput.trim())}
              type="button"
            >
              Apply
            </button>
          </div>

          <div className="mt-3 space-y-2">
            {loadingNotes && notes.length === 0 && (
              <>
                <div className="skeleton h-14 w-full" />
                <div className="skeleton h-14 w-full" />
              </>
            )}
            {notes.map((note) => (
              <button
                key={note.id}
                className={`w-full rounded-lg border p-3 text-left text-sm ${
                  selectedNoteId === note.id ? 'border-ink bg-paper/70' : 'border-black/10 bg-white'
                }`}
                onClick={() => setSelectedNoteId(note.id)}
                type="button"
              >
                <p className="font-semibold">{note.title}</p>
                <p className="muted mt-1 line-clamp-2 text-xs">{note.body}</p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1">
                    <span className="badge">{note.note_type}</span>
                    <span className="badge">{note.source_type.replace('_', ' ')}</span>
                  </div>
                  <span className="text-[11px] text-black/60">{new Date(note.updated_at).toLocaleDateString()}</span>
                </div>
                {note.tags.length > 0 && (
                  <p className="mt-2 text-[11px] text-black/60">Tags: {note.tags.join(', ')}</p>
                )}
              </button>
            ))}
            {!loadingNotes && notes.length === 0 && (
              <p className="muted rounded-lg border border-dashed border-black/15 bg-white p-4 text-sm">
                No notes yet. Create your first learning note.
              </p>
            )}
          </div>
        </article>

        <article className="panel p-5">
          <h2 className="text-lg font-semibold">{selectedNoteId ? 'Edit Note' : 'Create Note'}</h2>
          <p className="muted mt-1 text-sm">Personal notes are user-owned and only used in chat when you opt in.</p>

          <form className="mt-4 space-y-3" onSubmit={onSaveNote}>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Title (optional)"
              maxLength={NOTE_TITLE_MAX}
            />
            <p className="text-right text-xs text-black/60">{title.length}/{NOTE_TITLE_MAX}</p>

            <div className="grid gap-2 md:grid-cols-2">
              <select
                value={noteType}
                onChange={(event) => setNoteType(event.target.value as NoteType)}
                className="rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
              >
                {NOTE_TYPE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>

              <select
                value={linkedSkillId}
                onChange={(event) => setLinkedSkillId(event.target.value)}
                className="rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
              >
                <option value="">All skills (topic-level)</option>
                {tree.nodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.name}
                  </option>
                ))}
              </select>
            </div>

            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              className="min-h-[260px] w-full rounded-lg border border-black/15 bg-white p-3 text-sm"
              placeholder="Write notes, takeaways, reflections, reminders, or summaries..."
              maxLength={NOTE_BODY_MAX}
            />
            <p className="text-right text-xs text-black/60">{body.length}/{NOTE_BODY_MAX}</p>

            <div className="flex flex-wrap gap-2">
              <button className="rounded-lg bg-ink px-4 py-2 text-sm text-white disabled:opacity-60" disabled={savingNote}>
                {savingNote ? 'Saving...' : selectedNoteId ? 'Save changes' : 'Create note'}
              </button>
              {selectedNoteId && (
                <button
                  className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm text-red-700 disabled:opacity-60"
                  onClick={onDeleteNote}
                  disabled={savingNote}
                  type="button"
                >
                  Delete note
                </button>
              )}
            </div>
          </form>
        </article>

        <article className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Source Documents</h2>
            <span className="badge">Optional</span>
          </div>
          <p className="muted mt-1 text-sm">
            Source documents are reference material (docs, PDFs, markdown) for retrieval-grounded tutoring and generation.
            Your personal notes are separate, and you can use this app without uploading source documents.
          </p>

          <form className="mt-4 space-y-3" onSubmit={onUploadDocument}>
            <input
              type="file"
              accept=".txt,.md,.markdown,.pdf"
              onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              className="text-sm"
            />
            <button
              className="rounded-lg border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-60"
              disabled={uploadingDocument || !uploadFile}
            >
              {uploadingDocument ? 'Uploading...' : 'Upload document'}
            </button>
          </form>

          <div className="mt-4 space-y-2">
            {loadingDocuments && documents.length === 0 && (
              <>
                <div className="skeleton h-12 w-full" />
                <div className="skeleton h-12 w-full" />
              </>
            )}
            {documents.map((document) => (
              <div key={document.id} className="rounded-lg border border-black/10 bg-white p-3 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{document.filename}</p>
                    <p className="muted mt-1 text-xs">{new Date(document.created_at).toLocaleString()}</p>
                  </div>
                  <button
                    className="rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs text-red-700 disabled:opacity-60"
                    type="button"
                    onClick={() => onDeleteDocument(document)}
                    disabled={deletingDocumentId === document.id}
                  >
                    {deletingDocumentId === document.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            ))}
            {!loadingDocuments && documents.length === 0 && (
              <p className="muted rounded-lg border border-dashed border-black/15 bg-white p-4 text-sm">
                No source documents uploaded yet.
              </p>
            )}
          </div>
        </article>
      </section>

      {error && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    </main>
  );
}
