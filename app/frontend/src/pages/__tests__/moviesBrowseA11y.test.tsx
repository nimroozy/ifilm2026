import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MoviesPage } from '@/pages/Browse';
import { LangProvider } from '@/components/CustomerLayout';

const fetchMovies = vi.fn();
const fetchGenres = vi.fn();

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
  isApiMode: () => true,
}));

vi.mock('@/lib/catalogData', () => ({
  fetchMovies: (...args: unknown[]) => fetchMovies(...args),
  fetchGenres: (...args: unknown[]) => fetchGenres(...args),
}));

vi.mock('@/components/CustomerLayout', async () => {
  const actual = await vi.importActual<typeof import('@/components/CustomerLayout')>(
    '@/components/CustomerLayout'
  );
  return {
    ...actual,
    useAuth: () => ({ isLoggedIn: false }),
  };
});

function renderMovies(initial = '/movies') {
  return render(
    <LangProvider>
      <MemoryRouter initialEntries={[initial]}>
        <MoviesPage />
      </MemoryRouter>
    </LangProvider>
  );
}

describe('Movies browse a11y and empty state', () => {
  beforeEach(() => {
    fetchMovies.mockReset();
    fetchGenres.mockReset();
    fetchGenres.mockResolvedValue([{ name: 'Action' }, { name: 'Drama' }]);
    fetchMovies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    window.localStorage.setItem('ifilm.locale', 'fa');
  });

  it('names genre/sort comboboxes and view toggles', async () => {
    renderMovies();
    await waitFor(() => {
      expect(screen.getByTestId('movies-no-results')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('فیلتر بر اساس ژانر')).toBeInTheDocument();
    expect(screen.getByLabelText('مرتب‌سازی کاتالوگ')).toBeInTheDocument();
    expect(screen.getByLabelText('نمای شبکه‌ای')).toBeInTheDocument();
    expect(screen.getByLabelText('نمای فهرستی')).toBeInTheDocument();
    expect(screen.getByText('جدیدترین')).toBeInTheDocument();
  });

  it('offers clear filters when no results and filters are active', async () => {
    renderMovies('/movies?genre=Action');
    await waitFor(() => {
      expect(screen.getByTestId('movies-clear-filters')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('movies-clear-filters'));
    await waitFor(() => {
      expect(screen.queryByTestId('movies-clear-filters')).not.toBeInTheDocument();
    });
  });
});
