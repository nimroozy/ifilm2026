import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { MovieDetailView } from '@/components/MovieDetailView';
import { MOVIE_HERO_TRAILER_DELAY_MS } from '@/lib/catalogPresentation';
import type { CatalogMovie } from '@/lib/catalogData';

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

function renderDetail(movie: CatalogMovie, related: CatalogMovie[] = []) {
  return render(
    <LangProvider>
      <MemoryRouter>
        <MovieDetailView movie={movie} related={related} />
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

  it('starts on backdrop and transitions to trailer', async () => {
    renderDetail(baseMovie());
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 10);
    });
    expect(screen.getByTestId('movie-hero')).toHaveAttribute('data-hero-mode', 'trailer');
    expect(screen.getByTestId('youtube-trailer-embed').getAttribute('src')).toContain('mute=1');
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

  it('renders RTL-friendly cast and similar shelves', () => {
    renderDetail(baseMovie(), [baseMovie({ id: 8, title: 'Sibling Film', trailerKey: '' })]);
    expect(screen.getByTestId('movie-cast')).toHaveTextContent('Lead Actor');
    expect(screen.getByTestId('movie-similar')).toHaveTextContent('Sibling Film');
    expect(screen.getByTestId('movie-mylist-button')).toHaveTextContent(/My List/i);
    expect(screen.getByTestId('movie-reviews-placeholder')).toBeInTheDocument();
  });
});
