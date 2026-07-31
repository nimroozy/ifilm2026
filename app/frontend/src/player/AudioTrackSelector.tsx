import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AudioTrackInfo } from './types';

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
        className="w-[120px] h-8 bg-black/40 border-white/20 text-white text-xs"
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

export function SubtitleSelector() {
  // Placeholder — subtitle packaging is deferred.
  return null;
}
