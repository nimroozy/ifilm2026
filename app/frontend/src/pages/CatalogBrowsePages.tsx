import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
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
}: {
  movies: CatalogMovie[];
  series: CatalogSeries[];
  moviesLabel: string;
  seriesLabel: string;
  emptyLabel: string;
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
            {movies.map((movie) => (
              <MediaCard
                key={`m-${movie.id}`}
                className="!w-full max-w-none"
                title={movie.title}
                imageUrl={movie.poster}
                year={movie.year}
                rating={movie.rating}
                runtime={movie.duration ? `${movie.duration} min` : undefined}
                quality={movie.qualities?.[0] || undefined}
                showDemo={hasDemoClip(movie)}
                playable={canPlayFullMovie(movie) || hasDemoClip(movie)}
                onActivate={() => navigate(`/movie/${movie.id}`)}
              />
            ))}
          </div>
        </section>
      ) : null}
      {series.length > 0 ? (
        <section aria-labelledby="catalog-series-heading">
          <h2 id="catalog-series-heading" className="mb-4 text-lg font-semibold text-foreground">
            {seriesLabel}
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {series.map((show) => (
              <MediaCard
                key={`s-${show.id}`}
                className="!w-full max-w-none"
                title={show.title}
                imageUrl={show.poster}
                year={show.year}
                rating={show.rating}
                showDemo={hasDemoClip(show)}
                playable={hasDemoClip(show)}
                onActivate={() => navigate(`/series/${show.id}`)}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function hasTracks(list: string[] | undefined): boolean {
  return Array.isArray(list) && list.length > 0;
}

export function GenresBrowsePage() {
  const { t } = useLang();
  const [genres, setGenres] = useState<{ id?: number; name: string; slug?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchGenres();
      setGenres(rows);
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
          <div className="py-16 text-center text-muted-foreground">{t.pages.emptyCatalog}</div>
        ) : (
          <ul className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {genres.map((genre) => (
              <li key={genre.slug || genre.name}>
                <Link
                  to={`/movies?genre=${encodeURIComponent(genre.name)}`}
                  data-testid={`genre-card-${genre.slug || genre.name}`}
                  className="flex min-h-[4.5rem] items-center justify-center rounded-lg border border-border bg-card px-3 py-4 text-center text-sm font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="sr-only">{t.pages.browseGenre.replace('{genre}', genre.name)} — </span>
                  {genre.name}
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
      const [moviePage, seriesPage] = await Promise.all([
        fetchMovies({ sort: 'newest', page_size: 100 }),
        fetchSeries({ sort: 'newest', page_size: 100 }),
      ]);
      let nextMovies = moviePage.items;
      let nextSeries = seriesPage.items;
      if (mode === 'dubbed') {
        nextMovies = nextMovies.filter((m) => hasTracks(m.dubbed));
        nextSeries = nextSeries.filter((s) => hasTracks(s.dubbed));
      } else if (mode === 'subtitled') {
        nextMovies = nextMovies.filter((m) => hasTracks(m.subtitles));
        nextSeries = nextSeries.filter((s) => hasTracks(s.subtitles));
      } else {
        nextMovies = nextMovies.slice(0, 24);
        nextSeries = nextSeries.slice(0, 24);
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
