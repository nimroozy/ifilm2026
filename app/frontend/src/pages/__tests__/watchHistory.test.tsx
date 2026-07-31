import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoryPage } from '../Account';
import { tokenStore, type WatchProgressDto } from '@/lib/api';

const apiMocks = vi.hoisted(() => ({
  listWatchHistory: vi.fn(),
  deleteWatchHistoryItem: vi.fn(),
  clearWatchHistory: vi.fn(),
}));

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
}));

vi.mock('@/components/CustomerLayout', () => ({
  useAuth: () => ({ isLoggedIn: true }),
  useLang: () => ({
    t: {
      profile: { history: 'Watch History' },
      login: { signIn: 'Sign In' },
      common: { cancel: 'Cancel', delete: 'Delete' },
    },
  }),
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      listWatchHistory: (...args: unknown[]) => apiMocks.listWatchHistory(...args),
      deleteWatchHistoryItem: (...args: unknown[]) => apiMocks.deleteWatchHistoryItem(...args),
      clearWatchHistory: (...args: unknown[]) => apiMocks.clearWatchHistory(...args),
    },
  };
});

function item(overrides: Partial<WatchProgressDto> = {}): WatchProgressDto {
  return {
    id: 1,
    media_asset_id: 'asset-1',
    content_type: 'episode',
    movie_id: null,
    episode_id: 44,
    series_id: 5,
    season_number: 1,
    episode_number: 3,
    title: 'The Episode',
    subtitle: 'S1 E3',
    poster_url: '/episode.jpg',
    position_seconds: 600,
    duration_seconds: 1200,
    progress_percent: 50,
    completed: false,
    available: true,
    player_path: '/player/episode/44',
    last_watched_at: '2026-07-31T12:00:00Z',
    ...overrides,
  };
}

function renderHistory() {
  return render(
    <MemoryRouter>
      <HistoryPage />
    </MemoryRouter>
  );
}

describe('API watch history', () => {
  beforeEach(() => {
    tokenStore.clear();
    tokenStore.set('subscriber-token');
    apiMocks.listWatchHistory.mockReset();
    apiMocks.deleteWatchHistoryItem.mockReset().mockResolvedValue({ detail: 'ok', deleted: 1 });
    apiMocks.clearWatchHistory.mockReset().mockResolvedValue({ detail: 'ok', deleted: 2 });
  });

  it('lists history and removes one item', async () => {
    apiMocks.listWatchHistory.mockResolvedValue({
      items: [item()],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderHistory();

    expect(await screen.findByText('The Episode')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Remove The Episode/i }));

    await waitFor(() =>
      expect(apiMocks.deleteWatchHistoryItem).toHaveBeenCalledWith('asset-1')
    );
    await waitFor(() => expect(screen.queryByText('The Episode')).not.toBeInTheDocument());
  });

  it('clears all history after confirmation', async () => {
    apiMocks.listWatchHistory.mockResolvedValue({
      items: [item(), item({ id: 2, media_asset_id: 'asset-2', title: 'Second Movie' })],
      total: 2,
      page: 1,
      page_size: 100,
    });
    renderHistory();

    fireEvent.click(await screen.findByRole('button', { name: 'Clear All' }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('cannot be undone');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(apiMocks.clearWatchHistory).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('No watch history yet')).toBeInTheDocument();
  });

  it('renders unavailable items without a resume action', async () => {
    apiMocks.listWatchHistory.mockResolvedValue({
      items: [
        item({
          title: 'Unavailable',
          subtitle: '',
          poster_url: '',
          available: false,
          player_path: '',
        }),
      ],
      total: 1,
      page: 1,
      page_size: 100,
    });
    renderHistory();

    expect((await screen.findAllByText('Unavailable')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Unavailable unavailable' })
    ).toBeDisabled();
  });
});
