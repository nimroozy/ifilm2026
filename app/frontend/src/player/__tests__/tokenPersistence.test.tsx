import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { usePlaybackSession } from '../usePlaybackSession';
import { tokenStore } from '@/lib/api';

const createPlaybackSession = vi.fn();
const revokePlaybackSession = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      createPlaybackSession: (...args: unknown[]) => createPlaybackSession(...args),
      revokePlaybackSession: (...args: unknown[]) => revokePlaybackSession(...args),
    },
  };
});

describe('playback token persistence', () => {
  beforeEach(() => {
    tokenStore.clear();
    tokenStore.clearAdmin();
    tokenStore.set('user-token');
    createPlaybackSession.mockReset();
    revokePlaybackSession.mockResolvedValue({});
    createPlaybackSession.mockResolvedValue({
      id: 'sess-persist',
      media_asset_id: 'asset-1',
      media_package_id: 'pkg-1',
      expires_at: new Date().toISOString(),
      playback_token: 'persisttokensecretvalue012345678901234',
      master_playlist_url: '/api/stream/persisttokensecretvalue012345678901234/master.m3u8',
    });
    localStorage.clear();
    sessionStorage.clear();
    tokenStore.set('user-token');
  });

  it('does not write playback tokens to localStorage or sessionStorage', async () => {
    const { result } = renderHook(() => usePlaybackSession({ kind: 'movie', contentId: 9 }));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    const local = JSON.stringify({ ...localStorage });
    const session = JSON.stringify({ ...sessionStorage });
    expect(local).not.toContain('persisttokensecretvalue012345678901234');
    expect(session).not.toContain('persisttokensecretvalue012345678901234');
    expect(local).not.toMatch(/\/api\/stream\/[A-Za-z0-9_-]{16,}/);
    expect(session).not.toMatch(/\/api\/stream\/[A-Za-z0-9_-]{16,}/);
  });
});
