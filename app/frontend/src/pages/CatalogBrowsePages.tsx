import { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useLang } from '@/components/CustomerLayout';
import {
  fetchGenres,
  fetchMovies,
  fetchSeries,
  type CatalogMovie,
  type CatalogSeries,
} from '@/lib/catalogData';
import { ApiError } from '@/lib/api';
import { catalogAvailabilityBadges, itemIsDubbed, itemIsSubtitled } from '@/lib/catalogAvailability';
import { canPlayFullMovie, hasDemoClip } from '@/lib/catalogPresentation';
import { MediaCard } from '@/design-system';

function PageLoading() {
  return (
    <div className="container mx-auto space-y-4 px-4 pt-6" data-testid="browse-loading">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="aspect-[2/3] w-full" />
        ))}
      </div>
    </div>
  );
}

function PageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3" data-testid="browse-error">
      <p className="text-muted-foreground">{message}</p>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}

function CatalogGrid({
  movies,
  series,
  moviesLabel,
  seriesLabel,
  emptyLabel,
  availabilityLabels,
}: {
  movies: CatalogMovie[];
  series: CatalogSeries[];
  moviesLabel: string;
  seriesLabel: string;
  emptyLabel: string;
  availabilityLabels: { dubbed: string; subtitled: string; multiAudio: string };
}) {
  const navigate = useNavigate();
  if (movies.length === 0 && series.length === 0) {
    return (
      <div className="py-16 text-center text-muted-foreground" data-testid="catalog-empty">
        {emptyLabel}
      </div>
    );
  }
  return (
    <div className="space-y-10">
      {movies.length > 0 ? (
        <section aria-labelledby="catalog-movies-heading">
          <h2 id="catalog-movies-heading" className="mb-4 text-lg font-semibold text-foreground">
            {moviesLabel}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {movies.map((movie) => {
              const { badges, overflow } = catalogAvailabilityBadges(movie, availabilityLabels);
              return (
                <MediaCard
                  key={`m-${movie.id}`}
                  className="!w-full max-w-none"
                  title={movie.title}
                  imageUrl={movie.poster}
                  year={movie.year}
                  rating={movie.rating}
                  runtime={movie.duration ? `${movie.duration} min` : undefined}
                  quality={movie.qualities?.[0] || undefined}
                  availabilityBadges={badges}
                  availabilityOverflow={overflow}
                  showDemo={hasDemoClip(movie)}
                  playable={canPlayFullMovie(movie) || hasDemoClip(movie)}
                  onActivate={() => navigate(`/movie/${movie.id}`)}
                />
              );
            })}
          </div>
        </section>
      ) : null}
      {series.length > 0 ? (
        <section aria-labelledby="catalog-series-heading">
          <h2 id="catalog-series-heading" className="mb-4 text-lg font-semibold text-foreground">
            {seriesLabel}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {series.map((show) => {
              const { badges, overflow } = catalogAvailabilityBadges(show, availabilityLabels);
              return (
                <MediaCard
                  key={`s-${show.id}`}
                  className="!w-full max-w-none"
                  title={show.title}
                  imageUrl={show.poster}
                  year={show.year}
                  rating={show.rating}
                  availabilityBadges={badges}
                  availabilityOverflow={overflow}
                  showDemo={hasDemoClip(show)}
                  playable={hasDemoClip(show)}
                  onActivate={() => navigate(`/series/${show.id}`)}
                />
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function releaseSortKey(item: { publishedAt?: string | null; createdAt?: string | null; id: number }): number {
  const raw = item.publishedAt || item.createdAt;
  if (raw) {
    const ms = Date.parse(raw);
    if (!Number.isNaN(ms)) return ms;
  }
  return item.id;
}

function sortNewestPublished<T extends { publishedAt?: string | null; createdAt?: string | null; id: number; year?: number }>(
  items: T[]
): T[] {
  return [...items].sort((a, b) => {
    const kb = releaseSortKey(b);
    const ka = releaseSortKey(a);
    if (kb !== ka) return kb - ka;
    const yb = b.year ?? 0;
    const ya = a.year ?? 0;
    if (yb !== ya) return yb - ya;
    return b.id - a.id;
  });
}

export function GenresBrowsePage() {
  const { t } = useLang();
  const [genres, setGenres] = useState<{ name: string; slug?: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Only genres backed by published catalog items (public list endpoints are published-only).
      const [catalogGenres, moviePage, seriesPage] = await Promise.all([
        fetchGenres(),
        fetchMovies({ page_size: 100, sort: 'newest' }),
        fetchSeries({ page_size: 100, sort: 'newest' }),
      ]);
      const counts = new Map<string, number>();
      for (const movie of moviePage.items) {
        for (const name of movie.genres || []) {
          counts.set(name, (counts.get(name) || 0) + 1);
        }
      }
      for (const show of seriesPage.items) {
        for (const name of show.genres || []) {
          counts.set(name, (counts.get(name) || 0) + 1);
        }
      }
      const byName = new Map(catalogGenres.map((g) => [g.name, g]));
      const next = [...counts.entries()]
        .filter(([, count]) => count > 0)
        .map(([name, count]) => ({
          name,
          slug: byName.get(name)?.slug || name.toLowerCase().replace(/\s+/g, '-'),
          count,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
      setGenres(next);
    } catch (err) {
      setGenres([]);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load genres');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen" data-testid="genres-browse-page">
      <div className="container mx-auto px-4 pb-8 pt-6 sm:px-6 lg:px-8">
        <h1 className="font-serif text-2xl font-bold text-foreground md:text-3xl">{t.pages.genresTitle}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t.pages.genresSubtitle}</p>
        {loading ? (
          <PageLoading />
        ) : error ? (
          <PageError message={error} onRetry={load} />
        ) : genres.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground" data-testid="catalog-empty">
            {t.pages.emptyCatalog}
          </div>
        ) : (
          <ul className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {genres.map((genre) => (
              <li key={genre.slug || genre.name}>
                <Link
                  to={`/movies?genre=${encodeURIComponent(genre.name)}`}
                  data-testid={`genre-card-${genre.slug || genre.name}`}
                  data-count={genre.count}
                  className="flex min-h-[4.5rem] flex-col items-center justify-center gap-1 rounded-lg border border-border bg-card px-3 py-4 text-center transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="text-sm font-medium text-foreground">{genre.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.pages.genreCount.replace('{count}', String(genre.count))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

type ShelfMode = 'dubbed' | 'subtitled' | 'new';

export function CatalogShelfPage({ mode }: { mode: ShelfMode }) {
  const { t } = useLang();
  const [movies, setMovies] = useState<CatalogMovie[]>([]);
  const [series, setSeries] = useState<CatalogSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const title =
    mode === 'dubbed' ? t.pages.dubbedTitle : mode === 'subtitled' ? t.pages.subtitledTitle : t.pages.newReleasesTitle;
  const subtitle =
    mode === 'dubbed'
      ? t.pages.dubbedSubtitle
      : mode === 'subtitled'
        ? t.pages.subtitledSubtitle
        : t.pages.newReleasesSubtitle;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Published-only catalog. Dubbed/Subtitled use server semantic filters.
      const movieParams =
        mode === 'dubbed'
          ? { sort: 'newest' as const, page_size: 100, has_dubbed: true }
          : mode === 'subtitled'
            ? { sort: 'newest' as const, page_size: 100, has_subtitles: true }
            : { sort: 'newest' as const, page_size: 100 };
      const seriesParams = { ...movieParams };
      const [moviePage, seriesPage] = await Promise.all([
        fetchMovies(movieParams),
        fetchSeries(seriesParams),
      ]);
      let nextMovies = moviePage.items;
      let nextSeries = seriesPage.items;
      if (mode === 'dubbed') {
        // Client-side safety net for older API responses without structured fields.
        nextMovies = nextMovies.filter((m) => itemIsDubbed(m));
        nextSeries = nextSeries.filter((s) => itemIsDubbed(s));
      } else if (mode === 'subtitled') {
        nextMovies = nextMovies.filter((m) => itemIsSubtitled(m));
        nextSeries = nextSeries.filter((s) => itemIsSubtitled(s));
      } else {
        nextMovies = sortNewestPublished(nextMovies).slice(0, 24);
        nextSeries = sortNewestPublished(nextSeries).slice(0, 24);
      }
      setMovies(nextMovies);
      setSeries(nextSeries);
    } catch (err) {
      setMovies([]);
      setSeries([]);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load catalog');
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen" data-testid={`catalog-shelf-${mode}`}>
      <div className="container mx-auto px-4 pb-8 pt-6 sm:px-6 lg:px-8">
        <h1 className="font-serif text-2xl font-bold text-foreground md:text-3xl">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
        <div className="mt-8">
          {loading ? (
            <PageLoading />
          ) : error ? (
            <PageError message={error} onRetry={load} />
          ) : (
            <CatalogGrid
              movies={movies}
              series={series}
              moviesLabel={t.pages.moviesSection}
              seriesLabel={t.pages.seriesSection}
              emptyLabel={t.pages.emptyCatalog}
              availabilityLabels={{
                dubbed: t.nav.dubbed,
                subtitled: t.nav.subtitled,
                multiAudio: 'Multi Audio',
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export function DubbedPage() {
  return <CatalogShelfPage mode="dubbed" />;
}

export function SubtitledPage() {
  return <CatalogShelfPage mode="subtitled" />;
}

export function NewReleasesPage() {
  return <CatalogShelfPage mode="new" />;
}

/** Compatibility alias used by some external links / QA checklists. */
export function KidsRedirect() {
  return <Navigate to="/children" replace />;
}
