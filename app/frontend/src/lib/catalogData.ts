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
  type MovieDto,
  type SeriesDto,
} from './api';
import { resolveAudioAvailability } from './catalogAvailability';
import { isApiMode, isMockMode } from './dataMode';
import {
  movies as mockMovies,
  series as mockSeries,
  episodes as mockEpisodes,
  genres as mockGenreNames,
  type Movie,
  type Series,
} from '@/data/mockData';

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

export interface SeriesDetailResult {
  series: CatalogSeries;
  seasons: { number: number; episodeCount?: number; id?: number; status?: string }[];
  episodes: ReturnType<typeof mapEpisodeDto>[];
}

function publishedMockItems<T extends { catalogStatus?: string }>(items: T[]): T[] {
  return items.filter((item) => (item.catalogStatus ?? 'published') === 'published');
}

function filterMockMovies(params?: CatalogListParams): Movie[] {
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

function filterMockSeries(params?: CatalogListParams): Series[] {
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
  if (isMockMode()) {
    return paginateMock(filterMockMovies(params), params?.page ?? 1, params?.page_size ?? 100);
  }
  const page = await api.listMovies(params);
  return {
    items: page.items.map(mapMovieDto),
    total: page.total,
    page: page.page,
    page_size: page.page_size,
  };
}

export async function fetchMovie(idOrSlug: number | string): Promise<CatalogMovie> {
  if (isMockMode()) {
    const id = typeof idOrSlug === 'number' ? idOrSlug : Number(idOrSlug);
    const movie = publishedMockItems(mockMovies).find(
      (m) => m.id === id || String(m.id) === String(idOrSlug)
    );
    if (!movie) throw new Error('Movie not found');
    return movie;
  }
  return mapMovieDto(await api.getMovie(idOrSlug));
}

export async function fetchSeries(params?: CatalogListParams): Promise<CatalogListResult<CatalogSeries>> {
  if (isMockMode()) {
    return paginateMock(filterMockSeries(params), params?.page ?? 1, params?.page_size ?? 100);
  }
  const page = await api.listSeries(params);
  return {
    items: page.items.map(mapSeriesDto),
    total: page.total,
    page: page.page,
    page_size: page.page_size,
  };
}

export async function fetchSeriesDetail(idOrSlug: number | string): Promise<SeriesDetailResult> {
  if (isMockMode()) {
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
    return { series: show, seasons, episodes: eps };
  }

  const dto = await api.getSeries(idOrSlug);
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
  const episodesDto = await api.listEpisodes(idOrSlug);
  const episodes = [...episodesDto]
    .sort((a, b) => {
      const sa = a.season ?? 0;
      const sb = b.season ?? 0;
      if (sa !== sb) return sa - sb;
      return a.episode_number - b.episode_number;
    })
    .map(mapEpisodeDto);

  // Attach season numbers onto episodes when compatibility field missing
  const seasonById = new Map(seasonsDto.map((s) => [s.id, s.season_number]));
  for (const ep of episodes) {
    if (!ep.season && ep.seasonId) {
      ep.season = seasonById.get(ep.seasonId) ?? 0;
    }
  }

  return { series: mapped, seasons, episodes };
}

export async function fetchSearch(q: string): Promise<CatalogSearchResult> {
  if (isMockMode()) {
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
  const data = await api.search(q);
  return {
    movies: data.movies.map(mapMovieDto),
    series: data.series.map(mapSeriesDto),
  };
}

export async function fetchGenres(): Promise<{ id?: number; name: string; slug?: string }[]> {
  if (isMockMode()) {
    return mockGenreNames.map((name) => ({ name, slug: name.toLowerCase() }));
  }
  const page = await api.listGenres({ page_size: 100 });
  return page.items.map((g) => ({ id: g.id, name: g.name, slug: g.slug }));
}

export async function fetchFeaturedMovies(limit = 8): Promise<CatalogMovie[]> {
  if (isMockMode()) {
    return publishedMockItems(mockMovies).filter((m) => m.featured).slice(0, limit);
  }
  const page = await api.listMovies({ featured: true, page_size: limit, sort: 'newest' });
  return page.items.map(mapMovieDto);
}

export async function fetchTrendingMovies(limit = 12): Promise<CatalogMovie[]> {
  if (isMockMode()) {
    return publishedMockItems(mockMovies).sort((a, b) => b.views - a.views).slice(0, limit);
  }
  const page = await api.listMovies({ trending: true, page_size: limit, sort: 'views_desc' });
  if (page.items.length) return page.items.map(mapMovieDto);
  const fallback = await api.listMovies({ page_size: limit, sort: 'views_desc' });
  return fallback.items.map(mapMovieDto);
}

export async function fetchHomeCatalog() {
  if (isMockMode()) {
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
    };
  }

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
    api.listMovies({ featured: true, page_size: 8, sort: 'newest' }),
    api.listMovies({ trending: true, page_size: 12, sort: 'views_desc' }),
    api.listMovies({ page_size: 12, sort: 'newest' }),
    api.listMovies({ page_size: 12, sort: 'rating_desc' }),
    api.listMovies({ page_size: 40, sort: 'newest' }),
    api.listSeries({ page_size: 12, sort: 'views_desc' }),
    api.listMovies({ genre: 'Action', page_size: 12, sort: 'views_desc' }),
    api.listMovies({ genre: 'Comedy', page_size: 12, sort: 'views_desc' }),
  ]);

  const mapAll = (items: MovieDto[]) => items.map(mapMovieDto);
  const mapSeries = (items: SeriesDto[]) => items.map(mapSeriesDto);
  const pool = mapAll(poolPage.items);

  const trending =
    trendingPage.items.length > 0
      ? mapAll(trendingPage.items)
      : mapAll((await api.listMovies({ page_size: 12, sort: 'views_desc' })).items);

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
  };
}
