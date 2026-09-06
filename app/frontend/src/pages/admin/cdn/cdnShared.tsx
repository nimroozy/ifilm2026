import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { CDNNodeDto, NodeState } from '@/lib/cdnApi';

export function formatBytes(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let size = Number(value);
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatPercent(value?: number | null): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(1)}%`;
}

export function formatAge(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return 'never';
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const STATE_STYLES: Record<NodeState, string> = {
  online: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/30',
  offline: 'bg-red-500/15 text-red-600 dark:text-red-400 ring-1 ring-red-500/30',
  draining: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/30',
  provisioning: 'bg-sky-500/15 text-sky-700 dark:text-sky-400 ring-1 ring-sky-500/30',
  failed: 'bg-red-600/20 text-red-700 dark:text-red-300 ring-1 ring-red-600/40',
  disabled: 'bg-muted text-muted-foreground ring-1 ring-border',
};

export function NodeStateBadge({ state }: { state: NodeState | string }) {
  const style = STATE_STYLES[state as NodeState] || STATE_STYLES.disabled;
  return (
    <span
      className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide', style)}
      data-testid={`cdn-state-${state}`}
    >
      {state}
    </span>
  );
}

export function RoleBadge({ role }: { role: 'main' | 'cache' | string }) {
  return (
    <Badge variant={role === 'main' ? 'default' : 'secondary'} className="uppercase tracking-wide">
      {role === 'main' ? 'MAIN CDN' : 'CACHE'}
    </Badge>
  );
}

export function NodeBadges({ node }: { node: CDNNodeDto }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <RoleBadge role={node.role} />
      <NodeStateBadge state={node.state} />
      {node.is_default && (
        <Badge variant="outline" className="uppercase tracking-wide">
          Default
        </Badge>
      )}
    </div>
  );
}

export function StatTile({ label, value, hint, testId }: { label: string; value: ReactNode; hint?: ReactNode; testId?: string }) {
  return (
    <Card className="border-border bg-card" data-testid={testId}>
      <CardContent className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export function KeyValue({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('text-right', mono && 'font-mono text-xs')}>{value ?? '—'}</span>
    </div>
  );
}

export function errorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'message' in err && typeof (err as { message?: unknown }).message === 'string') {
    return (err as { message: string }).message;
  }
  return fallback;
}
