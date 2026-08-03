import { useCallback, useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
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
import type { PlayerTarget, SafePlayerError } from './types';

export function VideoPlayer({
  target,
  title,
  onBack,
}: {
  target: PlayerTarget;
  title?: string;
  onBack?: () => void;
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
    levels,
    currentLevel,
    setQuality,
    audioTracks,
    setAudioTrack,
    manualQualitySupported,
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

  const keyboardHandlers = useMemo(
    () => ({
      togglePlay,
      seekBy,
      volumeBy,
      toggleMute,
      toggleFullscreen,
      togglePiP,
    }),
    [togglePlay, seekBy, volumeBy, toggleMute, toggleFullscreen, togglePiP]
  );
  useKeyboardController(Boolean(session) && !fatal && !error, keyboardHandlers);

  const displayError = fatal || error;

  return (
    <div
      ref={setRootEl}
      className="fixed inset-0 z-50 flex flex-col bg-black text-white"
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
        <span className="w-10" />
      </div>

      <div className="relative flex-1 flex items-center justify-center">
        <video
          ref={videoRef}
          className="w-full h-full object-contain bg-black"
          playsInline
          controls={false}
          aria-label={title || 'Video'}
          data-testid="player-video"
        />

        {(loading || (!ready && session && !displayError)) && (
          <PlayerLoadingState label={loading ? 'Starting secure session…' : 'Loading stream…'} />
        )}

        {displayError ? (
          <PlaybackError error={displayError} onRetry={() => { setFatal(null); void retry(); }} onBack={onBack} />
        ) : null}

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
            playbackRate={playbackRate}
            isFs={fs}
            pipSupported={pipSupported}
            airPlaySupported={airPlaySupported}
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
            onRate={(rate) => {
              const video = videoRef.current;
              if (video) video.playbackRate = rate;
              setPlaybackRate(rate);
            }}
            onFullscreen={toggleFullscreen}
            onPiP={togglePiP}
            onAirPlay={() => showAirPlayPicker(videoRef.current)}
            onStartOver={startOver}
          />
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
