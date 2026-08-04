import { Play } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DemoBadge, QualityBadge, RatingBadge } from '@/design-system/Badges';
import { mediaSizes, surfaces } from '@/design-system/tokens';

export type MediaCardVariant = 'poster' | 'landscape';

export interface MediaCardProps {
  title: string;
  imageUrl?: string | null;
  href?: string;
  year?: number | string;
  rating?: number | string;
  runtime?: string;
  quality?: string;
  showDemo?: boolean;
  progress?: number;
  badge?: string;
  variant?: MediaCardVariant;
  size?: 'sm' | 'md' | 'lg';
  onActivate?: () => void;
  className?: string;
  'data-testid'?: string;
}

function sizeClass(variant: MediaCardVariant, size: 'sm' | 'md' | 'lg') {
  if (variant === 'landscape') {
    return size === 'sm' ? mediaSizes.landscapeSm : mediaSizes.landscapeMd;
  }
  if (size === 'sm') return mediaSizes.posterSm;
  if (size === 'lg') return mediaSizes.posterLg;
  return mediaSizes.posterMd;
}

/**
 * Premium title card — lift, shadow, play affordance, badges, optional progress.
 * Used by shelves, grids, search, and related rows.
 */
export function MediaCard({
  title,
  imageUrl,
  year,
  rating,
  runtime,
  quality,
  showDemo,
  progress,
  badge,
  variant = 'poster',
  size = 'md',
  onActivate,
  className,
  'data-testid': testId = 'media-card',
}: MediaCardProps) {
  const aspect = variant === 'landscape' ? 'aspect-video' : 'aspect-[2/3]';

  return (
    <div
      role={onActivate ? 'link' : undefined}
      tabIndex={onActivate ? 0 : undefined}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (!onActivate) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onActivate();
        }
      }}
      className={cn(
        'group/card flex-shrink-0 cursor-pointer outline-none',
        sizeClass(variant, size),
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-xl',
        className
      )}
      data-testid={testId}
    >
      <div
        className={cn(
          'relative mb-2 overflow-hidden transition-all duration-normal ease-out',
          surfaces.mediaCard,
          aspect,
          'group-hover/card:-translate-y-1 group-hover/card:shadow-xl group-hover/card:ring-white/15',
          'group-focus-visible/card:-translate-y-1'
        )}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover transition-transform duration-slow ease-out group-hover/card:scale-110"
          />
        ) : (
          <div className="flex h-full items-center justify-center bg-muted px-3 text-center text-xs text-muted-foreground">
            {title}
          </div>
        )}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-80" />

        <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all duration-normal group-hover/card:bg-black/35 group-hover/card:opacity-100">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg scale-90 transition-transform duration-normal group-hover/card:scale-100">
            <Play className="h-5 w-5 fill-current" aria-hidden />
          </span>
        </div>

        <div className="absolute left-2 right-2 top-2 flex flex-wrap items-start justify-between gap-1">
          <div className="flex flex-wrap gap-1">
            {badge ? (
              <span className="rounded-md bg-secondary/90 px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground">
                {badge}
              </span>
            ) : null}
            {showDemo ? <DemoBadge /> : null}
          </div>
          <div className="flex flex-wrap justify-end gap-1">
            {quality ? <QualityBadge label={quality} /> : null}
            {rating !== undefined && rating !== null && rating !== '' && Number(rating) > 0 ? (
              <RatingBadge value={rating} />
            ) : null}
          </div>
        </div>

        {typeof progress === 'number' && progress > 0 ? (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/20">
            <div
              className="h-full bg-primary transition-[width] duration-normal"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
              data-testid="media-card-progress"
            />
          </div>
        ) : null}
      </div>

      <h3 className="truncate text-sm font-semibold text-foreground md:text-[15px]">{title}</h3>
      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
        {year ? <span>{year}</span> : null}
        {year && runtime ? <span aria-hidden>•</span> : null}
        {runtime ? <span>{runtime}</span> : null}
      </div>
    </div>
  );
}
