import { Loader2 } from 'lucide-react';

export function PlayerLoadingState({ label = 'Preparing playback…' }: { label?: string }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-black/50 via-black/75 to-black/90 text-white backdrop-blur-[2px]"
      role="status"
      aria-live="polite"
      data-testid="player-loading"
    >
      <div className="relative flex h-16 w-16 items-center justify-center">
        <span className="absolute inset-0 rounded-full border border-primary/30 animate-ping" />
        <Loader2 className="h-10 w-10 animate-spin text-primary" aria-hidden />
      </div>
      <p className="text-sm font-medium tracking-wide text-white/85">{label}</p>
    </div>
  );
}
