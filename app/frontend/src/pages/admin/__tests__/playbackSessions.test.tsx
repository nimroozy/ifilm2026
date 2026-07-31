import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PlaybackSessionsPage from '../PlaybackSessionsPage';
import { tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const listPlaybackSessions = vi.fn();
const getStreamingStatus = vi.fn();
const revokePlaybackSession = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      listPlaybackSessions: (...args: unknown[]) => listPlaybackSessions(...args),
      getStreamingStatus: (...args: unknown[]) => getStreamingStatus(...args),
      revokePlaybackSession: (...args: unknown[]) => revokePlaybackSession(...args),
    },
  };
});

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('PlaybackSessionsPage', () => {
  beforeEach(() => {
    tokenStore.setAdmin('test-token');
    listPlaybackSessions.mockReset();
    getStreamingStatus.mockReset();
    revokePlaybackSession.mockReset();
  });

  it('lists sessions without showing tokens and can revoke', async () => {
    getStreamingStatus.mockResolvedValue({
      enabled: true,
      supported_principals: ['admin', 'subscriber'],
      subscriber_entitlement: 'deferred',
    });
    listPlaybackSessions.mockResolvedValue({
      items: [
        {
          id: 'sess-12345678-aaaa',
          media_asset_id: 'asset-12345678',
          media_package_id: 'pkg-12345678',
          principal_type: 'admin',
          principal_id: '1',
          status: 'active',
          expires_at: new Date().toISOString(),
          access_count: 0,
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    revokePlaybackSession.mockResolvedValue({
      id: 'sess-12345678-aaaa',
      status: 'revoked',
      media_asset_id: 'asset-12345678',
      media_package_id: 'pkg-12345678',
      principal_type: 'admin',
      principal_id: '1',
      expires_at: new Date().toISOString(),
      access_count: 0,
    });

    wrap(<PlaybackSessionsPage />);

    await waitFor(() => expect(screen.getByTestId('playback-sessions-page')).toBeInTheDocument());
    expect(screen.queryByText(/playback_token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/token_hash/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(revokePlaybackSession).toHaveBeenCalled());
  });

  it('shows disabled banner when streaming is off', async () => {
    getStreamingStatus.mockResolvedValue({
      enabled: false,
      supported_principals: ['admin'],
      subscriber_entitlement: 'deferred',
    });
    listPlaybackSessions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    wrap(<PlaybackSessionsPage />);
    await waitFor(() => expect(screen.getByTestId('streaming-disabled')).toBeInTheDocument());
  });
});
