import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { CollectionsIndexPage, CollectionDetailPage } from '../CollectionsPages';
import { ApiError } from '@/lib/api';

const fetchCollections = vi.fn();
const fetchCollection = vi.fn();

vi.mock('@/lib/catalogData', async () => {
  const actual = await vi.importActual<typeof import('@/lib/catalogData')>('@/lib/catalogData');
  return {
    ...actual,
    fetchCollections: (...args: unknown[]) => fetchCollections(...args),
    fetchCollection: (...args: unknown[]) => fetchCollection(...args),
  };
});

function renderIndex() {
  return render(
    <LangProvider>
      <MemoryRouter initialEntries={['/collections']}>
        <Routes>
          <Route path="/collections" element={<CollectionsIndexPage />} />
        </Routes>
      </MemoryRouter>
    </LangProvider>
  );
}

function renderDetail(slug: string) {
  return render(
    <LangProvider>
      <MemoryRouter initialEntries={[`/collections/${slug}`]}>
        <Routes>
          <Route path="/collections/:slug" element={<CollectionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </LangProvider>
  );
}

describe('customer collections pages', () => {
  beforeEach(() => {
    fetchCollections.mockReset();
    fetchCollection.mockReset();
  });

  it('renders published collections with artwork, title, description and item count', async () => {
    fetchCollections.mockResolvedValue({
      items: [
        {
          id: 1,
          title: 'Editorial Picks',
          slug: 'editorial-picks',
          collection_type: 'editorial',
          short_description: 'Hand-picked favorites',
          poster_url: 'https://example.com/poster.jpg',
          item_count: 4,
          items: [],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    });

    renderIndex();

    await waitFor(() => expect(screen.getByTestId('collections-grid')).toBeInTheDocument());
    expect(screen.getByText('Editorial Picks')).toBeInTheDocument();
    expect(screen.getByText('Hand-picked favorites')).toBeInTheDocument();
    expect(screen.getByTestId('collection-card-editorial-picks')).toBeInTheDocument();
  });

  it('hides collections with zero items and shows the empty state', async () => {
    fetchCollections.mockResolvedValue({
      items: [
        {
          id: 2,
          title: 'Empty Collection',
          slug: 'empty-collection',
          collection_type: 'editorial',
          item_count: 0,
          items: [],
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    });

    renderIndex();

    await waitFor(() => expect(screen.getByTestId('collections-empty')).toBeInTheDocument());
    expect(screen.queryByText('Empty Collection')).not.toBeInTheDocument();
  });

  it('shows an error state with retry when the index fails to load', async () => {
    fetchCollections.mockRejectedValue(new ApiError('Server exploded', 500));

    renderIndex();

    await waitFor(() => {
      expect(screen.getByTestId('collections-error')).toHaveTextContent(/server exploded/i);
    });
  });

  it('renders an ordered media grid with a hero banner when backdrop_url is present', async () => {
    fetchCollection.mockResolvedValue({
      id: 3,
      title: 'Franchise Marathon',
      slug: 'franchise-marathon',
      collection_type: 'franchise',
      backdrop_url: 'https://example.com/backdrop.jpg',
      item_count: 2,
      items: [
        {
          id: 1,
          collection_id: 3,
          movie_id: 10,
          position: 0,
          content_type: 'movie',
          movie: {
            id: 10,
            title: 'First Movie',
            slug: 'first-movie',
            status: 'published',
            poster_url: 'https://example.com/first.jpg',
          },
        },
        {
          id: 2,
          collection_id: 3,
          movie_id: 11,
          position: 1,
          content_type: 'movie',
          movie: {
            id: 11,
            title: 'Second Movie',
            slug: 'second-movie',
            status: 'published',
            poster_url: 'https://example.com/second.jpg',
          },
        },
      ],
    });

    renderDetail('franchise-marathon');

    await waitFor(() => expect(screen.getByTestId('collection-detail-page')).toBeInTheDocument());
    expect(screen.getByText('Franchise Marathon')).toBeInTheDocument();
    expect(screen.getByTestId('collection-items-grid')).toBeInTheDocument();
    expect(screen.getByText('First Movie')).toBeInTheDocument();
    expect(screen.getByText('Second Movie')).toBeInTheDocument();
  });

  it('renders NotFoundPage for unknown slugs', async () => {
    fetchCollection.mockRejectedValue(new ApiError('Not found', 404));

    renderDetail('unknown-slug');

    await waitFor(() => {
      expect(screen.getByTestId('not-found-page')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('collection-detail-page')).not.toBeInTheDocument();
  });
});
