import { describe, expect, it } from 'vitest';
import { resolveCustomerTitle } from '@/components/customer/CustomerDocumentTitle';
import { translations } from '@/data/translations';

describe('resolveCustomerTitle', () => {
  it('recognizes player routes instead of labeling them as not found', () => {
    expect(resolveCustomerTitle('/player/movie/39', translations.en)).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/episode/17', translations.en)).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/asset/test-asset', translations.en)).toBe('Playback · iFilm');
  });
});
