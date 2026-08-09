import type { WatchProgressDto } from '@/lib/api';
import { canPlayFullMovie, hasDemoClip } from '@/lib/catalogPresentation';

export type SeriesEpisodeLike = {
  id: number;
  season: number;
  episode: number;
  playable?: boolean;
  hasDemoClip?: boolean;
  hasPlayablePackage?: boolean;
  hasExternalMedia?: boolean;
  demoOwned?: boolean;
  status?: string;
};

export function formatEpisodeCode(season: number, episode: number): string {
  const s = String(Math.max(0, season)).padStart(2, '0');
  const e = String(Math.max(0, episode)).padStart(2, '0');
  return `S${s}E${e}`;
}

export function isEpisodePlayable(ep: SeriesEpisodeLike): boolean {
  return canPlayFullMovie(ep) || hasDemoClip(ep);
}

export function sortEpisodesByAirOrder<T extends SeriesEpisodeLike>(episodes: T[]): T[] {
  return [...episodes].sort((a, b) => {
    if (a.season !== b.season) return a.season - b.season;
    return a.episode - b.episode;
  });
}

/** Next published/playable episode after (season, episode), crossing seasons. */
export function findNextPlayableEpisode<T extends SeriesEpisodeLike>(
  ordered: T[],
  afterSeason: number,
  afterEpisode: number
): T | null {
  for (const ep of ordered) {
    if (ep.season < afterSeason) continue;
    if (ep.season === afterSeason && ep.episode <= afterEpisode) continue;
    if (isEpisodePlayable(ep)) return ep;
  }
  return null;
}

export function firstPlayableEpisode<T extends SeriesEpisodeLike>(ordered: T[]): T | null {
  return ordered.find((ep) => isEpisodePlayable(ep)) ?? null;
}

export type SeriesHeroCtaKind = 'continue' | 'next' | 'watch_again' | 'play' | 'unavailable';

export type SeriesHeroCta<T extends SeriesEpisodeLike = SeriesEpisodeLike> =
  | {
      kind: 'continue';
      episode: T;
      progress: WatchProgressDto;
      code: string;
      progressPercent: number;
    }
  | {
      kind: 'next';
      episode: T;
      from: WatchProgressDto;
      code: string;
    }
  | {
      kind: 'watch_again';
      episode: T;
      progress: WatchProgressDto;
      code: string;
    }
  | {
      kind: 'play';
      episode: T;
      code: string;
    }
  | { kind: 'unavailable' };

/**
 * Exclusive primary CTA for series detail.
 * Priority: continue → next (completed + next playable) → watch again → play.
 *
 * `catalogEpisodes` should include enough seasons to resolve next across boundaries
 * (at least the watched season and, when needed, the following season).
 */
export function resolveSeriesHeroCta<T extends SeriesEpisodeLike>(opts: {
  seriesId: number;
  catalogEpisodes: T[];
  continueWatching: WatchProgressDto[];
  watchHistory: WatchProgressDto[];
}): SeriesHeroCta<T> {
  const ordered = sortEpisodesByAirOrder(opts.catalogEpisodes);
  const bySeries = (row: WatchProgressDto) =>
    row.content_type === 'episode' && row.series_id === opts.seriesId;

  // CW rails are capped; incomplete progress may only appear in history.
  const active =
    opts.continueWatching.find((row) => bySeries(row) && !row.completed && row.episode_id) ||
    opts.watchHistory.find((row) => bySeries(row) && !row.completed && row.episode_id);
  if (active?.episode_id) {
    const episode =
      ordered.find((ep) => ep.id === active.episode_id) ??
      ({
        id: active.episode_id,
        season: active.season_number ?? 0,
        episode: active.episode_number ?? 0,
        playable: true,
      } as T);
    if (isEpisodePlayable(episode) || active.available) {
      return {
        kind: 'continue',
        episode,
        progress: active,
        code: formatEpisodeCode(episode.season, episode.episode),
        progressPercent: Math.round(active.progress_percent || 0),
      };
    }
  }

  const completed = opts.watchHistory.find((row) => bySeries(row) && row.completed && row.episode_id);
  if (completed?.episode_id) {
    const season = completed.season_number ?? 0;
    const epNum = completed.episode_number ?? 0;
    const next = findNextPlayableEpisode(ordered, season, epNum);
    if (next) {
      return {
        kind: 'next',
        episode: next,
        from: completed,
        code: formatEpisodeCode(next.season, next.episode),
      };
    }
    const again =
      ordered.find((ep) => ep.id === completed.episode_id) ??
      ({
        id: completed.episode_id,
        season,
        episode: epNum,
        playable: true,
      } as T);
    return {
      kind: 'watch_again',
      episode: again,
      progress: completed,
      code: formatEpisodeCode(again.season, again.episode),
    };
  }

  const play = firstPlayableEpisode(ordered);
  if (play) {
    return {
      kind: 'play',
      episode: play,
      code: formatEpisodeCode(play.season, play.episode),
    };
  }
  return { kind: 'unavailable' };
}

export function defaultSeasonNumber(opts: {
  seasons: { number: number; episodeCount?: number }[];
  cta: SeriesHeroCta;
  episodesBySeason?: Map<number, SeriesEpisodeLike[]>;
}): number {
  if (opts.cta.kind === 'continue' || opts.cta.kind === 'next' || opts.cta.kind === 'watch_again' || opts.cta.kind === 'play') {
    const season = opts.cta.episode.season;
    if (opts.seasons.some((s) => s.number === season)) return season;
  }
  for (const season of opts.seasons) {
    const eps = opts.episodesBySeason?.get(season.number);
    if (eps?.some((ep) => isEpisodePlayable(ep))) return season.number;
  }
  return opts.seasons[0]?.number ?? 1;
}

export function episodePlayerPath(seriesId: number, episodeId: number, season: number): string {
  return `/player/episode/${episodeId}?series=${encodeURIComponent(String(seriesId))}&season=${season}`;
}

export function buildEpisodeProgressMap(
  seriesId: number,
  rows: WatchProgressDto[]
): Map<number, WatchProgressDto> {
  const map = new Map<number, WatchProgressDto>();
  for (const row of rows) {
    if (row.content_type !== 'episode' || row.series_id !== seriesId || !row.episode_id) continue;
    const existing = map.get(row.episode_id);
    if (!existing) {
      map.set(row.episode_id, row);
      continue;
    }
    // Prefer in-progress over completed; otherwise keep the newer-looking higher percent.
    if (!row.completed && existing.completed) {
      map.set(row.episode_id, row);
    } else if (row.completed === existing.completed && (row.progress_percent || 0) > (existing.progress_percent || 0)) {
      map.set(row.episode_id, row);
    }
  }
  return map;
}
