const UPPERCASE_TOKENS = new Set([
  'ai',
  'api',
  'css',
  'html',
  'js',
  'json',
  'llm',
  'sql',
  'ts',
  'ui',
  'ux',
]);

function capitalizeSegment(value: string): string {
  if (!value) return '';
  const normalized = value.toLowerCase();
  if (UPPERCASE_TOKENS.has(normalized)) {
    return normalized.toUpperCase();
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatToken(token: string): string {
  if (!token) return '';
  if (/^\d+$/.test(token)) return token;
  return token
    .split('/')
    .map((chunk) =>
      chunk
        .split("'")
        .map((part) => capitalizeSegment(part))
        .join("'")
    )
    .join('/');
}

export function formatDisplayTag(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const raw = String(value).trim();
  if (!raw) return '';
  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .split(' ')
    .map((token) => formatToken(token))
    .join(' ');
}
