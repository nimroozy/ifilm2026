import type { MouseEvent } from 'react';
import { Info, Play, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DemoBadge, QualityBadge, RatingBadge } from '@/design-system/Badges';
import { mediaSizes, surfaces } from '@/design-system/tokens';
import { sizedArtworkUrl } from '@/lib/imageUrls';

export type MediaCardVariant = 'poster' | 'landscape';

export interface MediaCardProps {
  title: string;
  imageUrl?: string | null;
  href?: string;
  year?: number | string;
  rating?: number | string;
  runtime?: string;
  /** Compact status/season note shown under the title (e.g. Ongoing / S1 · E3). */
  status?: string;
  quality?: string;
  showDemo?: boolean;
  /** When true, show the Play overlay. Never imply playback if not playable. */
  playable?: boolean;
  progress?: number;
  badge?: string;
  availabilityBadges?: { key: string; label: string; fullLabel: string }[];
  availabilityOverflow?: number;
  variant?: MediaCardVariant;
  size?: 'sm' | 'md' | 'lg';
  /** Primary activate (details / resume). Enter/Space and card click. */
  onActivate?: () => void;
  /** Optional Play action (hover/focus control). Defaults to onActivate when omitted. */
  onPlay?: () => void;
  /** Optional My List action. When provided, shows control on hover/focus. */
  onMyList?: () => void;
  /** Genres for hover metadata (compact). */
  genres?: string[];
  className?: string;
  /** Eager-load above-the-fold artwork for LCP; default lazy. */
  priority?: boolean;
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

function stop(event: MouseEvent) {
  event.preventDefault();
  event.stopPropagation();
}

/**
 * Premium MediaCard V2 — lift/scale without grid reflow, focusable overlay controls,
 * progress, badges. No trailer autoplay on hover.
 */
export function MediaCard({
  title,
  imageUrl,
  year,
  rating,
  runtime,
  status,
  quality,
  showDemo,
  playable = false,
  progress,
  badge,
  availabilityBadges,
  availabilityOverflow = 0,
  variant = 'poster',
  size = 'md',
  onActivate,
  onPlay,
  onMyList,
  genres,
  className,
  priority = false,
  'data-testid': testId = 'media-card',
}: MediaCardProps) {
  const aspect = variant === 'landscape' ? 'aspect-video' : 'aspect-[2/3]';
  const intrinsic =
    variant === 'landscape'
      ? { width: 320, height: 180 }
      : size === 'sm'
        ? { width: 120, height: 180 }
        : size === 'lg'
          ? { width: 200, height: 300 }
          : { width: 160, height: 240 };
  const sizedSrc = sizedArtworkUrl(
    imageUrl,
    variant === 'landscape' ? 'backdrop' : 'poster',
    'card'
  );
  const showPlay = Boolean(playable || onPlay);
  const playHandler = onPlay ?? onActivate;
  const metaHover = [
    year,
    rating != null && rating !== '' && Number(rating) > 0 ? `${Number(rating).toFixed(1)}★` : null,
    (genres || []).slice(0, 2).join(' · ') || null,
  ]
    .filter(Boolean)
    .join(' · ');

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
        'group/card relative flex-shrink-0 outline-none',
        onActivate ? 'cursor-pointer' : undefined,
        sizeClass(variant, size),
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-xl',
        className
      )}
      data-testid={testId}
    >
      <div
        className={cn(
          'relative mb-2 overflow-hidden transition-[transform,box-shadow] duration-normal ease-out will-change-transform',
          surfaces.mediaCard,
          aspect,
          // Transform on the poster only — surrounding rail/grid must not reflow.
          'group-hover/card:z-10 group-hover/card:-translate-y-1.5 group-hover/card:scale-[1.04] group-hover/card:shadow-xl group-hover/card:ring-white/15',
          'group-focus-visible/card:z-10 group-focus-visible/card:-translate-y-1.5 group-focus-visible/card:scale-[1.04]',
          'active:-translate-y-0.5'
        )}
      >
        {sizedSrc ? (
          <img
            src={sizedSrc}
            alt=""
            width={intrinsic.width}
            height={intrinsic.height}
            loading={priority ? 'eager' : 'lazy'}
            decoding="async"
            {...({ fetchpriority: priority ? 'high' : 'auto' } as object)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center bg-gradient-to-br from-[#1c2740] to-[#0e1420] px-3 text-center text-sm font-semibold text-muted-foreground">
            {(title || '?').slice(0, 1)}
          </div>
        )}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-transparent opacity-90" />

        {/* Hover / focus overlay — also visible when card itself is keyboard-focused */}
        <div
          className={cn(
            'absolute inset-0 flex flex-col justify-end gap-2 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-2.5',
            'opacity-0 transition-opacity duration-normal',
            'group-hover/card:opacity-100 group-focus-within/card:opacity-100 group-focus-visible/card:opacity-100'
          )}
          data-testid="media-card-overlay"
        >
          <div className="flex items-center gap-1.5">
            {showPlay ? (
              <button
                type="button"
                aria-label={`Play ${title}`}
                data-testid="media-card-play"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md"
                onClick={(event) => {
                  stop(event);
                  playHandler?.();
                }}
              >
                <Play className="h-4 w-4 fill-current" aria-hidden />
              </button>
            ) : null}
            {onMyList ? (
              <button
                type="button"
                aria-label={`My List ${title}`}
                data-testid="media-card-mylist"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-white/10 text-white backdrop-blur-sm"
                onClick={(event) => {
                  stop(event);
                  onMyList();
                }}
              >
                <Plus className="h-4 w-4" aria-hidden />
              </button>
            ) : null}
            {onActivate ? (
              <button
                type="button"
                aria-label={`Details ${title}`}
                data-testid="media-card-details"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-white/10 text-white backdrop-blur-sm"
                onClick={(event) => {
                  stop(event);
                  onActivate();
                }}
              >
                <Info className="h-4 w-4" aria-hidden />
              </button>
            ) : null}
          </div>
          {metaHover ? (
            <p className="line-clamp-1 text-[11px] font-medium leading-snug text-white/85">{metaHover}</p>
          ) : null}
        </div>

        <div className="absolute left-2 right-2 top-2 z-[1] flex flex-wrap items-start justify-between gap-1">
          <div className="flex max-w-[70%] flex-wrap gap-1" data-testid="media-card-availability">
            {availabilityBadges?.map((b) => (
              <span
                key={b.key}
                title={b.fullLabel}
                aria-label={b.fullLabel}
                className="rounded-md bg-secondary/90 px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground"
              >
                {b.label}
              </span>
            ))}
            {availabilityOverflow > 0 ? (
              <span
                className="rounded-md bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white"
                aria-label={`Plus ${availabilityOverflow} more`}
              >
                +{availabilityOverflow}
              </span>
            ) : null}
            {!availabilityBadges?.length && badge ? (
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
          <div className="absolute bottom-0 left-0 right-0 z-[1] h-1 bg-white/20">
            <div
              className="h-full bg-primary transition-[width] duration-normal"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
              data-testid="media-card-progress"
            />
          </div>
        ) : null}
      </div>

      <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-foreground md:text-[15px]">
        {title}
      </h3>
      <div className="mt-0.5 flex min-h-[1rem] flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {year ? <span>{year}</span> : null}
        {year && runtime ? <span aria-hidden>•</span> : null}
        {runtime ? <span>{runtime}</span> : null}
        {(year || runtime) && status ? <span aria-hidden>•</span> : null}
        {status ? <span>{status}</span> : null}
        {badge && !availabilityBadges?.length && !status ? (
          <>
            {year || runtime ? <span aria-hidden>•</span> : null}
            <span>{badge}</span>
          </>
        ) : null}
      </div>
    </div>
  );
}
