import type { ReactNode } from 'react';
import { Star } from 'lucide-react';
import { cn } from '@/lib/utils';
import { statusToneClass, type StatusTone } from '@/design-system/tokens';

export function RatingBadge({
  value,
  className,
  size = 'sm',
}: {
  value: number | string;
  className?: string;
  size?: 'sm' | 'md';
}) {
  const display = typeof value === 'number' ? value.toFixed(1) : value;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md bg-black/65 px-1.5 py-0.5 font-medium text-white backdrop-blur-sm',
        size === 'sm' ? 'text-[11px]' : 'text-xs px-2 py-1',
        className
      )}
      data-testid="rating-badge"
    >
      <Star className={cn('fill-primary text-primary', size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
      {display}
    </span>
  );
}

export function QualityBadge({
  label,
  className,
}: {
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'rounded-md border border-white/25 bg-black/55 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur-sm',
        className
      )}
      data-testid="quality-badge"
    >
      {label}
    </span>
  );
}

export function DemoBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'rounded-md bg-emerald-600/90 px-1.5 py-0.5 text-[10px] font-semibold text-white shadow-sm',
        className
      )}
      data-testid="demo-clip-badge"
    >
      Demo Clip
    </span>
  );
}

export function StatusChip({
  children,
  tone = 'neutral',
  className,
}: {
  children: ReactNode;
  tone?: StatusTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        statusToneClass[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function MetaChip({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border border-white/15 bg-white/5 px-2 py-1 text-xs text-foreground/90 backdrop-blur-sm',
        className
      )}
    >
      {children}
    </span>
  );
}
