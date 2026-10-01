import { describe, expect, it } from 'vitest';
import { resolveCustomerTitle } from '@/components/customer/CustomerDocumentTitle';
import { translations } from '@/data/translations';

describe('resolveCustomerTitle', () => {
  it('recognizes player routes instead of labeling them as not found', () => {
    expect(resolveCustomerTitle('/player/movie/39', translations.en)).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/episode/17', translations.en)).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/asset/test-asset', translations.en)).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/movie/39', translations.en, '   ')).toBe('Playback · iFilm');
    expect(resolveCustomerTitle('/player/movie/39', translations.en, 'Playback')).toBe('Playback · iFilm');
  });

  it('uses movie and episode metadata when it is available', () => {
    expect(resolveCustomerTitle('/player/movie/39', translations.en, 'The Last Caravan')).toBe(
      'The Last Caravan · iFilm',
    );
    expect(resolveCustomerTitle('/player/episode/3', translations.en, 'Night Market')).toBe(
      'Night Market · iFilm',
    );
  });

  it('still labels unknown routes as not found', () => {
    expect(resolveCustomerTitle('/missing', translations.en)).toBe('Page not found · iFilm');
  });
});
