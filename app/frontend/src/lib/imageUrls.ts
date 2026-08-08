/**
 * Resize remote artwork URLs to sizes appropriate for rendered card/hero slots.
 * TMDB image CDN supports path width prefixes (/w185, /w342, /w780, /original).
 * Local/static artwork URLs are returned unchanged.
 */

const TMDB_IMAGE_HOST = /(?:^|\.)image\.tmdb\.org$/i;

export type ArtworkKind = 'poster' | 'backdrop' | 'logo';

const WIDTH: Record<ArtworkKind, { card: string; hero: string }> = {
  poster: { card: 'w342', hero: 'w780' },
  backdrop: { card: 'w780', hero: 'w1280' },
  logo: { card: 'w300', hero: 'w500' },
};

function isTmdbImageUrl(url: URL): boolean {
  return TMDB_IMAGE_HOST.test(url.hostname) && url.pathname.includes('/t/p/');
}

/** Rewrite TMDB `/t/p/{size}/…` to the requested width token. */
export function sizedArtworkUrl(
  raw: string | null | undefined,
  kind: ArtworkKind = 'poster',
  slot: 'card' | 'hero' = 'card'
): string {
  const value = (raw || '').trim();
  if (!value) return '';
  try {
    const url = new URL(value, typeof window !== 'undefined' ? window.location.origin : 'http://local');
    if (!isTmdbImageUrl(url)) return value;
    const parts = url.pathname.split('/');
    // …/t/p/{size}/{file}
    const pIndex = parts.indexOf('p');
    if (pIndex < 0 || pIndex + 1 >= parts.length) return value;
    parts[pIndex + 1] = WIDTH[kind][slot];
    url.pathname = parts.join('/');
    return url.toString();
  } catch {
    return value;
  }
}
