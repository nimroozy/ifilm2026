import type { ReactNode } from 'react';
import { AlertCircle, Film, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { cn } from '@/lib/utils';

export const POSTER_FALLBACK = 'https://placehold.co/300x450/1a1a2e/e8a838?text=No+Poster';

const STATUS_STYLES: Record<string, string> = {
  published: 'bg-success/15 text-success ring-1 ring-success/25',
  draft: 'bg-warning/15 text-warning ring-1 ring-warning/25',
  in_review: 'bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/25',
  approved: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/25',
  scheduled: 'bg-violet-500/15 text-violet-400 ring-1 ring-violet-500/25',
  unpublished: 'bg-orange-500/15 text-orange-400 ring-1 ring-orange-500/25',
  archived: 'bg-muted text-muted-foreground ring-1 ring-border',
  completed: 'bg-success/15 text-success ring-1 ring-success/25',
  pending: 'bg-warning/15 text-warning ring-1 ring-warning/25',
  uploading: 'bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/25',
  failed: 'bg-destructive/15 text-destructive ring-1 ring-destructive/25',
  cancelled: 'bg-muted text-muted-foreground ring-1 ring-border',
};

const STATUS_LABELS: Record<string, string> = {
  in_review: 'In review',
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
        STATUS_STYLES[status] || 'bg-muted text-muted-foreground ring-1 ring-border'
      )}
    >
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export function LoadingBlock({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" data-testid="loading-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-xl" />
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
    <Alert variant="destructive" className="rounded-xl" data-testid="error-state">
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
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border/80 bg-card/40 px-6 py-16 text-center"
      data-testid="empty-state"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Film className="h-5 w-5" />
      </div>
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

export function PosterThumb({
  src,
  alt,
  className = 'h-14 w-10 rounded-md object-cover bg-muted shadow-sm ring-1 ring-white/10',
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

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-foreground md:text-3xl">
          {title}
        </h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
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
