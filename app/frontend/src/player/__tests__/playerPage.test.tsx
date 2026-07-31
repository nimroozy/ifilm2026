import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PlayerPage from '@/pages/PlayerPage';
import { tokenStore } from '@/lib/api';

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
    },
  };
});

describe('PlayerPage routing', () => {
  beforeEach(() => {
    tokenStore.clear();
    tokenStore.clearAdmin();
    tokenStore.set('user-token');
  });

  it('resolves movie route', async () => {
    render(
      <MemoryRouter initialEntries={['/player/movie/42']}>
        <Routes>
          <Route path="/player/movie/:id" element={<PlayerPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByTestId('mock-video-player')).toHaveTextContent('movie'));
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
