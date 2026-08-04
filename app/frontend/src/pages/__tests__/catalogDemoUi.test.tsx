import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { ChildrenPage, MovieDetailsPage, MoviesPage } from '../Browse';

const fetchMovie = vi.fn();
const fetchMovies = vi.fn();
const fetchGenres = vi.fn();

vi.mock('@/lib/catalogData', async () => {
  const actual = await vi.importActual<typeof import('@/lib/catalogData')>('@/lib/catalogData');
  return {
    ...actual,
    fetchMovie: (...args: unknown[]) => fetchMovie(...args),
    fetchMovies: (...args: unknown[]) => fetchMovies(...args),
    fetchGenres: (...args: unknown[]) => fetchGenres(...args),
  };
});

function movie(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    title: 'TMDB Demo Title',
    originalTitle: 'Original Demo',
    year: 2024,
    duration: 101,
    rating: 7.8,
    ageRating: 'PG-13',
    genres: ['Drama'],
    country: 'US',
    language: 'English',
    director: 'Director',
    cast: ['Actor'],
    description: 'A demo catalog item.',
    poster: 'https://image.tmdb.org/t/p/w500/poster.jpg',
    backdrop: 'https://image.tmdb.org/t/p/w780/backdrop.jpg',
    audio: ['English'],
    subtitles: ['English'],
    qualities: [],
    featured: false,
    type: 'movie' as const,
    dubbed: [],
    views: 0,
    demoOwned: true,
    hasDemoClip: true,
    trailerProvider: 'YouTube',
    trailerKey: 'abc123XYZ',
    trailerUrl: 'https://www.youtube-nocookie.com/embed/abc123XYZ',
    ...overrides,
  };
}

function renderMovieDetails(path = '/movie/42') {
  return render(
    <LangProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/movie/:id" element={<MovieDetailsPage />} />
        </Routes>
      </MemoryRouter>
    </LangProvider>
  );
}

describe('demo catalog movie UI', () => {
  beforeEach(() => {
    fetchMovie.mockReset();
    fetchMovies.mockReset();
    fetchGenres.mockReset();
    fetchMovies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    fetchGenres.mockResolvedValue([]);
  });

  it('distinguishes trailer, demo clip, and unavailable full movie actions', async () => {
    fetchMovie.mockResolvedValue(movie());

    renderMovieDetails();

    expect(await screen.findByRole('button', { name: /Play demo clip for TMDB Demo Title/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Watch trailer for TMDB Demo Title/i })).toHaveAttribute(
      'href',
      'https://www.youtube-nocookie.com/embed/abc123XYZ'
    );
    expect(screen.getByTestId('full-movie-unavailable')).toHaveTextContent('Full Movie Unavailable');
    expect(screen.queryByRole('button', { name: /Watch Full Movie/i })).not.toBeInTheDocument();
    expect(screen.getByTestId('youtube-trailer-embed')).toHaveAttribute(
      'src',
      'https://www.youtube-nocookie.com/embed/abc123XYZ'
    );
  });

  it('rejects non-HTTPS trailer embeds', async () => {
    fetchMovie.mockResolvedValue(
      movie({
        trailerProvider: '',
        trailerKey: '',
        trailerUrl: 'http://www.youtube.com/embed/notSecure',
      })
    );

    renderMovieDetails();

    await screen.findByText('TMDB Demo Title');
    expect(screen.queryByRole('link', { name: /Watch trailer/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
  });

  it('shows Demo Clip badge on catalog cards', async () => {
    fetchMovies.mockResolvedValue({ items: [movie()], total: 1, page: 1, page_size: 100 });

    render(
      <LangProvider>
        <MemoryRouter>
          <MoviesPage />
        </MemoryRouter>
      </LangProvider>
    );

    expect(await screen.findByText('TMDB Demo Title')).toBeInTheDocument();
    expect(screen.getByTestId('demo-clip-badge')).toHaveTextContent('Demo Clip');
  });

  it('children route loads Family/Animation catalog, not generic Movies', async () => {
    fetchGenres.mockResolvedValue([{ id: 1, name: 'Family' }, { id: 2, name: 'Animation' }, { id: 3, name: 'Action' }]);
    fetchMovies.mockImplementation(async (opts?: { genre?: string }) => {
      if (opts?.genre === 'Family') {
        return {
          items: [movie({ id: 1, title: 'Family Title', genres: ['Family'] })],
          total: 1,
          page: 1,
          page_size: 100,
        };
      }
      if (opts?.genre === 'Animation') {
        return {
          items: [movie({ id: 2, title: 'Animation Title', genres: ['Animation'] })],
          total: 1,
          page: 1,
          page_size: 100,
        };
      }
      return {
        items: [movie({ id: 99, title: 'Unfiltered Action', genres: ['Action'] })],
        total: 1,
        page: 1,
        page_size: 100,
      };
    });

    render(
      <LangProvider>
        <MemoryRouter initialEntries={['/children']}>
          <Routes>
            <Route path="/children" element={<ChildrenPage />} />
          </Routes>
        </MemoryRouter>
      </LangProvider>
    );

    expect(await screen.findByTestId('children-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Children|کودکان|ماشومان/);
    expect(await screen.findByText('Family Title')).toBeInTheDocument();
    expect(screen.getByText('Animation Title')).toBeInTheDocument();
    expect(screen.queryByText('Unfiltered Action')).not.toBeInTheDocument();
    expect(screen.queryByTestId('movies-page')).not.toBeInTheDocument();

    const genres = fetchMovies.mock.calls.map((call) => (call[0] as { genre?: string } | undefined)?.genre);
    expect(genres).toEqual(expect.arrayContaining(['Family', 'Animation']));
    expect(genres).not.toContain(undefined);
  });
});
