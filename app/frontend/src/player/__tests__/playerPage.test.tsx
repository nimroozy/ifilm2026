import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PlayerPage from '@/pages/PlayerPage';
import { LangProvider, useLang } from '@/components/CustomerLayout';
import CustomerDocumentTitle, {
  PlayerDocumentTitleProvider,
} from '@/components/customer/CustomerDocumentTitle';
import { api, tokenStore } from '@/lib/api';

vi.mock('@/player/VideoPlayer', () => ({
  VideoPlayer: ({ target, title }: { target: { kind: string }; title?: string }) => (
    <div data-testid="mock-video-player">
      {title}:{target.kind}
    </div>
  ),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      getMovie: vi.fn().mockResolvedValue({ title: 'Test Movie', id: 42 }),
      listEpisodes: vi.fn().mockResolvedValue([]),
    },
  };
});

function LocaleSwitch() {
  const { setLang } = useLang();
  return (
    <button type="button" onClick={() => setLang('fa')}>
      switch-fa
    </button>
  );
}

function renderPlayer(path: string, { withDocumentTitle = false } = {}) {
  return render(
    <LangProvider>
      <PlayerDocumentTitleProvider>
        <MemoryRouter initialEntries={[path]}>
          {withDocumentTitle ? <LocaleSwitch /> : null}
          {withDocumentTitle ? <CustomerDocumentTitle /> : null}
          <Routes>
            <Route path="/player/movie/:id" element={<PlayerPage />} />
            <Route path="/player/episode/:id" element={<PlayerPage />} />
            <Route path="/player/asset/:assetId" element={<PlayerPage />} />
          </Routes>
        </MemoryRouter>
      </PlayerDocumentTitleProvider>
    </LangProvider>
  );
}

describe('PlayerPage routing', () => {
  beforeEach(() => {
    document.title = '';
    window.localStorage.setItem('ifilm.locale', 'en');
    tokenStore.clear();
    tokenStore.clearAdmin();
    tokenStore.set('user-token');
    vi.mocked(api.getMovie).mockResolvedValue({ title: 'Test Movie', id: 42 } as Awaited<
      ReturnType<typeof api.getMovie>
    >);
    vi.mocked(api.listEpisodes).mockResolvedValue([]);
  });

  it('resolves movie route', async () => {
    renderPlayer('/player/movie/42');
    await waitFor(() => expect(screen.getByTestId('mock-video-player')).toHaveTextContent('movie'));
    await waitFor(() => expect(document.title).toBe('Test Movie · iFilm'));
  });

  it('titles an episode route from series metadata', async () => {
    vi.mocked(api.listEpisodes).mockResolvedValue([
      { id: 3, title: 'Night Market', episode_number: 1, season: 1 } as Awaited<
        ReturnType<typeof api.listEpisodes>
      >[number],
    ]);
    renderPlayer('/player/episode/3?series=9&season=1');
    await waitFor(() => expect(document.title).toBe('Night Market · iFilm'));
    expect(screen.getByTestId('mock-video-player')).toHaveTextContent('Night Market:episode');
    expect(document.title).not.toContain('Page not found');
  });

  it('does not call a valid episode route page-not-found while metadata is unavailable', async () => {
    renderPlayer('/player/episode/3');
    await waitFor(() => expect(document.title).toBe('Episode 3 · iFilm'));
    expect(document.title).not.toContain('Page not found');
  });

  it('keeps the movie title after the document-title effect runs again', async () => {
    renderPlayer('/player/movie/42', { withDocumentTitle: true });
    await waitFor(() => expect(document.title).toBe('Test Movie · iFilm'));
    fireEvent.click(screen.getByRole('button', { name: 'switch-fa' }));
    await waitFor(() => expect(document.title).toBe('Test Movie · iFilm'));
    expect(document.title).not.toContain('پیدا نشد');
  });

  it('requires auth', async () => {
    tokenStore.clear();
    render(
      <MemoryRouter initialEntries={['/player/movie/42']}>
        <Routes>
          <Route path="/player/movie/:id" element={<PlayerPage />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText(/Sign in to watch/i)).toBeInTheDocument();
  });

  it('does not render playback tokens', async () => {
    render(
      <MemoryRouter initialEntries={['/player/asset/abc']}>
        <Routes>
          <Route path="/player/asset/:assetId" element={<PlayerPage />} />
        </Routes>
      </MemoryRouter>
    );
    // unauthenticated for asset without admin token
    tokenStore.clear();
    expect(screen.queryByText(/playback_token/i)).not.toBeInTheDocument();
  });
});
