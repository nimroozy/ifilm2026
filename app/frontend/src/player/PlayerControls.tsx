import {
  Maximize,
  Minimize,
  Pause,
  PictureInPicture2,
  Play,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { QualitySelector } from './QualitySelector';
import { AudioTrackSelector, SubtitleSelector } from './AudioTrackSelector';
import type { AudioTrackInfo, QualityLevel } from './types';

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
  playbackRate,
  isFs,
  onTogglePlay,
  onSeek,
  onVolume,
  onToggleMute,
  onQuality,
  onAudio,
  onRate,
  onFullscreen,
  onPiP,
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
  playbackRate: number;
  isFs: boolean;
  onTogglePlay: () => void;
  onSeek: (t: number) => void;
  onVolume: (v: number) => void;
  onToggleMute: () => void;
  onQuality: (level: number) => void;
  onAudio: (id: number) => void;
  onRate: (rate: number) => void;
  onFullscreen: () => void;
  onPiP: () => void;
}) {
  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;
  const bufferedPct = duration > 0 ? (buffered / duration) * 100 : 0;

  return (
    <div
      className={`absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-10 transition-opacity ${
        visible ? 'opacity-100' : 'opacity-0 pointer-events-none'
      }`}
      data-testid="player-controls"
    >
      <div className="relative h-1.5 mb-3 cursor-pointer group" data-testid="seek-bar">
        <div className="absolute inset-0 rounded-full bg-white/20" />
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-white/35"
          style={{ width: `${bufferedPct}%` }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-primary"
          style={{ width: `${progressPct}%` }}
        />
        <input
          type="range"
          min={0}
          max={Math.max(duration, 0.1)}
          step={0.1}
          value={currentTime}
          aria-label="Seek"
          className="absolute inset-0 w-full opacity-0 cursor-pointer"
          onChange={(e) => onSeek(Number(e.target.value))}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-white">
        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/10 h-10 w-10"
          onClick={onTogglePlay}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 fill-white" />}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/10 h-10 w-10"
          onClick={onToggleMute}
          aria-label={muted ? 'Unmute' : 'Mute'}
        >
          {muted || volume === 0 ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
        </Button>

        <div className="w-24 max-sm:w-16">
          <Slider
            value={[muted ? 0 : volume * 100]}
            max={100}
            step={1}
            aria-label="Volume"
            onValueChange={(v) => onVolume((v[0] ?? 0) / 100)}
          />
        </div>

        <span className="text-xs text-white/80 tabular-nums min-w-[5.5rem]">
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
        <AudioTrackSelector tracks={audioTracks} onChange={onAudio} />
        <SubtitleSelector />

        <select
          className="h-8 rounded-md bg-black/40 border border-white/20 text-xs px-2"
          aria-label="Playback speed"
          value={playbackRate}
          onChange={(e) => onRate(Number(e.target.value))}
        >
          {[0.5, 0.75, 1, 1.25, 1.5, 2].map((rate) => (
            <option key={rate} value={rate}>
              {rate}x
            </option>
          ))}
        </select>

        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/10 h-10 w-10"
          onClick={onPiP}
          aria-label="Picture in picture"
        >
          <PictureInPicture2 className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="text-white hover:bg-white/10 h-10 w-10"
          onClick={onFullscreen}
          aria-label={isFs ? 'Exit fullscreen' : 'Enter fullscreen'}
        >
          {isFs ? <Minimize className="h-5 w-5" /> : <Maximize className="h-5 w-5" />}
        </Button>
      </div>
    </div>
  );
}
