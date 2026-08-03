import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { isAirPlaySupported, isPiPSupported } from '../castAirPlay';
import {
  readQualityPreference,
  resolveQualityIndex,
  writeQualityPreference,
} from '../preferences';

describe('AirPlay / PiP capability detection', () => {
  it('does not claim AirPlay without WebKit playback-target APIs', () => {
    const video = document.createElement('video');
    expect(isAirPlaySupported(video)).toBe(false);
  });

  it('does not treat Chromium Remote Playback as AirPlay', () => {
    const video = document.createElement('video') as HTMLVideoElement & {
      remote?: { prompt: () => Promise<void> };
    };
    video.remote = { prompt: async () => undefined };
    expect(isAirPlaySupported(video)).toBe(false);
  });

  it('detects WebKit playback target picker when present', () => {
    const video = document.createElement('video') as HTMLVideoElement & {
      webkitShowPlaybackTargetPicker?: () => void;
    };
    video.webkitShowPlaybackTargetPicker = () => undefined;
    expect(isAirPlaySupported(video)).toBe(true);
  });

  it('reads pictureInPictureEnabled from document', () => {
    const original = Object.getOwnPropertyDescriptor(Document.prototype, 'pictureInPictureEnabled');
    Object.defineProperty(document, 'pictureInPictureEnabled', {
      configurable: true,
      value: true,
    });
    expect(isPiPSupported()).toBe(true);
    if (original) Object.defineProperty(Document.prototype, 'pictureInPictureEnabled', original);
  });
});

describe('quality preference', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it('defaults to auto and persists labels', () => {
    expect(readQualityPreference()).toBe('auto');
    writeQualityPreference('720p');
    expect(readQualityPreference()).toBe('720p');
  });

  it('resolves preferred height or falls back to Auto', () => {
    const levels = [
      { index: 0, label: '480p' },
      { index: 1, label: '720p' },
    ];
    expect(resolveQualityIndex('720p', levels)).toBe(1);
    expect(resolveQualityIndex('1080p', levels)).toBe(-1);
    expect(resolveQualityIndex('auto', levels)).toBe(-1);
  });
});
