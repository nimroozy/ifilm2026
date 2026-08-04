import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Play,
  Star,
  Clock,
  Plus,
  Grid,
  List,
  Search as SearchIcon,
  X,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useLang } from '@/components/CustomerLayout';
import {
  fetchGenres,
  fetchMovie,
  fetchMovies,
  fetchSearch,
  fetchSeries,
  fetchSeriesDetail,
  type CatalogMovie,
  type CatalogSeries,
} from '@/lib/catalogData';
import { ApiError } from '@/lib/api';
import { canPlayFullMovie, fullMovieUnavailableLabel, hasDemoClip, isDemoCatalogItem } from '@/lib/catalogPresentation';
import { trailerEmbedUrl } from '@/lib/trailers';
import { MediaCard } from '@/design-system';
import { MovieDetailView } from '@/components/MovieDetailView';

function PageLoading() {
  return (
    <div className="container mx-auto px-4 pt-6 space-y-4" data-testid="browse-loading">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="aspect-[2/3] w-full" />
        ))}
      </div>
    </div>
  );
}

function PageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="min-h-[40vh] flex flex-col items-center justify-center gap-3" data-testid="browse-error">
      <p className="text-muted-foreground">{message}</p>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}

function sortParam(sort: string): string {
  if (sort === 'rating') return 'rating_desc';
  if (sort === 'popular') return 'views_desc';
  if (sort === 'title') return 'title_asc';
  return 'newest';
}

function DemoClipBadge({ item }: { item: unknown }) {
  if (!hasDemoClip(item)) return null;
  return (
    <Badge className="bg-emerald-500 text-white text-[10px]" data-testid="demo-clip-badge">
      Demo Clip
    </Badge>
  );
}

const CHILDREN_GENRES = ['Family', 'Animation'] as const;

function mergeMoviesById(pages: Array<{ items: CatalogMovie[] }>): CatalogMovie[] {
  const byId = new Map<number, CatalogMovie>();
  for (const page of pages) {
    for (const movie of page.items) {
      byId.set(movie.id, movie);
    }
  }
  return [...byId.values()];
}

function sortMergedMovies(movies: CatalogMovie[], sort: string): CatalogMovie[] {
  const copy = [...movies];
  if (sort === 'rating') return copy.sort((a, b) => b.rating - a.rating);
  if (sort === 'popular') return copy.sort((a, b) => b.views - a.views);
  if (sort === 'title') return copy.sort((a, b) => a.title.localeCompare(b.title));
  // newest
  return copy.sort((a, b) => b.year - a.year || b.id - a.id);
}

// ============ MOVIES PAGE ============
export function MoviesPage({ audience = 'all' }: { audience?: 'all' | 'children' } = {}) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
  const [sort, setSort] = useState('newest');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [items, setItems] = useState<CatalogMovie[]>([]);
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isChildren = audience === 'children';

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (isChildren) {
        const selectedGenre = genre === 'all' ? null : genre;
        const genreFetches =
          selectedGenre && (CHILDREN_GENRES as readonly string[]).includes(selectedGenre)
            ? [
                fetchMovies({
                  q: search || undefined,
                  genre: selectedGenre,
                  sort: sortParam(sort),
                  page_size: 100,
                }),
              ]
            : CHILDREN_GENRES.map((childGenre) =>
                fetchMovies({
                  q: search || undefined,
                  genre: childGenre,
                  sort: sortParam(sort),
                  page_size: 100,
                })
              );
        const [genres, ...pages] = await Promise.all([fetchGenres(), ...genreFetches]);
        const available = new Set(genres.map((g) => g.name));
        setItems(sortMergedMovies(mergeMoviesById(pages), sort));
        setGenreOptions(CHILDREN_GENRES.filter((g) => available.has(g)));
      } else {
        const [page, genres] = await Promise.all([
          fetchMovies({
            q: search || undefined,
            genre: genre === 'all' ? undefined : genre,
            sort: sortParam(sort),
            page_size: 100,
          }),
          fetchGenres(),
        ]);
        setItems(page.items);
        setGenreOptions(genres.map((g) => g.name));
      }
    } catch (err) {
      setItems([]);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load movies');
    } finally {
      setLoading(false);
    }
  }, [search, genre, sort, isChildren]);

  useEffect(() => {
    const timer = window.setTimeout(load, 200);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <div className="min-h-screen" data-testid={isChildren ? 'children-page' : 'movies-page'}>
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">
          {isChildren ? t.nav.children : t.nav.movies}
        </h1>
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t.search.placeholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-card border-border"
            />
          </div>
          <Select value={genre} onValueChange={setGenre}>
            <SelectTrigger className="w-[140px] bg-card border-border">
              <SelectValue placeholder={t.common.filter} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t.common.all}</SelectItem>
              {genreOptions.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="w-[140px] bg-card border-border">
              <SelectValue placeholder={t.common.sort} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest</SelectItem>
              <SelectItem value="rating">Rating</SelectItem>
              <SelectItem value="popular">Popular</SelectItem>
              <SelectItem value="title">Title</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex gap-1">
            <Button variant={view === 'grid' ? 'default' : 'outline'} size="icon" onClick={() => setView('grid')}>
              <Grid className="h-4 w-4" />
            </Button>
            <Button variant={view === 'list' ? 'default' : 'outline'} size="icon" onClick={() => setView('list')}>
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {loading ? (
          <PageLoading />
        ) : error ? (
          <PageError message={error} onRetry={load} />
        ) : items.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p className="text-lg">{t.search.noResults}</p>
          </div>
        ) : view === 'grid' ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {items.map((movie) => (
              <MediaCard
                key={movie.id}
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
        ) : (
          <div className="space-y-3">
            {items.map((movie) => (
              <div
                key={movie.id}
                onClick={() => navigate(`/movie/${movie.id}`)}
                className="flex gap-4 p-3 rounded-lg bg-card hover:bg-card/80 cursor-pointer transition-colors"
              >
                <img src={movie.poster} alt={movie.title} className="w-16 h-24 rounded object-cover flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-foreground">{movie.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{movie.genres.join(', ')}</p>
                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                    <span>{movie.year}</span>
                    <span>{movie.duration} min</span>
                    <Star className="h-3 w-3 text-primary fill-primary" />
                    <span>{movie.rating}</span>
                  </div>
                  <div className="mt-2">
                    <DemoClipBadge item={movie} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Family / Animation catalog — distinct from the generic Movies browse page. */
export function ChildrenPage() {
  return <MoviesPage audience="children" />;
}

// ============ SERIES PAGE ============
export function SeriesPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
  const [items, setItems] = useState<CatalogSeries[]>([]);
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [page, genres] = await Promise.all([
        fetchSeries({
          q: search || undefined,
          genre: genre === 'all' ? undefined : genre,
          sort: 'views_desc',
          page_size: 100,
        }),
        fetchGenres(),
      ]);
      setItems(page.items);
      setGenreOptions(genres.map((g) => g.name));
    } catch (err) {
      setItems([]);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load series');
    } finally {
      setLoading(false);
    }
  }, [search, genre]);

  useEffect(() => {
    const timer = window.setTimeout(load, 200);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.nav.series}</h1>
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t.search.placeholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-card border-border"
            />
          </div>
          <Select value={genre} onValueChange={setGenre}>
            <SelectTrigger className="w-[140px] bg-card border-border">
              <SelectValue placeholder={t.common.filter} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t.common.all}</SelectItem>
              {genreOptions.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {loading ? (
          <PageLoading />
        ) : error ? (
          <PageError message={error} onRetry={load} />
        ) : items.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p className="text-lg">{t.search.noResults}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {items.map((s) => (
              <div key={s.id} onClick={() => navigate(`/series/${s.id}`)} className="cursor-pointer group">
                <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                  <img
                    src={s.poster}
                    alt={s.title}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                    <Play className="h-10 w-10 text-white fill-white" />
                  </div>
                  {s.newEpisode && (
                    <Badge className="absolute top-2 right-2 bg-destructive text-destructive-foreground text-[10px]">
                      NEW
                    </Badge>
                  )}
                  {hasDemoClip(s) && (
                    <div className="absolute top-9 right-2">
                      <DemoClipBadge item={s} />
                    </div>
                  )}
                  <Badge className="absolute bottom-2 left-2 bg-background/80 text-foreground text-[10px]">
                    {s.seasons}S • {s.episodes}E
                  </Badge>
                </div>
                <h3 className="text-sm font-medium text-foreground truncate">{s.title}</h3>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{s.year}</span>
                  <span>•</span>
                  <Star className="h-3 w-3 text-primary fill-primary" />
                  <span>{s.rating}</span>
                  <span>•</span>
                  <span>{s.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ MOVIE DETAILS PAGE ============
export function MovieDetailsPage() {
  const { id } = useParams();
  const [movie, setMovie] = useState<CatalogMovie | null>(null);
  const [related, setRelated] = useState<CatalogMovie[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const item = await fetchMovie(id);
      setMovie(item);
      const more = await fetchMovies({ page_size: 20, sort: 'newest' });
      setRelated(
        more.items
          .filter((m) => {
            if (m.id === item.id) return false;
            const status =
              'catalogStatus' in m && typeof (m as { catalogStatus?: string }).catalogStatus === 'string'
                ? (m as { catalogStatus?: string }).catalogStatus
                : 'published';
            if (status !== 'published') return false;
            return m.genres.some((g) => item.genres.includes(g));
          })
          .slice(0, 6)
      );
    } catch (err) {
      setMovie(null);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Movie not found');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <PageLoading />;
  if (error || !movie) return <PageError message={error || 'Movie not found'} onRetry={load} />;

  return <MovieDetailView movie={movie} related={related} />;
}

// ============ SERIES DETAILS PAGE ============
export function SeriesDetailsPage() {
  const { id } = useParams();
  const { t } = useLang();
  const navigate = useNavigate();
  const [selectedSeason, setSelectedSeason] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof fetchSeriesDetail>> | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSeriesDetail(id);
      setDetail(result);
      if (result.seasons.length) setSelectedSeason(result.seasons[0].number);
    } catch (err) {
      setDetail(null);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Series not found');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const showEpisodes = useMemo(() => {
    if (!detail) return [];
    return detail.episodes
      .filter((e) => e.season === selectedSeason)
      .sort((a, b) => a.episode - b.episode);
  }, [detail, selectedSeason]);

  if (loading) return <PageLoading />;
  if (error || !detail) return <PageError message={error || 'Series not found'} onRetry={load} />;

  const show = detail.series;
  const showTrailerEmbed = trailerEmbedUrl(show);
  const showIsDemo = isDemoCatalogItem(show);

  return (
    <div className="min-h-screen">
      <div className="relative h-[40vh] md:h-[50vh]">
        <img src={show.backdrop} alt={show.title} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 -mt-24 relative z-10 pb-12">
        <div className="flex flex-col md:flex-row gap-6">
          <div className="flex-shrink-0 w-[160px] md:w-[200px] mx-auto md:mx-0">
            <img src={show.poster} alt={show.title} className="w-full rounded-lg shadow-xl" />
          </div>
          <div className="flex-1 space-y-3">
            <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground">{show.title}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="outline" className="border-primary/50 text-primary">
                {show.ageRating}
              </Badge>
              <span>{show.year}</span>
              <span>
                {show.seasons} {t.common.season}s
              </span>
              <span>
                {show.episodes} {t.common.episode}s
              </span>
              <Badge variant={show.status === 'Ongoing' ? 'default' : 'secondary'}>{show.status}</Badge>
              <Star className="h-4 w-4 text-primary fill-primary" />
              <span>{show.rating}</span>
            </div>
            <p className="text-sm text-foreground/80">{show.description}</p>
            <div className="flex flex-wrap gap-2">
              {show.genres.map((g) => (
                <Badge key={g} variant="secondary">
                  {g}
                </Badge>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3" aria-label="Series actions">
              {showTrailerEmbed && (
                <Button variant="outline" size="lg" asChild className="gap-2">
                  <a href={showTrailerEmbed} target="_blank" rel="noreferrer" aria-label={`Watch trailer for ${show.title}`}>
                    <ExternalLink className="h-5 w-5" />
                    Watch Trailer
                  </a>
                </Button>
              )}
              {(() => {
                const playableEpisode = showEpisodes.find(
                  (ep) => canPlayFullMovie(ep) || hasDemoClip(ep)
                );
                if (playableEpisode) {
                  return (
                    <Button
                      size="lg"
                      onClick={() =>
                        navigate(
                          `/player/episode/${playableEpisode.id}?series=${encodeURIComponent(String(show.id))}&season=${selectedSeason}`
                        )
                      }
                      className="gap-2"
                      aria-label={
                        hasDemoClip(playableEpisode)
                          ? `Play demo clip for ${show.title}`
                          : `Play ${show.title}`
                      }
                    >
                      <Play className="h-5 w-5 fill-current" />
                      {hasDemoClip(playableEpisode) && !canPlayFullMovie(playableEpisode)
                        ? 'Play Demo Clip'
                        : t.movie.play}
                    </Button>
                  );
                }
                return (
                  <Badge variant="secondary" className="px-3 py-2 text-sm" data-testid="full-series-unavailable">
                    Full Series Unavailable
                  </Badge>
                );
              })()}
              {showIsDemo ? (
                <Badge variant="outline" className="px-3 py-2 text-sm">
                  Demo catalog
                </Badge>
              ) : null}
            </div>
            {showIsDemo && (
              <p className="text-xs text-muted-foreground">
                Demo catalog item: trailer and demo clip access do not indicate full series availability.
              </p>
            )}
          </div>
        </div>

        {showTrailerEmbed && (
          <section className="mt-10 space-y-3" aria-labelledby="series-trailer-heading">
            <h2 id="series-trailer-heading" className="text-xl font-serif font-bold text-foreground">
              Watch Trailer
            </h2>
            <div className="aspect-video overflow-hidden rounded-lg border border-border bg-black">
              <iframe
                src={showTrailerEmbed}
                title={`${show.title} trailer`}
                className="h-full w-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                loading="lazy"
                data-testid="youtube-trailer-embed"
              />
            </div>
          </section>
        )}

        <div className="mt-8">
          <div className="flex items-center gap-4 mb-4">
            <Select value={String(selectedSeason)} onValueChange={(v) => setSelectedSeason(Number(v))}>
              <SelectTrigger className="w-[160px] bg-card border-border">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(detail.seasons.length
                  ? detail.seasons
                  : Array.from({ length: show.seasons }, (_, i) => ({ number: i + 1 }))
                ).map((s) => (
                  <SelectItem key={s.number} value={String(s.number)}>
                    {t.common.season} {s.number}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            {showEpisodes.length > 0 ? (
              showEpisodes.map((ep) => {
                const playable = canPlayFullMovie(ep) || hasDemoClip(ep);
                return (
                  <div
                    key={ep.id}
                    role={playable ? 'button' : undefined}
                    tabIndex={playable ? 0 : undefined}
                    onClick={() => {
                      if (!playable) return;
                      navigate(
                        `/player/episode/${ep.id}?series=${encodeURIComponent(String(show.id))}&season=${selectedSeason}`
                      );
                    }}
                    onKeyDown={(e) => {
                      if (!playable) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(
                          `/player/episode/${ep.id}?series=${encodeURIComponent(String(show.id))}&season=${selectedSeason}`
                        );
                      }
                    }}
                    className={`flex gap-4 rounded-lg border border-border p-3 transition-colors ${
                      playable ? 'cursor-pointer bg-card hover:bg-muted/40' : 'cursor-default bg-muted/20 opacity-80'
                    }`}
                    data-testid={`episode-row-${ep.id}`}
                  >
                    <div className="relative w-[120px] md:w-[160px] flex-shrink-0">
                      <img
                        src={ep.thumbnail || show.poster}
                        alt=""
                        loading="lazy"
                        className="w-full aspect-video rounded object-cover"
                      />
                      {hasDemoClip(ep) ? (
                        <Badge className="absolute start-1 top-1 bg-emerald-600/90 text-[10px]">Demo Clip</Badge>
                      ) : null}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="font-medium text-foreground text-sm">
                        E{ep.episode} - {ep.title}
                      </h4>
                      <p className="text-xs text-muted-foreground mt-1">
                        {ep.duration} {t.common.min}
                        {!playable ? ' · Unavailable' : ''}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{ep.description}</p>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No episodes available for this season yet.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ VIDEO PLAYER PAGE ============
// ============ SEARCH PAGE ============
export function SearchPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<
    Array<(CatalogMovie | CatalogSeries) & { resultType: 'movie' | 'series' }>
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const popularSearches = ['Action', 'Comedy', 'Afghan Movies', 'New Releases', 'Dubbed', 'Drama'];

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSearch(query);
        if (cancelled) return;
        setResults([
          ...data.movies.map((m) => ({ ...m, resultType: 'movie' as const })),
          ...data.series.map((s) => ({ ...s, resultType: 'series' as const })),
        ]);
      } catch (err) {
        if (cancelled) return;
        setResults([]);
        setError(
          err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Search failed'
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <div className="relative max-w-2xl mx-auto mb-8">
          <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
          <Input
            placeholder={t.search.placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-12 h-14 text-lg bg-card border-border rounded-xl"
            autoFocus
          />
          {query && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              <X className="h-5 w-5" />
            </Button>
          )}
        </div>

        {!query ? (
          <div className="max-w-2xl mx-auto">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">{t.search.popular}</h3>
            <div className="flex flex-wrap gap-2">
              {popularSearches.map((s) => (
                <Button key={s} variant="secondary" size="sm" onClick={() => setQuery(s)} className="rounded-full">
                  {s}
                </Button>
              ))}
            </div>
          </div>
        ) : loading ? (
          <PageLoading />
        ) : error ? (
          <PageError message={error} onRetry={() => setQuery((q) => q + '')} />
        ) : results.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p className="text-lg">{t.search.noResults}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {results.map((item) => (
              <div
                key={`${item.resultType}-${item.id}`}
                onClick={() =>
                  navigate(item.resultType === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)
                }
                className="cursor-pointer group"
              >
                <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                  <img
                    src={item.poster}
                    alt={item.title}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                  <Badge className="absolute top-2 left-2 bg-primary/90 text-primary-foreground text-[10px]">
                    {item.resultType === 'series' ? 'Series' : 'Movie'}
                  </Badge>
                  {hasDemoClip(item) && (
                    <div className="absolute top-2 right-2">
                      <DemoClipBadge item={item} />
                    </div>
                  )}
                </div>
                <h3 className="text-sm font-medium text-foreground truncate">{item.title}</h3>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{item.year}</span>
                  <span>•</span>
                  <Star className="h-3 w-3 text-primary fill-primary" />
                  <span>{item.rating}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
