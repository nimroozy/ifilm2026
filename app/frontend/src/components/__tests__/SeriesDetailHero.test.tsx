import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { SeriesDetailView, type SeriesEpisodeView } from '@/components/SeriesDetailView';
import type { CatalogSeries } from '@/lib/catalogData';
import type { WatchProgressDto } from '@/lib/api';
import { MOVIE_HERO_TRAILER_DELAY_MS } from '@/lib/catalogPresentation';
import type { SeriesHeroCta } from '@/lib/seriesDetailPlayback';

function baseSeries(overrides: Partial<CatalogSeries> = {}): CatalogSeries {
  return {
    id: 9,
    title: 'Hero Series',
    originalTitle: '',
    year: 2020,
    endYear: 2022,
    rating: 8.4,
    ageRating: 'TV-MA',
    genres: ['Drama', 'Crime'],
    country: 'US',
    language: 'English',
    seasons: 2,
    episodes: 20,
    status: 'Completed',
    description: 'Cinematic series hero test with enough text to exercise overview clamping on desktop layouts.',
    poster: 'https://image.tmdb.org/t/p/w500/p.jpg',
    backdrop: 'https://image.tmdb.org/t/p/w780/b.jpg',
    logoUrl: '',
    audio: ['en'],
    subtitles: ['fa'],
    dubbed: [],
    audioAvailability: { languages: ['en'], dubbed_languages: [], source: 'tracks' },
    subtitleAvailability: { languages: ['fa'], source: 'tracks' },
    type: 'series',
    newEpisode: false,
    views: 0,
    slug: 'hero-series',
    catalogStatus: 'published',
    isFeatured: false,
    isTrending: false,
    tmdbId: null,
    metadataSource: '',
    demoOwned: false,
    hasDemoClip: false,
    trailerUrl: '',
    trailerProvider: 'YouTube',
    trailerKey: 'seriesTrail1',
    trailerTitle: '',
    trailerOfficial: true,
    trailerLanguage: 'en',
    trailerPublishedAt: null,
    publishedAt: null,
    createdAt: null,
    genreIds: [],
    credits: [{ personId: 1, name: 'Lead', character: 'Hero', profileUrl: '', order: 0 }],
    creditsSyncedAt: null,
    tagline: '',
    localization: null,
    ...overrides,
  } as CatalogSeries;
}

function episode(partial: Partial<SeriesEpisodeView> & Pick<SeriesEpisodeView, 'id' | 'season' | 'episode'>): SeriesEpisodeView {
  return {
    seriesId: 9,
    seasonId: 1,
    title: `Episode ${partial.episode}`,
    duration: 48,
    description: 'Episode synopsis',
    thumbnail: '',
    status: 'published',
    playable: true,
    hasDemoClip: false,
    ...partial,
  };
}

function renderSeries(
  cta: SeriesHeroCta<SeriesEpisodeView>,
  extras?: {
    episodes?: SeriesEpisodeView[];
    seasons?: { number: number; episodeCount: number }[];
    selectedSeason?: number;
  }
) {
  const eps = extras?.episodes ?? [episode({ id: 1, season: 1, episode: 1 })];
  return render(
    <LangProvider>
      <MemoryRouter>
        <SeriesDetailView
          series={baseSeries()}
          seasons={extras?.seasons ?? [{ number: 1, episodeCount: 1 }, { number: 2, episodeCount: 3 }]}
          episodes={eps}
          selectedSeason={extras?.selectedSeason ?? 1}
          onSeasonChange={() => undefined}
          recommended={[]}
          heroCta={cta}
          progressByEpisode={new Map()}
        />
      </MemoryRouter>
    </LangProvider>
  );
}

describe('SeriesDetailView G2b', () => {
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

  it('keeps cinematic backdrop and does not autoplay trailer', async () => {
    renderSeries({
      kind: 'play',
      episode: episode({ id: 1, season: 1, episode: 1 }),
      code: 'S01E01',
    });
    expect(screen.getByTestId('series-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    expect(screen.getByTestId('series-hero')).toHaveAttribute('data-trailer-policy', 'button-only');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MOVIE_HERO_TRAILER_DELAY_MS + 50);
    });
    expect(screen.getByTestId('series-hero')).toHaveAttribute('data-hero-mode', 'backdrop');
    expect(screen.queryByTestId('youtube-trailer-embed')).not.toBeInTheDocument();
  });

  it('opens muted trailer only after Trailer button click', () => {
    renderSeries({
      kind: 'play',
      episode: episode({ id: 1, season: 1, episode: 1 }),
      code: 'S01E01',
    });
    fireEvent.click(screen.getByTestId('series-trailer-button'));
    expect(screen.getByTestId('series-hero')).toHaveAttribute('data-hero-mode', 'trailer');
    const src = screen.getByTestId('youtube-trailer-embed').getAttribute('src') || '';
    expect(src).toContain('mute=1');
  });

  it('shows exclusive continue CTA', () => {
    const ep = episode({ id: 3, season: 1, episode: 3 });
    renderSeries({
      kind: 'continue',
      episode: ep,
      code: 'S01E03',
      progressPercent: 42,
      progress: {
        id: 1,
        media_asset_id: 'a',
        content_type: 'episode',
        episode_id: 3,
        series_id: 9,
        title: 'E3',
        progress_percent: 42,
        completed: false,
        available: true,
        player_path: '/player/episode/3',
      } as WatchProgressDto,
    });
    expect(screen.getByTestId('series-continue-button')).toBeInTheDocument();
    expect(screen.queryByTestId('series-play-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('series-next-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('series-watch-again-button')).not.toBeInTheDocument();
  });

  it('shows exclusive next episode CTA', () => {
    const ep = episode({ id: 4, season: 2, episode: 1 });
    renderSeries({
      kind: 'next',
      episode: ep,
      code: 'S02E01',
      from: {
        id: 1,
        media_asset_id: 'a',
        content_type: 'episode',
        episode_id: 3,
        series_id: 9,
        title: 'Finale',
        progress_percent: 100,
        completed: true,
        available: true,
        player_path: '/player/episode/3',
      } as WatchProgressDto,
    });
    expect(screen.getByTestId('series-next-button')).toHaveTextContent('S02E01');
    expect(screen.queryByTestId('series-continue-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('series-play-button')).not.toBeInTheDocument();
  });

  it('renders cast rail and episode codes', () => {
    renderSeries(
      {
        kind: 'play',
        episode: episode({ id: 1, season: 1, episode: 1 }),
        code: 'S01E01',
      },
      { episodes: [episode({ id: 1, season: 1, episode: 1, title: 'Pilot' })] }
    );
    expect(screen.getByTestId('series-cast')).toBeInTheDocument();
    expect(screen.getByTestId('episode-row-1')).toHaveAttribute('data-episode-code', 'S01E01');
  });
});
