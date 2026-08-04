import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Info, Star, Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth, useLang } from '@/components/CustomerLayout';
import { watchHistory } from '@/data/mockData';
import { fetchHomeCatalog, type CatalogMovie, type CatalogSeries } from '@/lib/catalogData';
import { api, ApiError, tokenStore, type WatchProgressDto } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import { canPlayFullMovie, fullMovieUnavailableLabel, hasDemoClip } from '@/lib/catalogPresentation';
import { trailerEmbedUrl } from '@/lib/trailers';

type HomeData = Awaited<ReturnType<typeof fetchHomeCatalog>>;

function HomeLoading() {
  return (
    <div className="space-y-6 pt-8" data-testid="home-loading">
      <Skeleton className="h-[50vh] w-full rounded-none" />
      <div className="container mx-auto px-4 space-y-4">
        <Skeleton className="h-6 w-48" />
        <div className="flex gap-3 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[210px] w-[140px] shrink-0" />
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

function HeroBanner({ featured }: { featured: CatalogMovie[] }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [current, setCurrent] = useState(0);
  const movie = featured[current] || featured[0];

  if (!movie) {
    return (
      <section className="relative h-[40vh] w-full overflow-hidden -mt-16 md:-mt-20 bg-muted flex items-center justify-center">
        <p className="text-muted-foreground">No featured titles yet.</p>
      </section>
    );
  }

  const playable = canPlayFullMovie(movie);
  const demo = hasDemoClip(movie);
  const trailerHref = trailerEmbedUrl(movie) || null;

  return (
    <section
      className="relative h-[70vh] md:h-[85vh] w-full overflow-hidden -mt-16 md:-mt-20"
      aria-label="Featured title"
    >
      <div className="absolute inset-0 bg-[hsl(222,28%,6%)]">
        <img
          src={movie.backdrop}
          alt=""
          className="h-full w-full object-cover opacity-55"
          loading="eager"
          decoding="async"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-background/15" />
        <div className="absolute inset-0 bg-gradient-to-r from-background/95 via-background/45 to-transparent" />
      </div>

      <div className="relative flex h-full items-end pb-16 md:pb-24">
        <div className="container mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="space-y-4 animate-fade-in">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">iFilm</p>
            <h1 className="max-w-[18ch] font-display text-3xl font-bold leading-tight text-foreground drop-shadow-lg md:text-5xl lg:text-6xl">
              {movie.title}
            </h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {movie.ageRating ? (
                <Badge variant="outline" className="border-primary/50 text-primary">
                  {movie.ageRating}
                </Badge>
              ) : null}
              <span>{movie.year}</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {movie.duration} {t.common.min}
              </span>
              <span className="flex items-center gap-1">
                <Star className="h-3.5 w-3.5 fill-primary text-primary" />
                {movie.rating}
              </span>
            </div>
            <p className="max-w-2xl text-sm text-foreground/85 md:text-base line-clamp-3 md:line-clamp-4">
              {movie.description}
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-2">
              {playable || demo ? (
                <Button
                  size="lg"
                  onClick={() => navigate(`/player/movie/${movie.id}`)}
                  className="gap-2 font-semibold shadow-lg"
                  aria-label={demo ? `Play demo clip for ${movie.title}` : `Play ${movie.title}`}
                >
                  <Play className="h-5 w-5 fill-current" />
                  {demo && !playable ? 'Play Demo Clip' : t.hero.play}
                </Button>
              ) : (
                <Badge variant="secondary" className="px-3 py-2 text-sm">
                  {fullMovieUnavailableLabel()}
                </Badge>
              )}
              <Button
                size="lg"
                variant="secondary"
                onClick={() => navigate(`/movie/${movie.id}`)}
                className="gap-2 shadow-md"
              >
                <Info className="h-5 w-5" />
                {t.hero.moreInfo}
              </Button>
              {trailerHref ? (
                <Button size="lg" variant="outline" asChild className="gap-2 bg-background/40 backdrop-blur">
                  <a href={trailerHref} target="_blank" rel="noopener noreferrer">
                    Trailer
                  </a>
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 gap-2" role="tablist" aria-label="Featured titles">
        {featured.map((item, i) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={i === current}
            aria-label={`Show ${item.title}`}
            onClick={() => setCurrent(i)}
            className={`h-2 rounded-full transition-all focus-visible:ring-2 focus-visible:ring-ring ${
              i === current ? 'w-6 bg-primary' : 'w-2 bg-foreground/30 hover:bg-foreground/50'
            }`}
          />
        ))}
      </div>
    </section>
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const scroll = (dir: 'left' | 'right') => {
    if (scrollRef.current) {
      const amount = dir === 'left' ? -400 : 400;
      scrollRef.current.scrollBy({ left: amount, behavior: 'smooth' });
    }
  };

  if (!items.length) return null;

  return (
    <section className="py-4 md:py-6">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-lg md:text-xl font-display font-bold text-foreground mb-3">{title}</h2>
      </div>
      <div className="relative group">
        <button
          onClick={() => scroll('left')}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-background/80 backdrop-blur-sm p-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hidden md:flex"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto hide-scrollbar px-4 sm:px-6 lg:px-8 scroll-smooth"
        >
          {items.map((item) => {
            const contentType = type === 'series' || item.type === 'series' ? 'Series' : 'Movie';
            return (
            <div
              key={`${contentType}-${item.id}`}
              role="link"
              tabIndex={0}
              onClick={() => navigate(type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`);
                }
              }}
              className="flex-shrink-0 w-[140px] md:w-[180px] cursor-pointer group/card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
            >
              <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                <img
                  src={item.poster}
                  alt={item.title}
                  loading="lazy"
                  decoding="async"
                  sizes="(max-width: 768px) 140px, 180px"
                  className="w-full h-full object-cover transition-transform duration-normal group-hover/card:scale-105"
                />
                <div className="absolute top-2 left-2 right-2 flex flex-wrap justify-between gap-1">
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0.5">
                    {contentType}
                  </Badge>
                  {hasDemoClip(item) && (
                    <Badge className="bg-emerald-600/90 text-white text-[10px] px-1.5 py-0.5" data-testid="demo-clip-badge">
                      Demo Clip
                    </Badge>
                  )}
                  {item.type === 'series' && 'newEpisode' in item && item.newEpisode && (
                    <Badge className="bg-destructive text-destructive-foreground text-[10px] px-1.5 py-0.5">
                      NEW
                    </Badge>
                  )}
                </div>
              </div>
              <h3 className="text-xs md:text-sm font-medium text-foreground truncate">{item.title}</h3>
              <div className="flex items-center gap-1.5 text-[10px] md:text-xs text-muted-foreground">
                <span>{item.year}</span>
                <span>•</span>
                <span className="flex items-center gap-0.5">
                  <Star className="h-3 w-3 text-primary fill-primary" />
                  {item.rating}
                </span>
              </div>
            </div>
            );
          })}
        </div>
        <button
          onClick={() => scroll('right')}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-background/80 backdrop-blur-sm p-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hidden md:flex"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </section>
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
    <section className="py-4 md:py-6">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-lg md:text-xl font-serif font-bold text-foreground mb-3">
          {t.sections.continueWatching}
        </h2>
      </div>
      <div className="flex gap-3 overflow-x-auto hide-scrollbar px-4 sm:px-6 lg:px-8">
        {items.map((item) => (
          <div
            key={item.id}
            role="link"
            tabIndex={0}
            onClick={() => {
              if ('media_asset_id' in item) {
                if (item.available && item.player_path) navigate(item.player_path);
              } else {
                navigate(item.type === 'series' ? `/series/${item.contentId}` : `/player/movie/${item.contentId}`);
              }
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                (event.currentTarget as HTMLDivElement).click();
              }
            }}
            className="flex-shrink-0 w-[200px] md:w-[280px] cursor-pointer group/card"
          >
            <div className="relative aspect-video rounded-lg overflow-hidden bg-muted mb-2">
              {('poster_url' in item ? item.poster_url : item.poster) ? (
                <img
                  src={'poster_url' in item ? item.poster_url : item.poster}
                  alt={item.title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="flex h-full items-center justify-center px-3 text-center text-xs text-muted-foreground">
                  {item.title}
                </div>
              )}
              <div className="absolute inset-0 bg-black/0 group-hover/card:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover/card:opacity-100">
                <Play className="h-10 w-10 text-white fill-white" />
              </div>
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted/50">
                <div
                  className="h-full bg-primary"
                  style={{
                    width: `${Math.min(100, Math.max(0, 'progress_percent' in item ? item.progress_percent : item.progress))}%`,
                  }}
                />
              </div>
            </div>
            <h3 className="text-xs md:text-sm font-medium text-foreground truncate">{item.title}</h3>
            {('subtitle' in item ? item.subtitle : item.episode) && (
              <p className="text-[10px] text-muted-foreground">
                {'subtitle' in item ? item.subtitle : item.episode}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
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

  return (
    <div>
      <HeroBanner featured={data.featured} />
      <div className="space-y-2 -mt-8 relative z-10">
        <ContinueWatchingRow />
        <ContentRow title={t.sections.trending} items={data.trending} />
        <ContentRow title={t.sections.popularSeries} items={data.popularSeries} type="series" />
        <ContentRow title={t.sections.recentlyAdded} items={data.recentlyAdded} />
        <ContentRow title={t.sections.popularMovies} items={data.popular} />
        <ContentRow title={t.sections.afghanMovies} items={data.afghanMovies} />
        <ContentRow title={t.sections.persianDubbed} items={data.persianDubbed} />
        <ContentRow title={t.sections.pashtoDubbed} items={data.pashtoDubbed} />
        <ContentRow title={t.sections.action} items={data.actionMovies} />
        <ContentRow title={t.sections.comedy} items={data.comedyMovies} />
        <ContentRow title={t.sections.family} items={data.familyMovies} />
      </div>
    </div>
  );
}
