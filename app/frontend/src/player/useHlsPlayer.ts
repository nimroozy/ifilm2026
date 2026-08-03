import { useCallback, useEffect, useRef, useState } from 'react';
import Hls, { type ErrorData, type ManifestParsedData } from 'hls.js';
import type {
  AudioTrackInfo,
  PlaybackEngine,
  PlayerStatsSnapshot,
  QualityLevel,
  SafePlayerError,
  SubtitleTrackInfo,
} from './types';
import { safePlayerError, supportsNativeHls, classifySessionGone } from './safeErrors';
import {
  readAudioPreference,
  readQualityPreference,
  readSubtitlePreference,
  resolveQualityIndex,
  writeAudioPreference,
  writeQualityPreference,
  writeSubtitlePreference,
} from './preferences';

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

function bufferedAhead(video: HTMLVideoElement | null): number | null {
  if (!video || !video.buffered.length) return null;
  try {
    const end = video.buffered.end(video.buffered.length - 1);
    return Math.max(0, end - video.currentTime);
  } catch {
    return null;
  }
}

export function useHlsPlayer({ masterUrl, onGone, onFatal }: UseHlsPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const nativeErrorHandlerRef = useRef<((ev: Event) => void) | null>(null);
  const [engine, setEngine] = useState<PlaybackEngine>('unsupported');
  const [ready, setReady] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [levels, setLevels] = useState<QualityLevel[]>([]);
  const [currentLevel, setCurrentLevel] = useState<number>(-1); // -1 = auto
  const [audioTracks, setAudioTracks] = useState<AudioTrackInfo[]>([]);
  const [subtitleTracks, setSubtitleTracks] = useState<SubtitleTrackInfo[]>([]);
  const [audioTrackId, setAudioTrackId] = useState(0);
  const [subtitleTrackId, setSubtitleTrackId] = useState(-1);
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
    setBuffering(false);
    setLevels([]);
    setAudioTracks([]);
    setSubtitleTracks([]);
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
        setSubtitleTracks([]);

        const onLoaded = () => {
          setReady(true);
          restorePlaybackTime(video, restoreTimeRef);
          // Native textTracks when present
          const tracks: SubtitleTrackInfo[] = [];
          for (let i = 0; i < video.textTracks.length; i += 1) {
            const track = video.textTracks[i];
            if (!track) continue;
            tracks.push({
              id: i,
              name: track.label || track.language || `Captions ${i + 1}`,
              lang: track.language || undefined,
            });
          }
          setSubtitleTracks(tracks);
          const pref = readSubtitlePreference();
          if (pref !== 'off') {
            const match = tracks.find((t) => t.lang === pref || t.name === pref);
            if (match) {
              for (let i = 0; i < video.textTracks.length; i += 1) {
                const track = video.textTracks[i];
                if (track) track.mode = i === match.id ? 'showing' : 'disabled';
              }
              setSubtitleTrackId(match.id);
            }
          }
        };

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
          const preferred = resolveQualityIndex(readQualityPreference(), nextLevels);
          hls.currentLevel = preferred;
          setCurrentLevel(preferred);
          setReady(true);
          restorePlaybackTime(video, restoreTimeRef);
        });

        hls.on(Hls.Events.LEVEL_SWITCHED, (_e, data) => {
          // Reflect active ABR level when in Auto mode
          if (hls.autoLevelEnabled) {
            setCurrentLevel(-1);
          } else {
            setCurrentLevel(data.level);
          }
        });

        hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, () => {
          const tracks = (hls.audioTracks || []).map((t, id) => ({
            id,
            name: t.name || t.lang || `Audio ${id + 1}`,
            lang: t.lang,
          }));
          setAudioTracks(tracks);
          const pref = readAudioPreference();
          if (pref) {
            const match = tracks.find((t) => t.lang === pref || t.name === pref);
            if (match) {
              hls.audioTrack = match.id;
              setAudioTrackId(match.id);
              return;
            }
          }
          setAudioTrackId(hls.audioTrack >= 0 ? hls.audioTrack : 0);
        });

        hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, () => {
          const tracks = (hls.subtitleTracks || []).map((t, id) => ({
            id,
            name: t.name || t.lang || `Captions ${id + 1}`,
            lang: t.lang,
          }));
          setSubtitleTracks(tracks);
          const pref = readSubtitlePreference();
          if (pref === 'off' || !tracks.length) {
            hls.subtitleTrack = -1;
            setSubtitleTrackId(-1);
            return;
          }
          const match = tracks.find((t) => t.lang === pref || t.name === pref);
          if (match) {
            hls.subtitleTrack = match.id;
            setSubtitleTrackId(match.id);
          } else {
            hls.subtitleTrack = -1;
            setSubtitleTrackId(-1);
          }
        });

        hls.on(Hls.Events.ERROR, (_e, data: ErrorData) => {
          if (!data.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            const status = (data.response as { code?: number; url?: string } | undefined)?.code;
            const failedUrl =
              (data.response as { url?: string } | undefined)?.url ||
              (data as { url?: string }).url ||
              url;
            if (status === 410 && onGone && !refreshingRef.current) {
              refreshingRef.current = true;
              restoreTimeRef.current = video.currentTime || 0;
              void (async () => {
                try {
                  const kind = await classifySessionGone(failedUrl);
                  if (kind === 'revoked') {
                    refreshingRef.current = false;
                    destroyEngine();
                    onFatal?.(safePlayerError('session_revoked', { retryable: false }));
                    return;
                  }
                  const nextUrl = await onGone();
                  refreshingRef.current = false;
                  if (nextUrl) void attach(nextUrl);
                  else onFatal?.(safePlayerError('session_expired', { retryable: false }));
                } catch {
                  refreshingRef.current = false;
                  onFatal?.(safePlayerError('session_expired', { retryable: false }));
                }
              })();
              return;
            }
            networkRetryRef.current += 1;
            if (networkRetryRef.current <= 3) {
              setBuffering(true);
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
              setBuffering(true);
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

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onWaiting = () => setBuffering(true);
    const onPlaying = () => setBuffering(false);
    const onCanPlay = () => setBuffering(false);
    video.addEventListener('waiting', onWaiting);
    video.addEventListener('playing', onPlaying);
    video.addEventListener('canplay', onCanPlay);
    return () => {
      video.removeEventListener('waiting', onWaiting);
      video.removeEventListener('playing', onPlaying);
      video.removeEventListener('canplay', onCanPlay);
    };
  }, [ready, masterUrl]);

  const setQuality = useCallback((levelIndex: number) => {
    const hls = hlsRef.current;
    if (!hls) return;
    hls.currentLevel = levelIndex;
    setCurrentLevel(levelIndex);
    if (levelIndex === -1) {
      writeQualityPreference('auto');
      return;
    }
    const level = hls.levels?.[levelIndex];
    writeQualityPreference(heightLabel(level?.height || 0));
  }, []);

  const setAudioTrack = useCallback((id: number) => {
    const hls = hlsRef.current;
    const video = videoRef.current;
    if (hls) {
      hls.audioTrack = id;
      const track = hls.audioTracks[id];
      writeAudioPreference(track?.lang || track?.name || String(id));
    }
    setAudioTrackId(id);
    void video;
  }, []);

  const setSubtitleTrack = useCallback((id: number) => {
    const hls = hlsRef.current;
    const video = videoRef.current;
    if (hls) {
      hls.subtitleTrack = id;
      if (id < 0) writeSubtitlePreference('off');
      else {
        const track = hls.subtitleTracks[id];
        writeSubtitlePreference(track?.lang || track?.name || String(id));
      }
    } else if (video?.textTracks) {
      for (let i = 0; i < video.textTracks.length; i += 1) {
        const track = video.textTracks[i];
        if (track) track.mode = i === id ? 'showing' : 'disabled';
      }
      if (id < 0) writeSubtitlePreference('off');
      else {
        const track = video.textTracks[id];
        writeSubtitlePreference(track?.language || track?.label || String(id));
      }
    }
    setSubtitleTrackId(id);
  }, []);

  const getStats = useCallback((): PlayerStatsSnapshot | null => {
    const video = videoRef.current;
    if (!video) return null;
    const hls = hlsRef.current;
    let currentResolution = '—';
    let currentRendition = currentLevel === -1 ? 'Auto' : '—';
    let estimatedBandwidthMbps: number | null = null;
    let videoCodec: string | null = null;
    let audioCodec: string | null = null;

    if (hls && hls.levels.length) {
      const active =
        currentLevel >= 0 ? hls.levels[currentLevel] : hls.levels[hls.currentLevel] || hls.levels[0];
      if (active) {
        currentResolution =
          active.width && active.height ? `${active.width}×${active.height}` : heightLabel(active.height || 0);
        currentRendition =
          currentLevel === -1
            ? `Auto (${heightLabel(active.height || 0)})`
            : heightLabel(active.height || 0);
        videoCodec = (active as { videoCodec?: string }).videoCodec || null;
        audioCodec = (active as { audioCodec?: string }).audioCodec || null;
      }
      if (typeof hls.bandwidthEstimate === 'number' && hls.bandwidthEstimate > 0) {
        estimatedBandwidthMbps = hls.bandwidthEstimate / 1_000_000;
      }
    } else if (video.videoWidth && video.videoHeight) {
      currentResolution = `${video.videoWidth}×${video.videoHeight}`;
    }

    let droppedFrames: number | null = null;
    const quality = (
      video as HTMLVideoElement & {
        getVideoPlaybackQuality?: () => { droppedVideoFrames?: number };
      }
    ).getVideoPlaybackQuality?.();
    if (quality && typeof quality.droppedVideoFrames === 'number') {
      droppedFrames = quality.droppedVideoFrames;
    }

    return {
      currentResolution,
      currentRendition,
      estimatedBandwidthMbps,
      bufferedSeconds: bufferedAhead(video),
      droppedFrames,
      currentTime: video.currentTime || 0,
      duration: video.duration || 0,
      playbackRate: video.playbackRate || 1,
      videoCodec,
      audioCodec,
    };
  }, [currentLevel]);

  return {
    videoRef,
    engine,
    ready,
    buffering,
    levels,
    currentLevel,
    setQuality,
    audioTracks,
    audioTrackId,
    setAudioTrack,
    subtitleTracks,
    subtitleTrackId,
    setSubtitleTrack,
    manualQualitySupported,
    getStats,
    destroyEngine,
    _hlsRef: hlsRef,
  };
}
