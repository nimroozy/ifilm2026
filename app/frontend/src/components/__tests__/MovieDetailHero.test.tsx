import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { MovieDetailView } from '@/components/MovieDetailView';
import { MOVIE_HERO_TRAILER_DELAY_MS } from '@/lib/catalogPresentation';
import type { CatalogMovie } from '@/lib/catalogData';
import type { WatchProgressDto } from '@/lib/api';

function baseMovie(overrides: Partial<CatalogMovie> = {}): CatalogMovie {
  return {
    id: 7,
    title: 'Hero Film',
    originalTitle: '',
    year: 2022,
    duration: 120,
    rating: 8.1,
    ageRating: 'PG-13',
    genres: ['Action'],
    country: 'US',
    language: 'English',
    director: 'Director',
    writer: 'Screenwriter',
    cast: [],
    description: 'Cinematic hero test.',
    poster: 'https://image.tmdb.org/t/p/w500/p.jpg',
    backdrop: 'https://image.tmdb.org/t/p/w780/b.jpg',
    audio: ['en'],
    subtitles: ['fa'],
    qualities: [],
    featured: false,
    type: 'movie',
    dubbed: ['fa'],
    views: 0,
    status: 'published',
    demoOwned: false,
    hasDemoClip: false,
    playable: true,
    hasPlayablePackage: true,
    trailerProvider: 'YouTube',
    trailerKey: 'trailKey1',
    trailerUrl: '',
    credits: [
      { personId: 9, name: 'Lead Actor', character: 'Captain', profileUrl: '', order: 0 },
    ],
    ...overrides,
  } as CatalogMovie;
}

function progress(partial: Partial<WatchProgressDto> = {}): WatchProgressDto {
  return {
    id: 1,
    media_asset_id: 'asset-1',
    content_type: 'movie',
    movie_id: 7,
    title: 'Hero Film',
    position_seconds: 600,
    duration_seconds: 7200,
    progress_percent: 42,
    completed: false,
    available: true,
    player_path: '/player/movie/7',
    ...partial,
  };
}

function renderDetail(
  movie: CatalogMovie,
  related: CatalogMovie[] = [],
  extras?: { watchState?: Parameters<typeof MovieDetailView>[0]['watchState'] }
) {
  return render(
    <LangProvider>
      <MemoryRouter>
        <MovieDetailView movie={movie} related={related} watchState={extras?.watchState ?? null} />
      </MemoryRouter>
    </LangProvider>
  );
}

describe('MovieDetailView hero experience', () => {
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
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts on backdrop and transitions to muted trailer', async () => {
    renderDetail(baseMovie());
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 10);
    });
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'trailer');
    const src = screen.getByTestId('youtube-trailer-embed').getAttribute('src') || '';
    expect(src).toContain('mute=1');
    expect(src).toContain('controls=0');
  });

  it('supports mute toggle, pause, and return to backdrop', async () => {
    renderDetail(baseMovie());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 10);
    });
    fireEvent.click(screen.getByTestId('trailer-mute-toggle'));
    expect(screen.getByTestId('youtube-trailer-embed').getAttribute('src')).toContain('mute=0');
    fireEvent.click(screen.getByTestId('trailer-pause-toggle'));
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('trailer-return-backdrop'));
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
  });

  it('shows Continue Watching with progress for incomplete state', () => {
    renderDetail(baseMovie(), [], { watchState: { kind: 'continue', progress: progress() } });
    expect(screen.getByTestId('movie-continue-button')).toHaveTextContent('Continue Watching');
    expect(screen.getByTestId('movie-continue-progress')).toBeInTheDocument();
    expect(screen.queryByTestId('movie-play-button')).not.toBeInTheDocument();
  });

  it('shows Watch Again for completed progress', () => {
    renderDetail(baseMovie(), [], {
      watchState: { kind: 'completed', progress: progress({ completed: true, progress_percent: 100 }) },
    });
    expect(screen.getByTestId('movie-watch-again-button')).toHaveTextContent('Watch Again');
  });

  it('renders portrait cast, crew, truthful tracks, and similar shelves', () => {
    renderDetail(baseMovie(), [baseMovie({ id: 8, title: 'Sibling Film', trailerKey: '' })]);
    expect(screen.getByTestId('movie-cast')).toHaveTextContent('Lead Actor');
    expect(screen.getByTestId('movie-cast')).toHaveTextContent('Captain');
    expect(screen.getByTestId('movie-crew')).toHaveTextContent('Director');
    expect(screen.getByTestId('movie-crew')).toHaveTextContent('Screenwriter');
    expect(screen.getByTestId('movie-track-meta')).toHaveTextContent('فارسی دوبله');
    expect(screen.getByTestId('movie-track-meta')).toHaveTextContent('فارسی');
    expect(screen.getByTestId('movie-similar')).toHaveTextContent('Sibling Film');
    expect(screen.getByTestId('watchlist-toggle')).toBeInTheDocument();
    expect(screen.queryByTestId('movie-reviews-placeholder')).not.toBeInTheDocument();
  });
});
