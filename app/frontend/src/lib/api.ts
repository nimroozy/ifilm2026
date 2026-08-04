/**
 * iFilm API client.
 *
 * Talks to the FastAPI backend through the Vite `/api` proxy (or VITE_API_BASE_URL).
 * Keeps a light compatibility export for the legacy MetaGPT SDK client.
 */
import axios, { type AxiosError, type AxiosInstance } from 'axios';
import { createClient } from '@metagptx/web-sdk';
import { getAPIBaseURL, type RuntimeConfig } from './config';

export const client = createClient();

const TOKEN_KEY = 'ifilm_access_token';
const REFRESH_TOKEN_KEY = 'ifilm_refresh_token';
const DEVICE_ID_KEY = 'ifilm_device_id';
const ADMIN_TOKEN_KEY = 'ifilm_admin_token';

export const ADMIN_UNAUTHORIZED_EVENT = 'ifilm:admin-unauthorized';

export type ContentType = 'movie' | 'series' | 'episode';
export type CatalogEntityType = 'movie' | 'series' | 'season' | 'episode';
export type CatalogStatus =
  | 'draft'
  | 'in_review'
  | 'approved'
  | 'scheduled'
  | 'published'
  | 'unpublished'
  | 'archived';

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
  tmdb_id?: number | null;
  metadata_source?: string;
  demo_owned?: boolean;
  poster_url?: string;
  backdrop_url?: string;
  logo_url?: string;
  trailer_url?: string;
  spoken_languages?: unknown[];
  trailer_provider?: string;
  trailer_key?: string;
  trailer_title?: string;
  trailer_official?: boolean;
  trailer_language?: string;
  trailer_published_at?: string | null;
  has_demo_clip?: boolean;
  status: CatalogStatus | string;
  is_featured?: boolean;
  is_trending?: boolean;
  published_at?: string | null;
  scheduled_publish_at?: string | null;
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
  tmdb_id?: number | null;
  metadata_source?: string;
  demo_owned?: boolean;
  poster_url?: string;
  backdrop_url?: string;
  logo_url?: string;
  trailer_url?: string;
  spoken_languages?: unknown[];
  trailer_provider?: string;
  trailer_key?: string;
  trailer_title?: string;
  trailer_official?: boolean;
  trailer_language?: string;
  trailer_published_at?: string | null;
  has_demo_clip?: boolean;
  status: CatalogStatus | string;
  airing_status?: string;
  is_featured?: boolean;
  is_trending?: boolean;
  published_at?: string | null;
  scheduled_publish_at?: string | null;
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
  scheduled_publish_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface EpisodeDto {
  id: number;
  season_id: number;
  series_id: number;
  episode_number: number;
  tmdb_id?: number | null;
  metadata_source?: string;
  demo_owned?: boolean;
  has_demo_clip?: boolean;
  title: string;
  description?: string;
  duration_minutes?: number | null;
  release_date?: string | null;
  thumbnail_url?: string;
  status: CatalogStatus | string;
  published_at?: string | null;
  scheduled_publish_at?: string | null;
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
  service_status?: string;
  max_devices?: number;
  identity_provider?: string;
  external_subject?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
}

export interface EntitlementDto {
  allowed: boolean;
  account_status: string;
  service_status: string;
  package_name: string;
  branch_code: string;
  valid_from?: string | null;
  valid_until?: string | null;
  denial_code?: string | null;
  safe_reason?: string | null;
  max_devices: number;
  source: string;
  checked_at?: string | null;
  from_cache?: boolean;
}

export interface DeviceDto {
  id: number;
  client_device_id: string;
  name: string;
  device_type: string;
  browser: string;
  ip: string;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  current?: boolean;
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
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
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
};

export type SeasonUpdatePayload = Partial<SeasonCreatePayload>;

export type EpisodeCreatePayload = {
  episode_number: number;
  title: string;
  description?: string;
  duration_minutes?: number | null;
  release_date?: string | null;
  thumbnail_url?: string;
};

export type EpisodeUpdatePayload = Partial<EpisodeCreatePayload>;

export type GenreCreatePayload = {
  name: string;
  slug?: string | null;
  description?: string;
};

export type GenreUpdatePayload = Partial<GenreCreatePayload>;

export type MediaCategory = 'originals' | 'posters' | 'backdrops' | 'trailers' | 'subtitles';

export interface MediaAssetDto {
  id: string;
  movie_id: number | null;
  series_id: number | null;
  season_id: number | null;
  episode_id: number | null;
  original_filename: string;
  stored_filename: string;
  mime_type: string;
  extension: string;
  size_bytes: number;
  checksum_sha256: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  storage_backend: string;
  storage_path: string | null;
  category: MediaCategory | string;
  upload_status: string;
  processing_status: string;
  container_format?: string | null;
  overall_bitrate?: number | null;
  video_codec?: string | null;
  video_profile?: string | null;
  display_aspect_ratio?: string | null;
  video_frame_rate?: number | null;
  video_bitrate?: number | null;
  pixel_format?: string | null;
  audio_codec?: string | null;
  audio_channels?: number | null;
  audio_channel_layout?: string | null;
  audio_sample_rate?: number | null;
  audio_bitrate?: number | null;
  audio_stream_count?: number | null;
  subtitle_stream_count?: number | null;
  probe_json?: Record<string, unknown> | null;
  probe_version?: string | null;
  probed_at?: string | null;
  created_by_admin_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProcessingJobDto {
  id: string;
  media_asset_id: string;
  job_type: string;
  status: string;
  priority: number;
  attempt_count: number;
  max_attempts: number;
  progress_percent: number;
  current_step: string | null;
  error_code: string | null;
  error_message: string | null;
  worker_id: string | null;
  cancel_requested: boolean;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  heartbeat_at?: string | null;
  next_retry_at?: string | null;
  created_by_admin_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  media_asset?: MediaAssetDto | null;
}

export interface EncodingProfileDto {
  id: string;
  name: string;
  label: string;
  height: number;
  video_bitrate: number;
  audio_bitrate: number;
  maxrate: number;
  bufsize: number;
  video_codec: string;
  audio_codec: string;
  video_profile: string;
  preset: string;
  enabled: boolean;
  sort_order: number;
}

export interface MediaRenditionDto {
  id: string;
  package_id: string;
  profile_id: string | null;
  label: string;
  height: number;
  width: number | null;
  bandwidth: number | null;
  average_bandwidth: number | null;
  playlist_path: string | null;
  segment_count: number;
  video_codec: string | null;
  audio_codec: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MediaPackageDto {
  id: string;
  media_asset_id: string;
  processing_job_id: string | null;
  package_type: string;
  status: string;
  is_active?: boolean;
  activated_at?: string | null;
  superseded_at?: string | null;
  storage_path: string | null;
  master_playlist_path: string | null;
  source_width: number | null;
  source_height: number | null;
  duration_seconds: number | null;
  segment_duration_seconds: number;
  rendition_count: number;
  error_code: string | null;
  error_message: string | null;
  created_by_admin_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  renditions: MediaRenditionDto[];
}

export interface PlaybackSessionDto {
  id: string;
  media_asset_id: string;
  media_package_id: string;
  principal_type: string;
  principal_id: string;
  status: string;
  expires_at: string;
  revoked_at?: string | null;
  created_at?: string | null;
  last_accessed_at?: string | null;
  created_by_admin_id?: number | null;
  client_ip?: string | null;
  user_agent?: string | null;
  revoke_reason?: string | null;
  access_count: number;
}

export interface PlaybackSessionCreatedDto {
  id: string;
  media_asset_id: string;
  media_package_id: string;
  expires_at: string;
  playback_token: string;
  master_playlist_url: string;
}

export type TmdbMediaType = 'movie' | 'series';

export interface TmdbSearchResultDto {
  id: number;
  title?: string;
  name?: string;
  original_title?: string;
  original_name?: string;
  overview?: string;
  release_date?: string;
  first_air_date?: string;
  poster_path?: string | null;
  backdrop_path?: string | null;
  vote_average?: number;
  original_language?: string;
}

export interface TmdbSearchResponseDto {
  page: number;
  results: TmdbSearchResultDto[];
  total_pages?: number;
  total_results?: number;
}

export interface TmdbTrailerDto {
  provider?: string;
  key?: string;
  title?: string;
  name?: string;
  official?: boolean;
  language?: string;
  iso_639_1?: string;
  published_at?: string | null;
  embed_url?: string;
  site?: string;
  type?: string;
}

export interface TmdbTranslationDto {
  iso_3166_1?: string;
  iso_639_1?: string;
  name?: string;
  english_name?: string;
  data?: {
    title?: string;
    name?: string;
    overview?: string;
    homepage?: string;
    tagline?: string;
  };
}

export interface TmdbPreviewDto {
  id: number;
  title?: string;
  name?: string;
  original_title?: string;
  original_name?: string;
  overview?: string;
  release_date?: string;
  first_air_date?: string;
  runtime?: number | null;
  number_of_seasons?: number;
  number_of_episodes?: number;
  vote_average?: number;
  poster_path?: string | null;
  backdrop_path?: string | null;
  images?: {
    posters?: Array<{ file_path?: string; iso_639_1?: string | null }>;
    backdrops?: Array<{ file_path?: string; iso_639_1?: string | null }>;
    logos?: Array<{ file_path?: string; iso_639_1?: string | null }>;
  };
  translations?: {
    translations?: TmdbTranslationDto[];
  };
  videos?: {
    results?: TmdbTrailerDto[];
  };
  selected_trailer?: TmdbTrailerDto | null;
}

export interface TmdbImportResultDto {
  media_type: TmdbMediaType;
  entity_id: number;
  tmdb_id: number;
  created: boolean;
  artwork_files?: string[];
  episode_ids?: number[];
  season_ids?: number[];
}

export interface TmdbImportResponseDto {
  result: TmdbImportResultDto;
  item: MovieDto | SeriesDto;
}

export interface TmdbRefreshResponseDto {
  refreshed: number;
  results: TmdbImportResultDto[];
}

export interface TmdbArtworkReplaceResponseDto {
  changed: Record<string, string>;
}

export interface WatchProgressDto {
  id: number;
  media_asset_id: string;
  content_type: 'movie' | 'episode';
  movie_id?: number | null;
  episode_id?: number | null;
  series_id?: number | null;
  season_number?: number | null;
  episode_number?: number | null;
  title: string;
  subtitle?: string;
  poster_url?: string;
  position_seconds: number;
  duration_seconds: number;
  progress_percent: number;
  completed: boolean;
  available: boolean;
  player_path: string;
  first_watched_at?: string | null;
  last_watched_at?: string | null;
  completed_at?: string | null;
  last_event_at?: string | null;
}

export interface WatchProgressUpdate {
  position_seconds: number;
  duration_seconds?: number;
  playback_session_id?: string;
  event_at: string;
  start_over?: boolean;
}

export interface WatchProgressActionDto {
  detail: string;
  deleted: number;
}

export interface StreamingStatusDto {
  enabled: boolean;
  supported_principals: string[];
  subscriber_entitlement: string;
}

export interface SystemVersionDto {
  version: string;
  build_commit: string;
  build_date?: string | null;
  migration_head?: string | null;
  deployment_mode: string;
  update_channel: string;
  maintenance_mode: boolean;
}

export interface SystemUpdateCheckDto {
  update_available: boolean;
  channel: string;
  current: Record<string, unknown>;
  latest: {
    version?: string;
    tag?: string;
    published_at?: string;
    notes?: string;
    prerelease?: boolean;
    migration_head?: string;
    database_backup_required?: boolean;
  } | null;
}

export interface SystemPreflightDto {
  ok: boolean;
  checks: Array<{ name: string; passed: boolean; detail?: string }>;
  checked_at?: string | null;
}

export interface SystemUpdateJobDto {
  id: string;
  state: string;
  channel: string;
  current_version?: string | null;
  target_version?: string | null;
  actor_admin_id?: number | null;
  backup_id?: string | null;
  previous_migration_head?: string | null;
  resulting_migration_head?: string | null;
  release_commit_sha?: string | null;
  preflight_ok?: boolean | null;
  error_code?: string | null;
  error_message?: string | null;
  rollback_result?: string | null;
  agent_job_id?: string | null;
  started_at: string;
  finished_at?: string | null;
  events?: Array<{ event_type: string; detail?: string | null; created_at?: string | null }>;
}

export interface PublicationReadinessIssueDto {
  code: string;
  message: string;
  field?: string | null;
}

export interface PublicationReadinessDto {
  entity_type: CatalogEntityType;
  entity_id: number;
  status: CatalogStatus;
  ready: boolean;
  playable: boolean;
  active_package_id?: string | null;
  package_status?: string | null;
  issues: PublicationReadinessIssueDto[];
  allowed_actions: string[];
  submitted_for_review_at?: string | null;
  submitted_for_review_by?: number | null;
  approved_at?: string | null;
  approved_by?: number | null;
  published_at?: string | null;
  published_by?: number | null;
  scheduled_publish_at?: string | null;
  unpublished_at?: string | null;
  unpublished_by?: number | null;
  archived_at?: string | null;
  archived_by?: number | null;
  publication_version: number;
}

export interface PublicationHistoryEventDto {
  id: number;
  entity_type: CatalogEntityType | string;
  entity_id: number;
  from_status: CatalogStatus | string;
  to_status: CatalogStatus | string;
  actor_user_id?: number | null;
  reason?: string | null;
  event_type: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface PublicationActionDto {
  detail: string;
  entity_type: CatalogEntityType;
  entity_id: number;
  status: CatalogStatus;
  scheduled_publish_at?: string | null;
  publication_version: number;
}

export type CustomerPlaybackSessionRequest =
  | { media_asset_id: string; content_type?: never; content_id?: never }
  | { media_asset_id?: never; content_type: 'movie' | 'episode'; content_id: number };


export interface EncodeJobCreateResult {
  job: ProcessingJobDto;
  package: MediaPackageDto;
  created: boolean;
}

export interface ProcessingJobCreateResult {
  job: ProcessingJobDto;
  created: boolean;
}

export interface ProcessingStatusDto {
  enabled: boolean;
  hls_encoding_enabled: boolean;
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
}

export interface UploadSessionDto {
  id: string;
  media_asset_id: string;
  expected_size_bytes: number;
  bytes_received: number;
  status: string;
  progress_percent: number;
  error: string | null;
  expires_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  media_asset?: MediaAssetDto | null;
}

export interface UploadSessionCreatePayload {
  filename: string;
  mime_type: string;
  size_bytes: number;
  category?: MediaCategory;
  movie_id?: number | null;
  series_id?: number | null;
  season_id?: number | null;
  episode_id?: number | null;
}

export interface UploadSessionCreateResult {
  session: UploadSessionDto;
  media_asset: MediaAssetDto;
}

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
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setRefresh(token: string) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
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

/** Application-generated stable device id (not a browser fingerprint). */
export function getOrCreateDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 32)
        : `dev${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export function clearSensitiveAuthState() {
  tokenStore.clear();
}

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
  async getConfig(): Promise<RuntimeConfig> {
    const { data } = await http.get('/config');
    return data;
  },

  async login(username: string, password: string, rememberDevice = false) {
    const { data } = await http.post<TokenResponse>('/auth/subscriber/login', {
      username,
      password,
      remember_device: rememberDevice,
      device_id: getOrCreateDeviceId(),
      device_name: typeof navigator !== 'undefined' ? navigator.platform || 'Web' : 'Web',
      device_type: 'desktop',
      browser: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 100) : '',
    });
    tokenStore.set(data.access_token);
    if (data.refresh_token) tokenStore.setRefresh(data.refresh_token);
    return data;
  },

  async refresh() {
    const refresh = tokenStore.getRefresh();
    if (!refresh) throw new ApiError('No refresh token', 401);
    const { data } = await http.post<TokenResponse>('/auth/subscriber/refresh', {
      refresh_token: refresh,
    });
    tokenStore.set(data.access_token);
    if (data.refresh_token) tokenStore.setRefresh(data.refresh_token);
    return data;
  },

  async logout() {
    try {
      await http.post('/auth/subscriber/logout', {
        refresh_token: tokenStore.getRefresh(),
      });
    } finally {
      clearSensitiveAuthState();
    }
  },

  async me(): Promise<SubscriberDto> {
    const { data } = await http.get<SubscriberDto>('/me');
    return data;
  },

  async entitlement(): Promise<EntitlementDto> {
    const { data } = await http.get<EntitlementDto>('/me/entitlement');
    return data;
  },

  async listDevices(): Promise<DeviceDto[]> {
    const { data } = await http.get<DeviceDto[]>('/me/devices');
    return data;
  },

  async revokeDevice(id: number) {
    const { data } = await http.delete<{ detail: string }>(`/me/devices/${id}`);
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

  async createPlaybackSession(body: CustomerPlaybackSessionRequest) {
    const { data } = await http.post<PlaybackSessionCreatedDto>('/playback/sessions', body);
    return data;
  },

  async revokePlaybackSession(sessionId: string) {
    const { data } = await http.post<PlaybackSessionDto>(`/playback/sessions/${sessionId}/revoke`);
    return data;
  },

  async putWatchProgress(assetId: string, body: WatchProgressUpdate) {
    const { data } = await http.put<WatchProgressDto>(`/me/watch-progress/${assetId}`, body);
    return data;
  },

  async getWatchProgress(assetId: string) {
    const { data } = await http.get<WatchProgressDto>(`/me/watch-progress/${assetId}`);
    return data;
  },

  async listContinueWatching() {
    const { data } = await http.get<WatchProgressDto[]>('/me/continue-watching');
    return data;
  },

  async listWatchHistory(params?: { page?: number; page_size?: number }) {
    const { data } = await http.get<Envelope<WatchProgressDto>>('/me/watch-history', { params });
    return unwrapList(data);
  },

  async deleteWatchHistoryItem(assetId: string) {
    const { data } = await http.delete<WatchProgressActionDto>(`/me/watch-history/${assetId}`);
    return data;
  },

  async clearWatchHistory() {
    const { data } = await http.delete<WatchProgressActionDto>('/me/watch-history');
    return data;
  },

  async completeWatchProgress(assetId: string, body: WatchProgressUpdate) {
    const { data } = await http.post<WatchProgressDto>(`/me/watch-progress/${assetId}/complete`, body);
    return data;
  },

  async getStreamingStatus() {
    const { data } = await http.get<StreamingStatusDto>('/streaming/status');
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

  async getPublicationReadiness(entityType: CatalogEntityType, id: number) {
    const { data } = await adminHttp.get<PublicationReadinessDto>(
      `/admin/catalog/${entityType}/${id}/publication-readiness`
    );
    return data;
  },

  async getPublicationHistory(entityType: CatalogEntityType, id: number) {
    const { data } = await adminHttp.get<PublicationHistoryEventDto[]>(
      `/admin/catalog/${entityType}/${id}/publication-history`
    );
    return data;
  },

  async submitReview(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/submit-review`,
      { reason }
    );
    return data;
  },

  async approve(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/approve`,
      { reason }
    );
    return data;
  },

  async publish(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/publish`,
      { reason }
    );
    return data;
  },

  async schedule(
    entityType: CatalogEntityType,
    id: number,
    scheduledPublishAt: string,
    reason?: string
  ) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/schedule`,
      { scheduled_publish_at: scheduledPublishAt, reason }
    );
    return data;
  },

  async unpublish(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/unpublish`,
      { reason }
    );
    return data;
  },

  async archive(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/archive`,
      { reason }
    );
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

  async searchTmdb(params: { query: string; media_type: TmdbMediaType; page?: number }) {
    const { data } = await adminHttp.get<TmdbSearchResponseDto>('/admin/tools/tmdb/search', {
      params: {
        query: params.query,
        media_type: params.media_type,
        page: params.page ?? 1,
      },
    });
    return data;
  },

  async previewTmdb(payload: { tmdb_id: number; media_type: TmdbMediaType }) {
    const { data } = await adminHttp.post<TmdbPreviewDto>('/admin/tools/tmdb/preview', payload);
    return data;
  },

  async importTmdbDraft(payload: { tmdb_id: number; media_type: TmdbMediaType; force?: boolean }) {
    const { data } = await adminHttp.post<TmdbImportResponseDto>('/admin/tools/tmdb/import', {
      ...payload,
      force: payload.force ?? false,
    });
    return data;
  },

  async refreshTmdbDemo(payload?: { force?: boolean }) {
    const { data } = await adminHttp.post<TmdbRefreshResponseDto>('/admin/tools/tmdb/refresh', {
      force: payload?.force ?? false,
    });
    return data;
  },

  async replaceTmdbArtwork(payload: {
    media_type: TmdbMediaType;
    entity_id: number;
    kinds: Array<'poster' | 'backdrop' | 'logo'>;
  }) {
    const { data } = await adminHttp.post<TmdbArtworkReplaceResponseDto>(
      '/admin/tools/tmdb/artwork/replace',
      payload
    );
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

  async createMediaUploadSession(payload: UploadSessionCreatePayload) {
    const { data } = await adminHttp.post<UploadSessionCreateResult>('/admin/media/sessions', payload);
    return data;
  },

  async uploadMediaSessionFile(
    sessionId: string,
    file: File,
    onUploadProgress?: (pct: number) => void,
    options?: { offset?: number; complete?: boolean }
  ) {
    const form = new FormData();
    form.append('file', file);
    const offset = options?.offset ?? 0;
    const complete = options?.complete ?? true;
    const { data } = await adminHttp.put<UploadSessionDto>(`/admin/media/sessions/${sessionId}`, form, {
      headers: {
        // Let the browser/axios set multipart boundary — do not force Content-Type.
        'Upload-Offset': String(offset),
        'Upload-Complete': complete ? 'true' : 'false',
      },
      timeout: 0,
      onUploadProgress: (event) => {
        if (!onUploadProgress || !event.total) return;
        onUploadProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)));
      },
    });
    return data;
  },

  async getMediaUploadSession(sessionId: string) {
    const { data } = await adminHttp.get<UploadSessionDto>(`/admin/media/sessions/${sessionId}`);
    return data;
  },

  async cancelMediaUploadSession(sessionId: string) {
    const { data } = await adminHttp.delete<UploadSessionDto>(`/admin/media/sessions/${sessionId}`);
    return data;
  },

  async listMediaAssets(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    movie_id?: number;
    episode_id?: number;
    unassigned?: boolean;
    category?: string;
    q?: string;
    video_only?: boolean;
    linkable_only?: boolean;
  }) {
    const { data } = await adminHttp.get<Envelope<MediaAssetDto>>('/admin/media/assets', { params });
    return unwrapList(data);
  },

  async getMediaAsset(assetId: string) {
    const { data } = await adminHttp.get<MediaAssetDto>(`/admin/media/assets/${assetId}`);
    return data;
  },

  async linkMediaAsset(assetId: string, payload: { owner_type: 'movie' | 'episode'; owner_id: number }) {
    const { data } = await adminHttp.post<MediaAssetDto>(`/admin/media/assets/${assetId}/link`, payload);
    return data;
  },

  async detachMediaAsset(assetId: string, payload?: { force_unpublish?: boolean }) {
    const { data } = await adminHttp.post<MediaAssetDto>(
      `/admin/media/assets/${assetId}/detach`,
      payload ?? {}
    );
    return data;
  },

  async getProcessingStatus() {
    const { data } = await adminHttp.get<ProcessingStatusDto>('/admin/media/processing/status');
    return data;
  },

  async queueMediaProbe(assetId: string) {
    const { data } = await adminHttp.post<ProcessingJobCreateResult>(
      `/admin/media/assets/${assetId}/processing/probe`
    );
    return data;
  },

  async queueMediaEncodeHls(assetId: string) {
    const { data } = await adminHttp.post<EncodeJobCreateResult>(
      `/admin/media/assets/${assetId}/processing/encode-hls`
    );
    return data;
  },

  async listAssetProcessingJobs(assetId: string) {
    const { data } = await adminHttp.get<Envelope<ProcessingJobDto>>(
      `/admin/media/assets/${assetId}/processing`
    );
    return unwrapList(data);
  },

  async listAssetPackages(assetId: string) {
    const { data } = await adminHttp.get<Envelope<MediaPackageDto>>(
      `/admin/media/assets/${assetId}/packages`
    );
    return unwrapList(data);
  },

  async getMediaPackage(packageId: string) {
    const { data } = await adminHttp.get<MediaPackageDto>(`/admin/media/packages/${packageId}`);
    return data;
  },

  async listEncodingProfiles() {
    const { data } = await adminHttp.get<Envelope<EncodingProfileDto>>(
      '/admin/media/encoding/profiles'
    );
    return unwrapList(data);
  },

  async listProcessingJobs(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    job_type?: string;
    media_asset_id?: string;
  }) {
    const { data } = await adminHttp.get<Envelope<ProcessingJobDto>>('/admin/media/processing/jobs', {
      params,
    });
    return unwrapList(data);
  },

  async getProcessingJob(jobId: string) {
    const { data } = await adminHttp.get<ProcessingJobDto>(`/admin/media/processing/jobs/${jobId}`);
    return data;
  },

  async retryProcessingJob(jobId: string) {
    const { data } = await adminHttp.post<ProcessingJobDto>(
      `/admin/media/processing/jobs/${jobId}/retry`
    );
    return data;
  },

  async cancelProcessingJob(jobId: string) {
    const { data } = await adminHttp.delete<ProcessingJobDto>(
      `/admin/media/processing/jobs/${jobId}`
    );
    return data;
  },

  async getStreamingStatus() {
    const { data } = await adminHttp.get<StreamingStatusDto>('/streaming/status');
    return data;
  },

  async listPlaybackSessions(params?: {
    page?: number;
    page_size?: number;
    media_asset_id?: string;
    media_package_id?: string;
    principal_type?: string;
    principal_id?: string;
    status?: string;
  }) {
    const { data } = await adminHttp.get<Envelope<PlaybackSessionDto>>('/admin/playback/sessions', {
      params,
    });
    return unwrapList(data);
  },

  async createPlaybackSession(mediaAssetId: string) {
    const { data } = await adminHttp.post<PlaybackSessionCreatedDto>('/admin/playback/sessions', {
      media_asset_id: mediaAssetId,
    });
    return data;
  },

  /** Same /playback/sessions endpoint; sends admin JWT for ops tests. */
  async createPlayerPlaybackSession(body: CustomerPlaybackSessionRequest) {
    const { data } = await adminHttp.post<PlaybackSessionCreatedDto>('/playback/sessions', body);
    return data;
  },

  async revokePlaybackSession(sessionId: string) {
    const { data } = await adminHttp.post<PlaybackSessionDto>(
      `/admin/playback/sessions/${sessionId}/revoke`
    );
    return data;
  },

  async revokePlaybackSessionsForAsset(mediaAssetId: string) {
    const { data } = await adminHttp.post<{ revoked: number }>(
      '/admin/playback/sessions/revoke-asset',
      null,
      { params: { media_asset_id: mediaAssetId } }
    );
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

  async getSystemVersion() {
    const { data } = await adminHttp.get<SystemVersionDto>('/admin/system/version');
    return data;
  },

  async checkSystemUpdates() {
    const { data } = await adminHttp.post<SystemUpdateCheckDto>('/admin/system/updates/check');
    return data;
  },

  async runSystemUpdatePreflight() {
    const { data } = await adminHttp.post<SystemPreflightDto>('/admin/system/updates/preflight');
    return data;
  },

  async createSystemUpdateBackup(password: string) {
    const { data } = await adminHttp.post<{ backup_id: string; created_at?: string; validated: boolean }>(
      '/admin/system/updates/backup',
      { password, confirm: true }
    );
    return data;
  },

  async installSystemUpdate(payload: { password: string; confirm: boolean; target_version?: string }) {
    const { data } = await adminHttp.post<SystemUpdateJobDto>('/admin/system/updates/install', payload);
    return data;
  },

  async getSystemUpdateJob(jobId: string) {
    const { data } = await adminHttp.get<SystemUpdateJobDto>(`/admin/system/updates/${jobId}`);
    return data;
  },

  async rollbackSystemUpdate(
    jobId: string,
    payload: { password: string; confirm: boolean; confirm_database_restore?: boolean }
  ) {
    const { data } = await adminHttp.post<SystemUpdateJobDto>(
      `/admin/system/updates/${jobId}/rollback`,
      payload
    );
    return data;
  },

  async listSystemUpdateHistory(limit = 50) {
    const { data } = await adminHttp.get<{ items: SystemUpdateJobDto[]; total: number }>(
      '/admin/system/updates/history',
      { params: { limit } }
    );
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
    tmdbId: dto.tmdb_id ?? null,
    metadataSource: dto.metadata_source || '',
    demoOwned: dto.demo_owned ?? false,
    hasDemoClip: dto.has_demo_clip ?? false,
    trailerUrl: dto.trailer_url || '',
    trailerProvider: dto.trailer_provider || '',
    trailerKey: dto.trailer_key || '',
    trailerTitle: dto.trailer_title || '',
    trailerOfficial: dto.trailer_official ?? false,
    trailerLanguage: dto.trailer_language || '',
    trailerPublishedAt: dto.trailer_published_at ?? null,
    hlsPath: dto.hls_path ?? null,
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
    tmdbId: dto.tmdb_id ?? null,
    metadataSource: dto.metadata_source || '',
    demoOwned: dto.demo_owned ?? false,
    hasDemoClip: dto.has_demo_clip ?? false,
    trailerUrl: dto.trailer_url || '',
    trailerProvider: dto.trailer_provider || '',
    trailerKey: dto.trailer_key || '',
    trailerTitle: dto.trailer_title || '',
    trailerOfficial: dto.trailer_official ?? false,
    trailerLanguage: dto.trailer_language || '',
    trailerPublishedAt: dto.trailer_published_at ?? null,
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
    tmdbId: dto.tmdb_id ?? null,
    metadataSource: dto.metadata_source || '',
    demoOwned: dto.demo_owned ?? false,
    hasDemoClip: dto.has_demo_clip ?? false,
    hlsPath: dto.hls_path ?? null,
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
