import { describe, expect, it, afterEach, vi, beforeEach } from 'vitest';
import { mapMovieDto, mapSeriesDto, tokenStore, ApiError, normalizeApiError } from './api';
import axios from 'axios';

describe('api helpers', () => {
  afterEach(() => {
    tokenStore.clear();
    tokenStore.clearAdmin();
  });

  it('maps movie DTOs with new backend field names into frontend shape', () => {
    const mapped = mapMovieDto({
      id: 1,
      title: 'Test',
      original_title: 'آزمایش',
      slug: 'test',
      release_year: 2026,
      duration_minutes: 100,
      imdb_rating: 8,
      age_rating: 'PG',
      genres: [{ id: 1, name: 'Drama', slug: 'drama' }],
      country: 'Afghanistan',
      language: 'Dari',
      director: 'Director',
      cast: ['A'],
      description: 'desc',
      poster_url: 'p',
      backdrop_url: 'b',
      audio: ['Dari'],
      subtitles: ['English'],
      qualities: ['720p'],
      dubbed: [],
      is_featured: true,
      status: 'published',
      views: 10,
      type: 'movie',
    });

    expect(mapped.originalTitle).toBe('آزمایش');
    expect(mapped.ageRating).toBe('PG');
    expect(mapped.year).toBe(2026);
    expect(mapped.duration).toBe(100);
    expect(mapped.rating).toBe(8);
    expect(mapped.poster).toBe('p');
    expect(mapped.featured).toBe(true);
    expect(mapped.genres).toEqual(['Drama']);
    expect(mapped.type).toBe('movie');
  });

  it('maps series DTOs using airing_status for UI status', () => {
    const mapped = mapSeriesDto({
      id: 2,
      title: 'Show',
      slug: 'show',
      status: 'published',
      airing_status: 'Ongoing',
      release_year: 2024,
      imdb_rating: 9,
      season_count: 2,
      episode_count: 16,
      poster_url: 'sp',
      genres: ['Crime'],
    });
    expect(mapped.status).toBe('Ongoing');
    expect(mapped.seasons).toBe(2);
    expect(mapped.episodes).toBe(16);
    expect(mapped.rating).toBe(9);
  });

  it('exposes token store helpers used by the API client', () => {
    tokenStore.set('abc');
    expect(tokenStore.get()).toBe('abc');
    tokenStore.clear();
    expect(tokenStore.get()).toBeNull();
    tokenStore.setAdmin('admin-tok');
    expect(tokenStore.getAdmin()).toBe('admin-tok');
    tokenStore.clearAdmin();
    expect(tokenStore.getAdmin()).toBeNull();
  });

  it('normalizes axios errors into ApiError', () => {
    const err = {
      isAxiosError: true,
      message: 'Request failed',
      response: { status: 409, data: { detail: 'Genre is assigned' } },
    };
    vi.spyOn(axios, 'isAxiosError').mockReturnValue(true);
    const normalized = normalizeApiError(err);
    expect(normalized).toBeInstanceOf(ApiError);
    expect(normalized.status).toBe(409);
    expect(normalized.message).toBe('Genre is assigned');
    vi.restoreAllMocks();
  });
});
