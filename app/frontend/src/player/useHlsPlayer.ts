import { useCallback, useEffect, useRef, useState } from 'react';
import Hls, { type ErrorData, type ManifestParsedData } from 'hls.js';
import type { AudioTrackInfo, PlaybackEngine, QualityLevel, SafePlayerError } from './types';
import { safePlayerError, supportsNativeHls } from './safeErrors';

export interface UseHlsPlayerOptions {
  masterUrl: string | null;
  onGone?: () => Promise<string | null>;
  onFatal?: (error: SafePlayerError) => void;
}

function heightLabel(height: number): string {
  if (height >= 1080) return '1080p';
  if (height >= 720) return '720p';
  if (height >= 480) return '480p';
  if (height >= 360) return '360p';
  if (height >= 240) return '240p';
  return `${height}p`;
}

function restorePlaybackTime(video: HTMLVideoElement, restoreTimeRef: { current: number | null }) {
  if (restoreTimeRef.current == null || !Number.isFinite(restoreTimeRef.current)) return;
  const t = Math.max(0, restoreTimeRef.current);
  const seek = () => {
    if (video.duration && Number.isFinite(video.duration)) {
      video.currentTime = Math.min(t, Math.max(0, video.duration - 0.25));
    } else {
      video.currentTime = t;
    }
    restoreTimeRef.current = null;
  };
  if (video.readyState >= 1) seek();
  else video.addEventListener('loadedmetadata', seek, { once: true });
}

export function useHlsPlayer({ masterUrl, onGone, onFatal }: UseHlsPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const nativeErrorHandlerRef = useRef<((ev: Event) => void) | null>(null);
  const [engine, setEngine] = useState<PlaybackEngine>('unsupported');
  const [ready, setReady] = useState(false);
  const [levels, setLevels] = useState<QualityLevel[]>([]);
  const [currentLevel, setCurrentLevel] = useState<number>(-1); // -1 = auto
  const [audioTracks, setAudioTracks] = useState<AudioTrackInfo[]>([]);
  const [manualQualitySupported, setManualQualitySupported] = useState(false);
  const refreshingRef = useRef(false);
  const restoreTimeRef = useRef<number | null>(null);
  const networkRetryRef = useRef(0);
  const mediaRetryRef = useRef(0);

  const destroyEngine = useCallback(() => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    const video = videoRef.current;
    if (video) {
      if (nativeErrorHandlerRef.current) {
        video.removeEventListener('error', nativeErrorHandlerRef.current);
        nativeErrorHandlerRef.current = null;
      }
      video.removeAttribute('src');
      video.load();
    }
    setReady(false);
    setLevels([]);
    setAudioTracks([]);
  }, []);

  const attach = useCallback(
    async (url: string) => {
      const video = videoRef.current;
      if (!video || !url) return;
      destroyEngine();
      networkRetryRef.current = 0;
      mediaRetryRef.current = 0;

      if (supportsNativeHls(video)) {
        setEngine('native');
        setManualQualitySupported(false);
        setLevels([]);
        setAudioTracks([]);

        const onLoaded = () => {
          setReady(true);
          restorePlaybackTime(video, restoreTimeRef);
        };

        // Native HLS does not expose HTTP status codes. On media error, attempt
        // at most one session refresh (bounded further by usePlaybackSession).
        const onError = () => {
          if (refreshingRef.current) {
            onFatal?.(safePlayerError('media_error', { retryable: false }));
            return;
          }
          if (!onGone) {
            onFatal?.(safePlayerError('media_error'));
            return;
          }
          refreshingRef.current = true;
          restoreTimeRef.current = video.currentTime || 0;
          void onGone()
            .then((nextUrl) => {
              refreshingRef.current = false;
              if (nextUrl) void attach(nextUrl);
              else onFatal?.(safePlayerError('session_revoked', { retryable: false }));
            })
            .catch(() => {
              refreshingRef.current = false;
              onFatal?.(safePlayerError('session_expired', { retryable: false }));
            });
        };

        nativeErrorHandlerRef.current = onError;
        video.addEventListener('loadedmetadata', onLoaded, { once: true });
        video.addEventListener('error', onError);
        video.src = url;
        return;
      }

      if (Hls.isSupported()) {
        setEngine('hls.js');
        setManualQualitySupported(true);
        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: false,
          backBufferLength: 30,
          maxBufferLength: 30,
          manifestLoadingMaxRetry: 2,
          levelLoadingMaxRetry: 2,
          fragLoadingMaxRetry: 3,
        });
        hlsRef.current = hls;
        hls.loadSource(url);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, (_e, data: ManifestParsedData) => {
          const nextLevels: QualityLevel[] = (data.levels || []).map((level, index) => ({
            index,
            height: level.height || 0,
            label: heightLabel(level.height || 0),
            bitrate: level.bitrate,
          }));
          setLevels(nextLevels);
          setCurrentLevel(-1);
          setReady(true);
          restorePlaybackTime(video, restoreTimeRef);
        });

        hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, () => {
          const tracks = (hls.audioTracks || []).map((t, id) => ({
            id,
            name: t.name || t.lang || `Audio ${id + 1}`,
            lang: t.lang,
          }));
          setAudioTracks(tracks);
        });

        hls.on(Hls.Events.ERROR, (_e, data: ErrorData) => {
          if (!data.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            const status = (data.response as { code?: number } | undefined)?.code;
            if (status === 410 && onGone && !refreshingRef.current) {
              refreshingRef.current = true;
              restoreTimeRef.current = video.currentTime || 0;
              void onGone()
                .then((nextUrl) => {
                  refreshingRef.current = false;
                  if (nextUrl) void attach(nextUrl);
                  else onFatal?.(safePlayerError('session_revoked', { retryable: false }));
                })
                .catch(() => {
                  refreshingRef.current = false;
                  onFatal?.(safePlayerError('session_expired', { retryable: false }));
                });
              return;
            }
            networkRetryRef.current += 1;
            if (networkRetryRef.current <= 3) {
              hls.startLoad();
              return;
            }
            destroyEngine();
            onFatal?.(safePlayerError('network_error', { retryable: true }));
            return;
          }
          if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            mediaRetryRef.current += 1;
            if (mediaRetryRef.current <= 3) {
              hls.recoverMediaError();
              return;
            }
            destroyEngine();
            onFatal?.(safePlayerError('media_error', { retryable: true }));
            return;
          }
          destroyEngine();
          onFatal?.(safePlayerError('fatal'));
        });
        return;
      }

      setEngine('unsupported');
      onFatal?.(safePlayerError('unsupported_browser', { retryable: false }));
    },
    [destroyEngine, onGone, onFatal]
  );

  useEffect(() => {
    if (!masterUrl) {
      destroyEngine();
      return;
    }
    void attach(masterUrl);
    return () => destroyEngine();
  }, [masterUrl, attach, destroyEngine]);

  const setQuality = useCallback((levelIndex: number) => {
    const hls = hlsRef.current;
    if (!hls) return;
    // -1 restores ABR
    hls.currentLevel = levelIndex;
    setCurrentLevel(levelIndex);
  }, []);

  const setAudioTrack = useCallback((id: number) => {
    const hls = hlsRef.current;
    if (!hls) return;
    hls.audioTrack = id;
  }, []);

  return {
    videoRef,
    engine,
    ready,
    levels,
    currentLevel,
    setQuality,
    audioTracks,
    setAudioTrack,
    manualQualitySupported,
    destroyEngine,
    _hlsRef: hlsRef,
  };
}
