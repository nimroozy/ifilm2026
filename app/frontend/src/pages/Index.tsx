import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth, useLang } from '@/components/CustomerLayout';
import { ContentShelf, MediaCard, mediaSizes } from '@/design-system';
import { HeroCarousel } from '@/components/HeroCarousel';
import {
  fetchHomeCatalog,
  fetchMeHomeCatalog,
  mapCollectionItems,
  type CatalogCollection,
  type CatalogMovie,
  type CatalogSeries,
} from '@/lib/catalogData';
import {
  api,
  ApiError,
  tokenStore,
  type HomeRecommendationsDto,
  type RecommendationItemDto,
  type WatchlistItemDto,
  type WatchProgressDto,
} from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import { hasDemoClip, canPlayFullMovie } from '@/lib/catalogPresentation';
import { catalogAvailabilityBadges } from '@/lib/catalogAvailability';
import {
  localizeRecommendationExplanation,
  localizeRecommendationShelfTitle,
} from '@/lib/recommendationI18n';
import { sizedArtworkUrl } from '@/lib/imageUrls';
import { X } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

type HomeCatalog = Awaited<ReturnType<typeof fetchHomeCatalog>>;

function HomeLoading() {
  return (
    <div className="space-y-8" data-testid="home-loading" aria-busy="true">
      <Skeleton
        className="ifilm-skeleton h-[min(62vh,640px)] w-full rounded-none md:h-[min(78vh,820px)]"
        data-testid="home-hero-skeleton"
      />
      <div className="space-y-4 px-4 sm:px-6 lg:px-8" data-testid="home-shelf-skeleton">
        <Skeleton className="ifilm-skeleton h-7 w-56" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={cn('shrink-0', mediaSizes.posterMd)}>
              <Skeleton className="ifilm-skeleton aspect-[2/3] w-full rounded-xl" />
              <Skeleton className="ifilm-skeleton mt-2 h-4 w-3/4" />
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-4 px-4 sm:px-6 lg:px-8" aria-hidden>
        <Skeleton className="ifilm-skeleton h-7 w-40" />
        <div className="flex gap-4 overflow-hidden">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className={cn('shrink-0', mediaSizes.posterMd)}>
              <Skeleton className="ifilm-skeleton aspect-[2/3] w-full rounded-xl" />
            </div>
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
  eagerCount = 0,
  showAvailability = false,
}: {
  title: string;
  items: (CatalogMovie | CatalogSeries)[];
  type?: 'movie' | 'series';
  /** First N cards load eagerly for LCP on above-the-fold shelves. */
  eagerCount?: number;
  /** Sparse human-language availability badges (never FA/PS codes). */
  showAvailability?: boolean;
}) {
  const navigate = useNavigate();
  const { t } = useLang();
  const { isLoggedIn } = useAuth();

  if (!items.length) return null;

  const availLabels = {
    dubbed: t.nav.dubbed,
    subtitled: t.nav.subtitled,
    multiAudio: 'Multi Audio',
    persianDubbed: t.sections.persianDubbed,
    pashtoDubbed: t.sections.pashtoDubbed,
  };

  return (
    <ContentShelf title={title}>
      {items.map((item, index) => {
        const contentType = type === 'series' || item.type === 'series' ? 'Series' : 'Movie';
        const qualities = 'qualities' in item ? item.qualities : undefined;
        const topQuality = Array.isArray(qualities) && qualities.length ? String(qualities[0]) : undefined;
        const runtime =
          'duration' in item && typeof item.duration === 'number' && item.duration > 0
            ? `${item.duration} min`
            : undefined;
        const detailPath =
          type === 'series' || item.type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`;
        const avail = showAvailability
          ? catalogAvailabilityBadges(item, availLabels)
          : { badges: [], overflow: 0 };
        // Prefer a single dubbed badge on home shelves to avoid clutter.
        const badges = avail.badges.filter((b) => b.key.startsWith('dub-')).slice(0, 1);
        return (
          <MediaCard
            key={`${contentType}-${item.id}`}
            title={item.title}
            imageUrl={sizedArtworkUrl(item.poster, 'poster', 'card')}
            year={item.year}
            rating={item.rating}
            runtime={runtime}
            genres={'genres' in item ? item.genres : undefined}
            quality={topQuality}
            showDemo={hasDemoClip(item)}
            playable={canPlayFullMovie(item) || hasDemoClip(item)}
            priority={index < eagerCount}
            availabilityBadges={badges}
            badge={
              badges.length
                ? undefined
                : item.type === 'series' && 'newEpisode' in item && item.newEpisode
                  ? 'NEW'
                  : contentType === 'Series'
                    ? 'Series'
                    : undefined
            }
            onActivate={() => navigate(detailPath)}
            onPlay={() => {
              if (canPlayFullMovie(item) || hasDemoClip(item)) {
                navigate(
                  contentType === 'Series' ? detailPath : `/player/movie/${item.id}`,
                  contentType === 'Series' ? undefined : { state: { autoplay: true } }
                );
              } else {
                navigate(detailPath);
              }
            }}
            onMyList={() => {
              if (!isLoggedIn || !tokenStore.get()) {
                navigate('/login');
                return;
              }
              navigate('/watchlist');
            }}
          />
        );
      })}
    </ContentShelf>
  );
}

function ContinueWatchingRow({
  preloaded,
}: {
  preloaded?: WatchProgressDto[] | null;
}) {
  const { t } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const mockMode = isMockMode();
  const [apiItems, setApiItems] = useState<WatchProgressDto[] | null>(preloaded ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [mockItems, setMockItems] = useState<
    Array<{
      id: number;
      contentId: number;
      title: string;
      type: string;
      progress: number;
      duration: number;
      poster: string;
      episode?: string;
    }>
  >([]);

  useEffect(() => {
    if (preloaded !== undefined) {
      setApiItems(preloaded);
      setLoading(false);
      setError(null);
      return;
    }
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
  }, [isLoggedIn, mockMode, reload, preloaded]);

  useEffect(() => {
    if (!mockMode) {
      setMockItems([]);
      return;
    }
    let cancelled = false;
    void import('@/data/mockData').then((mod) => {
      if (!cancelled) {
        setMockItems(mod.watchHistory.filter((item) => item.progress < 100));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [mockMode]);

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

  const items = mockMode ? mockItems : apiItems ?? [];
  if (!items.length) return null;

  const dismiss = async (assetId: string, title: string) => {
    try {
      await api.dismissContinueWatching(assetId);
      setApiItems((prev) => (prev ?? []).filter((row) => row.media_asset_id !== assetId));
      toast({ title: t.sections.continueWatching, description: `Removed “${title}”` });
    } catch (err) {
      toast({
        title: t.sections.continueWatching,
        description: err instanceof ApiError ? err.message : 'Unable to dismiss item',
        variant: 'destructive',
      });
    }
  };

  return (
    <ContentShelf title={t.sections.continueWatching} testId="home-continue-watching">
      {items.map((item) => {
        const episodeLabel =
          'season_number' in item &&
          item.season_number != null &&
          item.episode_number != null
            ? `S${item.season_number} · E${item.episode_number}`
            : 'subtitle' in item
              ? item.subtitle || undefined
              : 'episode' in item
                ? item.episode || undefined
                : undefined;
        return (
        <div key={item.id} className="relative snap-start">
          <MediaCard
            variant="landscape"
            size="sm"
            title={item.title}
            imageUrl={sizedArtworkUrl(
              'poster_url' in item ? item.poster_url : item.poster,
              'backdrop',
              'card'
            )}
            progress={
              Math.min(100, Math.max(0, 'progress_percent' in item ? item.progress_percent : item.progress))
            }
            status={episodeLabel}
            playable={
              'media_asset_id' in item
                ? Boolean(item.available && item.player_path)
                : true
            }
            onActivate={() => {
              if ('media_asset_id' in item) {
                if (item.available && item.player_path) {
                  navigate(item.player_path, { state: { autoplay: true } });
                }
              } else {
                navigate(
                  item.type === 'series' ? `/series/${item.contentId}` : `/player/movie/${item.contentId}`,
                  item.type === 'series' ? undefined : { state: { autoplay: true } }
                );
              }
            }}
            onPlay={() => {
              if ('media_asset_id' in item) {
                if (item.available && item.player_path) {
                  navigate(item.player_path, { state: { autoplay: true } });
                }
              } else {
                navigate(
                  item.type === 'series' ? `/series/${item.contentId}` : `/player/movie/${item.contentId}`,
                  item.type === 'series' ? undefined : { state: { autoplay: true } }
                );
              }
            }}
          />
          {'media_asset_id' in item ? (
            <Button
              size="icon"
              variant="secondary"
              className="absolute end-2 top-2 z-10 h-8 w-8 rounded-full opacity-90"
              aria-label={`Remove ${item.title} from Continue Watching`}
              data-testid={`cw-dismiss-${item.media_asset_id}`}
              onClick={(event) => {
                event.stopPropagation();
                void dismiss(item.media_asset_id, item.title);
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
        );
      })}
    </ContentShelf>
  );
}

function RecommendationShelfRow({
  title,
  items,
  testId,
  eagerCount = 0,
}: {
  title: string;
  items: RecommendationItemDto[];
  testId?: string;
  eagerCount?: number;
}) {
  const navigate = useNavigate();
  const { lang } = useLang();
  if (!items.length) return null;
  return (
    <ContentShelf title={title} testId={testId}>
      {items.map((item, index) => (
        <MediaCard
          key={`${item.content_type}-${item.id}`}
          title={item.title}
          imageUrl={sizedArtworkUrl(item.poster_url, 'poster', 'card')}
          year={item.release_year ?? undefined}
          rating={item.imdb_rating ?? undefined}
          playable={Boolean(item.playable)}
          status={localizeRecommendationExplanation(item.explanation, lang)}
          badge={item.content_type === 'series' ? 'Series' : undefined}
          priority={index < eagerCount}
          onActivate={() => navigate(item.detail_path)}
          data-testid={`rec-card-${item.id}`}
        />
      ))}
    </ContentShelf>
  );
}

function MyListHomeRow({ preloaded }: { preloaded?: WatchlistItemDto[] | null }) {
  const { t } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const mockMode = isMockMode();
  const [items, setItems] = useState<WatchlistItemDto[]>(preloaded ?? []);

  useEffect(() => {
    if (preloaded !== undefined) {
      setItems(preloaded ?? []);
      return;
    }
    if (mockMode || !isLoggedIn || !tokenStore.get()) {
      setItems([]);
      return;
    }
    let cancelled = false;
    api
      .listWatchlist({ page: 1, page_size: 20 })
      .then((page) => {
        if (!cancelled) setItems((page.items || []).filter((i) => i.available));
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoggedIn, mockMode, preloaded]);

  if (!items.length) return null;
  return (
    <ContentShelf title={t.sections.myList || t.nav.myList} testId="home-my-list">
      {items.map((item) => (
        <MediaCard
          key={`wl-${item.id}`}
          title={item.title}
          imageUrl={sizedArtworkUrl(item.poster_url, 'poster', 'card')}
          year={item.release_year ?? undefined}
          playable={Boolean(item.player_path)}
          badge={item.content_type === 'series' ? 'Series' : undefined}
          onActivate={() => navigate(item.detail_path)}
        />
      ))}
    </ContentShelf>
  );
}

function HomeRecommendationShelves({
  usedIds,
  preloaded,
  firstShelfOnly = false,
  eagerCount = 0,
}: {
  usedIds: Set<string>;
  preloaded?: HomeRecommendationsDto | null;
  /** When true, render only the first non-empty recommendation shelf (above-fold). */
  firstShelfOnly?: boolean;
  eagerCount?: number;
}) {
  const { isLoggedIn } = useAuth();
  const { t } = useLang();
  const [payload, setPayload] = useState<HomeRecommendationsDto | null>(preloaded ?? null);

  useEffect(() => {
    if (preloaded !== undefined) {
      setPayload(preloaded);
      return;
    }
    if (isMockMode()) {
      setPayload(null);
      return;
    }
    let cancelled = false;
    const fetcher =
      isLoggedIn && tokenStore.get() ? api.getMyHomeRecommendations() : api.getHomeRecommendations();
    fetcher
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoggedIn, preloaded]);

  if (!payload?.shelves?.length) return null;

  const rows: ReactNode[] = [];
  for (const shelf of payload.shelves) {
    if (shelf.shelf_type === 'editorial_collections') continue;
    const items = (shelf.items || []).filter((item) => {
      const key = `${item.content_type}:${item.id}`;
      if (usedIds.has(key)) return false;
      usedIds.add(key);
      return true;
    });
    if (!items.length) continue;
    rows.push(
      <RecommendationShelfRow
        key={`${shelf.shelf_type}-${shelf.title}`}
        title={localizeRecommendationShelfTitle(shelf, t.sections as Record<string, string>)}
        items={items}
        testId={`home-shelf-${shelf.shelf_type}`}
        eagerCount={rows.length === 0 ? eagerCount : 0}
      />
    );
    if (firstShelfOnly) break;
  }
  return <>{rows}</>;
}

export default function HomePage() {
  const { t, lang } = useLang();
  const { isLoggedIn } = useAuth();
  const [data, setData] = useState<HomeCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collections, setCollections] = useState<CatalogCollection[]>([]);
  const [continueWatching, setContinueWatching] = useState<WatchProgressDto[] | undefined>(undefined);
  const [watchlist, setWatchlist] = useState<WatchlistItemDto[] | undefined>(undefined);
  const [recommendations, setRecommendations] = useState<HomeRecommendationsDto | null | undefined>(
    undefined
  );
  /** Progressive shelves: hero + first rail first; rest after idle/paint. */
  const [showBelowFold, setShowBelowFold] = useState(false);
  const lastLoadKey = useRef<string>('');

  const load = useCallback(async (opts?: { force?: boolean }) => {
    // Prefer token over React auth flag so the first paint after login does not
    // fan out catalog/home + me/home.
    const hasToken = Boolean(tokenStore.get());
    const mode = !isMockMode() && (isLoggedIn || hasToken) ? 'me' : 'anon';
    const key = `${lang}:${mode}`;
    if (!opts?.force && lastLoadKey.current === key) return;
    lastLoadKey.current = key;

    setLoading(true);
    setError(null);
    setShowBelowFold(false);
    try {
      if (mode === 'me') {
        try {
          const me = await fetchMeHomeCatalog(lang);
          setData(me);
          setCollections(me.featuredCollections || []);
          setContinueWatching(me.continueWatching);
          setWatchlist(me.watchlist);
          setRecommendations(me.recommendations);
          return;
        } catch {
          // Fall back to public catalog + separate personalized calls.
        }
      }
      const result = await fetchHomeCatalog(lang);
      setData(result);
      // Aggregate already includes featured_collections (possibly empty) — do not
      // issue a second collections request when the home endpoint succeeded.
      setCollections(result.featuredCollections || []);
      setContinueWatching([]);
      setWatchlist([]);
      // Prefer recommendations embedded in catalog/home (single request).
      setRecommendations(result.recommendations ?? null);
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
  }, [lang, isLoggedIn]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (loading || !data || showBelowFold) return;
    const reveal = () => setShowBelowFold(true);
    const w = globalThis as typeof globalThis & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (typeof w.requestIdleCallback === 'function') {
      const id = w.requestIdleCallback(reveal, { timeout: 900 });
      return () => w.cancelIdleCallback?.(id);
    }
    const id = globalThis.setTimeout(reveal, 0);
    return () => globalThis.clearTimeout(id);
  }, [loading, data, showBelowFold]);

  if (loading) return <HomeLoading />;
  if (error) return <HomeError message={error} onRetry={() => void load({ force: true })} />;
  if (!data) return <HomeError message="No catalog data" onRetry={() => void load({ force: true })} />;

  const dramaMovies = data.popular.filter((m) => m.genres.includes('Drama')).slice(0, 12);
  const topRated = [...data.popular].sort((a, b) => b.rating - a.rating).slice(0, 12);
  const newReleases = [...data.recentlyAdded].slice(0, 12);
  const animationFamily = data.familyMovies.slice(0, 12);
  const collectionShelves = collections
    .map((collection) => ({ collection, items: mapCollectionItems(collection.items) }))
    .filter(({ items }) => items.length > 0);

  const usedIds = new Set<string>();
  const hasRecShelves = Boolean(recommendations?.shelves?.some((s) => s.shelf_type !== 'editorial_collections' && (s.items?.length ?? 0) > 0));
  const recHasNewReleases = Boolean(
    recommendations?.shelves?.some(
      (s) => s.shelf_type === 'new_releases' && (s.items?.length ?? 0) > 0
    )
  );

  return (
    <div className="pb-8">
      <HeroCarousel featured={data.featured} />
      <div className="relative z-10 -mt-10 space-y-1 md:-mt-14">
        <ContinueWatchingRow preloaded={continueWatching} />
        <MyListHomeRow preloaded={watchlist} />
        {hasRecShelves ? (
          <HomeRecommendationShelves
            usedIds={usedIds}
            preloaded={recommendations}
            firstShelfOnly
            eagerCount={4}
          />
        ) : (
          <ContentRow title={t.sections.recentlyAdded} items={newReleases} eagerCount={4} />
        )}
        <div className="px-4 sm:px-6 lg:px-8">
          <Button asChild variant="secondary" className="mt-2" data-testid="home-what-to-watch-cta">
            <Link to="/what-to-watch">{t.nav.whatToWatch}</Link>
          </Button>
        </div>
        {showBelowFold ? (
          <>
            {hasRecShelves ? (
              <HomeRecommendationShelves usedIds={usedIds} preloaded={recommendations} />
            ) : null}
            {collectionShelves.map(({ collection, items }) => (
              <ContentRow key={`collection-${collection.id}`} title={collection.title} items={items} />
            ))}
            {hasRecShelves && !recHasNewReleases ? (
              <ContentRow title={t.sections.recentlyAdded} items={newReleases} />
            ) : null}
            <ContentRow title={t.sections.popularMovies} items={data.popular} />
            <ContentRow title={t.sections.popularSeries} items={data.popularSeries} type="series" />
            <ContentRow title={t.sections.trending} items={data.trending} />
            <ContentRow title={t.sections.topRated || 'Top Rated'} items={topRated} />
            <ContentRow title={t.sections.action} items={data.actionMovies} />
            <ContentRow title={t.sections.drama} items={dramaMovies} />
            <ContentRow title={t.sections.comedy} items={data.comedyMovies} />
            <ContentRow title={t.sections.animationFamily} items={animationFamily} />
            <ContentRow title={t.sections.afghanMovies} items={data.afghanMovies} />
            <ContentRow
              title={t.sections.persianDubbed}
              items={data.persianDubbed}
              showAvailability
            />
            <ContentRow
              title={t.sections.pashtoDubbed}
              items={data.pashtoDubbed}
              showAvailability
            />
          </>
        ) : (
          <div className="space-y-4 px-4 py-6 sm:px-6 lg:px-8" data-testid="home-below-fold-pending" aria-hidden>
            <Skeleton className="h-6 w-40" />
            <div className="flex gap-4 overflow-hidden">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[200px] w-[140px] shrink-0 rounded-xl" />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
