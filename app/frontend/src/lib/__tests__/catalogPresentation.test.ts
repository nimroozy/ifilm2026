import { describe, expect, it } from 'vitest';
import {
  canPlayFullMovie,
  fullMovieUnavailableLabel,
  hasDemoClip,
  isDemoCatalogItem,
  movieDetailPrimaryActions,
} from '@/lib/catalogPresentation';

describe('catalogPresentation', () => {
  it('treats demo-owned items as non-full playback', () => {
    expect(isDemoCatalogItem({ demoOwned: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: true, hlsPath: '/x', playable: true })).toBe(false);
  });

  it('requires backend playable flags — never legacy hlsPath alone', () => {
    expect(canPlayFullMovie({ demoOwned: false })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '' })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '/hls/master.m3u8' })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, playable: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: false, hasPlayablePackage: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: false, hasExternalMedia: true })).toBe(true);
  });

  it('Killer Man regression: published + package flags show Play, not Unavailable', () => {
    // Mirrors published movie with linked completed HLS package (no legacy hlsPath).
    const item = {
      demoOwned: false,
      playable: true,
      hasPlayablePackage: true,
      hasExternalMedia: false,
      hlsPath: null,
    };
    expect(canPlayFullMovie(item)).toBe(true);
    expect(movieDetailPrimaryActions(item, false)).toEqual(['play', 'more']);
    expect(movieDetailPrimaryActions(item, false)).not.toContain('unavailable');
    expect(fullMovieUnavailableLabel()).toBe('Full Movie Unavailable');
  });

  it('never shows unavailable when playable package flag is set', () => {
    const item = { demoOwned: false, playable: true, hasPlayablePackage: true };
    expect(canPlayFullMovie(item)).toBe(true);
    expect(movieDetailPrimaryActions(item, false)).toEqual(['play', 'more']);
    expect(movieDetailPrimaryActions(item, false)).not.toContain('unavailable');
  });

  it('orders actions Play → Demo → Trailer before unavailable', () => {
    expect(movieDetailPrimaryActions({ playable: true, hasDemoClip: true }, true)).toEqual([
      'play',
      'demo',
      'trailer',
      'more',
    ]);
    expect(movieDetailPrimaryActions({ demoOwned: false }, false)).toEqual(['unavailable', 'more']);
  });

  it('detects demo clips', () => {
    expect(hasDemoClip({ hasDemoClip: true })).toBe(true);
    expect(hasDemoClip({ hasDemoClip: false })).toBe(false);
  });

  it('exposes unavailable label', () => {
    expect(fullMovieUnavailableLabel()).toBe('Full Movie Unavailable');
  });
});
