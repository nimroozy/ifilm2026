export interface CatalogPresentationFields {
  demoOwned?: boolean;
  hasDemoClip?: boolean;
  hlsPath?: string | null;
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

export function canPlayFullMovie(item: unknown): boolean {
  if (isDemoCatalogItem(item)) return false;
  const hlsPath = field<string | null>(item, 'hlsPath');
  if (typeof hlsPath === 'string' && hlsPath.trim().length > 0) return true;
  // Explicit playability flags from API when present
  if (field<boolean>(item, 'playable') === true) return true;
  if (field<boolean>(item, 'hasPlayablePackage') === true) return true;
  // Without a known playable package, do not claim full playback.
  return false;
}

export function fullMovieUnavailableLabel(): string {
  return 'Full Movie Unavailable';
}
