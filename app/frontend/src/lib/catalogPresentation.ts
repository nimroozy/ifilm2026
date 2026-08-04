export interface CatalogPresentationFields {
  demoOwned?: boolean;
  hasDemoClip?: boolean;
  hlsPath?: string | null;
  playable?: boolean;
  hasPlayablePackage?: boolean;
  hasExternalMedia?: boolean;
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

/**
 * Full-title playability. Prefer package/external flags from the API.
 * Demo-owned catalog items intentionally do not offer commercial full playback.
 */
export function canPlayFullMovie(item: unknown): boolean {
  if (isDemoCatalogItem(item)) return false;
  if (field<boolean>(item, 'playable') === true) return true;
  if (field<boolean>(item, 'hasPlayablePackage') === true) return true;
  if (field<boolean>(item, 'hasExternalMedia') === true) return true;
  const hlsPath = field<string | null>(item, 'hlsPath');
  if (typeof hlsPath === 'string' && hlsPath.trim().length > 0) return true;
  return false;
}

export function fullMovieUnavailableLabel(): string {
  return 'Full Movie Unavailable';
}

/** Primary CTA order for movie detail: Play → Demo → Trailer → More Info. */
export type MovieDetailAction = 'play' | 'demo' | 'trailer' | 'unavailable' | 'more';

export function movieDetailPrimaryActions(item: unknown, hasTrailer: boolean): MovieDetailAction[] {
  const actions: MovieDetailAction[] = [];
  if (canPlayFullMovie(item)) actions.push('play');
  if (hasDemoClip(item)) actions.push('demo');
  if (hasTrailer) actions.push('trailer');
  if (!canPlayFullMovie(item) && !hasDemoClip(item)) actions.push('unavailable');
  actions.push('more');
  return actions;
}
