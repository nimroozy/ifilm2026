import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, adminApi, tokenStore, ApiError } from '@/lib/api';
import type { LivePlaybackSession, PlayerTarget, SafePlayerError } from './types';
import { mapApiErrorToPlayerError, safePlayerError } from './safeErrors';

const MAX_AUTO_REFRESH = 1;

function targetKey(target: PlayerTarget | null): string {
  if (!target) return '';
  if (target.kind === 'asset') return `asset:${target.mediaAssetId}`;
  return `${target.kind}:${target.contentId}`;
}

async function createSessionForTarget(target: PlayerTarget): Promise<LivePlaybackSession> {
  const adminToken = tokenStore.getAdmin();
  const userToken = tokenStore.get();

  const toLive = (created: {
    id: string;
    media_asset_id: string;
    media_package_id: string | null;
    expires_at: string;
    master_playlist_url: string;
    source_type?: string;
    playback_url?: string | null;
    protection_level?: string;
    supports_revocation?: boolean;
    is_demo_only?: boolean;
  }): LivePlaybackSession => ({
    id: created.id,
    mediaAssetId: created.media_asset_id,
    mediaPackageId: created.media_package_id,
    expiresAt: created.expires_at,
    masterPlaylistUrl: created.master_playlist_url,
    sourceType: created.source_type,
    playbackUrl: created.playback_url ?? created.master_playlist_url,
    protectionLevel: created.protection_level,
    supportsRevocation: created.supports_revocation,
    isDemoOnly: created.is_demo_only,
  });

  if (target.kind === 'asset') {
    if (!adminToken && !userToken) throw new ApiError('Authentication required', 401);
    if (adminToken) {
      return toLive(await adminApi.createPlaybackSession(target.mediaAssetId));
    }
    return toLive(await api.createPlaybackSession({ media_asset_id: target.mediaAssetId }));
  }

  if (!userToken && !adminToken) throw new ApiError('Authentication required', 401);
  const body = {
    content_type: target.kind,
    content_id: target.contentId,
  } as const;
  if (userToken) return toLive(await api.createPlaybackSession(body));
  return toLive(await adminApi.createPlayerPlaybackSession(body));
}

export function usePlaybackSession(target: PlayerTarget | null) {
  const [session, setSession] = useState<LivePlaybackSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<SafePlayerError | null>(null);
  const refreshCountRef = useRef(0);
  const sessionRef = useRef<LivePlaybackSession | null>(null);
  sessionRef.current = session;
  const key = useMemo(() => targetKey(target), [target]);
  const targetRef = useRef(target);
  targetRef.current = target;

  const clearSensitive = useCallback(() => {
    setSession(null);
    sessionRef.current = null;
  }, []);

  const start = useCallback(async () => {
    const currentTarget = targetRef.current;
    if (!currentTarget) return;
    setLoading(true);
    setError(null);
    try {
      const next = await createSessionForTarget(currentTarget);
      setSession(next);
      refreshCountRef.current = 0;
    } catch (err) {
      setError(mapApiErrorToPlayerError(err));
      clearSensitive();
    } finally {
      setLoading(false);
    }
  }, [clearSensitive, key]);

  useEffect(() => {
    void start();
    return () => {
      const current = sessionRef.current;
      clearSensitive();
      if (!current?.id) return;
      if (tokenStore.getAdmin()) {
        void adminApi.revokePlaybackSession(current.id).catch(() => {
          void api.revokePlaybackSession(current.id).catch(() => undefined);
        });
      } else {
        void api.revokePlaybackSession(current.id).catch(() => undefined);
      }
    };
  }, [start, clearSensitive]);

  const refreshAfterGone = useCallback(async (): Promise<LivePlaybackSession | null> => {
    const currentTarget = targetRef.current;
    if (!currentTarget) return null;
    if (refreshCountRef.current >= MAX_AUTO_REFRESH) {
      setError(safePlayerError('session_revoked', { retryable: false }));
      clearSensitive();
      return null;
    }
    refreshCountRef.current += 1;
    setLoading(true);
    try {
      const next = await createSessionForTarget(currentTarget);
      setSession(next);
      setError(null);
      return next;
    } catch (err) {
      setError(mapApiErrorToPlayerError(err));
      clearSensitive();
      return null;
    } finally {
      setLoading(false);
    }
  }, [clearSensitive, key]);

  return {
    session,
    loading,
    error,
    setError,
    refreshAfterGone,
    retry: start,
    clearSensitive,
  };
}
