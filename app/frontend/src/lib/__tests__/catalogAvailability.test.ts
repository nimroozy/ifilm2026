import { describe, expect, it } from 'vitest';
import {
  catalogAvailabilityBadge,
  catalogAvailabilityBadges,
  catalogAvailabilityChips,
  formatCatalogTracks,
  hasCatalogTracks,
  itemIsDubbed,
  itemIsSubtitled,
  normalizeLanguageCode,
} from '../catalogAvailability';

const labels = { dubbed: 'Dubbed', subtitled: 'Subtitled', audio: 'Audio', original: 'Original' };
const badgeLabels = { dubbed: 'Dubbed', subtitled: 'Subtitled', multiAudio: 'Multi Audio' };

describe('catalogAvailability', () => {
  it('normalizes aliases without merging Dari and Persian', () => {
    expect(normalizeLanguageCode('Persian')).toBe('fa');
    expect(normalizeLanguageCode('Dari')).toBe('prs');
    expect(normalizeLanguageCode('Pashto')).toBe('ps');
  });

  it('detects non-empty track lists', () => {
    expect(hasCatalogTracks(['Persian'])).toBe(true);
    expect(hasCatalogTracks(['', '  '])).toBe(false);
    expect(hasCatalogTracks([])).toBe(false);
    expect(hasCatalogTracks(undefined)).toBe(false);
  });

  it('formats track lists with display names', () => {
    expect(formatCatalogTracks(['fa', 'ps'])).toBe('Persian, Pashto');
    expect(formatCatalogTracks([])).toBe('');
  });

  it('uses structured availability for dub/sub detection', () => {
    expect(
      itemIsDubbed({
        audioAvailability: {
          original_language: 'en',
          languages: ['en', 'fa'],
          dubbed_languages: ['fa'],
          source: 'admin_metadata',
        },
      })
    ).toBe(true);
    expect(
      itemIsDubbed({
        audioAvailability: {
          original_language: 'fa',
          languages: ['fa'],
          dubbed_languages: [],
          source: 'admin_metadata',
        },
      })
    ).toBe(false);
    expect(
      itemIsSubtitled({
        subtitleAvailability: { languages: ['en'], source: 'admin_metadata' },
      })
    ).toBe(true);
  });

  it('prefers dubbed badge over subtitled/audio (legacy helper)', () => {
    expect(
      catalogAvailabilityBadge(
        { dubbed: ['Persian'], subtitles: ['English'], audio: ['Dari'] },
        labels
      )
    ).toBe('Dubbed');
    expect(catalogAvailabilityBadge({ subtitles: ['English'] }, labels)).toBe('Subtitled');
    expect(catalogAvailabilityBadge({}, labels)).toBeUndefined();
  });

  it('builds compact card badges with overflow', () => {
    const { badges, overflow } = catalogAvailabilityBadges(
      {
        audioAvailability: {
          dubbed_languages: ['fa', 'ps'],
          languages: ['en', 'fa', 'ps'],
        },
        subtitleAvailability: { languages: ['en', 'fa'] },
      },
      badgeLabels
    );
    expect(badges.length).toBe(2);
    expect(overflow).toBeGreaterThan(0);
    expect(badges[0].label).toMatch(/Dub/);
  });

  it('returns availability chips including original', () => {
    const chips = catalogAvailabilityChips(
      {
        audioAvailability: {
          original_language: 'en',
          languages: ['en', 'fa'],
          dubbed_languages: ['fa'],
        },
        subtitleAvailability: { languages: ['en'] },
      },
      labels
    );
    expect(chips.some((c) => c.includes('Original'))).toBe(true);
    expect(chips.some((c) => c.includes('Dubbed'))).toBe(true);
  });
});
