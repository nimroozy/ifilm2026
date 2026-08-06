/**
 * Catalog availability helpers.
 *
 * These fields are admin-curated claims on movie/series records
 * (`audio`, `subtitles`, `dubbed`). They are independent of HLS
 * runtime tracks shown in the player selectors.
 */

export type CatalogAvailabilityFields = {
  audio?: string[] | null;
  subtitles?: string[] | null;
  dubbed?: string[] | null;
};

export function hasCatalogTracks(list: string[] | null | undefined): boolean {
  return Array.isArray(list) && list.some((item) => Boolean(item && String(item).trim()));
}

export function formatCatalogTracks(list: string[] | null | undefined): string {
  if (!hasCatalogTracks(list)) return '';
  return (list as string[])
    .map((item) => String(item).trim())
    .filter(Boolean)
    .join(', ');
}

/** Prefer a single card badge: Dubbed > Subtitles > Audio. */
export function catalogAvailabilityBadge(
  item: CatalogAvailabilityFields,
  labels: { dubbed: string; subtitled: string; audio: string }
): string | undefined {
  if (hasCatalogTracks(item.dubbed)) return labels.dubbed;
  if (hasCatalogTracks(item.subtitles)) return labels.subtitled;
  if (hasCatalogTracks(item.audio)) return labels.audio;
  return undefined;
}

export function catalogAvailabilityChips(
  item: CatalogAvailabilityFields,
  labels: { dubbed: string; subtitled: string; audio: string }
): string[] {
  const chips: string[] = [];
  if (hasCatalogTracks(item.dubbed)) chips.push(labels.dubbed);
  if (hasCatalogTracks(item.subtitles)) chips.push(labels.subtitled);
  if (hasCatalogTracks(item.audio)) chips.push(labels.audio);
  return chips;
}
