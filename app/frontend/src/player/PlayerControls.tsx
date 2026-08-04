import {
  Cast,
  ChevronLeft,
  ChevronRight,
  Maximize,
  Minimize,
  Pause,
  PictureInPicture2,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { QualitySelector } from './QualitySelector';
import { AudioTrackSelector, SubtitleSelector } from './AudioTrackSelector';
import type { AudioTrackInfo, QualityLevel, SubtitleTrackInfo } from './types';

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function PlayerControls({
  visible,
  playing,
  muted,
  volume,
  currentTime,
  duration,
  buffered,
  levels,
  currentLevel,
  manualQualitySupported,
  audioTracks,
  audioTrackId,
  subtitleTracks = [],
  subtitleTrackId = -1,
  playbackRate,
  isFs,
  pipSupported = true,
  airPlaySupported = false,
  hasPreviousEpisode = false,
  hasNextEpisode = false,
  onTogglePlay,
  onSeek,
  onSeekBy,
  onVolume,
  onToggleMute,
  onQuality,
  onAudio,
  onSubtitle,
  onRate,
  onFullscreen,
  onPiP,
  onAirPlay,
  onStartOver,
  onPreviousEpisode,
  onNextEpisode,
}: {
  visible: boolean;
  playing: boolean;
  muted: boolean;
  volume: number;
  currentTime: number;
  duration: number;
  buffered: number;
  levels: QualityLevel[];
  currentLevel: number;
  manualQualitySupported: boolean;
  audioTracks: AudioTrackInfo[];
  audioTrackId?: number;
  subtitleTracks?: SubtitleTrackInfo[];
  subtitleTrackId?: number;
  playbackRate: number;
  isFs: boolean;
  pipSupported?: boolean;
  airPlaySupported?: boolean;
  hasPreviousEpisode?: boolean;
  hasNextEpisode?: boolean;
  onTogglePlay: () => void;
  onSeek: (t: number) => void;
  onSeekBy?: (delta: number) => void;
  onVolume: (v: number) => void;
  onToggleMute: () => void;
  onQuality: (level: number) => void;
  onAudio: (id: number) => void;
  onSubtitle?: (id: number) => void;
  onRate: (rate: number) => void;
  onFullscreen: () => void;
  onPiP: () => void;
  onAirPlay?: () => void;
  onStartOver?: () => void;
  onPreviousEpisode?: () => void;
  onNextEpisode?: () => void;
}) {
  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;
  const bufferedPct = duration > 0 ? (buffered / duration) * 100 : 0;

  return (
    <div
      className={`absolute inset-x-0 bottom-0 z-20 px-3 pb-[max(0.85rem,env(safe-area-inset-bottom))] pt-16 transition-all duration-normal ${
        visible ? 'opacity-100 translate-y-0' : 'pointer-events-none translate-y-2 opacity-0'
      }`}
      data-testid="player-controls"
    >
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-black via-black/70 to-transparent" />

      <div className="relative mx-auto max-w-6xl space-y-3">
        <div className="relative h-2 cursor-pointer group/seek" data-testid="seek-bar">
          <div className="absolute inset-0 rounded-full bg-white/20" />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-white/40"
            style={{ width: `${bufferedPct}%` }}
          />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-primary shadow-[0_0_12px_hsl(var(--primary)/0.55)]"
            style={{ width: `${progressPct}%` }}
          />
          <div
            className="absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 border-white bg-primary opacity-0 shadow-lg transition-opacity group-hover/seek:opacity-100"
            style={{ left: `calc(${progressPct}% - 0.4rem)` }}
          />
          <input
            type="range"
            min={0}
            max={Math.max(duration, 0.1)}
            step={0.1}
            value={currentTime}
            aria-label="Seek"
            className="absolute inset-0 w-full cursor-pointer opacity-0"
            onChange={(e) => onSeek(Number(e.target.value))}
          />
        </div>

        <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-white/10 bg-black/45 px-2 py-1.5 text-white shadow-xl backdrop-blur-xl supports-[backdrop-filter]:bg-black/35 sm:gap-1.5 sm:px-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-white hover:bg-white/10"
          onClick={onTogglePlay}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 fill-white" />}
        </Button>

        {hasPreviousEpisode ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-white hover:bg-white/10"
            onClick={onPreviousEpisode}
            aria-label="Previous episode"
            data-testid="previous-episode"
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
        ) : null}

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-white hover:bg-white/10"
          onClick={() => onSeekBy?.(-10)}
          aria-label="Skip back 10 seconds"
          data-testid="skip-back"
        >
          <SkipBack className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-white hover:bg-white/10"
          onClick={() => onSeekBy?.(10)}
          aria-label="Skip forward 10 seconds"
          data-testid="skip-forward"
        >
          <SkipForward className="h-5 w-5" />
        </Button>

        {hasNextEpisode ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-white hover:bg-white/10"
            onClick={onNextEpisode}
            aria-label="Next episode"
            data-testid="next-episode"
          >
            <ChevronRight className="h-5 w-5" />
          </Button>
        ) : null}

        {onStartOver ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-white hover:bg-white/10"
            onClick={onStartOver}
            aria-label="Start over"
            data-testid="start-over"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        ) : null}

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-white hover:bg-white/10"
          onClick={onToggleMute}
          aria-label={muted ? 'Unmute' : 'Mute'}
        >
          {muted || volume === 0 ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
        </Button>

        <div className="w-24 max-sm:w-16 [&_[role=slider]]:bg-primary">
          <Slider
            value={[muted ? 0 : volume * 100]}
            max={100}
            step={1}
            aria-label="Volume"
            onValueChange={(v) => onVolume((v[0] ?? 0) / 100)}
          />
        </div>

        <span className="min-w-[5.5rem] text-xs tabular-nums text-white/85">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>

        <div className="flex-1" />

        <QualitySelector
          levels={levels}
          currentLevel={currentLevel}
          onChange={onQuality}
          unsupportedReason={
            manualQualitySupported
              ? null
              : 'Quality selection is managed by the browser on this device'
          }
        />
        <AudioTrackSelector tracks={audioTracks} value={audioTrackId} onChange={onAudio} />
        <SubtitleSelector
          tracks={subtitleTracks}
          value={subtitleTrackId}
          onChange={(id) => onSubtitle?.(id)}
        />

        <select
          className="h-8 rounded-md border border-white/15 bg-white/10 px-2 text-xs text-white backdrop-blur-sm"
          aria-label="Playback speed"
          value={playbackRate}
          onChange={(e) => onRate(Number(e.target.value))}
        >
          {[0.5, 0.75, 1, 1.25, 1.5, 2].map((rate) => (
            <option key={rate} value={rate} className="bg-zinc-900 text-white">
              {rate}x
            </option>
          ))}
        </select>

        {airPlaySupported && onAirPlay ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-white hover:bg-white/10"
            onClick={onAirPlay}
            aria-label="AirPlay"
            data-testid="airplay-button"
          >
            <span className="text-[10px] font-semibold tracking-wide">AP</span>
          </Button>
        ) : null}

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 cursor-not-allowed text-white/40 hover:bg-white/10"
          disabled
          aria-label="Google Cast unavailable"
          title="Google Cast requires a protected receiver and is not enabled in this release"
          data-testid="cast-button-disabled"
        >
          <Cast className="h-5 w-5" />
        </Button>

        {pipSupported ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-10 w-10 text-white hover:bg-white/10"
            onClick={onPiP}
            aria-label="Picture in picture"
            data-testid="pip-button"
          >
            <PictureInPicture2 className="h-5 w-5" />
          </Button>
        ) : null}

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-white hover:bg-white/10"
          onClick={onFullscreen}
          aria-label={isFs ? 'Exit fullscreen' : 'Enter fullscreen'}
        >
          {isFs ? <Minimize className="h-5 w-5" /> : <Maximize className="h-5 w-5" />}
        </Button>
        </div>
      </div>
    </div>
  );
}
