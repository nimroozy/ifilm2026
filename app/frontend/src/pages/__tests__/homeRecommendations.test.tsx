import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from '@/pages/Index';

const getHomeRecommendations = vi.fn();
const getMyHomeRecommendations = vi.fn();
const listWatchlist = vi.fn();
const listContinueWatching = vi.fn();

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
  isApiMode: () => true,
}));

vi.mock('@/lib/catalogData', () => ({
  fetchHomeCatalog: vi.fn(async () => ({
    featured: [],
    trending: [],
    recentlyAdded: [
      {
        id: 99,
        type: 'movie',
        title: 'Fresh Title',
        slug: 'fresh',
        year: 2026,
        rating: 7,
        duration: 100,
        genres: [],
        poster: '',
        backdrop: '',
        description: '',
        playable: true,
      },
    ],
    popular: [],
    popularSeries: [],
    actionMovies: [],
    comedyMovies: [],
    familyMovies: [],
    afghanMovies: [],
    persianDubbed: [],
    pashtoDubbed: [],
    featuredCollections: [],
    recommendations: {
      mode: 'anonymous',
      personalized: false,
      shelves: [
        {
          shelf_type: 'popular',
          title: 'Popular Now',
          personalized: false,
          items: [
            {
              content_type: 'movie',
              id: 1,
              slug: 'hit',
              title: 'Hit Movie',
              poster_url: 'https://example.test/p.jpg',
              score: 0.5,
              reasons: ['Popular in the catalog'],
              explanation: 'Popular in the catalog',
              detail_path: '/movie/hit',
            },
          ],
        },
        {
          shelf_type: 'new_releases',
          title: 'New Releases',
          personalized: false,
          items: [
            {
              content_type: 'movie',
              id: 2,
              slug: 'new',
              title: 'Brand New',
              poster_url: 'https://example.test/n.jpg',
              score: 0.4,
              reasons: ['Recently added'],
              explanation: 'Recently added',
              detail_path: '/movie/new',
            },
          ],
        },
      ],
    },
  })),
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
      sections: {
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
    },
  }),
  useAuth: () => ({ isLoggedIn: false }),
}));

vi.mock('@/components/HeroCarousel', () => ({
  HeroCarousel: () => <div data-testid="hero" />,
}));

describe('Home recommendation shelves', () => {
  beforeEach(() => {
    getHomeRecommendations.mockReset();
    getMyHomeRecommendations.mockReset();
    listWatchlist.mockReset();
    listContinueWatching.mockReset();
    listContinueWatching.mockResolvedValue([]);
    listWatchlist.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  });

  it('shows anonymous Popular Now shelf and What-to-Watch CTA', async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

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

  it('does not duplicate Recently Added when new_releases shelf is present', async () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-popular')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId('home-shelf-new_releases')).toBeInTheDocument();
    });
    expect(screen.getByText('New Releases')).toBeInTheDocument();
    expect(screen.queryByText('Recently Added')).not.toBeInTheDocument();
    expect(screen.getByText('Brand New')).toBeInTheDocument();
  });
});
