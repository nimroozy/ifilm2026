import { describe, expect, it, afterEach } from 'vitest';
import { api, mapMovieDto, tokenStore } from './api';

describe('api helpers', () => {
  afterEach(() => {
    tokenStore.clear();
    tokenStore.clearAdmin();
  });

  it('maps movie DTOs into frontend field names', () => {
    const mapped = mapMovieDto({
      id: 1,
      title: 'Test',
      original_title: 'آزمایش',
      year: 2026,
      duration: 100,
      rating: 8,
      age_rating: 'PG',
      genres: ['Drama'],
      country: 'Afghanistan',
      language: 'Dari',
      director: 'Director',
      cast: ['A'],
      description: 'desc',
      poster: 'p',
      backdrop: 'b',
      audio: ['Dari'],
      subtitles: ['English'],
      qualities: ['720p'],
      dubbed: [],
      featured: true,
      views: 10,
      type: 'movie',
    });

    expect(mapped.originalTitle).toBe('آزمایش');
    expect(mapped.ageRating).toBe('PG');
    expect(mapped.type).toBe('movie');
  });

  it('exposes token store helpers used by the API client', () => {
    tokenStore.set('abc');
    expect(tokenStore.get()).toBe('abc');
    tokenStore.clear();
    expect(tokenStore.get()).toBeNull();
    expect(api).toBeTruthy();
  });
});
