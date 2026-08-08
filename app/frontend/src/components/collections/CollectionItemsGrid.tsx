import type { CatalogMovie, CatalogSeries } from '@/lib/catalogData';
import { catalogAvailabilityBadges } from '@/lib/catalogAvailability';
import { canPlayFullMovie, hasDemoClip } from '@/lib/catalogPresentation';
import { MediaCard, mediaGridClass } from '@/design-system';

export interface CollectionAvailabilityLabels {
  dubbed: string;
  subtitled: string;
  multiAudio: string;
}

/**
 * Ordered grid of collection items (movies + series) — shared by the admin
 * preview tab and the customer collection detail page so both stay in sync.
 */
export function CollectionItemsGrid({
  items,
  availabilityLabels,
  onActivateMovie,
  onActivateSeries,
  className,
  'data-testid': testId = 'collection-items-grid',
}: {
  items: (CatalogMovie | CatalogSeries)[];
  availabilityLabels: CollectionAvailabilityLabels;
  onActivateMovie: (id: number) => void;
  onActivateSeries: (id: number) => void;
  className?: string;
  'data-testid'?: string;
}) {
  if (!items.length) return null;

  return (
    <div
      className={
        className ||
        mediaGridClass
      }
      data-testid={testId}
    >
      {items.map((item) => {
        const isSeries = item.type === 'series';
        const { badges, overflow } = catalogAvailabilityBadges(item, availabilityLabels);
        return (
          <MediaCard
            key={`${isSeries ? 'series' : 'movie'}-${item.id}`}
            className="!w-full max-w-none"
            title={item.title}
            imageUrl={item.poster}
            year={item.year}
            rating={item.rating}
            runtime={
              !isSeries && 'duration' in item && item.duration ? `${item.duration} min` : undefined
            }
            quality={!isSeries && 'qualities' in item ? item.qualities?.[0] || undefined : undefined}
            availabilityBadges={badges}
            availabilityOverflow={overflow}
            showDemo={hasDemoClip(item)}
            playable={isSeries ? hasDemoClip(item) : canPlayFullMovie(item) || hasDemoClip(item)}
            onActivate={() => (isSeries ? onActivateSeries(item.id) : onActivateMovie(item.id))}
          />
        );
      })}
    </div>
  );
}
