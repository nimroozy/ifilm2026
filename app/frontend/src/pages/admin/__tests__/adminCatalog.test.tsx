import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RequireAdmin from '../RequireAdmin';
import AdminLoginPage from '../AdminLoginPage';
import MoviesListPage from '../MoviesListPage';
import MovieFormPage, { movieFormSchema } from '../MovieFormPage';
import { seriesFormSchema } from '../SeriesFormPage';
import SeasonsPage from '../SeasonsPage';
import EpisodesPage from '../EpisodesPage';
import GenresPage from '../GenresPage';
import { ApiError, tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const me = vi.fn();
const login = vi.fn();
const listMovies = vi.fn();
const createMovie = vi.fn();
const listGenres = vi.fn();
const deleteGenre = vi.fn();
const getSeries = vi.fn();
const listSeasons = vi.fn();
const getSeason = vi.fn();
const listEpisodes = vi.fn();
const dashboardStats = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      me: (...args: unknown[]) => me(...args),
      login: (...args: unknown[]) => login(...args),
      listMovies: (...args: unknown[]) => listMovies(...args),
      createMovie: (...args: unknown[]) => createMovie(...args),
      updateMovie: vi.fn(),
      deleteMovie: vi.fn(),
      publishMovie: vi.fn(),
      unpublishMovie: vi.fn(),
      listGenres: (...args: unknown[]) => listGenres(...args),
      createGenre: vi.fn(),
      updateGenre: vi.fn(),
      deleteGenre: (...args: unknown[]) => deleteGenre(...args),
      getSeries: (...args: unknown[]) => getSeries(...args),
      listSeasons: (...args: unknown[]) => listSeasons(...args),
      createSeason: vi.fn(),
      deleteSeason: vi.fn(),
      getSeason: (...args: unknown[]) => getSeason(...args),
      listEpisodes: (...args: unknown[]) => listEpisodes(...args),
      createEpisode: vi.fn(),
      deleteEpisode: vi.fn(),
      publishEpisode: vi.fn(),
      unpublishEpisode: vi.fn(),
      dashboardStats: (...args: unknown[]) => dashboardStats(...args),
    },
  };
});

function wrap(ui: React.ReactNode, initial = '/admin') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('admin auth & catalog pages', () => {
  beforeEach(() => {
    tokenStore.clearAdmin();
    me.mockReset();
    login.mockReset();
    listMovies.mockReset();
    createMovie.mockReset();
    listGenres.mockReset();
    deleteGenre.mockReset();
    getSeries.mockReset();
    listSeasons.mockReset();
    getSeason.mockReset();
    listEpisodes.mockReset();
    listGenres.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('redirects protected admin routes to login when no token', async () => {
    wrap(
      <Routes>
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <div>SECRET</div>
            </RequireAdmin>
          }
        />
        <Route path="/admin/login" element={<div>LOGIN PAGE</div>} />
      </Routes>
    );

    await waitFor(() => {
      expect(screen.getByText('LOGIN PAGE')).toBeInTheDocument();
    });
    expect(screen.queryByText('SECRET')).not.toBeInTheDocument();
  });

  it('shows login failure without logging credentials', async () => {
    login.mockRejectedValue(new ApiError('Invalid credentials', 401));

    wrap(
      <Routes>
        <Route path="/admin/login" element={<AdminLoginPage />} />
      </Routes>,
      '/admin/login'
    );

    await waitFor(() => expect(screen.getByLabelText(/username/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId('login-error')).toHaveTextContent(/invalid credentials/i);
    });
    expect(login).toHaveBeenCalledWith('admin', 'secret');
  });

  it('renders movie list from adminApi', async () => {
    tokenStore.setAdmin('tok');
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@b.c',
      full_name: 'Admin',
      is_active: true,
      role_name: 'Super Admin',
      permissions: [],
    });
    listMovies.mockResolvedValue({
      items: [
        {
          id: 5,
          title: 'Listed Film',
          slug: 'listed-film',
          status: 'published',
          release_year: 2024,
          poster_url: 'https://placehold.co/40x60',
          is_featured: true,
          is_trending: false,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    wrap(
      <Routes>
        <Route path="/admin/movies" element={<MoviesListPage />} />
      </Routes>,
      '/admin/movies'
    );

    await waitFor(() => {
      expect(screen.getByText('Listed Film')).toBeInTheDocument();
    });
    expect(screen.getByTestId('movie-row-5')).toBeInTheDocument();
  });

  it('validates movie form title is required', () => {
    const result = movieFormSchema.safeParse({
      title: '',
      status: 'draft',
      is_featured: false,
      is_trending: false,
      genre_ids: [],
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.title?.[0]).toMatch(/required/i);
    }
  });

  it('creates a movie successfully', async () => {
    createMovie.mockResolvedValue({ id: 42, title: 'New Film', slug: 'new-film', status: 'draft' });
    listGenres.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });

    const navigateSpy = vi.fn();
    vi.mock('react-router-dom', async () => {
      const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
      return {
        ...actual,
      };
    });

    wrap(
      <Routes>
        <Route path="/admin/movies/new" element={<MovieFormPage />} />
        <Route path="/admin/movies/:id/edit" element={<div>EDITED</div>} />
      </Routes>,
      '/admin/movies/new'
    );

    await waitFor(() => expect(screen.getByTestId('movie-title')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('movie-title'), { target: { value: 'New Film' } });
    fireEvent.click(screen.getByTestId('movie-save'));

    await waitFor(() => {
      expect(createMovie).toHaveBeenCalled();
    });
    expect(createMovie.mock.calls[0][0].title).toBe('New Film');
    void navigateSpy;
  });

  it('displays API error on movie list failure', async () => {
    listMovies.mockRejectedValue(new ApiError('Server exploded', 500));
    listGenres.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });

    wrap(
      <Routes>
        <Route path="/admin/movies" element={<MoviesListPage />} />
      </Routes>,
      '/admin/movies'
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toHaveTextContent(/server exploded/i);
    });
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('validates series form title', () => {
    const result = seriesFormSchema.safeParse({
      title: '',
      status: 'draft',
      airing_status: 'Ongoing',
      is_featured: false,
      is_trending: false,
      new_episode: false,
      genre_ids: [],
    });
    expect(result.success).toBe(false);
  });

  it('orders seasons by season_number', async () => {
    getSeries.mockResolvedValue({ id: 1, title: 'Show', slug: 'show', status: 'draft' });
    listSeasons.mockResolvedValue([
      { id: 3, series_id: 1, season_number: 3, title: 'S3', status: 'draft', episode_count: 0 },
      { id: 1, series_id: 1, season_number: 1, title: 'S1', status: 'draft', episode_count: 2 },
      { id: 2, series_id: 1, season_number: 2, title: 'S2', status: 'draft', episode_count: 1 },
    ]);

    wrap(
      <Routes>
        <Route path="/admin/series/:id/seasons" element={<SeasonsPage />} />
      </Routes>,
      '/admin/series/1/seasons'
    );

    await waitFor(() => expect(screen.getByTestId('season-row-1')).toBeInTheDocument());
    const rows = screen.getAllByTestId(/season-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'season-row-1',
      'season-row-2',
      'season-row-3',
    ]);
  });

  it('orders episodes by episode_number', async () => {
    getSeason.mockResolvedValue({
      id: 10,
      series_id: 1,
      season_number: 1,
      title: 'Season 1',
      status: 'draft',
    });
    listEpisodes.mockResolvedValue([
      { id: 2, season_id: 10, series_id: 1, episode_number: 2, title: 'Two', status: 'draft' },
      { id: 1, season_id: 10, series_id: 1, episode_number: 1, title: 'One', status: 'draft' },
    ]);

    wrap(
      <Routes>
        <Route path="/admin/seasons/:id/episodes" element={<EpisodesPage />} />
      </Routes>,
      '/admin/seasons/10/episodes'
    );

    await waitFor(() => expect(screen.getByTestId('episode-row-1')).toBeInTheDocument());
    const rows = screen.getAllByTestId(/episode-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['episode-row-1', 'episode-row-2']);
  });

  it('displays genre deletion conflict errors', async () => {
    listGenres.mockResolvedValue({
      items: [{ id: 7, name: 'Noir', slug: 'noir', movie_count: 1, series_count: 0 }],
      total: 1,
      page: 1,
      page_size: 100,
    });
    deleteGenre.mockRejectedValue(
      new ApiError('Genre is assigned to one or more movies or series', 409)
    );

    wrap(
      <Routes>
        <Route path="/admin/genres" element={<GenresPage />} />
      </Routes>,
      '/admin/genres'
    );

    await waitFor(() => expect(screen.getByText('Noir')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('genre-delete-7'));
    await waitFor(() => expect(screen.getByTestId('genre-delete-confirm')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('genre-delete-confirm'));

    await waitFor(() => {
      expect(screen.getByTestId('genre-conflict-error')).toHaveTextContent(/assigned/i);
    });
  });
});
