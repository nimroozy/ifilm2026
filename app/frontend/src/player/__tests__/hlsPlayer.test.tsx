import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { render, screen, fireEvent } from '@testing-library/react';
import { useHlsPlayer } from '../useHlsPlayer';
import { QualitySelector } from '../QualitySelector';
import { PlayerControls } from '../PlayerControls';
import { PlaybackError } from '../PlaybackError';
import { useKeyboardController } from '../KeyboardController';
import { supportsNativeHls, sanitizeErrorText } from '../safeErrors';
import { isFullscreen, canPictureInPicture } from '../FullscreenController';

type HlsInstance = {
  destroy: ReturnType<typeof vi.fn>;
  loadSource: ReturnType<typeof vi.fn>;
  attachMedia: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  startLoad: ReturnType<typeof vi.fn>;
  recoverMediaError: ReturnType<typeof vi.fn>;
  currentLevel: number;
  audioTrack: number;
  audioTracks: unknown[];
  handlers: Record<string, Array<(...args: unknown[]) => void>>;
};

const hlsInstances: HlsInstance[] = [];

vi.mock('hls.js', () => {
  const HlsMock = vi.fn().mockImplementation(() => {
    const handlers: Record<string, Array<(...args: unknown[]) => void>> = {};
    const instance: HlsInstance = {
      destroy: vi.fn(),
      loadSource: vi.fn(),
      attachMedia: vi.fn(),
      startLoad: vi.fn(),
      recoverMediaError: vi.fn(),
      currentLevel: -1,
      audioTrack: 0,
      audioTracks: [],
      handlers,
      on: vi.fn((event: string, cb: (...args: unknown[]) => void) => {
        handlers[event] = handlers[event] || [];
        handlers[event].push(cb);
      }),
    };
    hlsInstances.push(instance);
    return instance;
  });
  (HlsMock as unknown as { isSupported: () => boolean }).isSupported = () => true;
  (HlsMock as unknown as { Events: Record<string, string> }).Events = {
    MANIFEST_PARSED: 'MANIFEST_PARSED',
    AUDIO_TRACKS_UPDATED: 'AUDIO_TRACKS_UPDATED',
    ERROR: 'ERROR',
  };
  (HlsMock as unknown as { ErrorTypes: Record<string, string> }).ErrorTypes = {
    NETWORK_ERROR: 'NETWORK_ERROR',
    MEDIA_ERROR: 'MEDIA_ERROR',
  };
  return { default: HlsMock };
});

function mockVideo(native = false): HTMLVideoElement {
  const listeners: Record<string, EventListener[]> = {};
  return {
    canPlayType: (t: string) => (native && t.includes('mpegurl') ? 'maybe' : ''),
    addEventListener: (type: string, cb: EventListener) => {
      listeners[type] = listeners[type] || [];
      listeners[type].push(cb);
    },
    removeEventListener: (type: string, cb: EventListener) => {
      listeners[type] = (listeners[type] || []).filter((x) => x !== cb);
    },
    removeAttribute: vi.fn(),
    load: vi.fn(),
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    buffered: { length: 0 },
    readyState: 1,
    duration: 100,
    currentTime: 12,
    paused: true,
    muted: false,
    volume: 1,
    playbackRate: 1,
    src: '',
  } as unknown as HTMLVideoElement;
}

function renderPlayer(url: string | null, opts?: { native?: boolean; onGone?: () => Promise<string | null> }) {
  const video = mockVideo(Boolean(opts?.native));
  let api: ReturnType<typeof useHlsPlayer> | null = null;
  const hook = renderHook(
    ({ masterUrl }: { masterUrl: string | null }) => {
      api = useHlsPlayer({ masterUrl, onGone: opts?.onGone });
      if (!api.videoRef.current) {
        (api.videoRef as { current: HTMLVideoElement | null }).current = video;
      }
      return api;
    },
    { initialProps: { masterUrl: null as string | null } }
  );
  hook.rerender({ masterUrl: url });
  return { ...hook, getApi: () => api!, video };
}

describe('useHlsPlayer', () => {
  beforeEach(() => {
    hlsInstances.length = 0;
  });

  it('uses native HLS when supported and does not create hls.js', async () => {
    const { getApi } = renderPlayer('/api/stream/tokensecretvalue012345678901234567890/master.m3u8', {
      native: true,
    });
    await waitFor(() => expect(getApi().engine).toBe('native'));
    expect(hlsInstances.length).toBe(0);
    expect(getApi().manualQualitySupported).toBe(false);
  });

  it('creates and destroys hls.js when native is unavailable', async () => {
    const { getApi, unmount } = renderPlayer(
      '/api/stream/tokensecretvalue012345678901234567890/master.m3u8'
    );
    await waitFor(() => expect(hlsInstances.length).toBeGreaterThan(0));
    expect(getApi().engine).toBe('hls.js');
    expect(getApi().manualQualitySupported).toBe(true);

    const parsed = hlsInstances[0].handlers.MANIFEST_PARSED?.[0];
    act(() => {
      parsed?.(null, {
        levels: [
          { height: 240, bitrate: 400000 },
          { height: 360, bitrate: 800000 },
        ],
      });
    });
    await waitFor(() => expect(getApi().levels.map((l) => l.label)).toEqual(['240p', '360p']));

    act(() => getApi().setQuality(0));
    expect(hlsInstances[0].currentLevel).toBe(0);
    act(() => getApi().setQuality(-1));
    expect(hlsInstances[0].currentLevel).toBe(-1);

    unmount();
    expect(hlsInstances[0].destroy).toHaveBeenCalled();
  });

  it('refreshes once on fatal 410 network error', async () => {
    const onGone = vi
      .fn()
      .mockResolvedValue('/api/stream/newtokenvalue0123456789012345678901/master.m3u8');
    renderPlayer('/api/stream/oldtokenvalue01234567890123456789012/master.m3u8', { onGone });
    await waitFor(() => expect(hlsInstances.length).toBe(1));
    const errHandler = hlsInstances[0].handlers.ERROR?.[0];
    await act(async () => {
      errHandler?.(null, {
        fatal: true,
        type: 'NETWORK_ERROR',
        response: { code: 410 },
      });
    });
    await waitFor(() => expect(onGone).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(hlsInstances.length).toBe(2));
  });

  it('recovers recoverable media errors then stops', async () => {
    const onFatal = vi.fn();
    let api: ReturnType<typeof useHlsPlayer> | null = null;
    const video = mockVideo(false);
    const { rerender } = renderHook(
      ({ masterUrl }: { masterUrl: string | null }) => {
        api = useHlsPlayer({ masterUrl, onFatal });
        if (!api.videoRef.current) {
          (api.videoRef as { current: HTMLVideoElement | null }).current = video;
        }
        return api;
      },
      { initialProps: { masterUrl: null as string | null } }
    );
    rerender({ masterUrl: '/api/stream/tokensecretvalue012345678901234567890/master.m3u8' });
    await waitFor(() => expect(hlsInstances.length).toBe(1));
    const errHandler = hlsInstances[0].handlers.ERROR?.[0];
    for (let i = 0; i < 3; i += 1) {
      act(() => {
        errHandler?.(null, { fatal: true, type: 'MEDIA_ERROR' });
      });
    }
    expect(hlsInstances[0].recoverMediaError).toHaveBeenCalledTimes(3);
    act(() => {
      errHandler?.(null, { fatal: true, type: 'MEDIA_ERROR' });
    });
    await waitFor(() => expect(onFatal).toHaveBeenCalled());
    expect(onFatal.mock.calls[0][0].code).toBe('media_error');
  });
});

describe('QualitySelector', () => {
  it('shows Auto and manifest levels only', () => {
    render(
      <QualitySelector
        levels={[
          { index: 0, height: 240, label: '240p', bitrate: 1 },
          { index: 1, height: 360, label: '360p', bitrate: 2 },
        ]}
        currentLevel={-1}
        onChange={() => undefined}
      />
    );
    expect(screen.getByTestId('quality-selector')).toBeTruthy();
  });

  it('hides selector with native reason', () => {
    render(
      <QualitySelector
        levels={[]}
        currentLevel={-1}
        onChange={() => undefined}
        unsupportedReason="Quality selection is managed by the browser on this device"
      />
    );
    expect(screen.getByTestId('quality-unavailable').textContent).toMatch(/browser/i);
  });
});

describe('PlayerControls accessibility', () => {
  it('exposes aria labels for primary controls', () => {
    render(
      <PlayerControls
        visible
        playing={false}
        muted={false}
        volume={1}
        currentTime={10}
        duration={100}
        buffered={40}
        levels={[{ index: 0, height: 240, label: '240p', bitrate: 1 }]}
        currentLevel={-1}
        manualQualitySupported
        audioTracks={[]}
        playbackRate={1}
        isFs={false}
        onTogglePlay={() => undefined}
        onSeek={() => undefined}
        onVolume={() => undefined}
        onToggleMute={() => undefined}
        onQuality={() => undefined}
        onAudio={() => undefined}
        onRate={() => undefined}
        onFullscreen={() => undefined}
        onPiP={() => undefined}
      />
    );
    expect(screen.getByLabelText('Play')).toBeTruthy();
    expect(screen.getByLabelText('Mute')).toBeTruthy();
    expect(screen.getByLabelText('Seek')).toBeTruthy();
    expect(screen.getByLabelText('Video quality')).toBeTruthy();
    expect(screen.getByLabelText('Enter fullscreen')).toBeTruthy();
    expect(screen.getByLabelText('Picture in picture')).toBeTruthy();
  });
});

describe('PlaybackError security', () => {
  it('redacts stream tokens in rendered error text', () => {
    render(
      <PlaybackError
        error={{
          code: 'fatal',
          message: 'Failed /api/stream/abcdefghijklmnopqrstuvwxyz012345/master.m3u8',
          retryable: false,
        }}
      />
    );
    expect(screen.getByTestId('player-error').textContent).not.toContain(
      'abcdefghijklmnopqrstuvwxyz012345'
    );
    expect(screen.getByTestId('player-error').textContent).toContain('[redacted]');
  });
});

describe('KeyboardController', () => {
  it('toggles play on Space and ignores when typing', () => {
    const handlers = {
      togglePlay: vi.fn(),
      seekBy: vi.fn(),
      volumeBy: vi.fn(),
      toggleMute: vi.fn(),
      toggleFullscreen: vi.fn(),
    };
    renderHook(() => useKeyboardController(true, handlers));
    fireEvent.keyDown(window, { key: ' ' });
    expect(handlers.togglePlay).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(handlers.seekBy).toHaveBeenCalledWith(10);
    fireEvent.keyDown(window, { key: 'm' });
    expect(handlers.toggleMute).toHaveBeenCalled();
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: ' ' });
    expect(handlers.togglePlay).toHaveBeenCalledTimes(1);
    document.body.removeChild(input);
  });
});

describe('Fullscreen helpers', () => {
  it('reports fullscreen and PiP capability safely', () => {
    expect(typeof isFullscreen()).toBe('boolean');
    expect(typeof canPictureInPicture()).toBe('boolean');
  });
});

describe('supportsNativeHls export', () => {
  it('detects capability from canPlayType', () => {
    expect(supportsNativeHls(mockVideo(true))).toBe(true);
    expect(supportsNativeHls(mockVideo(false))).toBe(false);
  });

  it('sanitize keeps messages free of raw tokens', () => {
    const out = sanitizeErrorText('/api/stream/tokensecretvalue012345678901234567890/x');
    expect(out).not.toContain('tokensecretvalue012345678901234567890');
  });
});
