/** Visible homepage rail titles, compared case-insensitively after trim. */

export function shelfTitleKey(title: string): string {
  return title.trim().toLocaleLowerCase();
}

/**
 * Reserve a shelf heading. The first caller receives the trimmed title;
 * a later rail with the same visible label receives null and should not render.
 * Empty titles are not reserved, so they cannot block a later real heading.
 */
export function claimShelfTitle(title: string, claimed: Set<string>): string | null {
  const trimmed = title.trim();
  if (!trimmed) return null;
  const key = shelfTitleKey(trimmed);
  if (claimed.has(key)) return null;
  claimed.add(key);
  return trimmed;
}
