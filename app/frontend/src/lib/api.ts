/**
 * iFilm API client.
 *
 * Talks to the FastAPI backend through the Vite `/api` proxy (or VITE_API_BASE_URL).
 * Keeps a light compatibility export for the legacy MetaGPT SDK client.
 */
import axios, { type AxiosError, type AxiosInstance } from 'axios';
import { createClient } from '@metagptx/web-sdk';
import { getAPIBaseURL } from './config';

export const client = createClient();

const TOKEN_KEY = 'ifilm_access_token';
const ADMIN_TOKEN_KEY = 'ifilm_admin_token';

export const ADMIN_UNAUTHORIZED_EVENT = 'ifilm:admin-unauthorized';

export type ContentType = 'movie' | 'series' | 'episode';
export type CatalogStatus = 'draft' | 'published' | 'archived';

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface Envelope<T> {
  data: T[] | T;
  meta?: PageMeta | null;
}

/** Legacy page shape kept for transitional callers. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status = 0, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    const ax = error as AxiosError<{ detail?: unknown; message?: string }>;
    const status = ax.response?.status ?? 0;
    const detail = ax.response?.data?.detail;
    let message = ax.message || 'Request failed';
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join('; ');
    } else if (detail && typeof detail === 'object') {
      message = JSON.stringify(detail);
    } else if (ax.response?.data?.message) {
      message = ax.response.data.message;
    }
    return new ApiError(message, status, detail ?? ax.response?.data);
  }
  if (error instanceof Error) {
    return new ApiError(error.message);
  }
  return new ApiError('Unknown error');
}

export interface GenreDto {
  id: number;
  name: string;
  slug: string;
  description?: string;
  movie_count?: number;
  series_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MovieDto {
  id: number;
  title: string;
  original_title?: string;
  slug: string;
  description?: string;
  short_description?: string;
  release_year?: number | null;
  release_date?: string | null;
  duration_minutes?: number | null;
  age_rating?: string;
  language?: string;
  country?: string;
  imdb_id?: string | null;
  imdb_rating?: number | null;
  poster_url?: string;
  backdrop_url?: string;
  trailer_url?: string;
  status: CatalogStatus | string;
  is_featured?: boolean;
  is_trending?: boolean;
  published_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  genres?: GenreDto[] | string[];
  director?: string;
  cast?: string[];
  audio?: string[];
  subtitles?: string[];
  qualities?: string[];
  dubbed?: string[];
  views?: number;
  type?: 'movie' | string;
  hls_path?: string | null;
  // Compatibility aliases
  year?: number | null;
  duration?: number | null;
  rating?: number | null;
  poster?: string;
  backdrop?: string;
  featured?: boolean;
}

export interface SeriesDto {
  id: number;
  title: string;
  original_title?: string;
  slug: string;
  description?: string;
  short_description?: string;
  release_year?: number | null;
  end_year?: number | null;
  age_rating?: string;
  language?: string;
  country?: string;
  imdb_id?: string | null;
  imdb_rating?: number | null;
  poster_url?: string;
  backdrop_url?: string;
  trailer_url?: string;
  status: CatalogStatus | string;
  airing_status?: string;
  is_featured?: boolean;
  is_trending?: boolean;
  published_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  genres?: GenreDto[] | string[];
  season_count?: number;
  episode_count?: number;
  audio?: string[];
  subtitles?: string[];
  dubbed?: string[];
  new_episode?: boolean;
  views?: number;
  type?: 'series' | string;
  // Compatibility aliases
  year?: number | null;
  seasons?: number;
  episodes?: number;
  rating?: number | null;
  poster?: string;
  backdrop?: string;
  featured?: boolean;
}

export interface SeasonDto {
  id: number;
  series_id: number;
  season_number: number;
  title?: string;
  description?: string;
  poster_url?: string;
  release_year?: number | null;
  status: CatalogStatus | string;
  episode_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface EpisodeDto {
  id: number;
  season_id: number;
  series_id: number;
  episode_number: number;
  title: string;
  description?: string;
  duration_minutes?: number | null;
  release_date?: string | null;
  thumbnail_url?: string;
  status: CatalogStatus | string;
  published_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  hls_path?: string | null;
  // Compatibility
  season?: number | null;
  episode?: number | null;
  duration?: number | null;
  thumbnail?: string;
}

export interface DashboardStatsDto {
  total_movies: number;
  published_movies: number;
  draft_movies: number;
  total_series: number;
  published_series: number;
  total_seasons: number;
  total_episodes: number;
  total_genres: number;
}

export interface AdminUserDto {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role_name?: string | null;
  permissions?: string[];
}

export interface SubscriberDto {
  id: number;
  username: string;
  name: string;
  branch: string;
  status: string;
  package: string;
  expiration: string;
}

export interface StreamManifest {
  content_type: string;
  content_id: number;
  episode_id?: number | null;
  title: string;
  qualities: string[];
  playlist_url: string;
  cdn_node?: string | null;
  skip_intro_seconds: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface CatalogListParams {
  q?: string;
  genre?: string;
  year?: number;
  language?: string;
  featured?: boolean;
  trending?: boolean;
  status?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export type MovieCreatePayload = {
  title: string;
  original_title?: string;
  slug?: string | null;
  description?: string;
  short_description?: string;
  release_year?: number | null;
  release_date?: string | null;
  duration_minutes?: number | null;
  age_rating?: string;
  language?: string;
  country?: string;
  imdb_id?: string | null;
  imdb_rating?: number | null;
  poster_url?: string;
  backdrop_url?: string;
  trailer_url?: string;
  status?: string;
  is_featured?: boolean;
  is_trending?: boolean;
  genre_ids?: number[];
  director?: string;
  cast?: string[];
  audio?: string[];
  subtitles?: string[];
  qualities?: string[];
  dubbed?: string[];
};

export type MovieUpdatePayload = Partial<MovieCreatePayload> & {
  hls_path?: string | null;
};

export type SeriesCreatePayload = {
  title: string;
  original_title?: string;
  slug?: string | null;
  description?: string;
  short_description?: string;
  release_year?: number | null;
  end_year?: number | null;
  age_rating?: string;
  language?: string;
  country?: string;
  imdb_id?: string | null;
  imdb_rating?: number | null;
  poster_url?: string;
  backdrop_url?: string;
  trailer_url?: string;
  status?: string;
  airing_status?: string;
  is_featured?: boolean;
  is_trending?: boolean;
  genre_ids?: number[];
  audio?: string[];
  subtitles?: string[];
  dubbed?: string[];
  new_episode?: boolean;
};

export type SeriesUpdatePayload = Partial<SeriesCreatePayload>;

export type SeasonCreatePayload = {
  season_number: number;
  title?: string;
  description?: string;
  poster_url?: string;
  release_year?: number | null;
  status?: string;
};

export type SeasonUpdatePayload = Partial<SeasonCreatePayload>;

export type EpisodeCreatePayload = {
  episode_number: number;
  title: string;
  description?: string;
  duration_minutes?: number | null;
  release_date?: string | null;
  thumbnail_url?: string;
  status?: string;
};

export type EpisodeUpdatePayload = Partial<EpisodeCreatePayload>;

export type GenreCreatePayload = {
  name: string;
  slug?: string | null;
  description?: string;
};

export type GenreUpdatePayload = Partial<GenreCreatePayload>;

function resolveBaseURL(): string {
  const configured = getAPIBaseURL();
  if (!configured || configured === '/') {
    return '/api';
  }
  return configured.replace(/\/$/, '') + '/api';
}

function createHttp(getToken: () => string | null, options?: { onUnauthorized?: () => void }): AxiosInstance {
  const http = axios.create({
    baseURL: resolveBaseURL(),
    timeout: 15000,
  });

  http.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    config.baseURL = resolveBaseURL();
    return config;
  });

  http.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status;
      if (status === 401 && options?.onUnauthorized) {
        options.onUnauthorized();
      }
      return Promise.reject(normalizeApiError(error));
    }
  );

  return http;
}

function unwrapList<T>(envelope: Envelope<T>): Page<T> {
  if (!envelope || typeof envelope !== 'object' || !('data' in envelope)) {
    throw new ApiError('Malformed API list response', 0);
  }
  const items = Array.isArray(envelope.data) ? envelope.data : envelope.data != null ? [envelope.data] : [];
  const meta = envelope.meta;
  return {
    items,
    total: meta?.total ?? items.length,
    page: meta?.page ?? 1,
    page_size: meta?.page_size ?? items.length,
  };
}

function genreNames(genres?: GenreDto[] | string[]): string[] {
  if (!genres?.length) return [];
  return genres.map((g) => (typeof g === 'string' ? g : g.name));
}

export const tokenStore = {
  get(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
  getAdmin(): string | null {
    return localStorage.getItem(ADMIN_TOKEN_KEY);
  },
  setAdmin(token: string) {
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
  },
  clearAdmin() {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  },
};

function clearAdminAndNotify() {
  tokenStore.clearAdmin();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(ADMIN_UNAUTHORIZED_EVENT));
  }
}

const http = createHttp(() => tokenStore.get());
const adminHttp = createHttp(() => tokenStore.getAdmin(), {
  onUnauthorized: clearAdminAndNotify,
});

export const api = {
  async getConfig(): Promise<{ API_BASE_URL: string }> {
    const { data } = await http.get('/config');
    return data;
  },

  async login(username: string, password: string, rememberDevice = false) {
    const { data } = await http.post<TokenResponse>('/auth/login', {
      username,
      password,
      remember_device: rememberDevice,
    });
    tokenStore.set(data.access_token);
    return data;
  },

  async logout() {
    try {
      await http.post('/auth/logout');
    } finally {
      tokenStore.clear();
    }
  },

  async me(): Promise<SubscriberDto> {
    const { data } = await http.get<SubscriberDto>('/auth/me');
    return data;
  },

  async listMovies(params?: CatalogListParams) {
    const { data } = await http.get<Envelope<MovieDto>>('/movies', { params });
    return unwrapList(data);
  },

  async getMovie(idOrSlug: number | string) {
    const { data } = await http.get<MovieDto>(`/movies/${idOrSlug}`);
    return data;
  },

  async listSeries(params?: CatalogListParams) {
    const { data } = await http.get<Envelope<SeriesDto>>('/series', { params });
    return unwrapList(data);
  },

  async getSeries(idOrSlug: number | string) {
    const { data } = await http.get<SeriesDto>(`/series/${idOrSlug}`);
    return data;
  },

  async listSeasons(idOrSlug: number | string) {
    const { data } = await http.get<SeasonDto[]>(`/series/${idOrSlug}/seasons`);
    return data;
  },

  async listEpisodes(idOrSlug: number | string, season?: number) {
    const { data } = await http.get<EpisodeDto[]>(`/series/${idOrSlug}/episodes`, {
      params: season != null ? { season } : undefined,
    });
    return data;
  },

  async listGenres(params?: { q?: string; page?: number; page_size?: number }) {
    const { data } = await http.get<Envelope<GenreDto>>('/genres', { params });
    return unwrapList(data);
  },

  async search(q: string) {
    const { data } = await http.get<{ movies: MovieDto[]; series: SeriesDto[] }>('/search', {
      params: { q },
    });
    return data;
  },

  async getStream(contentType: ContentType, contentId: number, episodeId?: number) {
    const { data } = await http.get<StreamManifest>(`/stream/${contentType}/${contentId}`, {
      params: episodeId != null ? { episode_id: episodeId } : undefined,
    });
    return data;
  },
};

export const adminApi = {
  async login(username: string, password: string) {
    const { data } = await adminHttp.post<TokenResponse>('/admin/auth/login', {
      username,
      password,
    });
    tokenStore.setAdmin(data.access_token);
    return data;
  },

  async me(): Promise<AdminUserDto> {
    const { data } = await adminHttp.get<AdminUserDto>('/admin/auth/me');
    return data;
  },

  async dashboardStats(): Promise<DashboardStatsDto> {
    const { data } = await adminHttp.get<DashboardStatsDto>('/admin/dashboard/stats');
    return data;
  },

  async listMovies(params?: CatalogListParams) {
    const { data } = await adminHttp.get<Envelope<MovieDto>>('/admin/movies', { params });
    return unwrapList(data);
  },

  async getMovie(id: number) {
    const { data } = await adminHttp.get<MovieDto>(`/admin/movies/${id}`);
    return data;
  },

  async createMovie(payload: MovieCreatePayload) {
    const { data } = await adminHttp.post<MovieDto>('/admin/movies', payload);
    return data;
  },

  async updateMovie(id: number, payload: MovieUpdatePayload) {
    const { data } = await adminHttp.patch<MovieDto>(`/admin/movies/${id}`, payload);
    return data;
  },

  async deleteMovie(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/movies/${id}`);
    return data;
  },

  async publishMovie(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/movies/${id}/publish`);
    return data;
  },

  async unpublishMovie(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/movies/${id}/unpublish`);
    return data;
  },

  async listSeries(params?: CatalogListParams) {
    const { data } = await adminHttp.get<Envelope<SeriesDto>>('/admin/series', { params });
    return unwrapList(data);
  },

  async getSeries(id: number) {
    const { data } = await adminHttp.get<SeriesDto>(`/admin/series/${id}`);
    return data;
  },

  async createSeries(payload: SeriesCreatePayload) {
    const { data } = await adminHttp.post<SeriesDto>('/admin/series', payload);
    return data;
  },

  async updateSeries(id: number, payload: SeriesUpdatePayload) {
    const { data } = await adminHttp.patch<SeriesDto>(`/admin/series/${id}`, payload);
    return data;
  },

  async deleteSeries(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/series/${id}`);
    return data;
  },

  async publishSeries(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/series/${id}/publish`);
    return data;
  },

  async unpublishSeries(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/series/${id}/unpublish`);
    return data;
  },

  async listSeasons(seriesId: number) {
    const { data } = await adminHttp.get<SeasonDto[]>(`/admin/series/${seriesId}/seasons`);
    return data;
  },

  async createSeason(seriesId: number, payload: SeasonCreatePayload) {
    const { data } = await adminHttp.post<SeasonDto>(`/admin/series/${seriesId}/seasons`, payload);
    return data;
  },

  async getSeason(id: number) {
    const { data } = await adminHttp.get<SeasonDto>(`/admin/seasons/${id}`);
    return data;
  },

  async updateSeason(id: number, payload: SeasonUpdatePayload) {
    const { data } = await adminHttp.patch<SeasonDto>(`/admin/seasons/${id}`, payload);
    return data;
  },

  async deleteSeason(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/seasons/${id}`);
    return data;
  },

  async listEpisodes(seasonId: number) {
    const { data } = await adminHttp.get<EpisodeDto[]>(`/admin/seasons/${seasonId}/episodes`);
    return data;
  },

  async createEpisode(seasonId: number, payload: EpisodeCreatePayload) {
    const { data } = await adminHttp.post<EpisodeDto>(`/admin/seasons/${seasonId}/episodes`, payload);
    return data;
  },

  async getEpisode(id: number) {
    const { data } = await adminHttp.get<EpisodeDto>(`/admin/episodes/${id}`);
    return data;
  },

  async updateEpisode(id: number, payload: EpisodeUpdatePayload) {
    const { data } = await adminHttp.patch<EpisodeDto>(`/admin/episodes/${id}`, payload);
    return data;
  },

  async deleteEpisode(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/episodes/${id}`);
    return data;
  },

  async publishEpisode(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/episodes/${id}/publish`);
    return data;
  },

  async unpublishEpisode(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/episodes/${id}/unpublish`);
    return data;
  },

  async listGenres(params?: { q?: string; page?: number; page_size?: number }) {
    const { data } = await adminHttp.get<Envelope<GenreDto>>('/admin/genres', { params });
    return unwrapList(data);
  },

  async getGenre(id: number) {
    const { data } = await adminHttp.get<GenreDto>(`/admin/genres/${id}`);
    return data;
  },

  async createGenre(payload: GenreCreatePayload) {
    const { data } = await adminHttp.post<GenreDto>('/admin/genres', payload);
    return data;
  },

  async updateGenre(id: number, payload: GenreUpdatePayload) {
    const { data } = await adminHttp.patch<GenreDto>(`/admin/genres/${id}`, payload);
    return data;
  },

  async deleteGenre(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/genres/${id}`);
    return data;
  },

  // Placeholder tooling endpoints (not wired in catalog admin UI)
  async listEncodingJobs() {
    const { data } = await adminHttp.get('/admin/encoding/jobs');
    return data;
  },

  async listUploads() {
    const { data } = await adminHttp.get('/admin/uploads');
    return data;
  },

  async listCdnNodes() {
    const { data } = await adminHttp.get('/admin/cdn/nodes');
    return data;
  },

  async syncCdn(payload: {
    node_id?: number;
    content_type: string;
    content_id: number;
    hls_path: string;
  }) {
    const { data } = await adminHttp.post('/admin/cdn/sync', payload);
    return data;
  },
};

/** Map API movie DTO field names to the existing frontend Movie shape. */
export function mapMovieDto(dto: MovieDto) {
  const year = dto.release_year ?? dto.year ?? 0;
  const duration = dto.duration_minutes ?? dto.duration ?? 0;
  const rating = dto.imdb_rating ?? dto.rating ?? 0;
  const poster = dto.poster_url || dto.poster || '';
  const backdrop = dto.backdrop_url || dto.backdrop || '';
  const featured = dto.is_featured ?? dto.featured ?? false;

  return {
    id: dto.id,
    title: dto.title,
    originalTitle: dto.original_title || '',
    year,
    duration,
    rating,
    ageRating: dto.age_rating || '',
    genres: genreNames(dto.genres),
    country: dto.country || '',
    language: dto.language || '',
    director: dto.director || '',
    cast: dto.cast ?? [],
    description: dto.description || '',
    poster,
    backdrop,
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    qualities: dto.qualities ?? [],
    featured,
    type: 'movie' as const,
    dubbed: dto.dubbed ?? [],
    views: dto.views ?? 0,
    slug: dto.slug,
    status: dto.status,
    isTrending: dto.is_trending ?? false,
    genreIds: Array.isArray(dto.genres)
      ? dto.genres.filter((g): g is GenreDto => typeof g !== 'string').map((g) => g.id)
      : [],
  };
}

export function mapSeriesDto(dto: SeriesDto) {
  const year = dto.release_year ?? dto.year ?? 0;
  const rating = dto.imdb_rating ?? dto.rating ?? 0;
  const poster = dto.poster_url || dto.poster || '';
  const backdrop = dto.backdrop_url || dto.backdrop || '';
  const seasons = dto.season_count ?? dto.seasons ?? 0;
  const episodes = dto.episode_count ?? dto.episodes ?? 0;
  const airing = (dto.airing_status || 'Ongoing') as 'Ongoing' | 'Completed' | 'Upcoming';

  return {
    id: dto.id,
    title: dto.title,
    originalTitle: dto.original_title || '',
    year,
    rating,
    ageRating: dto.age_rating || '',
    genres: genreNames(dto.genres),
    country: dto.country || '',
    language: dto.language || '',
    seasons,
    episodes,
    status: airing,
    description: dto.description || '',
    poster,
    backdrop,
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    dubbed: dto.dubbed ?? [],
    type: 'series' as const,
    newEpisode: dto.new_episode ?? false,
    views: dto.views ?? 0,
    slug: dto.slug,
    catalogStatus: dto.status,
    isFeatured: dto.is_featured ?? dto.featured ?? false,
    isTrending: dto.is_trending ?? false,
    genreIds: Array.isArray(dto.genres)
      ? dto.genres.filter((g): g is GenreDto => typeof g !== 'string').map((g) => g.id)
      : [],
  };
}

export function mapEpisodeDto(dto: EpisodeDto) {
  return {
    id: dto.id,
    seriesId: dto.series_id,
    seasonId: dto.season_id,
    season: dto.season ?? 0,
    episode: dto.episode_number ?? dto.episode ?? 0,
    title: dto.title,
    duration: dto.duration_minutes ?? dto.duration ?? 0,
    description: dto.description || '',
    thumbnail: dto.thumbnail_url || dto.thumbnail || '',
    status: dto.status,
  };
}

export function mapSeasonDto(dto: SeasonDto) {
  return {
    id: dto.id,
    seriesId: dto.series_id,
    seasonNumber: dto.season_number,
    title: dto.title || '',
    description: dto.description || '',
    poster: dto.poster_url || '',
    releaseYear: dto.release_year ?? null,
    status: dto.status,
    episodeCount: dto.episode_count ?? 0,
  };
}
