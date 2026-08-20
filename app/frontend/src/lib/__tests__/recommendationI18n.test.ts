import { describe, expect, it } from 'vitest';
import { localizeRecommendationShelfTitle } from '@/lib/recommendationI18n';
import { translations } from '@/data/translations';

describe('localizeRecommendationShelfTitle', () => {
  it('uses distinct newReleases title for new_releases shelves', () => {
    const fa = translations.fa.sections as Record<string, string>;
    expect(
      localizeRecommendationShelfTitle(
        { shelf_type: 'new_releases', title: 'New Releases' },
        fa
      )
    ).toBe(fa.newReleases);
    expect(fa.newReleases).not.toBe(fa.recentlyAdded);
  });

  it('falls back to recentlyAdded when newReleases is missing', () => {
    expect(
      localizeRecommendationShelfTitle(
        { shelf_type: 'new_releases', title: 'New Releases' },
        { recentlyAdded: 'Recently Added' }
      )
    ).toBe('Recently Added');
  });
});
