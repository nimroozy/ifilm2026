import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AudioTrackInfo, SubtitleTrackInfo } from './types';

export function AudioTrackSelector({
  tracks,
  onChange,
  value,
}: {
  tracks: AudioTrackInfo[];
  onChange: (id: number) => void;
  value?: number;
}) {
  if (tracks.length <= 1) return null;
  const selected = value ?? tracks[0]?.id ?? 0;
  return (
    <Select value={String(selected)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger
        className="w-[120px] h-10 min-h-10 bg-black/40 border-white/20 text-white text-xs"
        aria-label="Audio track"
        data-testid="audio-selector"
      >
        <SelectValue placeholder="Audio" />
      </SelectTrigger>
      <SelectContent>
        {tracks.map((track) => (
          <SelectItem key={track.id} value={String(track.id)}>
            {track.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function SubtitleSelector({
  tracks,
  value,
  onChange,
}: {
  tracks: SubtitleTrackInfo[];
  value: number; // -1 = Off
  onChange: (id: number) => void;
}) {
  // Always show Off + available tracks so the captions control is discoverable.
  const options: SubtitleTrackInfo[] = [{ id: -1, name: 'Off' }, ...tracks];
  const selected = options.some((t) => t.id === value) ? value : -1;

  return (
    <Select value={String(selected)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger
        className="w-[120px] h-10 min-h-10 bg-black/40 border-white/20 text-white text-xs"
        aria-label="Subtitles"
        data-testid="subtitle-selector"
      >
        <SelectValue placeholder="Subtitles" />
      </SelectTrigger>
      <SelectContent>
        {options.map((track) => (
          <SelectItem key={track.id} value={String(track.id)}>
            {track.name}
            {track.lang && track.id >= 0 ? ` (${track.lang})` : ''}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
