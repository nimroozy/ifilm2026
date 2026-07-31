import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { api, ApiError, tokenStore, type WatchProgressUpdate } from '@/lib/api';
import { getConfig } from '@/lib/config';
import type { LivePlaybackSession, PlayerTarget } from './types';

const EVENT_THROTTLE_MS = 2_000;

function positiveNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback;
}

function watchProgressConfig() {
  const config = getConfig();
  return {
    enabled: config.ENABLE_WATCH_HISTORY !== false,
    minSeconds: positiveNumber(config.WATCH_PROGRESS_MIN_SECONDS, 30),
    saveIntervalSeconds: positiveNumber(config.WATCH_PROGRESS_SAVE_INTERVAL_SECONDS, 20),
    resumeMarginSeconds: positiveNumber(config.WATCH_PROGRESS_RESUME_MARGIN_SECONDS, 10),
  };
}

function reportFailure(action: string, error: unknown) {
  if (error instanceof ApiError && error.status === 404) return;
  // Progress is best-effort and must never interrupt playback.
  console.warn(`Watch progress ${action} failed`);
}

export interface UseWatchProgressOptions {
  target: PlayerTarget;
  session: LivePlaybackSession | null;
  videoRef: RefObject<HTMLVideoElement>;
}

export function useWatchProgress({ target, session, videoRef }: UseWatchProgressOptions) {
  const [resumePosition, setResumePosition] = useState<number | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const loadedAssetRef = useRef<string | null>(null);
  const lastSavedAtRef = useRef(0);
  const settings = watchProgressConfig();
  const mediaAssetId = session?.mediaAssetId ?? null;
  const eligible =
    settings.enabled &&
    (target.kind === 'movie' || target.kind === 'episode') &&
    Boolean(tokenStore.get());

  const applyPendingSeek = useCallback(() => {
    const video = videoRef.current;
    const requested = pendingSeekRef.current;
    if (!video || requested == null || video.readyState < 1) return;

    const duration =
      Number.isFinite(video.duration) && video.duration > 0 ? video.duration : Number.POSITIVE_INFINITY;
    const maxPosition = Number.isFinite(duration)
      ? Math.max(0, duration - settings.resumeMarginSeconds)
      : requested;
    video.currentTime = Math.max(0, Math.min(requested, maxPosition));
    pendingSeekRef.current = null;
  }, [settings.resumeMarginSeconds, videoRef]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.addEventListener('loadedmetadata', applyPendingSeek);
    applyPendingSeek();
    return () => video.removeEventListener('loadedmetadata', applyPendingSeek);
  }, [applyPendingSeek, session]);

  useEffect(() => {
    if (!eligible || !mediaAssetId || loadedAssetRef.current === mediaAssetId) return;
    loadedAssetRef.current = mediaAssetId;
    let cancelled = false;

    void api
      .getWatchProgress(mediaAssetId)
      .then((progress) => {
        if (
          !cancelled &&
          !progress.completed &&
          Number.isFinite(progress.position_seconds) &&
          progress.position_seconds >= settings.minSeconds
        ) {
          setResumePosition(progress.position_seconds);
        }
      })
      .catch((error) => reportFailure('load', error));

    return () => {
      cancelled = true;
    };
  }, [eligible, mediaAssetId, settings.minSeconds]);

  const makePayload = useCallback(
    (positionOverride?: number, startOver = false): WatchProgressUpdate | null => {
      if (!eligible || !session) return null;
      const video = videoRef.current;
      if (!video) return null;
      const position =
        positionOverride ??
        (Number.isFinite(video.currentTime) && video.currentTime >= 0 ? video.currentTime : 0);
      const duration =
        Number.isFinite(video.duration) && video.duration > 0 ? video.duration : undefined;

      return {
        position_seconds: Math.max(0, position),
        ...(duration ? { duration_seconds: duration } : {}),
        playback_session_id: session.id,
        event_at: new Date().toISOString(),
        ...(startOver ? { start_over: true } : {}),
      };
    },
    [eligible, session, videoRef]
  );

  const save = useCallback(
    (options?: { complete?: boolean; force?: boolean }) => {
      if (!eligible || !session) return;
      const now = Date.now();
      if (!options?.force && now - lastSavedAtRef.current < EVENT_THROTTLE_MS) return;
      const payload = makePayload();
      if (!payload) return;
      lastSavedAtRef.current = now;
      if (options?.complete) {
        void api.completeWatchProgress(session.mediaAssetId, payload).catch((error) => {
          if (error instanceof ApiError && error.status === 404) {
            void api
              .putWatchProgress(session.mediaAssetId, payload)
              .catch((fallbackError) => reportFailure('completion', fallbackError));
            return;
          }
          reportFailure('completion', error);
        });
        return;
      }
      void api
        .putWatchProgress(session.mediaAssetId, payload)
        .catch((error) => reportFailure('save', error));
    },
    [eligible, makePayload, session]
  );

  useEffect(() => {
    const video = videoRef.current;
    if (!eligible || !session || !video) return;

    const saveEvent = () => save();
    const saveCompletion = () => save({ complete: true, force: true });
    const saveWhenHidden = () => {
      if (document.visibilityState === 'hidden') save({ force: true });
    };
    const saveOnPageHide = () => save({ force: true });
    const saveWhilePlaying = () => {
      if (!video.paused && !video.ended) save();
    };
    const intervalId = window.setInterval(
      saveWhilePlaying,
      settings.saveIntervalSeconds * 1_000
    );

    video.addEventListener('pause', saveEvent);
    video.addEventListener('seeked', saveEvent);
    video.addEventListener('ended', saveCompletion);
    document.addEventListener('visibilitychange', saveWhenHidden);
    window.addEventListener('pagehide', saveOnPageHide);

    return () => {
      window.clearInterval(intervalId);
      video.removeEventListener('pause', saveEvent);
      video.removeEventListener('seeked', saveEvent);
      video.removeEventListener('ended', saveCompletion);
      document.removeEventListener('visibilitychange', saveWhenHidden);
      window.removeEventListener('pagehide', saveOnPageHide);
    };
  }, [eligible, save, session, settings.saveIntervalSeconds, videoRef]);

  const resume = useCallback(() => {
    if (resumePosition == null) return;
    pendingSeekRef.current = resumePosition;
    setResumePosition(null);
    applyPendingSeek();
  }, [applyPendingSeek, resumePosition]);

  const startOver = useCallback(() => {
    if (!eligible || !session) {
      setResumePosition(null);
      return;
    }
    pendingSeekRef.current = 0;
    setResumePosition(null);
    applyPendingSeek();
    const payload = makePayload(0, true);
    if (!payload) return;
    lastSavedAtRef.current = Date.now();
    void api
      .putWatchProgress(session.mediaAssetId, payload)
      .catch((error) => reportFailure('start over', error));
  }, [applyPendingSeek, eligible, makePayload, session]);

  return {
    resumePosition,
    resume,
    startOver,
    dismissResume: () => setResumePosition(null),
  };
}
