import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import { tokenStore } from '@/lib/api';
import { SeriesDetailsPage } from '@/pages/Browse';
import { GenresBrowsePage } from '@/pages/CatalogBrowsePages';
import { CollectionsIndexPage } from '@/pages/CollectionsPages';
import HomePage from '@/pages/Index';

const fetchGenres = vi.fn();
const fetchMovies = vi.fn();
const fetchSeries = vi.fn();
const fetchSeriesShell = vi.fn();
const fetchCollections = vi.fn();
const fetchHomeCatalog = vi.fn();

vi.mock('@/lib/catalogData', () => ({
  fetchGenres: (...args: unknown[]) => fetchGenres(...args),
  fetchMovies: (...args: unknown[]) => fetchMovies(...args),
  fetchSeries: (...args: unknown[]) => fetchSeries(...args),
  fetchSeriesShell: (...args: unknown[]) => fetchSeriesShell(...args),
  fetchSeasonEpisodes: vi.fn(),
  fetchSeriesRecommendations: vi.fn(async () => []),
  fetchMovie: vi.fn(),
  fetchSearch: vi.fn(),
  fetchSimilarMovies: vi.fn(),
  fetchCollections: (...args: unknown[]) => fetchCollections(...args),
  fetchCollection: vi.fn(),
  fetchHomeCatalog: (...args: unknown[]) => fetchHomeCatalog(...args),
  fetchMeHomeCatalog: vi.fn(),
  mapCollectionItems: () => [],
}));

function renderWithLang(ui: ReactNode) {
  return render(<LangProvider>{ui}</LangProvider>);
}

describe('catalog loading and error accessibility', () => {
  beforeEach(() => {
    window.localStorage.setItem('ifilm.locale', 'en');
    tokenStore.clear();
    tokenStore.clearAdmin();
    fetchGenres.mockReset();
    fetchMovies.mockReset();
    fetchSeries.mockReset();
    fetchSeriesShell.mockReset();
    fetchCollections.mockReset();
    fetchHomeCatalog.mockReset();
    const pending = () => new Promise(() => {});
    fetchGenres.mockImplementation(pending);
    fetchMovies.mockImplementation(pending);
    fetchSeries.mockImplementation(pending);
    fetchSeriesShell.mockImplementation(pending);
    fetchCollections.mockImplementation(pending);
    fetchHomeCatalog.mockImplementation(pending);
  });

  it('names the home loading region', () => {
    renderWithLang(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAccessibleName(/loading ifilm/i);
  });

  it('exposes a home catalog failure as an alert', async () => {
    fetchHomeCatalog.mockRejectedValue(new Error('catalog down'));
    renderWithLang(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('catalog down');
  });

  it('names genre browse loading', () => {
    renderWithLang(
      <MemoryRouter>
        <GenresBrowsePage />
      </MemoryRouter>
    );
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAccessibleName(/loading/i);
  });

  it('alerts when genre browse fails', async () => {
    fetchGenres.mockRejectedValue(new Error('genres unavailable'));
    fetchMovies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    fetchSeries.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    renderWithLang(
      <MemoryRouter>
        <GenresBrowsePage />
      </MemoryRouter>
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('genres unavailable');
  });

  it('names series detail loading instead of leaving a silent skeleton', () => {
    renderWithLang(
      <MemoryRouter initialEntries={['/series/4']}>
        <Routes>
          <Route path="/series/:id" element={<SeriesDetailsPage />} />
        </Routes>
      </MemoryRouter>
    );
    const status = screen.getByTestId('series-detail-loading');
    expect(status).toHaveAttribute('role', 'status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAccessibleName(/loading series/i);
  });

  it('names collections loading', () => {
    renderWithLang(
      <MemoryRouter>
        <CollectionsIndexPage />
      </MemoryRouter>
    );
    expect(screen.getByRole('status')).toHaveAccessibleName(/loading collections/i);
  });

  it('alerts when collections fail to load', async () => {
    fetchCollections.mockRejectedValue(new Error('collections unavailable'));
    renderWithLang(
      <MemoryRouter>
        <CollectionsIndexPage />
      </MemoryRouter>
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('collections unavailable');
  });
});
