import type { PlayerErrorCode, SafePlayerError } from './types';
import { ApiError } from '@/lib/api';

const SAFE_MESSAGES: Record<PlayerErrorCode, string> = {
  auth_required: 'Sign in to watch this title.',
  streaming_disabled: 'Streaming is temporarily unavailable.',
  no_active_package: 'This title is not ready for playback yet.',
  session_create_failed: 'Unable to start playback. Please try again.',
  session_expired: 'Your playback session expired. Refreshing…',
  session_revoked: 'Playback was stopped. Please try again.',
  manifest_error: 'Unable to load the video stream.',
  network_error: 'Network problem while loading video.',
  media_error: 'A media error occurred while playing.',
  unsupported_browser: 'This browser cannot play adaptive HLS video.',
  fatal: 'Playback failed. Please try again later.',
  unknown: 'Something went wrong during playback.',
};

export function safePlayerError(
  code: PlayerErrorCode,
  overrides?: Partial<SafePlayerError>
): SafePlayerError {
  return {
    code,
    message: overrides?.message ?? SAFE_MESSAGES[code],
    retryable: overrides?.retryable ?? ['network_error', 'session_create_failed', 'session_expired'].includes(code),
  };
}

export function mapApiErrorToPlayerError(err: unknown): SafePlayerError {
  if (err instanceof ApiError) {
    const detail = String(err.message || '').toLowerCase();
    if (err.status === 401 || err.status === 403) return safePlayerError('auth_required');
    if (err.status === 503 || detail.includes('streaming is disabled')) {
      return safePlayerError('streaming_disabled');
    }
    if (err.status === 409 || detail.includes('no active') || detail.includes('no playable')) {
      return safePlayerError('no_active_package');
    }
    if (err.status === 410) {
      if (detail.includes('revok')) return safePlayerError('session_revoked', { retryable: false });
      return safePlayerError('session_expired');
    }
    return safePlayerError('session_create_failed');
  }
  return safePlayerError('unknown');
}

/** Strip anything that looks like a stream token path from user-visible text. */
export function sanitizeErrorText(text: string): string {
  return text.replace(/\/api\/stream\/[A-Za-z0-9_-]{16,128}/g, '/api/stream/[redacted]');
}

export type SessionGoneKind = 'expired' | 'revoked' | 'unknown';

/**
 * Classify a 410 stream response. Explicit revocation must not be silently
 * refreshed; expiry may trigger a single automatic session replacement.
 */
export async function classifySessionGone(url: string): Promise<SessionGoneKind> {
  try {
    const resp = await fetch(url, { method: 'GET', cache: 'no-store' });
    if (resp.status !== 410) return 'unknown';
    const body = (await resp.json().catch(() => null)) as
      | { detail?: string | { code?: string; message?: string } }
      | null;
    const detail = body?.detail;
    const code =
      typeof detail === 'object' && detail
        ? String(detail.code || detail.message || '')
        : String(detail || '');
    const normalized = code.toLowerCase();
    if (normalized.includes('revok')) return 'revoked';
    if (normalized.includes('expir')) return 'expired';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

export function supportsNativeHls(video: HTMLVideoElement | null): boolean {
  if (!video) return false;
  // Chrome/Chromium often return "maybe" for HLS without reliable native playback.
  // Prefer hls.js everywhere except Apple Safari / iOS.
  if (typeof navigator !== 'undefined') {
    const ua = navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(ua);
    const isAppleSafari =
      /Safari/.test(ua) && !/Chrome|Chromium|CriOS|Edg|OPR|Firefox/.test(ua);
    if (!isIOS && !isAppleSafari) return false;
  }
  const type = video.canPlayType('application/vnd.apple.mpegurl');
  return type === 'probably' || type === 'maybe';
}
