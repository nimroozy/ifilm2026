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

function withTmdbWidth(raw: string, widthToken: string): string {
  try {
    const url = new URL(raw, typeof window !== 'undefined' ? window.location.origin : 'http://local');
    if (!isTmdbImageUrl(url)) return raw;
    const parts = url.pathname.split('/');
    const pIndex = parts.indexOf('p');
    if (pIndex < 0 || pIndex + 1 >= parts.length) return raw;
    parts[pIndex + 1] = widthToken;
    url.pathname = parts.join('/');
    return url.toString();
  } catch {
    return raw;
  }
}

/** Rewrite TMDB `/t/p/{size}/…` to the requested width token. */
export function sizedArtworkUrl(
  raw: string | null | undefined,
  kind: ArtworkKind = 'poster',
  slot: 'card' | 'hero' = 'card'
): string {
  const value = (raw || '').trim();
  if (!value) return '';
  return withTmdbWidth(value, WIDTH[kind][slot]);
}

/**
 * Responsive hero backdrop candidates: mobile prefers w780, desktop w1280.
 * Never returns /original/.
 */
export function heroBackdropSrcSet(raw: string | null | undefined): {
  src: string;
  srcSet: string;
  sizes: string;
} {
  const base = (raw || '').trim();
  if (!base) return { src: '', srcSet: '', sizes: '100vw' };
  const w780 = withTmdbWidth(base, 'w780');
  const w1280 = withTmdbWidth(base, 'w1280');
  if (w780 === base && w1280 === base) {
    return { src: base, srcSet: '', sizes: '100vw' };
  }
  return {
    src: w780,
    srcSet: `${w780} 780w, ${w1280} 1280w`,
    sizes: '100vw',
  };
}
