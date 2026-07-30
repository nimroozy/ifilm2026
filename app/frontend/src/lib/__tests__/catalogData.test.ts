import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchMovies } from '../catalogData';
import { ApiError } from '../api';

vi.mock('../dataMode', () => ({
  getDataMode: () => 'api',
  isApiMode: () => true,
  isMockMode: () => false,
}));

const listMovies = vi.fn();

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    api: {
      ...actual.api,
      listMovies: (...args: unknown[]) => listMovies(...args),
    },
  };
});

describe('catalogData api mode', () => {
  beforeEach(() => {
    listMovies.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does NOT fall back to mock data when the API fails', async () => {
    listMovies.mockRejectedValue(new ApiError('backend down', 500));

    await expect(fetchMovies()).rejects.toThrow('backend down');
    expect(listMovies).toHaveBeenCalled();
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
