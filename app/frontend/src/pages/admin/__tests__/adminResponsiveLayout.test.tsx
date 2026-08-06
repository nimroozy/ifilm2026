import { describe, it, expect, vi, afterEach } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, cleanup, within, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DashboardPage from '../DashboardPage';
import MoviesListPage from '../MoviesListPage';
import { PageHeader, AdminTableCard } from '../adminShared';

const dashboardStats = vi.fn();
const listMovies = vi.fn();
const listGenres = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      dashboardStats: (...args: unknown[]) => dashboardStats(...args),
      listMovies: (...args: unknown[]) => listMovies(...args),
      listGenres: (...args: unknown[]) => listGenres(...args),
      deleteMovie: vi.fn(),
    },
  };
});

function wrap(ui: ReactNode, path = '/admin') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('admin responsive layout primitives', () => {
  afterEach(() => cleanup());

  it('PageHeader actions container wraps and stays within width', () => {
    wrap(
      <PageHeader
        title="Test"
        actions={
          <>
            <button type="button">New Movie</button>
            <button type="button">Import TMDB</button>
          </>
        }
      />
    );
    const actions = screen.getByTestId('admin-page-header-actions');
    expect(actions.className).toContain('flex-wrap');
    expect(actions.className).toContain('min-w-0');
    expect(screen.getByText('New Movie')).toBeTruthy();
    expect(screen.getByText('Import TMDB')).toBeTruthy();
  });

  it('AdminTableCard provides local horizontal scroll without page overflow wrappers', () => {
    wrap(
      <AdminTableCard>
        <table>
          <tbody>
            <tr>
              <td>cell</td>
            </tr>
          </tbody>
        </table>
      </AdminTableCard>
    );
    const scroll = screen.getByTestId('admin-table-scroll');
    expect(scroll.className).toContain('overflow-x-auto');
    expect(screen.getByTestId('admin-table-card').className).toContain('min-w-0');
  });
});

describe('dashboard header actions', () => {
  afterEach(() => {
    cleanup();
    dashboardStats.mockReset();
  });

  it('shows New Movie, New Series, and Import TMDB fully labeled', async () => {
    dashboardStats.mockResolvedValue({
      total_movies: 10,
      published_movies: 4,
      draft_movies: 6,
      total_series: 2,
      published_series: 1,
      total_seasons: 3,
      total_episodes: 8,
      total_genres: 5,
    });
    wrap(<DashboardPage />);
    expect(await screen.findByRole('link', { name: /New Movie/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /New Series/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /Import TMDB/i })).toBeTruthy();
    const actions = screen.getByTestId('admin-page-header-actions');
    expect(within(actions).getByText('New Movie')).toBeTruthy();
    expect(screen.getByTestId('dashboard-stats').className).toContain('min-w-0');
  });
});

describe('movies list responsive', () => {
  afterEach(() => {
    cleanup();
    listMovies.mockReset();
    listGenres.mockReset();
  });

  it('shows header actions and movie content in mobile and desktop layouts', async () => {
    listMovies.mockResolvedValue({
      items: [
        {
          id: 1,
          title: 'Sample Film',
          slug: 'sample-film',
          status: 'published',
          playable: true,
          has_playable_package: true,
          release_year: 2024,
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    listGenres.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });

    wrap(<MoviesListPage />, '/admin/movies');
    expect(await screen.findByRole('link', { name: /New Movie/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /Import TMDB/i })).toBeTruthy();

    await waitFor(() => {
      expect(screen.getAllByText('Sample Film').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByTestId('movies-mobile-list')).toBeTruthy();
    expect(screen.getByTestId('movies-table-desktop')).toBeTruthy();
    expect(screen.getByTestId('admin-table-scroll').className).toContain('overflow-x-auto');
  });
});
