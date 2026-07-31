import { Loader2 } from 'lucide-react';

export function PlayerLoadingState({ label = 'Preparing playback…' }: { label?: string }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 text-white"
      role="status"
      aria-live="polite"
      data-testid="player-loading"
    >
      <Loader2 className="h-10 w-10 animate-spin" aria-hidden />
      <p className="text-sm text-white/80">{label}</p>
    </div>
  );
}
