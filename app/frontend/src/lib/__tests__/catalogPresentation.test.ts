import { describe, expect, it } from 'vitest';
import { canPlayFullMovie, hasDemoClip, isDemoCatalogItem } from '@/lib/catalogPresentation';

describe('catalogPresentation', () => {
  it('treats demo-owned items as non-full playback', () => {
    expect(isDemoCatalogItem({ demoOwned: true })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: true, hlsPath: '/x' })).toBe(false);
  });

  it('requires playable package evidence for full movie', () => {
    expect(canPlayFullMovie({ demoOwned: false })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '' })).toBe(false);
    expect(canPlayFullMovie({ demoOwned: false, hlsPath: '/hls/master.m3u8' })).toBe(true);
    expect(canPlayFullMovie({ demoOwned: false, playable: true })).toBe(true);
  });

  it('detects demo clips', () => {
    expect(hasDemoClip({ hasDemoClip: true })).toBe(true);
    expect(hasDemoClip({ hasDemoClip: false })).toBe(false);
  });
});
