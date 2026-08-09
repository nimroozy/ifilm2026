import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Play,
  Star,
  Clock,
  Plus,
  Grid,
  List,
  Search as SearchIcon,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth, useLang } from '@/components/CustomerLayout';
import {
  fetchGenres,
  fetchMovie,
  fetchMovies,
  fetchSearch,
  fetchSeries,
  fetchSeasonEpisodes,
  fetchSeriesRecommendations,
  fetchSeriesShell,
  fetchSimilarMovies,
  type CatalogMovie,
  type CatalogSeries,
} from '@/lib/catalogData';
import { api, ApiError, mapMovieDto, type MovieDto, type WatchProgressDto } from '@/lib/api';
import type { MovieWatchState } from '@/components/MovieDetailView';
import {
  catalogAvailabilityBadges,
} from '@/lib/catalogAvailability';
import { canPlayFullMovie, hasDemoClip } from '@/lib/catalogPresentation';
import { MediaCard, mediaGridClass } from '@/design-system';
import { MovieDetailView } from '@/components/MovieDetailView';
import {
  SeriesDetailView,
  type SeriesEpisodeView,
  type SeriesSeasonView,
} from '@/components/SeriesDetailView';
import {
  buildEpisodeProgressMap,
  defaultSeasonNumber,
  findNextPlayableEpisode,
  resolveSeriesHeroCta,
  sortEpisodesByAirOrder,
} from '@/lib/seriesDetailPlayback';

function PageLoading() {
  return (
    <div className="container mx-auto px-4 pt-6 space-y-4" data-testid="browse-loading">
      <Skeleton className="h-8 w-48" />
      <div className={mediaGridClass}>
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
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const genreFromUrl = searchParams.get('genre')?.trim() || 'all';
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState(genreFromUrl);
  const [sort, setSort] = useState('newest');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [items, setItems] = useState<CatalogMovie[]>([]);
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isChildren = audience === 'children';
  const availabilityLabels = {
    dubbed: t.nav.dubbed,
    subtitled: t.nav.subtitled,
    multiAudio: 'Multi',
    persianDubbed: t.player.persianDub,
    pashtoDubbed: t.player.pashtoDub,
  };

  useEffect(() => {
    setGenre(genreFromUrl);
  }, [genreFromUrl]);

  function onGenreChange(next: string) {
    setGenre(next);
    if (isChildren) return;
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('genre');
    else params.set('genre', next);
    setSearchParams(params, { replace: true });
  }

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
                  locale: lang,
                }),
              ]
            : CHILDREN_GENRES.map((childGenre) =>
                fetchMovies({
                  q: search || undefined,
                  genre: childGenre,
                  sort: sortParam(sort),
                  page_size: 100,
                  locale: lang,
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
            locale: lang,
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
  }, [search, genre, sort, isChildren, lang]);

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
          <Select value={genre} onValueChange={onGenreChange}>
            <SelectTrigger className="w-[140px] bg-card border-border" data-testid="movies-genre-filter">
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
          <div className={mediaGridClass}>
            {items.map((movie) => {
              const { badges, overflow } = catalogAvailabilityBadges(movie, availabilityLabels);
              return (
                <MediaCard
                  key={movie.id}
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
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
  const [items, setItems] = useState<CatalogSeries[]>([]);
  const [genreOptions, setGenreOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const availabilityLabels = {
    dubbed: t.nav.dubbed,
    subtitled: t.nav.subtitled,
    multiAudio: 'Multi',
    persianDubbed: t.player.persianDub,
    pashtoDubbed: t.player.pashtoDub,
  };

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
          locale: lang,
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
  }, [search, genre, lang]);

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
          <div className={mediaGridClass}>
            {items.map((s) => {
              const { badges, overflow } = catalogAvailabilityBadges(s, availabilityLabels);
              const seasonLabel = s.seasons ? `${s.seasons} season${s.seasons === 1 ? '' : 's'}` : undefined;
              return (
                <MediaCard
                  key={s.id}
                  className="!w-full max-w-none"
                  title={s.title}
                  imageUrl={s.poster}
                  year={s.year}
                  rating={s.rating}
                  runtime={seasonLabel}
                  status={s.status || undefined}
                  availabilityBadges={badges}
                  availabilityOverflow={overflow}
                  showDemo={hasDemoClip(s)}
                  playable={hasDemoClip(s)}
                  onActivate={() => navigate(`/series/${s.id}`)}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ MOVIE DETAILS PAGE ============
export function MovieDetailsPage() {
  const { id } = useParams();
  const { lang } = useLang();
  const { isLoggedIn } = useAuth();
  const [movie, setMovie] = useState<CatalogMovie | null>(null);
  const [related, setRelated] = useState<CatalogMovie[]>([]);
  const [recommended, setRecommended] = useState<CatalogMovie[]>([]);
  const [watchState, setWatchState] = useState<MovieWatchState>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const item = await fetchMovie(id, lang);
      setMovie(item);

      const similarPromise = fetchSimilarMovies(id, 12, lang).catch(async () => {
        const more = await fetchMovies({ page_size: 20, sort: 'newest', locale: lang });
        return more.items
          .filter((m) => m.id !== item.id && m.genres.some((g) => item.genres.includes(g)))
          .slice(0, 6);
      });

      const recPromise = api
        .getMovieRecommendations(id, 12)
        .then((payload) =>
          (payload.items || [])
            .filter((row) => row.content_type === 'movie' && row.id !== item.id)
            .map((row) =>
              mapMovieDto({
                id: row.id,
                title: row.title,
                slug: row.slug,
                poster_url: row.poster_url || '',
                backdrop_url: row.backdrop_url || '',
                release_year: row.release_year ?? undefined,
                imdb_rating: row.imdb_rating ?? undefined,
                genres: row.genres || [],
                playable: row.playable,
                status: 'published',
              } as MovieDto)
            )
        )
        .catch(() => [] as CatalogMovie[]);

      const [similar, recs] = await Promise.all([similarPromise, recPromise]);
      setRelated(similar);
      setRecommended(recs);

      if (isLoggedIn) {
        try {
          const cw = await api.listContinueWatching();
          const active = cw.find(
            (row) => row.content_type === 'movie' && row.movie_id === item.id && !row.completed
          );
          if (active) {
            setWatchState({ kind: 'continue', progress: active });
          } else {
            const history = await api.listWatchHistory({ page: 1, page_size: 40 });
            const done = history.items.find(
              (row) => row.content_type === 'movie' && row.movie_id === item.id && row.completed
            );
            setWatchState(done ? { kind: 'completed', progress: done } : null);
          }
        } catch {
          setWatchState(null);
        }
      } else {
        setWatchState(null);
      }
    } catch (err) {
      setMovie(null);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Movie not found');
    } finally {
      setLoading(false);
    }
  }, [id, lang, isLoggedIn]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <PageLoading />;
  if (error || !movie) return <PageError message={error || 'Movie not found'} onRetry={load} />;

  return (
    <MovieDetailView
      movie={movie}
      related={related}
      recommended={recommended}
      watchState={watchState}
    />
  );
}

// ============ SERIES DETAILS PAGE ============
export function SeriesDetailsPage() {
  const { id } = useParams();
  const { lang } = useLang();
  const { isLoggedIn } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [series, setSeries] = useState<CatalogSeries | null>(null);
  const [seasons, setSeasons] = useState<SeriesSeasonView[]>([]);
  const [selectedSeason, setSelectedSeason] = useState(1);
  const [seasonInitialized, setSeasonInitialized] = useState(false);
  const [episodesBySeason, setEpisodesBySeason] = useState<Map<number, SeriesEpisodeView[]>>(
    () => new Map()
  );
  const [seasonLoading, setSeasonLoading] = useState(false);
  const [recommended, setRecommended] = useState<CatalogSeries[]>([]);
  const [continueWatching, setContinueWatching] = useState<WatchProgressDto[]>([]);
  const [watchHistory, setWatchHistory] = useState<WatchProgressDto[]>([]);

  const loadShell = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    setSeasonInitialized(false);
    setEpisodesBySeason(new Map());
    try {
      const [shell, recs] = await Promise.all([
        fetchSeriesShell(id, lang),
        fetchSeriesRecommendations(id, 12).catch(() => [] as CatalogSeries[]),
      ]);
      setSeries(shell.series);
      setSeasons(shell.seasons as SeriesSeasonView[]);
      setRecommended(recs.filter((item) => item.id !== shell.series.id));

      let cw: WatchProgressDto[] = [];
      let history: WatchProgressDto[] = [];
      if (isLoggedIn) {
        try {
          cw = await api.listContinueWatching();
          const hist = await api.listWatchHistory({ page: 1, page_size: 60 });
          history = hist.items || [];
        } catch {
          cw = [];
          history = [];
        }
      }
      setContinueWatching(cw);
      setWatchHistory(history);

      // Prefetch a seed season for CTA / default season (watch season, else first).
      const hintSeason =
        cw.find((r) => r.content_type === 'episode' && r.series_id === shell.series.id && !r.completed)
          ?.season_number ??
        history.find((r) => r.content_type === 'episode' && r.series_id === shell.series.id && r.completed)
          ?.season_number ??
        shell.seasons[0]?.number ??
        1;

      const seasonsToPrefetch = new Set<number>([hintSeason]);
      const nextSeason = shell.seasons.find((s) => s.number > hintSeason)?.number;
      if (nextSeason != null) seasonsToPrefetch.add(nextSeason);

      const fetched = new Map<number, SeriesEpisodeView[]>();
      await Promise.all(
        [...seasonsToPrefetch].map(async (seasonNum) => {
          const eps = (await fetchSeasonEpisodes(id, seasonNum, lang)) as SeriesEpisodeView[];
          fetched.set(seasonNum, eps);
        })
      );
      setEpisodesBySeason(fetched);

      const catalog = sortEpisodesByAirOrder([...fetched.values()].flat());
      const cta = resolveSeriesHeroCta({
        seriesId: shell.series.id,
        catalogEpisodes: catalog,
        continueWatching: cw,
        watchHistory: history,
      });
      // If completed at season end, ensure next season episodes loaded for Next CTA.
      if (cta.kind === 'watch_again' || (cta.kind === 'next' && !fetched.has(cta.episode.season))) {
        const completed = history.find(
          (r) => r.content_type === 'episode' && r.series_id === shell.series.id && r.completed
        );
        if (completed) {
          const nextHint = shell.seasons.find(
            (s) => s.number > (completed.season_number ?? 0)
          )?.number;
          if (nextHint != null && !fetched.has(nextHint)) {
            const eps = (await fetchSeasonEpisodes(id, nextHint, lang)) as SeriesEpisodeView[];
            fetched.set(nextHint, eps);
            setEpisodesBySeason(new Map(fetched));
            const nextEp = findNextPlayableEpisode(
              sortEpisodesByAirOrder([...fetched.values()].flat()),
              completed.season_number ?? 0,
              completed.episode_number ?? 0
            );
            if (nextEp) {
              // catalog refresh happens via state; season default uses updated map below
            }
          }
        }
      }

      const refreshedCatalog = sortEpisodesByAirOrder([...fetched.values()].flat());
      const refreshedCta = resolveSeriesHeroCta({
        seriesId: shell.series.id,
        catalogEpisodes: refreshedCatalog,
        continueWatching: cw,
        watchHistory: history,
      });
      const initial = defaultSeasonNumber({
        seasons: shell.seasons,
        cta: refreshedCta,
        episodesBySeason: fetched,
      });
      setSelectedSeason(initial);
      if (!fetched.has(initial)) {
        const eps = (await fetchSeasonEpisodes(id, initial, lang)) as SeriesEpisodeView[];
        fetched.set(initial, eps);
        setEpisodesBySeason(new Map(fetched));
      }
      setSeasonInitialized(true);
    } catch (err) {
      setSeries(null);
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Series not found');
    } finally {
      setLoading(false);
    }
  }, [id, lang, isLoggedIn]);

  useEffect(() => {
    void loadShell();
  }, [loadShell]);

  const onSeasonChange = useCallback(
    async (season: number) => {
      setSelectedSeason(season);
      if (!id) return;
      if (episodesBySeason.has(season)) return;
      setSeasonLoading(true);
      try {
        const eps = (await fetchSeasonEpisodes(id, season, lang)) as SeriesEpisodeView[];
        setEpisodesBySeason((prev) => {
          const next = new Map(prev);
          next.set(season, eps);
          return next;
        });
      } finally {
        setSeasonLoading(false);
      }
    },
    [id, lang, episodesBySeason]
  );

  const catalogEpisodes = useMemo(
    () => sortEpisodesByAirOrder([...episodesBySeason.values()].flat()),
    [episodesBySeason]
  );

  const heroCta = useMemo(() => {
    if (!series) {
      return { kind: 'unavailable' as const };
    }
    return resolveSeriesHeroCta({
      seriesId: series.id,
      catalogEpisodes,
      continueWatching,
      watchHistory,
    });
  }, [series, catalogEpisodes, continueWatching, watchHistory]);

  const progressByEpisode = useMemo(() => {
    if (!series) return new Map<number, WatchProgressDto>();
    return buildEpisodeProgressMap(series.id, [...continueWatching, ...watchHistory]);
  }, [series, continueWatching, watchHistory]);

  const selectedEpisodes = episodesBySeason.get(selectedSeason) ?? [];

  if (loading || !seasonInitialized) {
    return (
      <div className="min-h-screen" data-testid="series-detail-loading">
        <Skeleton className="h-[58vh] w-full rounded-none" />
        <div className="container mx-auto max-w-6xl space-y-4 px-4 py-8">
          <Skeleton className="h-8 w-48" />
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="grid grid-cols-[120px_1fr] gap-3">
              <Skeleton className="aspect-video w-full" />
              <div className="space-y-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-16 w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (error || !series) return <PageError message={error || 'Series not found'} onRetry={loadShell} />;

  return (
    <SeriesDetailView
      series={series}
      seasons={seasons}
      episodes={selectedEpisodes}
      selectedSeason={selectedSeason}
      onSeasonChange={(n) => void onSeasonChange(n)}
      seasonLoading={seasonLoading}
      recommended={recommended}
      heroCta={heroCta}
      progressByEpisode={progressByEpisode}
      catalogEpisodesForCta={catalogEpisodes}
    />
  );
}

// ============ VIDEO PLAYER PAGE ============
// ============ SEARCH PAGE ============
export function SearchPage() {
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
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
      setActiveIndex(0);
      return;
    }
    let cancelled = false;
    const requestId = reloadToken;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSearch(query, lang);
        if (cancelled) return;
        setResults([
          ...data.movies.map((m) => ({ ...m, resultType: 'movie' as const })),
          ...data.series.map((s) => ({ ...s, resultType: 'series' as const })),
        ]);
        setActiveIndex(0);
      } catch (err) {
        if (cancelled) return;
        setResults([]);
        setError(
          err instanceof ApiError
            ? err.message || 'Search request failed. Please try again.'
            : err instanceof Error
              ? err.message
              : 'Search request failed. Please try again.'
        );
      } finally {
        if (!cancelled && requestId === reloadToken) setLoading(false);
      }
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, reloadToken, lang]);

  useEffect(() => {
    if (!results.length) return;
    const active = results[activeIndex];
    if (!active) return;
    const node = document.getElementById(`search-result-${active.resultType}-${active.id}`);
    node?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [activeIndex, results]);

  const openResult = (item: (typeof results)[number]) => {
    navigate(item.resultType === 'series' ? `/series/${item.id}` : `/movie/${item.id}`);
  };

  /** Highlight match using text nodes only — never inject HTML from titles/queries. */
  const highlight = (text: string) => {
    const q = query.trim();
    if (!q) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="rounded-sm bg-primary/30 px-0.5 text-foreground">
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </>
    );
  };

  const listExpanded = Boolean(query.trim()) && results.length > 0 && !loading && !error;

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 pb-10 pt-6 sm:px-6 lg:px-8">
        <div className="relative mx-auto mb-8 max-w-2xl">
          <SearchIcon className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
          <Input
            role="combobox"
            placeholder={t.search.placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                setQuery('');
                return;
              }
              if (!results.length) return;
              if (event.key === 'ArrowDown') {
                event.preventDefault();
                setActiveIndex((value) => Math.min(results.length - 1, value + 1));
              } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                setActiveIndex((value) => Math.max(0, value - 1));
              } else if (event.key === 'Enter') {
                event.preventDefault();
                const item = results[activeIndex];
                if (item) openResult(item);
              }
            }}
            className="h-14 rounded-2xl border-border bg-card/80 pl-12 pr-12 text-lg shadow-md backdrop-blur-sm"
            autoFocus
            autoComplete="off"
            aria-label="Search catalog"
            aria-autocomplete="list"
            aria-expanded={listExpanded}
            aria-controls="search-results"
            aria-activedescendant={
              listExpanded && results[activeIndex]
                ? `search-result-${results[activeIndex].resultType}-${results[activeIndex].id}`
                : undefined
            }
          />
          {query ? (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2"
              aria-label="Clear search"
            >
              <X className="h-5 w-5" />
            </Button>
          ) : null}
        </div>

        {!query.trim() ? (
          <div className="mx-auto max-w-2xl">
            <h3 className="mb-3 text-sm font-medium text-muted-foreground">{t.search.popular}</h3>
            <div className="flex flex-wrap gap-2">
              {popularSearches.map((term) => (
                <Button
                  key={term}
                  variant="secondary"
                  size="sm"
                  onClick={() => setQuery(term)}
                  className="rounded-full"
                >
                  {term}
                </Button>
              ))}
            </div>
          </div>
        ) : loading ? (
          <PageLoading />
        ) : error ? (
          <div className="mx-auto max-w-lg space-y-3 text-center" data-testid="search-api-error">
            <p className="text-muted-foreground" role="alert">
              {error}
            </p>
            <p className="text-xs text-muted-foreground">This is a search service error, not an empty result.</p>
            <Button onClick={() => setReloadToken((value) => value + 1)}>Retry</Button>
          </div>
        ) : results.length === 0 ? (
          <div className="py-20 text-center text-muted-foreground" data-testid="search-no-results">
            <p className="text-lg">{t.search.noResults}</p>
          </div>
        ) : (
          <div
            id="search-results"
            role="listbox"
            aria-label="Search results"
            className={mediaGridClass}
          >
            {results.map((item, index) => (
              <div
                key={`${item.resultType}-${item.id}`}
                id={`search-result-${item.resultType}-${item.id}`}
                role="option"
                aria-selected={index === activeIndex}
                className={
                  index === activeIndex
                    ? 'rounded-xl ring-2 ring-primary ring-offset-2 ring-offset-background'
                    : undefined
                }
              >
                <MediaCard
                  className="!w-full max-w-none"
                  title={item.title}
                  imageUrl={item.poster}
                  year={item.year}
                  rating={item.rating}
                  showDemo={hasDemoClip(item)}
                  playable={canPlayFullMovie(item) || hasDemoClip(item)}
                  badge={item.resultType === 'series' ? 'Series' : 'Movie'}
                  onActivate={() => openResult(item)}
                />
                <p className="mt-1 px-0.5 text-xs text-muted-foreground">
                  {highlight(item.title)}
                  {item.genres?.length ? ` · ${item.genres.slice(0, 2).join(', ')}` : ''}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
