import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TmdbToolsPage from '../TmdbToolsPage';

const searchTmdb = vi.fn();
const previewTmdb = vi.fn();
const importTmdbDraft = vi.fn();
const refreshTmdbDemo = vi.fn();
const replaceTmdbArtwork = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      searchTmdb: (...args: unknown[]) => searchTmdb(...args),
      previewTmdb: (...args: unknown[]) => previewTmdb(...args),
      importTmdbDraft: (...args: unknown[]) => importTmdbDraft(...args),
      refreshTmdbDemo: (...args: unknown[]) => refreshTmdbDemo(...args),
      replaceTmdbArtwork: (...args: unknown[]) => replaceTmdbArtwork(...args),
    },
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <TmdbToolsPage />
    </MemoryRouter>
  );
}

describe('TmdbToolsPage', () => {
  beforeEach(() => {
    searchTmdb.mockReset();
    previewTmdb.mockReset();
    importTmdbDraft.mockReset();
    refreshTmdbDemo.mockReset();
    replaceTmdbArtwork.mockReset();
  });

  it('searches TMDB and previews metadata with trailer URL', async () => {
    searchTmdb.mockResolvedValue({
      page: 1,
      results: [
        {
          id: 123,
          title: 'Demo Movie',
          release_date: '2024-01-01',
          overview: 'Search overview',
          poster_path: '/poster.jpg',
        },
      ],
    });
    previewTmdb.mockResolvedValue({
      id: 123,
      title: 'Demo Movie',
      overview: 'Preview overview',
      runtime: 95,
      poster_path: '/poster.jpg',
      backdrop_path: '/backdrop.jpg',
      translations: {
        translations: [
          {
            iso_639_1: 'fa',
            iso_3166_1: 'AF',
            english_name: 'Persian',
            data: { title: 'فیلم آزمایشی', overview: 'Persian overview' },
          },
        ],
      },
      selected_trailer: {
        provider: 'YouTube',
        key: 'abc123XYZ',
        title: 'Official Trailer',
        official: true,
        language: 'en',
        embed_url: 'https://www.youtube-nocookie.com/embed/abc123XYZ',
      },
    });

    renderPage();
    fireEvent.change(screen.getByLabelText(/Search TMDB/i), { target: { value: 'Demo Movie' } });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    expect(await screen.findByText('Demo Movie')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Preview/i }));

    expect(await screen.findByText('Preview overview')).toBeInTheDocument();
    expect(screen.getByText('https://www.youtube-nocookie.com/embed/abc123XYZ')).toBeInTheDocument();
    expect(previewTmdb).toHaveBeenCalledWith({ tmdb_id: 123, media_type: 'movie' });
  });

  it('imports the selected preview as a draft', async () => {
    previewTmdb.mockResolvedValue({
      id: 123,
      title: 'Demo Movie',
      overview: 'Preview overview',
      translations: { translations: [] },
      selected_trailer: null,
    });
    importTmdbDraft.mockResolvedValue({
      result: { media_type: 'movie', entity_id: 77, tmdb_id: 123, created: true, artwork_files: [] },
      item: { id: 77, title: 'Demo Movie', slug: 'demo-movie', status: 'draft' },
    });

    renderPage();
    // Seed page state through preview button flow.
    searchTmdb.mockResolvedValue({ page: 1, results: [{ id: 123, title: 'Demo Movie' }] });
    fireEvent.change(screen.getByLabelText(/Search TMDB/i), { target: { value: 'Demo Movie' } });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Preview/i }));
    await screen.findByText('Preview overview');

    fireEvent.click(screen.getByRole('button', { name: /Import as draft/i }));

    await waitFor(() =>
      expect(importTmdbDraft).toHaveBeenCalledWith({ tmdb_id: 123, media_type: 'movie', force: false })
    );
    expect(await screen.findByTestId('tmdb-import-result')).toHaveTextContent('draft');
    expect(screen.getByText(/Imported Demo Movie as draft/i)).toBeInTheDocument();
  });
});
