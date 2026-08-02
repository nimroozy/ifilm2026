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
  return !isDemoCatalogItem(item);
}

export function fullMovieUnavailableLabel(): string {
  return 'Full Movie Unavailable';
}
