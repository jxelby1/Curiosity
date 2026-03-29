'use client';

import { useEffect, useMemo, useState } from 'react';

import { fetchProtectedBlob } from '@/lib/api';

export function ProofArtifactViewer({
  proofUrl,
  showPreview = true,
  className = '',
}: {
  proofUrl: string;
  showPreview?: boolean;
  className?: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [contentType, setContentType] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    let localObjectUrl: string | null = null;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const blob = await fetchProtectedBlob(proofUrl);
        if (cancelled) return;
        localObjectUrl = URL.createObjectURL(blob);
        setObjectUrl((prev) => {
          if (prev && prev !== localObjectUrl) URL.revokeObjectURL(prev);
          return localObjectUrl;
        });
        setContentType(blob.type || '');
      } catch (err) {
        if (cancelled) return;
        setObjectUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        setContentType('');
        setError(err instanceof Error ? err.message : 'Could not load artifact');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (localObjectUrl) URL.revokeObjectURL(localObjectUrl);
    };
  }, [proofUrl]);

  const isImage = useMemo(() => contentType.startsWith('image/'), [contentType]);

  return (
    <div className={`mt-2 space-y-2 ${className}`}>
      {loading && <p className="text-xs text-black/60">Loading artifact…</p>}
      {error && <p className="text-xs text-red-700">{error}</p>}
      {!loading && !error && objectUrl && showPreview && isImage && (
        <a href={objectUrl} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-md border border-black/10">
          <img src={objectUrl} alt="Uploaded exercise artifact" className="max-h-56 w-full object-contain bg-white" />
        </a>
      )}
      {!loading && !error && objectUrl && (
        <a href={objectUrl} target="_blank" rel="noreferrer" className="inline-flex text-xs text-ink underline underline-offset-4">
          {isImage ? 'Open full artifact image' : 'Open uploaded artifact'}
        </a>
      )}
    </div>
  );
}

