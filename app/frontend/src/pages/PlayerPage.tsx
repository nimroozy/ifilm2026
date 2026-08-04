import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { VideoPlayer } from '@/player';
import type { PlayerTarget } from '@/player';
import { api, tokenStore, type EpisodeDto } from '@/lib/api';

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
  const seriesRef = params.get('series');
  const seasonRef = params.get('season');
  const [title, setTitle] = useState('Playback');
  const [neighbors, setNeighbors] = useState<{ prevId: number | null; nextId: number | null }>({
    prevId: null,
    nextId: null,
  });
  const [autoplayNext, setAutoplayNext] = useState(() => {
    try {
      return localStorage.getItem('ifilm.autoplayNext') !== '0';
    } catch {
      return true;
    }
  });

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

  useEffect(() => {
    let cancelled = false;
    async function loadNeighbors() {
      if (!target || target.kind !== 'episode' || !seriesRef) {
        setNeighbors({ prevId: null, nextId: null });
        return;
      }
      try {
        const seasonNum = seasonRef ? Number(seasonRef) : undefined;
        const episodes = await api.listEpisodes(
          seriesRef,
          Number.isFinite(seasonNum) ? seasonNum : undefined
        );
        if (cancelled) return;
        const ordered = [...episodes].sort((a, b) => {
          const sa = a.season ?? 0;
          const sb = b.season ?? 0;
          if (sa !== sb) return sa - sb;
          return a.episode_number - b.episode_number;
        });
        const index = ordered.findIndex((item: EpisodeDto) => item.id === target.contentId);
        if (index < 0) {
          setNeighbors({ prevId: null, nextId: null });
          return;
        }
        const current = ordered[index];
        if (current?.title) setTitle(current.title);
        setNeighbors({
          prevId: index > 0 ? ordered[index - 1].id : null,
          nextId: index < ordered.length - 1 ? ordered[index + 1].id : null,
        });
      } catch {
        if (!cancelled) setNeighbors({ prevId: null, nextId: null });
      }
    }
    void loadNeighbors();
    return () => {
      cancelled = true;
    };
  }, [target, seriesRef, seasonRef]);

  function goToEpisode(episodeId: number) {
    const qs = new URLSearchParams();
    if (seriesRef) qs.set('series', seriesRef);
    if (seasonRef) qs.set('season', seasonRef);
    const query = qs.toString();
    navigate(`/player/episode/${episodeId}${query ? `?${query}` : ''}`, { replace: true });
  }

  function toggleAutoplayNext(next: boolean) {
    setAutoplayNext(next);
    try {
      localStorage.setItem('ifilm.autoplayNext', next ? '1' : '0');
    } catch {
      /* ignore */
    }
  }

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

  return (
    <VideoPlayer
      target={target}
      title={title}
      onBack={() => navigate(-1)}
      previousEpisodeId={neighbors.prevId}
      nextEpisodeId={neighbors.nextId}
      autoplayNext={autoplayNext}
      onAutoplayNextChange={toggleAutoplayNext}
      onPreviousEpisode={neighbors.prevId != null ? () => goToEpisode(neighbors.prevId!) : undefined}
      onNextEpisode={neighbors.nextId != null ? () => goToEpisode(neighbors.nextId!) : undefined}
    />
  );
}
