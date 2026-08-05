import * as React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { VideoPlayer } from '../VideoPlayer';
import { ApiError, tokenStore } from '@/lib/api';

const apiMocks = vi.hoisted(() => ({
  getWatchProgress: vi.fn(),
  putWatchProgress: vi.fn(),
  completeWatchProgress: vi.fn(),
}));
const playbackSession = vi.hoisted(() => ({
  id: 'session-1',
  mediaAssetId: 'asset-1',
  mediaPackageId: 'package-1' as string | null,
  expiresAt: '2026-08-01T00:00:00Z',
  masterPlaylistUrl: '/api/stream/redacted/master.m3u8',
  sourceType: 'package',
  playbackUrl: '/api/stream/redacted/master.m3u8',
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      getWatchProgress: (...args: unknown[]) => apiMocks.getWatchProgress(...args),
      putWatchProgress: (...args: unknown[]) => apiMocks.putWatchProgress(...args),
      completeWatchProgress: (...args: unknown[]) => apiMocks.completeWatchProgress(...args),
    },
  };
});

vi.mock('../usePlaybackSession', () => ({
  usePlaybackSession: () => ({
    session: playbackSession,
    loading: false,
    error: null,
    setError: vi.fn(),
    refreshAfterGone: vi.fn(),
    retry: vi.fn(),
  }),
}));

vi.mock('../useHlsPlayer', () => ({
  useHlsPlayer: () => {
    const videoRef = React.useRef<HTMLVideoElement | null>(null);
    return {
      videoRef,
      ready: true,
      levels: [],
      currentLevel: -1,
      setQuality: vi.fn(),
      audioTracks: [],
      setAudioTrack: vi.fn(),
      manualQualitySupported: false,
    };
  },
}));

function progress(position = 70) {
  return {
    id: 1,
    media_asset_id: 'asset-1',
    content_type: 'movie' as const,
    title: 'Test Movie',
    position_seconds: position,
    duration_seconds: 120,
    progress_percent: (position / 120) * 100,
    completed: false,
    available: true,
    player_path: '/player/movie/1',
  };
}

function configureVideo(video: HTMLVideoElement, currentTime = 0) {
  Object.defineProperty(video, 'readyState', { configurable: true, value: 1 });
  Object.defineProperty(video, 'duration', { configurable: true, value: 120 });
  Object.defineProperty(video, 'currentTime', {
    configurable: true,
    writable: true,
    value: currentTime,
  });
}

describe('watch progress player integration', () => {
  beforeEach(() => {
    tokenStore.clear();
    tokenStore.clearAdmin();
    tokenStore.set('subscriber-token');
    apiMocks.getWatchProgress.mockReset();
    apiMocks.putWatchProgress.mockReset().mockResolvedValue(progress());
    apiMocks.completeWatchProgress.mockReset().mockResolvedValue({ ...progress(120), completed: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    tokenStore.clear();
  });

  it('shows the resume dialog and seeks to saved progress', async () => {
    apiMocks.getWatchProgress.mockResolvedValue(progress(70));
    render(<VideoPlayer target={{ kind: 'movie', contentId: 1 }} title="Test Movie" />);

    await waitFor(() => expect(apiMocks.getWatchProgress).toHaveBeenCalledWith('asset-1'));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Resume from 1:10');
    const video = screen.getByTestId('player-video') as HTMLVideoElement;
    configureVideo(video);
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));

    expect(video.currentTime).toBe(70);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('starts over and records an explicit start_over event', async () => {
    apiMocks.getWatchProgress.mockResolvedValue(progress(70));
    render(<VideoPlayer target={{ kind: 'episode', contentId: 10 }} title="Episode" />);

    await waitFor(() => expect(apiMocks.getWatchProgress).toHaveBeenCalledWith('asset-1'));
    await screen.findByRole('dialog');
    const video = screen.getByTestId('player-video') as HTMLVideoElement;
    configureVideo(video, 70);
    fireEvent.click(screen.getByRole('button', { name: 'Start Over' }));

    expect(video.currentTime).toBe(0);
    await waitFor(() =>
      expect(apiMocks.putWatchProgress).toHaveBeenCalledWith(
        'asset-1',
        expect.objectContaining({
          position_seconds: 0,
          playback_session_id: 'session-1',
          start_over: true,
        })
      )
    );
  });

  it('saves periodically while playback is active', async () => {
    vi.useFakeTimers();
    apiMocks.getWatchProgress.mockRejectedValue(new ApiError('not found', 404));
    render(<VideoPlayer target={{ kind: 'movie', contentId: 1 }} />);
    const video = screen.getByTestId('player-video') as HTMLVideoElement;
    configureVideo(video, 42);
    Object.defineProperty(video, 'paused', { configurable: true, value: false });
    Object.defineProperty(video, 'ended', { configurable: true, value: false });

    await act(async () => {
      vi.advanceTimersByTime(20_000);
      await Promise.resolve();
    });

    expect(apiMocks.putWatchProgress).toHaveBeenCalledWith(
      'asset-1',
      expect.objectContaining({
        position_seconds: 42,
        duration_seconds: 120,
        playback_session_id: 'session-1',
      })
    );
  });

  it('keeps playback rendered when progress requests fail', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    apiMocks.getWatchProgress.mockRejectedValue(new Error('offline'));
    apiMocks.putWatchProgress.mockRejectedValue(new Error('offline'));
    render(<VideoPlayer target={{ kind: 'movie', contentId: 1 }} />);
    const video = screen.getByTestId('player-video') as HTMLVideoElement;
    configureVideo(video, 45);

    await waitFor(() => expect(apiMocks.getWatchProgress).toHaveBeenCalled());
    fireEvent.pause(video);
    await waitFor(() => expect(apiMocks.putWatchProgress).toHaveBeenCalled());
    expect(screen.getByTestId('video-player')).toBeInTheDocument();
  });
});
