import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchMovies, fetchMovie, fetchSearch, fetchGenres, fetchSeries } from '../catalogData';
import { ApiError } from '../api';
import { movies as mockMovies } from '@/data/mockData';

vi.mock('../dataMode', () => ({
  getDataMode: () => 'api',
  isApiMode: () => true,
  isMockMode: () => false,
}));

const listMovies = vi.fn();
const getMovie = vi.fn();
const listSeries = vi.fn();
const search = vi.fn();
const listGenres = vi.fn();

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    api: {
      ...actual.api,
      listMovies: (...args: unknown[]) => listMovies(...args),
      getMovie: (...args: unknown[]) => getMovie(...args),
      listSeries: (...args: unknown[]) => listSeries(...args),
      search: (...args: unknown[]) => search(...args),
      listGenres: (...args: unknown[]) => listGenres(...args),
    },
  };
});

describe('catalogData api mode isolation', () => {
  beforeEach(() => {
    listMovies.mockReset();
    getMovie.mockReset();
    listSeries.mockReset();
    search.mockReset();
    listGenres.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('failed API request surfaces an error (no mock fallback)', async () => {
    listMovies.mockRejectedValue(new ApiError('backend down', 500));
    await expect(fetchMovies()).rejects.toThrow('backend down');
    await expect(fetchMovies()).rejects.not.toMatchObject({ items: expect.anything() });
  });

  it('empty API response returns empty state without fixtures', async () => {
    listMovies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    const result = await fetchMovies();
    expect(result.items).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.items.map((m) => m.title)).not.toContain(mockMovies[0]?.title);
  });

  it('timeout displays as recoverable ApiError', async () => {
    listMovies.mockRejectedValue(new ApiError('timeout of 15000ms exceeded', 0));
    await expect(fetchMovies()).rejects.toMatchObject({ message: expect.stringMatching(/timeout/i) });
  });

  it('malformed API response is rejected', async () => {
    listMovies.mockResolvedValue({ not: 'an envelope' } as never);
    await expect(fetchMovies()).rejects.toBeTruthy();
  });

  it('detail/search/genres failures never return mock fixtures', async () => {
    getMovie.mockRejectedValue(new ApiError('missing', 404));
    search.mockRejectedValue(new ApiError('search failed', 500));
    listGenres.mockRejectedValue(new ApiError('genres failed', 500));
    listSeries.mockRejectedValue(new ApiError('series failed', 503));

    await expect(fetchMovie('1')).rejects.toThrow('missing');
    await expect(fetchSearch('caravan')).rejects.toThrow('search failed');
    await expect(fetchGenres()).rejects.toThrow('genres failed');
    await expect(fetchSeries()).rejects.toThrow('series failed');
  });

  it('maps API envelope items on success', async () => {
    listMovies.mockResolvedValue({
      items: [
        {
          id: 9,
          title: 'API Film',
          slug: 'api-film',
          status: 'published',
          release_year: 2025,
          duration_minutes: 90,
          imdb_rating: 7.5,
          poster_url: 'https://example.com/p.jpg',
          genres: [{ id: 1, name: 'Drama', slug: 'drama' }],
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    const result = await fetchMovies();
    expect(result.items).toHaveLength(1);
    expect(result.items[0].title).toBe('API Film');
    expect(result.items[0].year).toBe(2025);
    expect(result.items[0].poster).toBe('https://example.com/p.jpg');
  });
});
