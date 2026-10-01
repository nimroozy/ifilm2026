import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from '@/pages/Index';

const getHomeRecommendations = vi.fn();
const getMyHomeRecommendations = vi.fn();
const listWatchlist = vi.fn();
const listContinueWatching = vi.fn();

function movie(id: number, title: string, rating = 7) {
  return {
    id,
    type: 'movie' as const,
    title,
    slug: title.toLowerCase().replace(/\s+/g, '-'),
    year: 2026,
    rating,
    duration: 100,
    genres: [] as string[],
    poster: '',
    backdrop: '',
    description: '',
    playable: true,
  };
}

function recItem(id: number, title: string, slug: string) {
  return {
    content_type: 'movie' as const,
    id,
    slug,
    title,
    poster_url: 'https://example.test/p.jpg',
    score: 0.5,
    reasons: ['Popular in the catalog'],
    explanation: 'Popular in the catalog',
    detail_path: `/movie/${slug}`,
  };
}

const { sectionCopy, homePayload } = vi.hoisted(() => ({
  sectionCopy: {
    continueWatching: 'Continue Watching',
    trending: 'Trending',
    recentlyAdded: 'Recently Added',
    newReleases: 'New Releases',
    popularMovies: 'Popular Movies',
    popularSeries: 'Popular Series',
    action: 'Action',
    comedy: 'Comedy',
    drama: 'Drama',
    animationFamily: 'Animation & Family',
    afghanMovies: 'Afghan',
    persianDubbed: 'Persian',
    pashtoDubbed: 'Pashto',
    recommended: 'Recommended for You',
    popularNow: 'Popular Now',
    myList: 'My List',
    topRated: 'Top Rated',
  },
  homePayload: {
    featured: [] as unknown[],
    trending: [] as unknown[],
    recentlyAdded: [] as unknown[],
    popular: [] as unknown[],
    popularSeries: [] as unknown[],
    actionMovies: [] as unknown[],
    comedyMovies: [] as unknown[],
    familyMovies: [] as unknown[],
    afghanMovies: [] as unknown[],
    persianDubbed: [] as unknown[],
    pashtoDubbed: [] as unknown[],
    featuredCollections: [] as unknown[],
    recommendations: null as null | {
      mode: string;
      personalized: boolean;
      shelves: Array<{
        shelf_type: string;
        title: string;
        personalized: boolean;
        items: unknown[];
      }>;
    },
  },
}));

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
  isApiMode: () => true,
}));

vi.mock('@/lib/catalogData', () => ({
  fetchHomeCatalog: vi.fn(async () => structuredClone(homePayload)),
  fetchMeHomeCatalog: vi.fn(async () => {
    throw new Error('not authenticated in test');
  }),
  fetchFeaturedHomeCollections: vi.fn(async () => []),
  mapCollectionItems: () => [],
}));

vi.mock('@/lib/api', () => ({
  api: {
    getHomeRecommendations: (...args: unknown[]) => getHomeRecommendations(...args),
    getMyHomeRecommendations: (...args: unknown[]) => getMyHomeRecommendations(...args),
    listWatchlist: (...args: unknown[]) => listWatchlist(...args),
    listContinueWatching: (...args: unknown[]) => listContinueWatching(...args),
  },
  tokenStore: {
    get: () => null,
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 400) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock('@/components/CustomerLayout', () => ({
  useLang: () => ({
    lang: 'en',
    t: {
      nav: { whatToWatch: 'What to Watch', myList: 'My List' },
      sections: sectionCopy,
    },
  }),
  useAuth: () => ({ isLoggedIn: false }),
}));

vi.mock('@/components/HeroCarousel', () => ({
  HeroCarousel: () => <div data-testid="hero" />,
}));

function headingTexts(): string[] {
  return screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent ?? '');
}

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

describe('Home recommendation shelves', () => {
  beforeEach(() => {
    getHomeRecommendations.mockReset();
    getMyHomeRecommendations.mockReset();
    listWatchlist.mockReset();
    listContinueWatching.mockReset();
    listContinueWatching.mockResolvedValue([]);
    listWatchlist.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    sectionCopy.recentlyAdded = 'Recently Added';
    sectionCopy.newReleases = 'New Releases';
    sectionCopy.topRated = 'Top Rated';
    homePayload.recentlyAdded = [movie(99, 'Fresh Title')];
    homePayload.popular = [movie(10, 'Catalog Favorite', 9.1), movie(11, 'Catalog Only Hit', 8.2)];
    homePayload.recommendations = {
      mode: 'anonymous',
      personalized: false,
      shelves: [
        {
          shelf_type: 'popular',
          title: 'Popular Now',
          personalized: false,
          items: [recItem(1, 'Hit Movie', 'hit')],
        },
        {
          shelf_type: 'new_releases',
          title: 'New Releases',
          personalized: false,
          items: [recItem(2, 'Brand New', 'new')],
        },
        {
          shelf_type: 'top_rated',
          title: 'Top Rated',
          personalized: false,
          items: [recItem(10, 'Catalog Favorite', 'catalog-favorite')],
        },
      ],
    };
  });

  it('shows anonymous Popular Now shelf and What-to-Watch CTA', async () => {
    renderHome();

    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-popular')).toBeInTheDocument();
    });
    expect(screen.getByText('Popular Now')).toBeInTheDocument();
    expect(screen.getByText('Hit Movie')).toBeInTheDocument();
    expect(screen.queryByText('Recommended for You')).not.toBeInTheDocument();
    expect(screen.getByTestId('home-what-to-watch-cta')).toBeInTheDocument();
    // Recommendations come from catalog/home aggregate — no separate recs call.
    expect(getHomeRecommendations).not.toHaveBeenCalled();
  });

  it('keeps distinct New Releases and Recently Added rails, each once', async () => {
    renderHome();

    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-new_releases')).toBeInTheDocument();
    });
    expect(screen.getAllByRole('heading', { level: 2, name: 'New Releases' })).toHaveLength(1);
    expect(screen.getAllByRole('heading', { level: 2, name: 'Recently Added' })).toHaveLength(1);
    expect(screen.getByText('Brand New')).toBeInTheDocument();
    expect(screen.getByText('Fresh Title')).toBeInTheDocument();
    expect(new Set(headingTexts()).size).toBe(headingTexts().length);
  });

  it('renders Top Rated once and still shows catalog-only movies', async () => {
    renderHome();

    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-top_rated')).toBeInTheDocument();
    });
    expect(screen.getAllByRole('heading', { level: 2, name: 'Top Rated' })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 2, name: 'Popular Movies' })).toBeInTheDocument();
    expect(screen.getAllByText('Catalog Favorite').length).toBeGreaterThan(0);
    expect(screen.getByText('Catalog Only Hit')).toBeInTheDocument();
    expect(new Set(headingTexts()).size).toBe(headingTexts().length);
  });

  it('drops the catalog rail when its title matches a recommendation shelf', async () => {
    sectionCopy.newReleases = 'Recently Added';
    renderHome();

    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-new_releases')).toBeInTheDocument();
    });
    expect(screen.getAllByRole('heading', { level: 2, name: 'Recently Added' })).toHaveLength(1);
    expect(screen.queryByRole('heading', { level: 2, name: 'New Releases' })).not.toBeInTheDocument();
    expect(screen.getByText('Brand New')).toBeInTheDocument();
    expect(screen.queryByText('Fresh Title')).not.toBeInTheDocument();
  });

  it('shows Recently Added once when recommendation shelves are absent', async () => {
    homePayload.recommendations = null;
    homePayload.popular = [];
    renderHome();

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: 'Recently Added' })).toBeInTheDocument();
    });
    expect(screen.getAllByRole('heading', { level: 2, name: 'Recently Added' })).toHaveLength(1);
    expect(screen.getByText('Fresh Title')).toBeInTheDocument();
    expect(screen.queryByTestId('home-shelf-new_releases')).not.toBeInTheDocument();
  });
});
