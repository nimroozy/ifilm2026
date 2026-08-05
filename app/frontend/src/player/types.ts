/** Shared player types — never include token hashes or filesystem paths. */

export type PlayerTarget =
  | { kind: 'movie'; contentId: number }
  | { kind: 'episode'; contentId: number }
  | { kind: 'asset'; mediaAssetId: string };

export type PlaybackEngine = 'native' | 'hls.js' | 'unsupported';

export type PlayerErrorCode =
  | 'auth_required'
  | 'streaming_disabled'
  | 'no_active_package'
  | 'session_create_failed'
  | 'session_expired'
  | 'session_revoked'
  | 'manifest_error'
  | 'network_error'
  | 'media_error'
  | 'unsupported_browser'
  | 'fatal'
  | 'unknown';

export interface SafePlayerError {
  code: PlayerErrorCode;
  message: string;
  retryable: boolean;
}

export interface QualityLevel {
  index: number;
  height: number;
  label: string;
  bitrate?: number;
}

export interface AudioTrackInfo {
  id: number;
  name: string;
  lang?: string;
}

export interface SubtitleTrackInfo {
  id: number;
  name: string;
  lang?: string;
}

export interface PlayerStatsSnapshot {
  currentResolution: string;
  currentRendition: string;
  estimatedBandwidthMbps: number | null;
  bufferedSeconds: number | null;
  droppedFrames: number | null;
  currentTime: number;
  duration: number;
  playbackRate: number;
  videoCodec: string | null;
  audioCodec: string | null;
}

/** In-memory session handle — never persist. */
export interface LivePlaybackSession {
  id: string;
  mediaAssetId: string;
  mediaPackageId: string | null;
  expiresAt: string;
  /** Opaque; keep only in memory. */
  masterPlaylistUrl: string;
  sourceType?: 'package' | 'external' | string;
  playbackUrl?: string | null;
  protectionLevel?: 'session_proxied' | 'unprotected_direct' | string;
  supportsRevocation?: boolean;
  isDemoOnly?: boolean;
}
