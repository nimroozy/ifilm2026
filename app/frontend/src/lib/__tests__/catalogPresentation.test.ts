import { describe, expect, it } from 'vitest';
import {
  canPlayFullMovie,
  canShowPlayButton,
  fullMovieUnavailableLabel,
  hasDemoClip,
  isDemoCatalogItem,
  isPublishedCatalogItem,
  movieDetailPrimaryActions,
  movieUnavailableLabel,
  shouldAutoplayTrailerHero,
} from '@/lib/catalogPresentation';

describe('catalogPresentation', () => {
  it('treats demo-owned items as non-full playback', () => {
    expect(isDemoCatalogItem({ demoOwned: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: true, hlsPath: '/x', playable: true })).toBe(false);
    expect(canShowPlayButton({ demoOwned: true, playable: true, status: 'published' })).toBe(false);
  });

  it('requires backend playable flags — never legacy hlsPath alone', () => {
    expect(canPlayFullMovie({ demoOwned: false })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '' })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '/hls/master.m3u8' })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, playable: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: false, hasPlayablePackage: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: false, hasExternalMedia: true })).toBe(true);
  });

  it('Play button requires published + playable', () => {
    expect(canShowPlayButton({ demoOwned: false, playable: true, status: 'draft' })).toBe(false);
    expect(canShowPlayButton({ demoOwned: false, playable: true, status: 'published' })).toBe(true);
    expect(isPublishedCatalogItem({ status: 'published' })).toBe(true);
  });

  it('Killer Man regression: published + package flags show Play, not Unavailable', () => {
    const item = {
      demoOwned: false,
      playable: true,
      hasPlayablePackage: true,
      hasExternalMedia: false,
      hlsPath: null,
      status: 'published',
    };
    expect(canShowPlayButton(item)).toBe(true);
    expect(movieDetailPrimaryActions(item, false)).toEqual(['play', 'more']);
    expect(movieDetailPrimaryActions(item, false)).not.toContain('coming_soon');
    expect(movieUnavailableLabel()).toBe('Coming Soon');
  });

  it('never shows coming soon when playable package flag is set', () => {
    const item = { demoOwned: false, playable: true, hasPlayablePackage: true, status: 'published' };
    expect(canShowPlayButton(item)).toBe(true);
    expect(movieDetailPrimaryActions(item, false)).toEqual(['play', 'more']);
    expect(movieDetailPrimaryActions(item, false)).not.toContain('coming_soon');
  });

  it('orders actions Play → Demo → Trailer before Coming Soon', () => {
    expect(movieDetailPrimaryActions({ playable: true, hasDemoClip: true, status: 'published' }, true)).toEqual([
      'play',
      'demo',
      'trailer',
      'more',
    ]);
    expect(movieDetailPrimaryActions({ demoOwned: false }, false)).toEqual(['coming_soon', 'more']);
    expect(movieDetailPrimaryActions({ demoOwned: false }, true)).toEqual(['trailer', 'more']);
  });

  it('detects demo clips', () => {
    expect(hasDemoClip({ hasDemoClip: true })).toBe(true);
    expect(hasDemoClip({ hasDemoClip: false })).toBe(false);
  });

  it('replaces Full Movie Unavailable copy with Coming Soon', () => {
    expect(fullMovieUnavailableLabel()).toBe('Coming Soon');
    expect(movieUnavailableLabel({ hasTrailer: true })).toBe('Unavailable');
  });

  it('autoplays trailer hero only when allowed', () => {
    expect(shouldAutoplayTrailerHero({ hasTrailer: true, reduceMotion: false, userDismissed: false })).toBe(true);
    expect(shouldAutoplayTrailerHero({ hasTrailer: false, reduceMotion: false, userDismissed: false })).toBe(false);
    expect(shouldAutoplayTrailerHero({ hasTrailer: true, reduceMotion: true, userDismissed: false })).toBe(false);
    expect(shouldAutoplayTrailerHero({ hasTrailer: true, reduceMotion: false, userDismissed: true })).toBe(false);
  });
});
