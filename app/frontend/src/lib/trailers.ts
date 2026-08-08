const YOUTUBE_KEY_RE = /^[A-Za-z0-9_-]{6,}$/;
const ALLOWED_HOSTS = new Set(['www.youtube-nocookie.com', 'www.youtube.com']);

function validYoutubeKey(key?: string | null): string {
  const value = (key || '').trim();
  return YOUTUBE_KEY_RE.test(value) ? value : '';
}

export function youtubeEmbedUrlFromKey(key?: string | null): string {
  const safeKey = validYoutubeKey(key);
  return safeKey ? `https://www.youtube-nocookie.com/embed/${safeKey}` : '';
}

export function safeYoutubeEmbedUrl(input?: string | null): string {
  if (!input) return '';
  try {
    const url = new URL(input);
    if (url.protocol !== 'https:' || !ALLOWED_HOSTS.has(url.hostname)) return '';
    if (url.pathname.startsWith('/embed/')) {
      return validYoutubeKey(url.pathname.split('/')[2]) ? url.toString() : '';
    }
    if (url.hostname === 'www.youtube.com' && url.pathname === '/watch') {
      return youtubeEmbedUrlFromKey(url.searchParams.get('v'));
    }
  } catch {
    return '';
  }
  return '';
}

export function trailerEmbedUrl(item: {
  trailerKey?: string | null;
  trailerUrl?: string | null;
  trailerProvider?: string | null;
} | unknown): string {
  const value = item && typeof item === 'object' ? (item as Record<string, unknown>) : {};
  const trailerProvider = typeof value.trailerProvider === 'string' ? value.trailerProvider : '';
  const trailerKey = typeof value.trailerKey === 'string' ? value.trailerKey : '';
  const trailerUrl = typeof value.trailerUrl === 'string' ? value.trailerUrl : '';
  if (trailerProvider.toLowerCase() === 'youtube' && trailerKey) {
    return youtubeEmbedUrlFromKey(trailerKey);
  }
  return safeYoutubeEmbedUrl(trailerUrl);
}

/** YouTube embed with muted autoplay — never downloads or rehosts trailers. */
export function trailerAutoplayEmbedUrl(item: unknown): string {
  const base = trailerEmbedUrl(item);
  if (!base) return '';
  try {
    const url = new URL(base);
    url.searchParams.set('autoplay', '1');
    url.searchParams.set('mute', '1');
    url.searchParams.set('rel', '0');
    url.searchParams.set('modestbranding', '1');
    url.searchParams.set('playsinline', '1');
    return url.toString();
  } catch {
    return '';
  }
}
