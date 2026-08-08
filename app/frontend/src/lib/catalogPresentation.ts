export interface CatalogPresentationFields {
  demoOwned?: boolean;
  hasDemoClip?: boolean;
  hlsPath?: string | null;
  playable?: boolean;
  hasPlayablePackage?: boolean;
  hasExternalMedia?: boolean;
  status?: string | null;
}

function field<T>(item: unknown, key: string): T | undefined {
  return item && typeof item === 'object' && key in item ? (item as Record<string, T>)[key] : undefined;
}

export function isDemoCatalogItem(item: unknown): boolean {
  return field<boolean>(item, 'demoOwned') === true;
}

export function hasDemoClip(item: unknown): boolean {
  return field<boolean>(item, 'hasDemoClip') === true;
}

/** Customer-facing publish gate. Missing status is treated as published (public API). */
export function isPublishedCatalogItem(item: unknown): boolean {
  const status = field<string>(item, 'status');
  if (status == null || status === '') return true;
  return status === 'published';
}

/**
 * Full-title playability. Backend-authoritative flags only
 * (`playable` / `hasPlayablePackage` / `hasExternalMedia`).
 * Do not infer from legacy `hlsPath`.
 * Demo-owned catalog items intentionally do not offer commercial full playback.
 */
export function canPlayFullMovie(item: unknown): boolean {
  if (isDemoCatalogItem(item)) return false;
  if (field<boolean>(item, 'playable') === true) return true;
  if (field<boolean>(item, 'hasPlayablePackage') === true) return true;
  if (field<boolean>(item, 'hasExternalMedia') === true) return true;
  return false;
}

/** Play CTA: published + playable only. Never show Play incorrectly. */
export function canShowPlayButton(item: unknown): boolean {
  return isPublishedCatalogItem(item) && canPlayFullMovie(item);
}

/** Prefer Coming Soon / Unavailable — not the old "Full Movie Unavailable" copy. */
export function movieUnavailableLabel(opts?: { hasTrailer?: boolean; published?: boolean }): string {
  if (opts?.hasTrailer) return 'Unavailable';
  if (opts?.published === false) return 'Coming Soon';
  return 'Coming Soon';
}

/** @deprecated Use movieUnavailableLabel — kept for transitional callers. */
export function fullMovieUnavailableLabel(): string {
  return movieUnavailableLabel();
}

/** Primary CTA order for movie detail: Play → Demo → Trailer → Coming Soon. */
export type MovieDetailAction = 'play' | 'demo' | 'trailer' | 'coming_soon' | 'unavailable' | 'more';

export function movieDetailPrimaryActions(item: unknown, hasTrailer: boolean): MovieDetailAction[] {
  const actions: MovieDetailAction[] = [];
  if (canShowPlayButton(item)) actions.push('play');
  if (hasDemoClip(item)) actions.push('demo');
  if (hasTrailer) actions.push('trailer');
  if (!canShowPlayButton(item) && !hasDemoClip(item) && !hasTrailer) {
    actions.push('coming_soon');
  }
  actions.push('more');
  return actions;
}

export const MOVIE_HERO_TRAILER_DELAY_MS = 6000;

export function shouldAutoplayTrailerHero(opts: {
  hasTrailer: boolean;
  reduceMotion: boolean;
  userDismissed: boolean;
}): boolean {
  return opts.hasTrailer && !opts.reduceMotion && !opts.userDismissed;
}
