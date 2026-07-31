import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { VideoPlayer } from '@/player';
import type { PlayerTarget } from '@/player';
import { api, tokenStore } from '@/lib/api';

/**
 * Customer / admin adaptive HLS player page.
 * Resolves trusted catalog or asset identifiers — never accepts arbitrary stream URLs.
 */
export default function PlayerPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { id, assetId } = useParams<{ id?: string; assetId?: string }>();
  const [params] = useSearchParams();
  const ep = params.get('ep');
  const [title, setTitle] = useState('Playback');

  const target: PlayerTarget | null = useMemo(() => {
    if (location.pathname.startsWith('/player/asset/') && assetId) {
      return { kind: 'asset', mediaAssetId: assetId };
    }
    if (location.pathname.startsWith('/player/episode/') && id) {
      return { kind: 'episode', contentId: Number(id) };
    }
    if (location.pathname.startsWith('/player/movie/') && id) {
      return { kind: 'movie', contentId: Number(id) };
    }
    // Legacy /player/:id?ep=
    if (id && ep) return { kind: 'episode', contentId: Number(ep) };
    if (id) return { kind: 'movie', contentId: Number(id) };
    return null;
  }, [assetId, id, ep, location.pathname]);

  useEffect(() => {
    let cancelled = false;
    async function loadTitle() {
      if (!target) {
        setTitle('Playback');
        return;
      }
      if (target.kind === 'asset') {
        setTitle('Admin playback test');
        return;
      }
      try {
        if (target.kind === 'movie') {
          const movie = await api.getMovie(target.contentId);
          if (!cancelled) setTitle(movie.title || `Movie ${target.contentId}`);
          return;
        }
        // Episode titles are not always available via a single customer endpoint;
        // keep a stable label without leaking internal ids into stream URLs.
        if (!cancelled) setTitle(`Episode ${target.contentId}`);
      } catch {
        if (!cancelled) {
          setTitle(target.kind === 'movie' ? `Movie ${target.contentId}` : `Episode ${target.contentId}`);
        }
      }
    }
    void loadTitle();
    return () => {
      cancelled = true;
    };
  }, [target]);

  const authed = Boolean(tokenStore.get() || tokenStore.getAdmin());
  if (!authed) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-black text-white">
        <p>Sign in to watch.</p>
        <button
          type="button"
          className="underline"
          onClick={() => navigate('/login', { replace: true })}
        >
          Go to login
        </button>
      </div>
    );
  }

  if (
    !target ||
    ((target.kind === 'movie' || target.kind === 'episode') && !Number.isFinite(target.contentId))
  ) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black text-white">
        Invalid player target
      </div>
    );
  }

  return <VideoPlayer target={target} title={title} onBack={() => navigate(-1)} />;
}
