/**
 * iFilm API client.
 *
 * Talks to the FastAPI backend through the Vite `/api` proxy (or VITE_API_BASE_URL).
 * Keeps a light compatibility export for the legacy MetaGPT SDK client.
 */
import axios, { type AxiosInstance } from 'axios';
import { createClient } from '@metagptx/web-sdk';
import { getAPIBaseURL } from './config';

export const client = createClient();

const TOKEN_KEY = 'ifilm_access_token';
const ADMIN_TOKEN_KEY = 'ifilm_admin_token';

export type ContentType = 'movie' | 'series' | 'episode';

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MovieDto {
  id: number;
  title: string;
  original_title: string;
  year: number;
  duration: number;
  rating: number;
  age_rating: string;
  genres: string[];
  country: string;
  language: string;
  director: string;
  cast: string[];
  description: string;
  poster: string;
  backdrop: string;
  audio: string[];
  subtitles: string[];
  qualities: string[];
  dubbed: string[];
  featured: boolean;
  views: number;
  type: 'movie';
  hls_path?: string | null;
}

export interface SeriesDto {
  id: number;
  title: string;
  original_title: string;
  year: number;
  rating: number;
  age_rating: string;
  genres: string[];
  country: string;
  language: string;
  seasons: number;
  episode_count: number;
  episodes: number;
  status: string;
  description: string;
  poster: string;
  backdrop: string;
  audio: string[];
  subtitles: string[];
  dubbed: string[];
  new_episode: boolean;
  views: number;
  type: 'series';
}

export interface EpisodeDto {
  id: number;
  series_id: number;
  season: number;
  episode: number;
  title: string;
  duration: number;
  description: string;
  thumbnail: string;
  hls_path?: string | null;
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

function resolveBaseURL(): string {
  const configured = getAPIBaseURL();
  // Empty or "/" => same-origin (Vite proxies /api -> backend).
  if (!configured || configured === '/') {
    return '/api';
  }
  return configured.replace(/\/$/, '') + '/api';
}

function createHttp(getToken: () => string | null): AxiosInstance {
  const http = axios.create({
    baseURL: resolveBaseURL(),
    timeout: 15000,
  });

  http.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    // Re-resolve base URL after runtime config loads.
    config.baseURL = resolveBaseURL();
    return config;
  });

  return http;
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

const http = createHttp(() => tokenStore.get());
const adminHttp = createHttp(() => tokenStore.getAdmin());

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

  async listMovies(params?: {
    q?: string;
    genre?: string;
    sort?: string;
    page?: number;
    page_size?: number;
  }) {
    const { data } = await http.get<Page<MovieDto>>('/movies', { params });
    return data;
  },

  async getMovie(id: number) {
    const { data } = await http.get<MovieDto>(`/movies/${id}`);
    return data;
  },

  async listSeries(params?: { q?: string; genre?: string; page?: number; page_size?: number }) {
    const { data } = await http.get<Page<SeriesDto>>('/series', { params });
    return data;
  },

  async getSeries(id: number) {
    const { data } = await http.get<SeriesDto>(`/series/${id}`);
    return data;
  },

  async listEpisodes(seriesId: number, season?: number) {
    const { data } = await http.get<EpisodeDto[]>(`/series/${seriesId}/episodes`, {
      params: season != null ? { season } : undefined,
    });
    return data;
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

  async me() {
    const { data } = await adminHttp.get('/admin/auth/me');
    return data;
  },

  async createMovie(payload: Partial<MovieDto> & { title: string }) {
    const { data } = await adminHttp.post('/admin/movies', payload);
    return data;
  },

  async updateMovie(id: number, payload: Record<string, unknown>) {
    const { data } = await adminHttp.patch(`/admin/movies/${id}`, payload);
    return data;
  },

  async deleteMovie(id: number) {
    const { data } = await adminHttp.delete(`/admin/movies/${id}`);
    return data;
  },

  async createSeries(payload: Partial<SeriesDto> & { title: string }) {
    const { data } = await adminHttp.post('/admin/series', payload);
    return data;
  },

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
  return {
    id: dto.id,
    title: dto.title,
    originalTitle: dto.original_title,
    year: dto.year,
    duration: dto.duration,
    rating: dto.rating,
    ageRating: dto.age_rating,
    genres: dto.genres ?? [],
    country: dto.country,
    language: dto.language,
    director: dto.director,
    cast: dto.cast ?? [],
    description: dto.description,
    poster: dto.poster,
    backdrop: dto.backdrop,
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    qualities: dto.qualities ?? [],
    featured: dto.featured,
    type: 'movie' as const,
    dubbed: dto.dubbed ?? [],
    views: dto.views,
  };
}

export function mapSeriesDto(dto: SeriesDto) {
  return {
    id: dto.id,
    title: dto.title,
    originalTitle: dto.original_title,
    year: dto.year,
    rating: dto.rating,
    ageRating: dto.age_rating,
    genres: dto.genres ?? [],
    country: dto.country,
    language: dto.language,
    seasons: dto.seasons,
    episodes: dto.episodes ?? dto.episode_count,
    status: dto.status as 'Ongoing' | 'Completed' | 'Upcoming',
    description: dto.description,
    poster: dto.poster,
    backdrop: dto.backdrop,
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    dubbed: dto.dubbed ?? [],
    type: 'series' as const,
    newEpisode: dto.new_episode,
    views: dto.views,
  };
}
