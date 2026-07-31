import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { usePlaybackSession } from '../usePlaybackSession';
import { safePlayerError, sanitizeErrorText, supportsNativeHls, mapApiErrorToPlayerError } from '../safeErrors';
import { ApiError, tokenStore } from '@/lib/api';

const createPlaybackSession = vi.fn();
const revokePlaybackSession = vi.fn();
const adminCreate = vi.fn();
const adminRevoke = vi.fn();
const adminPlayerCreate = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      createPlaybackSession: (...args: unknown[]) => createPlaybackSession(...args),
      revokePlaybackSession: (...args: unknown[]) => revokePlaybackSession(...args),
    },
    adminApi: {
      ...actual.adminApi,
      createPlaybackSession: (...args: unknown[]) => adminCreate(...args),
      createPlayerPlaybackSession: (...args: unknown[]) => adminPlayerCreate(...args),
      revokePlaybackSession: (...args: unknown[]) => adminRevoke(...args),
    },
  };
});

describe('safeErrors', () => {
  it('sanitizes stream tokens from text', () => {
    const raw = '/api/stream/abcdefghijklmnopqrstuvwxyz012345/master.m3u8 failed';
    expect(sanitizeErrorText(raw)).not.toContain('abcdefghijklmnopqrstuvwxyz012345');
    expect(sanitizeErrorText(raw)).toContain('[redacted]');
  });

  it('maps 409 to no_active_package', () => {
    const err = mapApiErrorToPlayerError(new ApiError('No active completed HLS package', 409));
    expect(err.code).toBe('no_active_package');
  });

  it('detects native HLS capability', () => {
    const video = {
      canPlayType: (t: string) => (t.includes('mpegurl') ? 'maybe' : ''),
    } as unknown as HTMLVideoElement;
    expect(supportsNativeHls(video)).toBe(true);
    expect(supportsNativeHls(null)).toBe(false);
  });
});

describe('usePlaybackSession', () => {
  beforeEach(() => {
    createPlaybackSession.mockReset();
    revokePlaybackSession.mockReset();
    adminCreate.mockReset();
    tokenStore.clear();
    tokenStore.clearAdmin();
    tokenStore.set('user-token');
    createPlaybackSession.mockResolvedValue({
      id: 'sess-1',
      media_asset_id: 'asset-1',
      media_package_id: 'pkg-1',
      expires_at: new Date().toISOString(),
      playback_token: 'tokensecretvalue012345678901234567890',
      master_playlist_url: '/api/stream/tokensecretvalue012345678901234567890/master.m3u8',
    });
    revokePlaybackSession.mockResolvedValue({});
  });

  it('creates a session for a movie target', async () => {
    const { result } = renderHook(() => usePlaybackSession({ kind: 'movie', contentId: 12 }));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    expect(createPlaybackSession).toHaveBeenCalledWith({
      content_type: 'movie',
      content_id: 12,
    });
    expect(result.current.session?.masterPlaylistUrl).toContain('/api/stream/');
  });

  it('bounds automatic refresh after gone', async () => {
    const { result } = renderHook(() => usePlaybackSession({ kind: 'movie', contentId: 1 }));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    createPlaybackSession.mockRejectedValueOnce(new ApiError('revoked', 410));
    await act(async () => {
      await result.current.refreshAfterGone();
    });
    // second failure hits bound
    createPlaybackSession.mockRejectedValueOnce(new ApiError('revoked', 410));
    await act(async () => {
      const next = await result.current.refreshAfterGone();
      expect(next).toBeNull();
    });
    expect(result.current.error?.code).toBe('session_revoked');
  });

  it('does not expose helper messages with raw tokens', () => {
    const err = safePlayerError('fatal');
    expect(err.message.toLowerCase()).not.toContain('token');
  });
});
