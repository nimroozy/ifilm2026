import { describe, expect, it } from 'vitest';
import type { WatchProgressDto } from '@/lib/api';
import {
  findNextPlayableEpisode,
  formatEpisodeCode,
  resolveSeriesHeroCta,
  sortEpisodesByAirOrder,
} from '@/lib/seriesDetailPlayback';

function ep(id: number, season: number, episode: number, playable = true) {
  return { id, season, episode, playable, hasDemoClip: false };
}

function progress(partial: Partial<WatchProgressDto> & Pick<WatchProgressDto, 'episode_id' | 'series_id'>): WatchProgressDto {
  return {
    id: 1,
    media_asset_id: 'a',
    content_type: 'episode',
    title: 't',
    progress_percent: 0,
    completed: false,
    available: true,
    player_path: `/player/episode/${partial.episode_id}`,
    position_seconds: 0,
    duration_seconds: 100,
    updated_at: '',
    ...partial,
  } as WatchProgressDto;
}

describe('seriesDetailPlayback', () => {
  it('formats SxxExx codes', () => {
    expect(formatEpisodeCode(1, 3)).toBe('S01E03');
    expect(formatEpisodeCode(12, 10)).toBe('S12E10');
  });

  it('finds next episode across season boundary', () => {
    const ordered = sortEpisodesByAirOrder([
      ep(1, 1, 9),
      ep(2, 1, 10),
      ep(3, 2, 1),
      ep(4, 2, 2),
    ]);
    const next = findNextPlayableEpisode(ordered, 1, 10);
    expect(next?.id).toBe(3);
    expect(formatEpisodeCode(next!.season, next!.episode)).toBe('S02E01');
  });

  it('skips unplayable episodes when finding next', () => {
    const ordered = [ep(1, 1, 1), ep(2, 1, 2, false), ep(3, 1, 3)];
    expect(findNextPlayableEpisode(ordered, 1, 1)?.id).toBe(3);
  });

  it('resolves continue CTA exclusively', () => {
    const catalog = [ep(10, 1, 2), ep(11, 1, 3)];
    const cta = resolveSeriesHeroCta({
      seriesId: 5,
      catalogEpisodes: catalog,
      continueWatching: [
        progress({
          episode_id: 11,
          series_id: 5,
          season_number: 1,
          episode_number: 3,
          completed: false,
          progress_percent: 42,
        }),
      ],
      watchHistory: [],
    });
    expect(cta.kind).toBe('continue');
    if (cta.kind === 'continue') {
      expect(cta.code).toBe('S01E03');
      expect(cta.progressPercent).toBe(42);
    }
  });

  it('resolves continue from history when CW rail omits the series', () => {
    const catalog = [ep(20, 1, 2)];
    const cta = resolveSeriesHeroCta({
      seriesId: 4,
      catalogEpisodes: catalog,
      continueWatching: [],
      watchHistory: [
        progress({
          episode_id: 20,
          series_id: 4,
          season_number: 1,
          episode_number: 2,
          completed: false,
          progress_percent: 44,
        }),
      ],
    });
    expect(cta.kind).toBe('continue');
    if (cta.kind === 'continue') expect(cta.code).toBe('S01E02');
  });

  it('resolves next episode after completed finale', () => {
    const catalog = [ep(1, 1, 10), ep(2, 2, 1)];
    const cta = resolveSeriesHeroCta({
      seriesId: 5,
      catalogEpisodes: catalog,
      continueWatching: [],
      watchHistory: [
        progress({
          episode_id: 1,
          series_id: 5,
          season_number: 1,
          episode_number: 10,
          completed: true,
          progress_percent: 100,
        }),
      ],
    });
    expect(cta.kind).toBe('next');
    if (cta.kind === 'next') expect(cta.code).toBe('S02E01');
  });

  it('resolves watch again when no next playable', () => {
    const catalog = [ep(1, 1, 10)];
    const cta = resolveSeriesHeroCta({
      seriesId: 5,
      catalogEpisodes: catalog,
      continueWatching: [],
      watchHistory: [
        progress({
          episode_id: 1,
          series_id: 5,
          season_number: 1,
          episode_number: 10,
          completed: true,
        }),
      ],
    });
    expect(cta.kind).toBe('watch_again');
  });

  it('resolves play when no history', () => {
    const catalog = [ep(1, 1, 1, false), ep(2, 1, 2)];
    const cta = resolveSeriesHeroCta({
      seriesId: 5,
      catalogEpisodes: catalog,
      continueWatching: [],
      watchHistory: [],
    });
    expect(cta.kind).toBe('play');
    if (cta.kind === 'play') expect(cta.episode.id).toBe(2);
  });
});
