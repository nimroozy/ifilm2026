/**
 * Catalog data access for customer-facing pages.
 * mock mode → local fixtures; api mode → backend (never falls back to mock on failure).
 */
import {
  api,
  mapEpisodeDto,
  mapMovieDto,
  mapSeriesDto,
  type CatalogListParams,
  type CollectionItemDto,
  type CollectionListParams,
  type CollectionPublicDto,
  type MovieDto,
  type SeriesDto,
} from './api';
import { resolveAudioAvailability } from './catalogAvailability';
import { isMockMode } from './dataMode';
import type { AppLocale } from './locale';
import type { Movie, Series } from '@/data/mockData';

/** Lazy mock fixtures — excluded from customer production builds (VITE_DATA_MODE=api). */
async function loadMockData() {
  return import('@/data/mockData');
}

function hasDubCode(item: { dubbed?: string[]; audioAvailability?: unknown }, code: string): boolean {
  const audio = resolveAudioAvailability(item as never);
  if ((audio.dubbed_languages || []).includes(code)) return true;
  // Legacy free-text fallback for mock fixtures
  return Array.isArray(item.dubbed) && item.dubbed.some((d) => String(d).toLowerCase().includes(
    code === 'fa' ? 'persian' : code === 'ps' ? 'pashto' : code
  ));
}

export type CatalogMovie = ReturnType<typeof mapMovieDto> | Movie;
export type CatalogSeries = ReturnType<typeof mapSeriesDto> | Series;
/** Collections V1 — public payload is API-only; no mock fixtures exist yet. */
export type CatalogCollection = CollectionPublicDto;

export interface CatalogListResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface CatalogSearchResult {
  movies: CatalogMovie[];
  series: CatalogSeries[];
}

function publishedMockItems<T extends { catalogStatus?: string }>(items: T[]): T[] {
  return items.filter((item) => (item.catalogStatus ?? 'published') === 'published');
}

async function filterMockMovies(params?: CatalogListParams): Promise<Movie[]> {
  const { movies: mockMovies } = await loadMockData();
  let result = publishedMockItems(mockMovies);
  if (params?.q) {
    const q = params.q.toLowerCase();
    result = result.filter(
      (m) =>
        m.title.toLowerCase().includes(q) ||
        m.originalTitle.toLowerCase().includes(q) ||
        m.director.toLowerCase().includes(q)
    );
  }
  if (params?.genre) {
    result = result.filter((m) => m.genres.includes(params.genre!));
  }
  if (params?.year) {
    result = result.filter((m) => m.year === params.year);
  }
  if (params?.language) {
    result = result.filter((m) => m.language === params.language);
  }
  if (params?.featured) {
    result = result.filter((m) => m.featured);
  }
  const sort = params?.sort || 'newest';
  if (sort === 'newest') result.sort((a, b) => b.year - a.year || b.id - a.id);
  else if (sort === 'rating' || sort === 'rating_desc') result.sort((a, b) => b.rating - a.rating);
  else if (sort === 'popular' || sort === 'views_desc') result.sort((a, b) => b.views - a.views);
  else if (sort === 'title' || sort === 'title_asc') result.sort((a, b) => a.title.localeCompare(b.title));
  return result;
}

async function filterMockSeries(params?: CatalogListParams): Promise<Series[]> {
  const { series: mockSeries } = await loadMockData();
  let result = publishedMockItems(mockSeries);
  if (params?.q) {
    const q = params.q.toLowerCase();
    result = result.filter(
      (s) => s.title.toLowerCase().includes(q) || s.originalTitle.toLowerCase().includes(q)
    );
  }
  if (params?.genre) {
    result = result.filter((s) => s.genres.includes(params.genre!));
  }
  if (params?.year) {
    result = result.filter((s) => s.year === params.year);
  }
  const sort = params?.sort || 'newest';
  if (sort === 'newest') result.sort((a, b) => b.year - a.year || b.id - a.id);
  else if (sort === 'rating' || sort === 'rating_desc') result.sort((a, b) => b.rating - a.rating);
  else if (sort === 'popular' || sort === 'views_desc') result.sort((a, b) => b.views - a.views);
  else if (sort === 'title' || sort === 'title_asc') result.sort((a, b) => a.title.localeCompare(b.title));
  return result;
}

function paginateMock<T>(items: T[], page = 1, pageSize = 20): CatalogListResult<T> {
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    total: items.length,
    page,
    page_size: pageSize,
  };
}

export async function fetchMovies(params?: CatalogListParams): Promise<CatalogListResult<CatalogMovie>> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    return paginateMock(await filterMockMovies(params), params?.page ?? 1, params?.page_size ?? 100);
  }
  const page = await api.listMovies(params);
  return {
    items: page.items.map(mapMovieDto),
    total: page.total,
    page: page.page,
    page_size: page.page_size,
  };
}

export async function fetchMovie(
  idOrSlug: number | string,
  locale?: AppLocale,
): Promise<CatalogMovie> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { movies: mockMovies } = await loadMockData();
    const id = typeof idOrSlug === 'number' ? idOrSlug : Number(idOrSlug);
    const movie = publishedMockItems(mockMovies).find(
      (m) => m.id === id || String(m.id) === String(idOrSlug)
    );
    if (!movie) throw new Error('Movie not found');
    return movie;
  }
  return mapMovieDto(await api.getMovie(idOrSlug, locale));
}

export async function fetchSimilarMovies(
  idOrSlug: number | string,
  limit = 12,
  locale?: AppLocale,
): Promise<CatalogMovie[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const item = await fetchMovie(idOrSlug, locale);
    const page = await fetchMovies({ page_size: 40, sort: 'popular', locale });
    return page.items
      .filter((m) => m.id !== item.id && m.genres.some((g) => item.genres.includes(g)))
      .slice(0, limit);
  }
  const rows = await api.getSimilarMovies(idOrSlug, limit, locale);
  return rows.map(mapMovieDto);
}

export async function fetchSeries(params?: CatalogListParams): Promise<CatalogListResult<CatalogSeries>> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    return paginateMock(await filterMockSeries(params), params?.page ?? 1, params?.page_size ?? 100);
  }
  const page = await api.listSeries(params);
  return {
    items: page.items.map(mapSeriesDto),
    total: page.total,
    page: page.page,
    page_size: page.page_size,
  };
}

export type SeriesSeasonSummary = {
  number: number;
  episodeCount: number;
  id?: number;
  status?: string;
};

export type SeriesDetailResult = {
  series: CatalogSeries;
  seasons: SeriesSeasonSummary[];
  /** Episodes for the requested season only (or all in mock mode when season omitted). */
  episodes: ReturnType<typeof mapEpisodeDto>[];
};

/** Series metadata + seasons only — no episode dump. */
export async function fetchSeriesShell(
  idOrSlug: number | string,
  locale?: AppLocale,
): Promise<{ series: CatalogSeries; seasons: SeriesSeasonSummary[] }> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const detail = await fetchSeriesDetail(idOrSlug, locale);
    return { series: detail.series, seasons: detail.seasons };
  }
  const dto = await api.getSeries(idOrSlug, locale);
  const mapped = mapSeriesDto(dto);
  const seasonsDto = await api.listSeasons(idOrSlug);
  const seasons = [...seasonsDto]
    .sort((a, b) => a.season_number - b.season_number)
    .map((s) => ({
      number: s.season_number,
      episodeCount: s.episode_count ?? 0,
      id: s.id,
      status: s.status,
    }));
  return { series: mapped, seasons };
}

/** Season-scoped episodes. Prefer this over loading the full series episode list. */
export async function fetchSeasonEpisodes(
  idOrSlug: number | string,
  season: number,
  locale?: AppLocale,
): Promise<ReturnType<typeof mapEpisodeDto>[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const detail = await fetchSeriesDetail(idOrSlug, locale);
    return detail.episodes.filter((e) => e.season === season).sort((a, b) => a.episode - b.episode);
  }
  const episodesDto = await api.listEpisodes(idOrSlug, season, locale);
  return [...episodesDto]
    .map(mapEpisodeDto)
    .map((ep) => {
      if (!ep.season) ep.season = season;
      return ep;
    })
    .sort((a, b) => a.episode - b.episode);
}

export async function fetchSeriesRecommendations(
  idOrSlug: number | string,
  limit = 12,
): Promise<CatalogSeries[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    return [];
  }
  const page = await api.getSeriesRecommendations(idOrSlug, limit);
  const currentId = typeof idOrSlug === 'number' ? idOrSlug : Number(idOrSlug);
  const seen = new Set<number>();
  const out: CatalogSeries[] = [];
  for (const row of page.items ?? []) {
    if (row.content_type !== 'series') continue;
    if (row.id === currentId || seen.has(row.id)) continue;
    seen.add(row.id);
    out.push(
      mapSeriesDto({
        id: row.id,
        title: row.title,
        slug: row.slug,
        poster_url: row.poster_url || '',
        backdrop_url: row.backdrop_url || '',
        release_year: row.release_year ?? undefined,
        imdb_rating: row.imdb_rating ?? undefined,
        genres: row.genres || [],
        status: 'published',
        airing_status: 'Ongoing',
      } as SeriesDto)
    );
  }
  return out;
}

export async function fetchSeriesDetail(
  idOrSlug: number | string,
  locale?: AppLocale,
  season?: number,
): Promise<SeriesDetailResult> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { series: mockSeries, episodes: mockEpisodes } = await loadMockData();
    const id = typeof idOrSlug === 'number' ? idOrSlug : Number(idOrSlug);
    const show = publishedMockItems(mockSeries).find(
      (s) => s.id === id || String(s.id) === String(idOrSlug)
    );
    if (!show) throw new Error('Series not found');
    const eps = publishedMockItems(mockEpisodes)
      .filter((e) => e.seriesId === show.id)
      .map((e) => ({
        id: e.id,
        seriesId: e.seriesId,
        seasonId: 0,
        season: e.season,
        episode: e.episode,
        title: e.title,
        duration: e.duration,
        description: e.description,
        thumbnail: e.thumbnail,
        status: 'published',
        tmdbId: null,
        metadataSource: '',
        demoOwned: false,
        hasDemoClip: false,
        hlsPath: null as string | null,
        playable: false,
        hasPlayablePackage: false,
        hasExternalMedia: false,
        audioAvailability: null,
        subtitleAvailability: null,
      }));
    const seasonNumbers = Array.from(new Set(eps.map((e) => e.season))).sort((a, b) => a - b);
    const seasons =
      seasonNumbers.length > 0
        ? seasonNumbers.map((n) => ({
            number: n,
            episodeCount: eps.filter((e) => e.season === n).length,
          }))
        : Array.from({ length: show.seasons }, (_, i) => ({ number: i + 1, episodeCount: 0 }));
    const scoped = season != null ? eps.filter((e) => e.season === season) : eps;
    return { series: show, seasons, episodes: scoped.sort((a, b) => a.episode - b.episode) };
  }

  const { series: mapped, seasons } = await fetchSeriesShell(idOrSlug, locale);
  const initialSeason = season ?? seasons[0]?.number ?? 1;
  const episodes = seasons.length
    ? await fetchSeasonEpisodes(idOrSlug, initialSeason, locale)
    : [];

  return { series: mapped, seasons, episodes };
}

export async function fetchSearch(q: string, locale?: AppLocale): Promise<CatalogSearchResult> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { movies: mockMovies, series: mockSeries } = await loadMockData();
    const query = q.toLowerCase().trim();
    if (!query) return { movies: [], series: [] };
    const movies = publishedMockItems(mockMovies).filter(
      (m) =>
        m.title.toLowerCase().includes(query) ||
        m.originalTitle.includes(q) ||
        m.cast.some((c) => c.toLowerCase().includes(query)) ||
        m.director.toLowerCase().includes(query)
    );
    const series = publishedMockItems(mockSeries).filter(
      (s) => s.title.toLowerCase().includes(query) || s.originalTitle.includes(q)
    );
    return { movies, series };
  }
  const data = await api.search(q, locale);
  return {
    movies: data.movies.map(mapMovieDto),
    series: data.series.map(mapSeriesDto),
  };
}

export async function fetchGenres(): Promise<{ id?: number; name: string; slug?: string }[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { genres: mockGenreNames } = await loadMockData();
    return mockGenreNames.map((name) => ({ name, slug: name.toLowerCase() }));
  }
  const page = await api.listGenres({ page_size: 100 });
  return page.items.map((g) => ({ id: g.id, name: g.name, slug: g.slug }));
}

export async function fetchFeaturedMovies(limit = 8): Promise<CatalogMovie[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { movies: mockMovies } = await loadMockData();
    return publishedMockItems(mockMovies).filter((m) => m.featured).slice(0, limit);
  }
  const page = await api.listMovies({ featured: true, page_size: limit, sort: 'newest' });
  return page.items.map(mapMovieDto);
}

export async function fetchTrendingMovies(limit = 12): Promise<CatalogMovie[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { movies: mockMovies } = await loadMockData();
    return publishedMockItems(mockMovies).sort((a, b) => b.views - a.views).slice(0, limit);
  }
  const page = await api.listMovies({ trending: true, page_size: limit, sort: 'views_desc' });
  if (page.items.length) return page.items.map(mapMovieDto);
  const fallback = await api.listMovies({ page_size: limit, sort: 'views_desc' });
  return fallback.items.map(mapMovieDto);
}

export async function fetchHomeCatalog(locale?: AppLocale) {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const { movies: mockMovies, series: mockSeries } = await loadMockData();
    const movies = publishedMockItems(mockMovies);
    const series = publishedMockItems(mockSeries);
    return {
      featured: movies.filter((m) => m.featured),
      trending: [...movies].sort((a, b) => b.views - a.views).slice(0, 12),
      recentlyAdded: [...movies].sort((a, b) => b.year - a.year || b.id - a.id).slice(0, 12),
      popular: movies.filter((m) => m.rating >= 8.0).slice(0, 12),
      afghanMovies: movies.filter((m) => m.country === 'Afghanistan').slice(0, 12),
      persianDubbed: movies.filter((m) => hasDubCode(m, 'fa')).slice(0, 12),
      pashtoDubbed: movies.filter((m) => hasDubCode(m, 'ps')).slice(0, 12),
      actionMovies: movies.filter((m) => m.genres.includes('Action')).slice(0, 12),
      comedyMovies: movies.filter((m) => m.genres.includes('Comedy')).slice(0, 12),
      familyMovies: movies
        .filter((m) => m.genres.includes('Family') || m.genres.includes('Animation'))
        .slice(0, 12),
      popularSeries: [...series].sort((a, b) => b.views - a.views).slice(0, 12),
      featuredCollections: [] as CatalogCollection[],
      recommendations: null as import('./api').HomeRecommendationsDto | null,
    };
  }

  const loc = locale ? { locale } : undefined;
  // Prefer bounded aggregate endpoint (one HTTP call). Fall back to legacy fan-out
  // only if the aggregate route is unavailable on older backends.
  try {
    const home = await api.getCatalogHome(loc);
    return {
      featured: home.featured.map(mapMovieDto),
      trending: home.trending.map(mapMovieDto),
      recentlyAdded: home.recently_added.map(mapMovieDto),
      popular: home.top_rated.map(mapMovieDto),
      afghanMovies: home.afghan.map(mapMovieDto),
      persianDubbed: home.persian_dubbed.map(mapMovieDto),
      pashtoDubbed: home.pashto_dubbed.map(mapMovieDto),
      actionMovies: home.action.map(mapMovieDto),
      comedyMovies: home.comedy.map(mapMovieDto),
      familyMovies: home.family.map(mapMovieDto),
      popularSeries: home.popular_series.map(mapSeriesDto),
      featuredCollections: home.featured_collections || [],
      recommendations: home.recommendations ?? null,
    };
  } catch {
    /* fall through to legacy multi-call path */
  }

  const params = locale ? { locale } : {};
  const [
    featuredPage,
    trendingPage,
    recentPage,
    popularPage,
    poolPage,
    seriesPage,
    actionPage,
    comedyPage,
  ] = await Promise.all([
    api.listMovies({ featured: true, page_size: 8, sort: 'newest', ...params }),
    api.listMovies({ trending: true, page_size: 12, sort: 'views_desc', ...params }),
    api.listMovies({ page_size: 12, sort: 'newest', ...params }),
    api.listMovies({ page_size: 12, sort: 'rating_desc', ...params }),
    api.listMovies({ page_size: 40, sort: 'newest', ...params }),
    api.listSeries({ page_size: 12, sort: 'views_desc', ...params }),
    api.listMovies({ genre: 'Action', page_size: 12, sort: 'views_desc', ...params }),
    api.listMovies({ genre: 'Comedy', page_size: 12, sort: 'views_desc', ...params }),
  ]);

  const mapAll = (items: MovieDto[]) => items.map(mapMovieDto);
  const mapSeries = (items: SeriesDto[]) => items.map(mapSeriesDto);
  const pool = mapAll(poolPage.items);

  const trending =
    trendingPage.items.length > 0
      ? mapAll(trendingPage.items)
      : mapAll((await api.listMovies({ page_size: 12, sort: 'views_desc', ...params })).items);

  return {
    featured: mapAll(featuredPage.items.length ? featuredPage.items : recentPage.items.slice(0, 5)),
    trending,
    recentlyAdded: mapAll(recentPage.items),
    popular: mapAll(popularPage.items),
    afghanMovies: pool.filter((m) => m.country === 'Afghanistan').slice(0, 12),
    persianDubbed: pool.filter((m) => hasDubCode(m, 'fa')).slice(0, 12),
    pashtoDubbed: pool.filter((m) => hasDubCode(m, 'ps')).slice(0, 12),
    actionMovies: mapAll(actionPage.items),
    comedyMovies: mapAll(comedyPage.items),
    familyMovies: pool
      .filter((m) => m.genres.includes('Family') || m.genres.includes('Animation'))
      .slice(0, 12),
    popularSeries: mapSeries(seriesPage.items),
    featuredCollections: [] as CatalogCollection[],
    recommendations: null as import('./api').HomeRecommendationsDto | null,
  };
}

/** Authenticated homepage aggregate (catalog + CW + watchlist + recommendations). */
export async function fetchMeHomeCatalog(locale?: AppLocale) {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    const catalog = await fetchHomeCatalog(locale);
    return {
      ...catalog,
      continueWatching: [] as import('./api').WatchProgressDto[],
      watchlist: [] as import('./api').WatchlistItemDto[],
      recommendations: null as import('./api').HomeRecommendationsDto | null,
    };
  }
  const home = await api.getMeHome(locale ? { locale } : undefined);
  return {
    featured: home.featured.map(mapMovieDto),
    trending: home.trending.map(mapMovieDto),
    recentlyAdded: home.recently_added.map(mapMovieDto),
    popular: home.top_rated.map(mapMovieDto),
    afghanMovies: home.afghan.map(mapMovieDto),
    persianDubbed: home.persian_dubbed.map(mapMovieDto),
    pashtoDubbed: home.pashto_dubbed.map(mapMovieDto),
    actionMovies: home.action.map(mapMovieDto),
    comedyMovies: home.comedy.map(mapMovieDto),
    familyMovies: home.family.map(mapMovieDto),
    popularSeries: home.popular_series.map(mapSeriesDto),
    featuredCollections: home.featured_collections || [],
    continueWatching: home.continue_watching || [],
    watchlist: (home.watchlist || []).filter((i) => i.available),
    recommendations: home.recommendations,
  };
}

// ============ COLLECTIONS V1 ============
// Public collections are backend-only (Collections V1 has no mock fixtures);
// mock mode returns empty results so existing demo pages are unaffected.

export async function fetchCollections(
  params?: CollectionListParams
): Promise<CatalogListResult<CatalogCollection>> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    return { items: [], total: 0, page: params?.page ?? 1, page_size: params?.page_size ?? 20 };
  }
  const page = await api.listCollections(params);
  return {
    items: page.items,
    total: page.total,
    page: page.page,
    page_size: page.page_size,
  };
}

export async function fetchCollection(slug: string): Promise<CatalogCollection> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) {
    throw new Error('Collection not found');
  }
  return api.getCollection(slug);
}

export async function fetchFeaturedHomeCollections(params?: {
  page_size?: number;
  min_items?: number;
}): Promise<CatalogCollection[]> {
  if (import.meta.env.VITE_DATA_MODE !== 'api' && isMockMode()) return [];
  const page = await api.listFeaturedHomeCollections(params);
  return page.items;
}

/** Map ordered collection items to catalog cards, dropping items missing embedded content. */
export function mapCollectionItems(items: CollectionItemDto[]): (CatalogMovie | CatalogSeries)[] {
  const mapped: (CatalogMovie | CatalogSeries)[] = [];
  for (const item of items) {
    if (item.content_type === 'movie' && item.movie) {
      mapped.push(mapMovieDto(item.movie));
    } else if (item.content_type === 'series' && item.series) {
      mapped.push(mapSeriesDto(item.series));
    }
  }
  return mapped;
}
