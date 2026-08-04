import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth, useLang } from '@/components/CustomerLayout';
import { ContentShelf, MediaCard } from '@/design-system';
import { HeroCarousel } from '@/components/HeroCarousel';
import { watchHistory } from '@/data/mockData';
import { fetchHomeCatalog, type CatalogMovie, type CatalogSeries } from '@/lib/catalogData';
import { api, ApiError, tokenStore, type WatchProgressDto } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import { hasDemoClip, canPlayFullMovie } from '@/lib/catalogPresentation';

type HomeData = Awaited<ReturnType<typeof fetchHomeCatalog>>;

function HomeLoading() {
  return (
    <div className="space-y-6 pt-8" data-testid="home-loading">
      <Skeleton className="h-[70vh] w-full rounded-none" />
      <div className="space-y-4 px-4 sm:px-6 lg:px-8">
        <Skeleton className="h-7 w-56" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[260px] w-[160px] shrink-0 rounded-xl" />
          ))}
        </div>
      </div>
    </div>
  );
}

function HomeError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const safe =
    message.includes('status code') || message.toLowerCase().includes('network')
      ? 'Unable to load the catalog right now. Check your connection and try again.'
      : message;
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center gap-4 px-4" data-testid="home-error">
      <p className="text-muted-foreground text-center" role="alert">
        {safe}
      </p>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}

function ContentRow({
  title,
  items,
  type = 'movie',
}: {
  title: string;
  items: (CatalogMovie | CatalogSeries)[];
  type?: 'movie' | 'series';
}) {
  const navigate = useNavigate();

  if (!items.length) return null;

  return (
    <ContentShelf title={title}>
      {items.map((item) => {
        const contentType = type === 'series' || item.type === 'series' ? 'Series' : 'Movie';
        const qualities = 'qualities' in item ? item.qualities : undefined;
        const topQuality = Array.isArray(qualities) && qualities.length ? String(qualities[0]) : undefined;
        const runtime =
          'duration' in item && typeof item.duration === 'number' && item.duration > 0
            ? `${item.duration} min`
            : undefined;
        return (
          <MediaCard
            key={`${contentType}-${item.id}`}
            title={item.title}
            imageUrl={item.poster}
            year={item.year}
            rating={item.rating}
            runtime={runtime}
            quality={topQuality}
            showDemo={hasDemoClip(item)}
            playable={canPlayFullMovie(item) || hasDemoClip(item)}
            badge={
              item.type === 'series' && 'newEpisode' in item && item.newEpisode
                ? 'NEW'
                : contentType === 'Series'
                  ? 'Series'
                  : undefined
            }
            onActivate={() =>
              navigate(type === 'series' || item.type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)
            }
          />
        );
      })}
    </ContentShelf>
  );
}

function ContinueWatchingRow() {
  const { t } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const mockMode = isMockMode();
  const [apiItems, setApiItems] = useState<WatchProgressDto[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (mockMode || !isLoggedIn || !tokenStore.get()) {
      setApiItems(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void api
      .listContinueWatching()
      .then((items) => {
        if (!cancelled) setApiItems(items);
      })
      .catch(() => {
        if (!cancelled) {
          setApiItems([]);
          setError('Unable to load Continue Watching.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoggedIn, mockMode, reload]);

  if (!mockMode && (!isLoggedIn || !tokenStore.get())) return null;
  if (!mockMode && loading) {
    return (
      <section className="container mx-auto px-4 py-4 sm:px-6 lg:px-8" aria-label={t.sections.continueWatching}>
        <Skeleton className="mb-3 h-6 w-48" />
        <div className="flex gap-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="aspect-video w-[200px] shrink-0 md:w-[280px]" />
          ))}
        </div>
      </section>
    );
  }
  if (!mockMode && error) {
    return (
      <section className="container mx-auto px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span role="alert">{error}</span>
          <Button variant="outline" size="sm" onClick={() => setReload((value) => value + 1)}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  const items = mockMode ? watchHistory.filter((item) => item.progress < 100) : apiItems ?? [];
  if (!items.length) return null;

  return (
    <ContentShelf title={t.sections.continueWatching}>
      {items.map((item) => (
        <MediaCard
          key={item.id}
          variant="landscape"
          size="sm"
          title={item.title}
          imageUrl={'poster_url' in item ? item.poster_url : item.poster}
          progress={
            Math.min(100, Math.max(0, 'progress_percent' in item ? item.progress_percent : item.progress))
          }
          runtime={'subtitle' in item ? item.subtitle || undefined : item.episode || undefined}
          playable={
            'media_asset_id' in item
              ? Boolean(item.available && item.player_path)
              : true
          }
          onActivate={() => {
            if ('media_asset_id' in item) {
              if (item.available && item.player_path) navigate(item.player_path);
            } else {
              navigate(item.type === 'series' ? `/series/${item.contentId}` : `/player/movie/${item.contentId}`);
            }
          }}
        />
      ))}
    </ContentShelf>
  );
}

export default function HomePage() {
  const { t } = useLang();
  const [data, setData] = useState<HomeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchHomeCatalog();
      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to load catalog'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <HomeLoading />;
  if (error) return <HomeError message={error} onRetry={load} />;
  if (!data) return <HomeError message="No catalog data" onRetry={load} />;

  const dramaMovies = data.popular.filter((m) => m.genres.includes('Drama')).slice(0, 12);
  const topRated = [...data.popular].sort((a, b) => b.rating - a.rating).slice(0, 12);
  const newReleases = [...data.recentlyAdded].slice(0, 12);
  const animationFamily = data.familyMovies.slice(0, 12);

  return (
    <div className="pb-8">
      <HeroCarousel featured={data.featured} />
      <div className="relative z-10 -mt-10 space-y-1 md:-mt-14">
        <ContinueWatchingRow />
        <ContentRow title={t.sections.trending} items={data.trending} />
        <ContentRow title={t.sections.recentlyAdded} items={newReleases} />
        <ContentRow title="Top Rated" items={topRated} />
        <ContentRow title={t.sections.popularMovies} items={data.popular} />
        <ContentRow title={t.sections.popularSeries} items={data.popularSeries} type="series" />
        <ContentRow title={t.sections.action} items={data.actionMovies} />
        <ContentRow title="Drama" items={dramaMovies} />
        <ContentRow title={t.sections.comedy} items={data.comedyMovies} />
        <ContentRow title="Animation & Family" items={animationFamily} />
        <ContentRow title={t.sections.afghanMovies} items={data.afghanMovies} />
        <ContentRow title={t.sections.persianDubbed} items={data.persianDubbed} />
        <ContentRow title={t.sections.pashtoDubbed} items={data.pashtoDubbed} />
      </div>
    </div>
  );
}
