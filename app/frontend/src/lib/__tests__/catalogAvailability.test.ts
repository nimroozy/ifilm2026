import { describe, expect, it } from 'vitest';
import {
  catalogAvailabilityBadge,
  catalogAvailabilityChips,
  formatCatalogTracks,
  hasCatalogTracks,
} from '../catalogAvailability';

const labels = { dubbed: 'Dubbed', subtitled: 'Subtitled', audio: 'Audio' };

describe('catalogAvailability', () => {
  it('detects non-empty track lists', () => {
    expect(hasCatalogTracks(['Persian'])).toBe(true);
    expect(hasCatalogTracks(['', '  '])).toBe(false);
    expect(hasCatalogTracks([])).toBe(false);
    expect(hasCatalogTracks(undefined)).toBe(false);
  });

  it('formats track lists', () => {
    expect(formatCatalogTracks(['Persian', 'Pashto'])).toBe('Persian, Pashto');
    expect(formatCatalogTracks([])).toBe('');
  });

  it('prefers dubbed badge over subtitled/audio', () => {
    expect(
      catalogAvailabilityBadge(
        { dubbed: ['Persian'], subtitles: ['English'], audio: ['Dari'] },
        labels
      )
    ).toBe('Dubbed');
    expect(catalogAvailabilityBadge({ subtitles: ['English'] }, labels)).toBe('Subtitled');
    expect(catalogAvailabilityBadge({ audio: ['Dari'] }, labels)).toBe('Audio');
    expect(catalogAvailabilityBadge({}, labels)).toBeUndefined();
  });

  it('returns all availability chips when present', () => {
    expect(
      catalogAvailabilityChips(
        { dubbed: ['Persian'], subtitles: ['English'], audio: ['Dari'] },
        labels
      )
    ).toEqual(['Dubbed', 'Subtitled', 'Audio']);
  });
});
