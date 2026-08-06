import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import HomePage from '../Index';

const fetchHomeCatalog = vi.fn();
const fetchFeaturedHomeCollections = vi.fn();

vi.mock('@/lib/catalogData', async () => {
  const actual = await vi.importActual<typeof import('@/lib/catalogData')>('@/lib/catalogData');
  return {
    ...actual,
    fetchHomeCatalog: (...args: unknown[]) => fetchHomeCatalog(...args),
    fetchFeaturedHomeCollections: (...args: unknown[]) => fetchFeaturedHomeCollections(...args),
  };
});

function emptyHomeData() {
  return {
    featured: [],
    trending: [],
    recentlyAdded: [],
    popular: [],
    afghanMovies: [],
    persianDubbed: [],
    pashtoDubbed: [],
    actionMovies: [],
    comedyMovies: [],
    familyMovies: [],
    popularSeries: [],
  };
}

function renderHome() {
  return render(
    <LangProvider>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </LangProvider>
  );
}

describe('homepage featured collection shelves', () => {
  beforeEach(() => {
    fetchHomeCatalog.mockReset();
    fetchFeaturedHomeCollections.mockReset();
    fetchHomeCatalog.mockResolvedValue(emptyHomeData());
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

  it('renders a ContentShelf per featured collection while preserving existing shelves', async () => {
    fetchFeaturedHomeCollections.mockResolvedValue([
      {
        id: 1,
        title: 'Staff Picks',
        slug: 'staff-picks',
        collection_type: 'staff_pick',
        item_count: 1,
        items: [
          {
            id: 1,
            collection_id: 1,
            movie_id: 99,
            position: 0,
            content_type: 'movie',
            movie: {
              id: 99,
              title: 'Featured Film',
              slug: 'featured-film',
              status: 'published',
              poster_url: 'https://example.com/p.jpg',
            },
          },
        ],
      },
    ]);

    renderHome();

    await waitFor(() => expect(screen.getByText('Staff Picks')).toBeInTheDocument());
    expect(screen.getByText('Featured Film')).toBeInTheDocument();
  });

  it('hides collection shelves that end up with zero mapped items', async () => {
    fetchFeaturedHomeCollections.mockResolvedValue([
      {
        id: 2,
        title: 'Broken Collection',
        slug: 'broken-collection',
        collection_type: 'editorial',
        item_count: 1,
        items: [
          {
            id: 5,
            collection_id: 2,
            movie_id: 100,
            position: 0,
            content_type: 'movie',
            movie: undefined,
          },
        ],
      },
    ]);

    renderHome();

    await waitFor(() => expect(fetchFeaturedHomeCollections).toHaveBeenCalled());
    expect(screen.queryByText('Broken Collection')).not.toBeInTheDocument();
  });

  it('never breaks the homepage when the collections fetch fails', async () => {
    fetchFeaturedHomeCollections.mockRejectedValue(new Error('boom'));

    renderHome();

    await waitFor(() => expect(fetchHomeCatalog).toHaveBeenCalled());
    // Homepage should still render without throwing / crashing — no error state shown.
    await waitFor(() => expect(screen.queryByTestId('home-loading')).not.toBeInTheDocument());
    expect(screen.queryByTestId('home-error')).not.toBeInTheDocument();
  });
});
