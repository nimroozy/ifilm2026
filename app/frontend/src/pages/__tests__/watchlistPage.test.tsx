import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { WatchlistPage } from '@/pages/Account';

const listWatchlist = vi.fn();
const deleteWatchlistItem = vi.fn();
const clearWatchlist = vi.fn();

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
  isApiMode: () => true,
}));

vi.mock('@/lib/api', () => ({
  api: {
    listWatchlist: (...args: unknown[]) => listWatchlist(...args),
    deleteWatchlistItem: (...args: unknown[]) => deleteWatchlistItem(...args),
    clearWatchlist: (...args: unknown[]) => clearWatchlist(...args),
  },
  tokenStore: {
    get: () => 'token',
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
    t: {
      profile: { watchlist: 'Watchlist' },
      common: { cancel: 'Cancel', delete: 'Delete' },
      login: { signIn: 'Sign In' },
    },
  }),
  useAuth: () => ({ isLoggedIn: true }),
}));

vi.mock('@/hooks/use-toast', () => ({
  toast: vi.fn(),
}));

describe('WatchlistPage', () => {
  beforeEach(() => {
    listWatchlist.mockReset();
    deleteWatchlistItem.mockReset();
    clearWatchlist.mockReset();
  });

  it('renders watchlist grid from API', async () => {
    listWatchlist.mockResolvedValue({
      items: [
        {
          id: 1,
          content_type: 'movie',
          movie_id: 10,
          title: 'Pulp Fiction',
          poster_url: 'https://example.test/p.jpg',
          available: true,
          detail_path: '/movie/pulp-fiction',
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
    });

    render(
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('watchlist-grid')).toBeInTheDocument();
    });
    expect(screen.getByText('Pulp Fiction')).toBeInTheDocument();
    expect(screen.queryByTestId('watchlist-deferred-page')).not.toBeInTheDocument();
  });

  it('shows empty state when no items', async () => {
    listWatchlist.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    render(
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId('watchlist-empty')).toBeInTheDocument();
    });
  });
});
