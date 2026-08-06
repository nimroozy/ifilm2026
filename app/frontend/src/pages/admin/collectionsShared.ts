/** Shared constants/helpers for the Collections V1 admin UI (list + form pages). */

export const COLLECTION_TYPES = [
  'editorial',
  'franchise',
  'seasonal',
  'genre_feature',
  'regional',
  'language',
  'staff_pick',
] as const;

export type CollectionTypeValue = (typeof COLLECTION_TYPES)[number];

export const COLLECTION_TYPE_LABELS: Record<string, string> = {
  editorial: 'Editorial',
  franchise: 'Franchise',
  seasonal: 'Seasonal',
  genre_feature: 'Genre Feature',
  regional: 'Regional',
  language: 'Language',
  staff_pick: 'Staff Pick',
};

export function collectionTypeLabel(value: string): string {
  return COLLECTION_TYPE_LABELS[value] || value;
}

/**
 * Allowed quick actions given the current status.
 * Mirrors backend transition rules: publish requires draft; unpublish always
 * resets to draft (including restoring from archived); archive is allowed
 * from any non-archived status.
 */
export function collectionStatusActions(status: string) {
  return {
    canPublish: status !== 'published' && status !== 'archived',
    canUnpublish: status === 'published',
    canRestore: status === 'archived',
    canArchive: status !== 'archived',
  };
}
