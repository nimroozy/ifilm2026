import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { ChildrenPage, MovieDetailsPage, MoviesPage } from '../Browse';
import { MOVIE_HERO_TRAILER_DELAY_MS } from '@/lib/catalogPresentation';

const fetchMovie = vi.fn();
const fetchMovies = vi.fn();
const fetchGenres = vi.fn();
const fetchSimilarMovies = vi.fn();

vi.mock('@/lib/catalogData', async () => {
  const actual = await vi.importActual<typeof import('@/lib/catalogData')>('@/lib/catalogData');
  return {
    ...actual,
    fetchMovie: (...args: unknown[]) => fetchMovie(...args),
    fetchMovies: (...args: unknown[]) => fetchMovies(...args),
    fetchGenres: (...args: unknown[]) => fetchGenres(...args),
    fetchSimilarMovies: (...args: unknown[]) => fetchSimilarMovies(...args),
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
    credits: [
      {
        personId: 1,
        name: 'Actor One',
        character: 'Hero',
        profileUrl: 'https://image.tmdb.org/t/p/w185/a.jpg',
        order: 0,
      },
    ],
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
    status: 'published',
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
    vi.useFakeTimers({ shouldAdvanceTime: true });
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    fetchMovie.mockReset();
    fetchMovies.mockReset();
    fetchGenres.mockReset();
    fetchSimilarMovies.mockReset();
    fetchMovies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    fetchSimilarMovies.mockResolvedValue([]);
    fetchGenres.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('distinguishes trailer and demo clip; hides full play for demo-owned titles', async () => {
    fetchMovie.mockResolvedValue(movie());

    renderMovieDetails();

    expect(await screen.findByRole('button', { name: /Play demo clip for TMDB Demo Title/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Watch trailer for TMDB Demo Title/i })).toBeInTheDocument();
    expect(screen.queryByTestId('movie-unavailable')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Watch Full Movie/i })).not.toBeInTheDocument();
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
  });

  it('auto-transitions hero to muted YouTube trailer after 6 seconds', async () => {
    fetchMovie.mockResolvedValue(movie());
    renderMovieDetails();
    await screen.findByTestId('movie-hero-backdrop');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 50);
    });

    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'trailer');
    const embed = screen.getByTestId('youtube-trailer-embed');
    expect(embed.getAttribute('src')).toContain('autoplay=1');
    expect(embed.getAttribute('src')).toContain('mute=1');
    expect(embed.getAttribute('src')).toContain('youtube-nocookie.com/embed/abc123XYZ');
  });

  it('keeps backdrop when no trailer exists', async () => {
    fetchMovie.mockResolvedValue(
      movie({
        trailerProvider: '',
        trailerKey: '',
        trailerUrl: '',
      })
    );
    renderMovieDetails();
    await screen.findByTestId('movie-hero-backdrop');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 50);
    });
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
  });

  it('exposes compact language badges and cast photos', async () => {
    fetchMovie.mockResolvedValue(
      movie({
        audio: ['en', 'fa'],
        dubbed: ['fa'],
        subtitles: ['en'],
        language: 'English',
        audioAvailability: {
          original_language: 'en',
          languages: ['en', 'fa'],
          dubbed_languages: ['fa'],
          track_count: null,
          source: 'admin_metadata',
          selectable_in_player: false,
        },
        subtitleAvailability: {
          languages: ['en'],
          track_count: null,
          source: 'admin_metadata',
          selectable_in_player: false,
        },
      })
    );

    renderMovieDetails();

    expect(await screen.findByTestId('movie-language-badges')).toHaveTextContent(/FA Dub/i);
    expect(screen.getByTestId('movie-language-badges')).toHaveTextContent(/EN Audio|EN Subtitle/i);
    expect(screen.getByTestId('movie-cast')).toHaveTextContent('Actor One');
    expect(screen.getByTestId('movie-cast')).toHaveTextContent('Hero');
    expect(screen.getByTestId('movie-mylist-button')).toBeInTheDocument();
  });

  it('shows Coming Soon when neither playable nor trailer exists', async () => {
    fetchMovie.mockResolvedValue(
      movie({
        demoOwned: false,
        hasDemoClip: false,
        playable: false,
        hasPlayablePackage: false,
        hasExternalMedia: false,
        trailerProvider: '',
        trailerKey: '',
        trailerUrl: '',
      })
    );

    renderMovieDetails();

    expect(await screen.findByTestId('movie-unavailable')).toHaveTextContent('Coming Soon');
    expect(screen.queryByText('Full Movie Unavailable')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Watch Full Movie/i })).not.toBeInTheDocument();
  });

  it('shows Play when backend marks package playable (Killer Man regression)', async () => {
    fetchMovie.mockResolvedValue(
      movie({
        title: 'The Killer Man',
        demoOwned: false,
        hasDemoClip: false,
        playable: true,
        hasPlayablePackage: true,
        hasExternalMedia: false,
        hlsPath: null,
        trailerProvider: '',
        trailerKey: '',
        trailerUrl: '',
      })
    );

    renderMovieDetails();

    expect(await screen.findByRole('button', { name: /Play The Killer Man/i })).toBeInTheDocument();
    expect(screen.queryByTestId('movie-unavailable')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Play demo clip/i })).not.toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: /Watch trailer/i })).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 50);
    });
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
  });

  it('renders similar movies shelf from API', async () => {
    fetchMovie.mockResolvedValue(movie());
    fetchSimilarMovies.mockResolvedValue([
      movie({ id: 99, title: 'Similar Title', demoOwned: false, hasDemoClip: false, playable: true }),
    ]);
    renderMovieDetails();
    expect(await screen.findByTestId('movie-similar')).toHaveTextContent('Similar Title');
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
