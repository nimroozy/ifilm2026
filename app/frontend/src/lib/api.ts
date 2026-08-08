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
      const obj = detail as { message?: unknown; code?: unknown; detail?: unknown };
      if (typeof obj.message === 'string' && obj.message.trim()) {
        message = obj.message;
      } else if (typeof obj.detail === 'string' && obj.detail.trim()) {
        message = obj.detail;
      } else {
        message = JSON.stringify(detail);
      }
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

export interface CastCreditDto {
  person_id: number;
  name: string;
  character?: string;
  profile_path?: string;
  profile_url?: string;
  order?: number;
}

export interface MovieDto {
  id: number;
  title: string;
  original_title?: string;
  slug: string;
  description?: string;
  short_description?: string;
  tagline?: string;
  localization?: { locale?: string; sources?: Record<string, string> } | null;
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
  credits?: CastCreditDto[];
  credits_synced_at?: string | null;
  audio?: string[];
  subtitles?: string[];
  qualities?: string[];
  dubbed?: string[];
  audio_availability?: {
    original_language?: string | null;
    languages?: string[];
    dubbed_languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
  subtitle_availability?: {
    languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
  views?: number;
  type?: 'movie' | string;
  hls_path?: string | null;
  playable?: boolean;
  has_playable_package?: boolean;
  has_external_media?: boolean;
  producer?: string;
  writer?: string;
  studio?: string;
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
  tagline?: string;
  localization?: { locale?: string; sources?: Record<string, string> } | null;
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
  audio_availability?: {
    original_language?: string | null;
    languages?: string[];
    dubbed_languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
  subtitle_availability?: {
    languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
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
  playable?: boolean;
  has_playable_package?: boolean;
  has_external_media?: boolean;
  audio_availability?: {
    original_language?: string | null;
    languages?: string[];
    dubbed_languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
  subtitle_availability?: {
    languages?: string[];
    track_count?: number | null;
    source?: string;
    selectable_in_player?: boolean;
  };
  // Compatibility
  season?: number | null;
  episode?: number | null;
  duration?: number | null;
  thumbnail?: string;
}

export type CollectionType =
  | 'editorial'
  | 'franchise'
  | 'seasonal'
  | 'genre_feature'
  | 'regional'
  | 'language'
  | 'staff_pick';

export type CollectionStatus = 'draft' | 'published' | 'archived';
export type CollectionVisibility = 'public' | 'unlisted';

export interface CollectionItemDto {
  id: number;
  collection_id: number;
  movie_id?: number | null;
  series_id?: number | null;
  position: number;
  custom_title?: string | null;
  custom_description?: string | null;
  content_type: 'movie' | 'series';
  movie?: MovieDto | null;
  series?: SeriesDto | null;
  created_at?: string | null;
  publicly_visible?: boolean;
}

export interface CollectionDto {
  id: number;
  title: string;
  slug: string;
  description?: string;
  short_description?: string;
  collection_type: CollectionType | string;
  status: CollectionStatus | string;
  visibility: CollectionVisibility | string;
  poster_url?: string;
  backdrop_url?: string;
  sort_order?: number;
  is_featured?: boolean;
  demo_owned?: boolean;
  demo_seed_version?: string;
  item_count?: number;
  visible_item_count?: number;
  items: CollectionItemDto[];
  created_by_admin_id?: number | null;
  updated_by_admin_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  published_at?: string | null;
  archived_at?: string | null;
}

/** Public-safe collection payload — no admin/audit/demo internals. */
export interface CollectionPublicDto {
  id: number;
  title: string;
  slug: string;
  description?: string;
  short_description?: string;
  collection_type: CollectionType | string;
  poster_url?: string;
  backdrop_url?: string;
  sort_order?: number;
  is_featured?: boolean;
  item_count?: number;
  items: CollectionItemDto[];
  published_at?: string | null;
}

export type CollectionCreatePayload = {
  title: string;
  slug?: string | null;
  description?: string;
  short_description?: string;
  collection_type?: CollectionType;
  visibility?: CollectionVisibility;
  poster_url?: string;
  backdrop_url?: string;
  sort_order?: number;
  is_featured?: boolean;
};

export type CollectionUpdatePayload = Partial<CollectionCreatePayload> & {
  expected_updated_at?: string | null;
};

export type CollectionItemAddPayload = {
  movie_id?: number | null;
  series_id?: number | null;
  custom_title?: string | null;
  custom_description?: string | null;
  position?: number | null;
};

export interface CollectionPickerResultDto {
  movies: MovieDto[];
  series: SeriesDto[];
  page: number;
  page_size: number;
}

export interface CollectionListParams {
  collection_type?: string;
  featured?: boolean;
  page?: number;
  page_size?: number;
}

export interface AdminCollectionListParams {
  q?: string;
  status?: string;
  collection_type?: string;
  page?: number;
  page_size?: number;
}

export interface CollectionPickerParams {
  q?: string;
  content_type?: 'movie' | 'series';
  published_only?: boolean;
  year?: number;
  genre?: string;
  language?: string;
  page?: number;
  page_size?: number;
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
  has_dubbed?: boolean;
  has_subtitles?: boolean;
  locale?: 'en' | 'fa' | 'ps';
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
  tmdb_id?: number | null;
  poster_url?: string;
  backdrop_url?: string;
  trailer_url?: string;
  is_featured?: boolean;
  is_trending?: boolean;
  genre_ids?: number[];
  director?: string;
  producer?: string;
  writer?: string;
  studio?: string;
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
  source_type?: 'uploaded' | 'external' | string;
  /** Masked display URL only (no query tokens). */
  external_url?: string | null;
  external_url_masked?: string | null;
  external_kind?: string | null;
  external_content_type?: string | null;
  external_content_length?: number | null;
  external_accept_ranges?: boolean;
  external_validated_at?: string | null;
  external_is_primary?: boolean;
  external_protection_mode?: string;
  external_acknowledged_at?: string | null;
  created_by_admin_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MediaAssetUsageDto {
  kind: string;
  id: string | number;
  label?: string;
  status?: string | null;
  is_active?: boolean;
}

export interface MediaDuplicateDetail {
  code: 'duplicate_checksum';
  message: string;
  existing_asset_id: string;
  existing_asset?: Partial<MediaAssetDto> & { id: string };
  actions?: string[];
}

export interface MediaStorageHealthDto {
  ok: boolean;
  summary: {
    healthy: number;
    missing_files: number;
    size_mismatches: number;
    bad_paths: number;
    orphan_files: number;
    duplicate_hashes: number;
    failed_probes: number;
    stuck_uploads: number;
  };
  mounts?: Record<string, unknown>;
  missing_files: Array<Record<string, unknown>>;
  size_mismatches: Array<Record<string, unknown>>;
  bad_paths: Array<Record<string, unknown>>;
  orphan_files: Array<Record<string, unknown>>;
  duplicate_hashes: Array<Record<string, unknown>>;
  failed_probes: Array<Record<string, unknown>>;
  stuck_uploads: Array<Record<string, unknown>>;
  healthy_sample?: Array<Record<string, unknown>>;
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
  media_package_id: string | null;
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
  media_package_id: string | null;
  expires_at: string;
  playback_token: string;
  master_playlist_url: string;
  source_type?: 'package' | 'external' | string;
  playback_url?: string | null;
  protection_level?: 'session_proxied' | 'unprotected_direct' | string;
  supports_seek?: boolean;
  supports_range?: boolean;
  supports_quality_selection?: boolean;
  supports_revocation?: boolean;
  is_demo_only?: boolean;
  external_kind?: string | null;
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

export interface TmdbTitleRefreshResultDto {
  media_type?: string;
  entity_id?: number;
  tmdb_id?: number | null;
  trailer_updated?: boolean;
  credits_count?: number;
  similar_preview_count?: number;
  fields_updated?: string[];
  skipped_manual_fields?: string[];
}

export interface TmdbTitleRefreshResponseDto {
  result: TmdbTitleRefreshResultDto;
  item: MovieDto | SeriesDto | null;
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

export interface WatchlistItemDto {
  id: number;
  content_type: 'movie' | 'series';
  movie_id?: number | null;
  series_id?: number | null;
  title: string;
  poster_url?: string;
  backdrop_url?: string;
  release_year?: number | null;
  available: boolean;
  detail_path: string;
  player_path?: string;
  created_at?: string | null;
}

export interface WatchlistActionDto {
  detail: string;
  deleted: number;
}

export interface WatchlistMembershipDto {
  in_watchlist: boolean;
  item_id: number | null;
}

export interface WatchlistAddBody {
  movie_id?: number;
  series_id?: number;
}

export interface RecommendationItemDto {
  content_type: 'movie' | 'series';
  id: number;
  slug: string;
  title: string;
  poster_url?: string;
  backdrop_url?: string;
  release_year?: number | null;
  imdb_rating?: number | null;
  genres?: string[];
  score: number;
  reasons: string[];
  explanation?: string | null;
  playable?: boolean;
  detail_path: string;
  components?: Record<string, number> | null;
}

export interface RecommendationListDto {
  mode: string;
  personalized: boolean;
  label: string;
  count: number;
  items: RecommendationItemDto[];
}

export interface RecommendationShelfDto {
  shelf_type: string;
  title: string;
  personalized: boolean;
  source?: Record<string, unknown> | null;
  collections?: { id: number; slug: string; title: string }[] | null;
  items: RecommendationItemDto[];
}

export interface HomeRecommendationsDto {
  mode: string;
  personalized: boolean;
  preference_summary?: Record<string, unknown> | null;
  shelves: RecommendationShelfDto[];
}

/** Aggregated anonymous homepage shelves (card payloads). */
export interface CatalogHomeDto {
  featured: MovieDto[];
  trending: MovieDto[];
  recently_added: MovieDto[];
  top_rated: MovieDto[];
  action: MovieDto[];
  comedy: MovieDto[];
  afghan: MovieDto[];
  persian_dubbed: MovieDto[];
  pashto_dubbed: MovieDto[];
  family: MovieDto[];
  popular_series: SeriesDto[];
  featured_collections: CollectionPublicDto[];
  recommendations?: HomeRecommendationsDto | null;
}

/** Authenticated homepage: catalog shelves + personalized rails. */
export interface MeHomeDto extends CatalogHomeDto {
  continue_watching: WatchProgressDto[];
  watchlist: WatchlistItemDto[];
  recommendations: HomeRecommendationsDto | null;
}

export interface WhatToWatchBody {
  content_type?: 'movie' | 'series' | 'either';
  genre?: string | null;
  mood?: string | null;
  duration?: 'under_90' | '90_120' | 'over_120' | 'any' | null;
  language?: string | null;
  subtitles?: 'required' | 'optional' | 'any' | null;
  release_period?: 'new' | 'modern' | 'classic' | 'any' | null;
  limit?: number;
}

export interface WhatToWatchDto {
  mode: 'what_to_watch';
  ai: boolean;
  filters: Record<string, unknown>;
  /** Filter dimensions loosened when exact match was too sparse. */
  relaxed?: string[];
  count: number;
  items: RecommendationItemDto[];
}

export interface RecommendationInspectDto {
  subscriber_id?: number | null;
  username?: string | null;
  mode?: string | null;
  preference_signals?: Record<string, unknown> | null;
  weights?: Record<string, number> | null;
  candidates?: RecommendationItemDto[];
  error?: string | null;
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
  update_blocked?: boolean;
  integrity?: {
    ok?: boolean;
    installed_version?: string | null;
    release_manifest_verified?: boolean;
    configured_digests_match?: boolean;
    running_digests_match?: boolean;
    migration_head?: string | null;
    health_status?: string | null;
    update_channel?: string | null;
    rollback_target?: string | null;
    digest_mismatch?: boolean;
    digest_summary?: {
      backend?: string | null;
      frontend?: string | null;
      running_backend?: string | null;
      running_frontend?: string | null;
    };
    checks?: Array<{ name: string; passed: boolean; detail?: string }>;
    checked_at?: string | null;
  } | null;
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

export function createHttp(getToken: () => string | null, options?: { onUnauthorized?: () => void }): AxiosInstance {
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

export function unwrapList<T>(envelope: Envelope<T>): Page<T> {
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

const http = createHttp(() => tokenStore.get());
export type ContentRequestStatus =
  | 'new'
  | 'reviewing'
  | 'approved'
  | 'rejected'
  | 'added'
  | 'withdrawn';

export interface CatalogMatchDto {
  content_type: 'movie' | 'series';
  id: number;
  slug: string;
  title: string;
  release_year?: number | null;
  poster_url?: string;
  detail_path: string;
  match_strength?: 'exact' | 'likely';
  match_reason?: string;
}

export interface ContentRequestDto {
  id: number;
  request_type: 'movie' | 'series';
  title: string;
  year?: number | null;
  tmdb_id?: number | null;
  imdb_id?: string | null;
  tmdb_url?: string | null;
  imdb_url?: string | null;
  preferred_language?: string | null;
  notes?: string | null;
  status: ContentRequestStatus | string;
  public_response?: string | null;
  linked_movie_id?: number | null;
  linked_series_id?: number | null;
  linked_detail_path?: string | null;
  linked_title?: string | null;
  demand_count?: number;
  created_at: string;
  updated_at: string;
  reviewed_at?: string | null;
  subscriber_id?: number;
  subscriber_username?: string | null;
  admin_note?: string | null;
  reviewed_by_admin_id?: number | null;
  normalized_title?: string;
}

export interface ContentRequestCreateBody {
  request_type: 'movie' | 'series';
  title: string;
  year?: number;
  tmdb_url?: string;
  imdb_url?: string;
  tmdb_id?: number;
  imdb_id?: string;
  preferred_language?: string;
  notes?: string;
  force?: boolean;
}

export interface ContentRequestCreateResult {
  outcome: 'created' | 'existing_request' | 'already_available' | 'suggestions';
  message: string;
  request?: ContentRequestDto | null;
  catalog_item?: CatalogMatchDto | null;
  suggestions: CatalogMatchDto[];
}

export interface ContentRequestAggregateDto {
  request_type: 'movie' | 'series';
  title: string;
  normalized_title: string;
  year?: number | null;
  tmdb_id?: number | null;
  imdb_id?: string | null;
  request_count: number;
  open_count: number;
  preferred_languages: Record<string, number>;
  latest_requested_at?: string | null;
}

export interface ContentRequestAdminListDto {
  items: ContentRequestDto[];
  total: number;
  page: number;
  page_size: number;
  aggregates: ContentRequestAggregateDto[];
}

export interface ContentRequestAdminDetailDto {
  request: ContentRequestDto;
  events: Array<{
    id: number;
    event_type: string;
    from_status?: string | null;
    to_status?: string | null;
    actor_admin_id?: number | null;
    actor_subscriber_id?: number | null;
    detail?: string | null;
    created_at: string;
  }>;
}

export interface ContentRequestAdminActionBody {
  action: 'review' | 'approve' | 'reject' | 'mark_added' | 'reopen';
  admin_note?: string;
  public_response?: string;
  linked_movie_id?: number;
  linked_series_id?: number;
}

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

  async getMovie(idOrSlug: number | string, locale?: 'en' | 'fa' | 'ps') {
    const { data } = await http.get<MovieDto>(`/movies/${idOrSlug}`, {
      params: locale ? { locale } : undefined,
    });
    return data;
  },

  async getSimilarMovies(idOrSlug: number | string, limit = 12, locale?: 'en' | 'fa' | 'ps') {
    const { data } = await http.get<MovieDto[]>(`/movies/${idOrSlug}/similar`, {
      params: { limit, ...(locale ? { locale } : {}) },
    });
    return data;
  },

  async listSeries(params?: CatalogListParams) {
    const { data } = await http.get<Envelope<SeriesDto>>('/series', { params });
    return unwrapList(data);
  },

  async getSeries(idOrSlug: number | string, locale?: 'en' | 'fa' | 'ps') {
    const { data } = await http.get<SeriesDto>(`/series/${idOrSlug}`, {
      params: locale ? { locale } : undefined,
    });
    return data;
  },

  async listSeasons(idOrSlug: number | string) {
    const { data } = await http.get<SeasonDto[]>(`/series/${idOrSlug}/seasons`);
    return data;
  },

  async listEpisodes(idOrSlug: number | string, season?: number, locale?: 'en' | 'fa' | 'ps') {
    const { data } = await http.get<EpisodeDto[]>(`/series/${idOrSlug}/episodes`, {
      params: {
        ...(season != null ? { season } : {}),
        ...(locale ? { locale } : {}),
      },
    });
    return data;
  },

  async listGenres(params?: { q?: string; page?: number; page_size?: number }) {
    const { data } = await http.get<Envelope<GenreDto>>('/genres', { params });
    return unwrapList(data);
  },

  async search(q: string, locale?: 'en' | 'fa' | 'ps') {
    const { data } = await http.get<{ movies: MovieDto[]; series: SeriesDto[] }>('/search', {
      params: { q, ...(locale ? { locale } : {}) },
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

  async dismissContinueWatching(assetId: string) {
    const { data } = await http.delete<WatchProgressActionDto>(`/me/continue-watching/${assetId}`);
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

  async listWatchlist(params?: { page?: number; page_size?: number }) {
    const { data } = await http.get<Envelope<WatchlistItemDto>>('/me/watchlist', { params });
    return unwrapList(data);
  },

  async getWatchlistMembership(params: { movie_id?: number; series_id?: number }) {
    const { data } = await http.get<WatchlistMembershipDto>('/me/watchlist/membership', { params });
    return data;
  },

  async addWatchlistItem(body: WatchlistAddBody) {
    const { data } = await http.post<WatchlistItemDto>('/me/watchlist', body);
    return data;
  },

  async deleteWatchlistItem(itemId: number) {
    const { data } = await http.delete<WatchlistActionDto>(`/me/watchlist/${itemId}`);
    return data;
  },

  async removeWatchlistByContent(params: { movie_id?: number; series_id?: number }) {
    const { data } = await http.delete<WatchlistActionDto>('/me/watchlist', { params });
    return data;
  },

  async clearWatchlist() {
    const { data } = await http.delete<WatchlistActionDto>('/me/watchlist');
    return data;
  },

  async getStreamingStatus() {
    const { data } = await http.get<StreamingStatusDto>('/streaming/status');
    return data;
  },

  async listCollections(params?: CollectionListParams) {
    const { data } = await http.get<Envelope<CollectionPublicDto>>('/catalog/collections', { params });
    return unwrapList(data);
  },

  async getCollection(slug: string) {
    const { data } = await http.get<CollectionPublicDto>(`/catalog/collections/${slug}`);
    return data;
  },

  async listFeaturedHomeCollections(params?: { page_size?: number; min_items?: number }) {
    const { data } = await http.get<Envelope<CollectionPublicDto>>('/catalog/collections/featured/home', {
      params,
    });
    return unwrapList(data);
  },

  async getMyRecommendations(params?: {
    limit?: number;
    content_type?: 'movie' | 'series' | 'either';
    genre?: string;
    language?: string;
  }) {
    const { data } = await http.get<RecommendationListDto>('/me/recommendations', { params });
    return data;
  },

  async getCatalogHome(params?: { locale?: string }) {
    const { data } = await http.get<CatalogHomeDto>('/catalog/home', { params });
    return data;
  },

  async getMeHome(params?: { locale?: string }) {
    const { data } = await http.get<MeHomeDto>('/me/home', { params });
    return data;
  },

  async getHomeRecommendations() {
    const { data } = await http.get<HomeRecommendationsDto>('/recommendations/home');
    return data;
  },

  async getMyHomeRecommendations() {
    const { data } = await http.get<HomeRecommendationsDto>('/me/recommendations/home');
    return data;
  },

  async getMovieRecommendations(idOrSlug: string | number, limit = 12) {
    const { data } = await http.get<RecommendationListDto>(
      `/catalog/movies/${idOrSlug}/recommendations`,
      { params: { limit } }
    );
    return data;
  },

  async getSeriesRecommendations(idOrSlug: string | number, limit = 12) {
    const { data } = await http.get<RecommendationListDto>(
      `/catalog/series/${idOrSlug}/recommendations`,
      { params: { limit } }
    );
    return data;
  },

  async whatToWatch(body: WhatToWatchBody) {
    const { data } = await http.post<WhatToWatchDto>('/recommendations/what-to-watch', body);
    return data;
  },

  async createContentRequest(body: ContentRequestCreateBody) {
    const { data } = await http.post<ContentRequestCreateResult>('/me/content-requests', body);
    return data;
  },

  async listContentRequests(params?: { page?: number; page_size?: number }) {
    const { data } = await http.get<Envelope<ContentRequestDto>>('/me/content-requests', { params });
    return unwrapList(data);
  },

  async getContentRequest(id: number) {
    const { data } = await http.get<ContentRequestDto>(`/me/content-requests/${id}`);
    return data;
  },

  async withdrawContentRequest(id: number) {
    const { data } = await http.delete<ContentRequestDto>(`/me/content-requests/${id}`);
    return data;
  },
};

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
    credits: (dto.credits ?? []).map((credit) => ({
      personId: credit.person_id,
      name: credit.name,
      character: credit.character || '',
      profilePath: credit.profile_path || '',
      profileUrl: credit.profile_url || '',
      order: credit.order ?? 0,
    })),
    creditsSyncedAt: dto.credits_synced_at ?? null,
    description: dto.description || '',
    tagline: dto.tagline || '',
    localization: dto.localization ?? null,
    poster,
    backdrop,
    logoUrl: dto.logo_url || '',
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    qualities: dto.qualities ?? [],
    featured,
    type: 'movie' as const,
    dubbed: dto.dubbed ?? [],
    audioAvailability: dto.audio_availability ?? null,
    subtitleAvailability: dto.subtitle_availability ?? null,
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
    publishedAt: dto.published_at ?? null,
    createdAt: dto.created_at ?? null,
    hlsPath: dto.hls_path ?? null,
    playable: dto.playable ?? false,
    hasPlayablePackage: dto.has_playable_package ?? false,
    hasExternalMedia: dto.has_external_media ?? false,
    producer: dto.producer || '',
    writer: dto.writer || '',
    studio: dto.studio || '',
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
    tagline: dto.tagline || '',
    localization: dto.localization ?? null,
    poster,
    backdrop,
    logoUrl: dto.logo_url || '',
    audio: dto.audio ?? [],
    subtitles: dto.subtitles ?? [],
    dubbed: dto.dubbed ?? [],
    audioAvailability: dto.audio_availability ?? null,
    subtitleAvailability: dto.subtitle_availability ?? null,
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
    publishedAt: dto.published_at ?? null,
    createdAt: dto.created_at ?? null,
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
    playable: dto.playable ?? false,
    hasPlayablePackage: dto.has_playable_package ?? false,
    hasExternalMedia: dto.has_external_media ?? false,
    audioAvailability: dto.audio_availability ?? null,
    subtitleAvailability: dto.subtitle_availability ?? null,
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
