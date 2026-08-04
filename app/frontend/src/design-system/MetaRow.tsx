import { cn } from '@/lib/utils';
import { MetaChip } from '@/design-system/Badges';

export interface MetaRowProps {
  items: Array<string | number | null | undefined | false>;
  className?: string;
  asChips?: boolean;
}

/** Compact metadata strip (year · runtime · rating · genres). */
export function MetaRow({ items, className, asChips = false }: MetaRowProps) {
  const cleaned = items.filter((item): item is string | number => Boolean(item) || item === 0);
  if (!cleaned.length) return null;

  if (asChips) {
    return (
      <div className={cn('flex flex-wrap items-center gap-2', className)}>
        {cleaned.map((item) => (
          <MetaChip key={String(item)}>{item}</MetaChip>
        ))}
      </div>
    );
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground', className)}>
      {cleaned.map((item, index) => (
        <span key={`${item}-${index}`} className="inline-flex items-center gap-2">
          {index > 0 ? <span aria-hidden className="text-muted-foreground/50">·</span> : null}
          <span>{item}</span>
        </span>
      ))}
    </div>
  );
}
