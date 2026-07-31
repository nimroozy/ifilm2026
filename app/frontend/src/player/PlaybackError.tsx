import { Button } from '@/components/ui/button';
import type { SafePlayerError } from './types';
import { sanitizeErrorText } from './safeErrors';

export function PlaybackError({
  error,
  onRetry,
  onBack,
}: {
  error: SafePlayerError;
  onRetry?: () => void;
  onBack?: () => void;
}) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-black/85 px-6 text-center text-white"
      role="alert"
      data-testid="player-error"
    >
      <p className="text-lg font-medium">{sanitizeErrorText(error.message)}</p>
      <div className="flex flex-wrap gap-2 justify-center">
        {error.retryable && onRetry ? (
          <Button onClick={onRetry} variant="secondary">
            Try again
          </Button>
        ) : null}
        {onBack ? (
          <Button onClick={onBack} variant="outline" className="border-white/30 text-white">
            Go back
          </Button>
        ) : null}
      </div>
    </div>
  );
}
