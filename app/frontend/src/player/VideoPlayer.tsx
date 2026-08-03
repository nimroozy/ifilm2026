import { useCallback, useEffect, useMemo, useState } from 'react';
import { Play, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { usePlaybackSession } from './usePlaybackSession';
import { useHlsPlayer } from './useHlsPlayer';
import { useWatchProgress } from './useWatchProgress';
import { PlayerControls } from './PlayerControls';
import { PlaybackError } from './PlaybackError';
import { PlayerLoadingState } from './PlaybackLoadingState';
import { useKeyboardController } from './KeyboardController';
import {
  exitFullscreen,
  isFullscreen,
  requestFullscreen,
  togglePictureInPicture,
} from './FullscreenController';
import { isAirPlaySupported, isPiPSupported, showAirPlayPicker } from './castAirPlay';
import { StatsOverlay } from './StatsOverlay';
import type { PlayerStatsSnapshot, PlayerTarget, SafePlayerError } from './types';

export function VideoPlayer({
  target,
  title,
  onBack,
  previousEpisodeId = null,
  nextEpisodeId = null,
  autoplayNext = true,
  onAutoplayNextChange,
  onPreviousEpisode,
  onNextEpisode,
}: {
  target: PlayerTarget;
  title?: string;
  onBack?: () => void;
  previousEpisodeId?: number | null;
  nextEpisodeId?: number | null;
  autoplayNext?: boolean;
  onAutoplayNextChange?: (value: boolean) => void;
  onPreviousEpisode?: () => void;
  onNextEpisode?: () => void;
}) {
  const { session, loading, error, setError, refreshAfterGone, retry } = usePlaybackSession(target);
  const [fatal, setFatal] = useState<SafePlayerError | null>(null);

  const onGone = useCallback(async () => {
    const next = await refreshAfterGone();
    return next?.masterPlaylistUrl ?? null;
  }, [refreshAfterGone]);

  const {
    videoRef,
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
  } = useHlsPlayer({
    masterUrl: session?.masterPlaylistUrl ?? null,
    onGone,
    onFatal: setFatal,
  });
  const { resumePosition, resume, startOver, dismissResume } = useWatchProgress({
    target,
    session,
    videoRef,
  });

  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [showControls, setShowControls] = useState(true);
  const [fs, setFs] = useState(false);
  const [rootEl, setRootEl] = useState<HTMLDivElement | null>(null);
  const [airPlaySupported, setAirPlaySupported] = useState(false);
  const [upNextSeconds, setUpNextSeconds] = useState<number | null>(null);
  const [statsOpen, setStatsOpen] = useState(false);
  const [stats, setStats] = useState<PlayerStatsSnapshot | null>(null);
  const pipSupported = isPiPSupported();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTime = () => {
      setCurrentTime(video.currentTime);
      if (video.buffered.length) {
        setBuffered(video.buffered.end(video.buffered.length - 1));
      }
    };
    const onMeta = () => setDuration(video.duration || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('loadedmetadata', onMeta);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    return () => {
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('loadedmetadata', onMeta);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
    };
  }, [videoRef, ready]);

  useEffect(() => {
    if (!showControls || !playing) return;
    const id = window.setTimeout(() => setShowControls(false), 3200);
    return () => window.clearTimeout(id);
  }, [showControls, playing, currentTime]);

  useEffect(() => {
    const onFs = () => setFs(isFullscreen());
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  useEffect(() => {
    setAirPlaySupported(isAirPlaySupported(videoRef.current));
  }, [videoRef, ready, session]);

  useEffect(() => {
    setUpNextSeconds(null);
  }, [target]);

  useEffect(() => {
    if (!autoplayNext || !onNextEpisode || !nextEpisodeId || !duration || duration < 15) {
      setUpNextSeconds(null);
      return;
    }
    const remaining = duration - currentTime;
    if (remaining <= 10 && remaining > 0.25 && playing) {
      setUpNextSeconds(Math.max(1, Math.ceil(remaining)));
    } else {
      setUpNextSeconds(null);
    }
  }, [autoplayNext, onNextEpisode, nextEpisodeId, duration, currentTime, playing]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !autoplayNext || !onNextEpisode || !nextEpisodeId) return;
    const onEnded = () => onNextEpisode();
    video.addEventListener('ended', onEnded);
    return () => video.removeEventListener('ended', onEnded);
  }, [videoRef, autoplayNext, onNextEpisode, nextEpisodeId, target]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play().catch(() => undefined);
    else video.pause();
  }, [videoRef]);

  const seekBy = useCallback(
    (delta: number) => {
      const video = videoRef.current;
      if (!video) return;
      const next = Math.min(Math.max(0, video.currentTime + delta), video.duration || 0);
      video.currentTime = next;
    },
    [videoRef]
  );

  const volumeBy = useCallback(
    (delta: number) => {
      const video = videoRef.current;
      if (!video) return;
      const next = Math.min(1, Math.max(0, (muted ? 0 : volume) + delta));
      video.volume = next;
      video.muted = next === 0;
      setVolume(next);
      setMuted(next === 0);
    },
    [videoRef, muted, volume]
  );

  const toggleMute = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  }, [videoRef]);

  const toggleFullscreen = useCallback(() => {
    if (!rootEl) return;
    if (isFullscreen()) void exitFullscreen();
    else void requestFullscreen(rootEl);
  }, [rootEl]);

  const togglePiP = useCallback(() => {
    const video = videoRef.current;
    if (video) void togglePictureInPicture(video);
  }, [videoRef]);

  const toggleCaptions = useCallback(() => {
    if (subtitleTrackId >= 0) setSubtitleTrack(-1);
    else if (subtitleTracks[0]) setSubtitleTrack(subtitleTracks[0].id);
  }, [subtitleTrackId, subtitleTracks, setSubtitleTrack]);

  const keyboardHandlers = useMemo(
    () => ({
      togglePlay,
      seekBy,
      volumeBy,
      toggleMute,
      toggleFullscreen,
      togglePiP,
      toggleCaptions,
      escape: () => {
        if (statsOpen) {
          setStatsOpen(false);
          return;
        }
        if (upNextSeconds != null) {
          setUpNextSeconds(null);
          onAutoplayNextChange?.(false);
          return;
        }
        if (isFullscreen()) void exitFullscreen();
      },
    }),
    [
      togglePlay,
      seekBy,
      volumeBy,
      toggleMute,
      toggleFullscreen,
      togglePiP,
      toggleCaptions,
      statsOpen,
      upNextSeconds,
      onAutoplayNextChange,
    ]
  );
  useKeyboardController(Boolean(session) && !fatal && !error, keyboardHandlers);

  useEffect(() => {
    if (!statsOpen) return;
    const id = window.setInterval(() => {
      setStats(getStats());
    }, 500);
    setStats(getStats());
    return () => window.clearInterval(id);
  }, [statsOpen, getStats, currentTime, currentLevel]);

  // Ctrl+Shift+D toggles diagnostics (no token leakage)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && (event.key === 'd' || event.key === 'D')) {
        event.preventDefault();
        setStatsOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const displayError = fatal || error;

  return (
    <div
      ref={setRootEl}
      className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-black text-white overscroll-none"
      data-testid="video-player"
      onPointerMove={() => setShowControls(true)}
      onClick={() => setShowControls(true)}
    >
      <div
        className={`absolute top-0 inset-x-0 z-20 flex items-center justify-between p-3 bg-gradient-to-b from-black/70 to-transparent transition-opacity ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/10"
          onClick={onBack}
          aria-label="Close player"
        >
          <X className="h-6 w-6" />
        </Button>
        <h1 className="text-sm font-medium truncate max-w-[70%]">{title || 'Playback'}</h1>
        <Button
          variant="ghost"
          size="sm"
          className="text-white/70 hover:bg-white/10 text-xs"
          onClick={() => setStatsOpen((v) => !v)}
          aria-pressed={statsOpen}
          data-testid="toggle-stats"
        >
          Stats
        </Button>
      </div>

      <div className="relative flex-1 flex items-center justify-center">
        <video
          ref={videoRef}
          className="w-full h-full object-contain bg-black"
          playsInline
          controls={false}
          aria-label={title || 'Video'}
          data-testid="player-video"
          onDoubleClick={(e) => {
            e.preventDefault();
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            if (x < rect.width / 2) seekBy(-10);
            else seekBy(10);
          }}
        />

        {(loading || (!ready && session && !displayError)) && (
          <PlayerLoadingState label={loading ? 'Starting secure session…' : 'Loading stream…'} />
        )}

        {buffering && ready && !displayError ? (
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
            data-testid="buffering-indicator"
            role="status"
            aria-live="polite"
          >
            <div className="h-12 w-12 animate-spin rounded-full border-2 border-white/30 border-t-primary" />
          </div>
        ) : null}

        {session && !displayError && !playing && ready ? (
          <button
            type="button"
            className="absolute inset-0 z-10 flex items-center justify-center bg-black/20"
            onClick={(e) => {
              e.stopPropagation();
              togglePlay();
            }}
            aria-label="Play"
            data-testid="center-play"
          >
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-black/60 text-white shadow-lg ring-1 ring-white/20">
              <Play className="h-8 w-8 fill-white" />
            </span>
          </button>
        ) : null}

        {displayError ? (
          <PlaybackError error={displayError} onRetry={() => { setFatal(null); void retry(); }} onBack={onBack} />
        ) : null}

        <StatsOverlay open={statsOpen} stats={stats} onClose={() => setStatsOpen(false)} />

        {session && !displayError ? (
          <PlayerControls
            visible={showControls}
            playing={playing}
            muted={muted}
            volume={volume}
            currentTime={currentTime}
            duration={duration}
            buffered={buffered}
            levels={levels}
            currentLevel={currentLevel}
            manualQualitySupported={manualQualitySupported}
            audioTracks={audioTracks}
            audioTrackId={audioTrackId}
            subtitleTracks={subtitleTracks}
            subtitleTrackId={subtitleTrackId}
            playbackRate={playbackRate}
            isFs={fs}
            pipSupported={pipSupported}
            airPlaySupported={airPlaySupported}
            hasPreviousEpisode={Boolean(onPreviousEpisode)}
            hasNextEpisode={Boolean(onNextEpisode)}
            onTogglePlay={togglePlay}
            onSeek={(t) => {
              const video = videoRef.current;
              if (video) video.currentTime = t;
            }}
            onSeekBy={seekBy}
            onVolume={(v) => {
              const video = videoRef.current;
              if (!video) return;
              video.volume = v;
              video.muted = v === 0;
              setVolume(v);
              setMuted(v === 0);
            }}
            onToggleMute={toggleMute}
            onQuality={setQuality}
            onAudio={setAudioTrack}
            onSubtitle={setSubtitleTrack}
            onRate={(rate) => {
              const video = videoRef.current;
              if (video) video.playbackRate = rate;
              setPlaybackRate(rate);
            }}
            onFullscreen={toggleFullscreen}
            onPiP={togglePiP}
            onAirPlay={() => showAirPlayPicker(videoRef.current)}
            onStartOver={startOver}
            onPreviousEpisode={onPreviousEpisode}
            onNextEpisode={onNextEpisode}
          />
        ) : null}

        {upNextSeconds != null && nextEpisodeId != null ? (
          <div
            className="absolute bottom-24 end-4 z-30 max-w-xs rounded-lg border border-white/20 bg-black/80 p-4 text-sm shadow-lg"
            data-testid="up-next-overlay"
            role="status"
            aria-live="polite"
          >
            <p className="font-medium">Next episode in {upNextSeconds}s</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onNextEpisode?.()}>
                Play now
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-white/30 bg-transparent"
                onClick={() => {
                  setUpNextSeconds(null);
                  onAutoplayNextChange?.(false);
                }}
              >
                Cancel
              </Button>
            </div>
            {onAutoplayNextChange ? (
              <label className="mt-3 flex items-center gap-2 text-xs text-white/70">
                <input
                  type="checkbox"
                  checked={autoplayNext}
                  onChange={(e) => onAutoplayNextChange(e.target.checked)}
                />
                Autoplay next episode
              </label>
            ) : null}
          </div>
        ) : null}
      </div>

      <Dialog
        open={resumePosition != null}
        onOpenChange={(open) => {
          if (!open) dismissResume();
        }}
      >
        <DialogContent
          className="max-w-md border-white/10 bg-card text-foreground [&>button]:end-4 [&>button]:right-auto"
          data-testid="resume-dialog"
        >
          <DialogHeader className="text-start">
            <DialogTitle>Continue watching?</DialogTitle>
            <DialogDescription>
              Resume from {formatResumeTime(resumePosition ?? 0)}, or start from the beginning.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 space-x-0 sm:justify-start">
            <Button onClick={resume}>Resume</Button>
            <Button variant="outline" onClick={startOver}>
              Start Over
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function formatResumeTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
    : `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}
