import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

export const POSTER_FALLBACK = 'https://placehold.co/300x450/1a1a2e/e8a838?text=No+Poster';

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    published: 'bg-green-500/20 text-green-500',
    draft: 'bg-yellow-500/20 text-yellow-500',
    archived: 'bg-muted text-muted-foreground',
    completed: 'bg-green-500/20 text-green-500',
    pending: 'bg-yellow-500/20 text-yellow-500',
    uploading: 'bg-blue-500/20 text-blue-500',
    failed: 'bg-red-500/20 text-red-500',
    cancelled: 'bg-muted text-muted-foreground',
  };
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium capitalize ${styles[status] || 'bg-muted text-muted-foreground'}`}>
      {status}
    </span>
  );
}

export function LoadingBlock({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" data-testid="loading-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Alert variant="destructive" data-testid="error-state">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Error</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{message}</span>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} className="gap-2 shrink-0">
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-16 text-muted-foreground" data-testid="empty-state">
      <p>{message}</p>
    </div>
  );
}

export function PosterThumb({
  src,
  alt,
  className = 'w-10 h-14 rounded object-cover bg-muted',
}: {
  src?: string;
  alt: string;
  className?: string;
}) {
  return (
    <img
      src={src || POSTER_FALLBACK}
      alt={alt}
      className={className}
      onError={(e) => {
        const img = e.currentTarget;
        if (img.src !== POSTER_FALLBACK) img.src = POSTER_FALLBACK;
      }}
    />
  );
}

export function csvToList(value: string): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export function listToCsv(value?: string[]): string {
  return (value ?? []).join(', ');
}
