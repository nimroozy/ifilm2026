/** Local player preferences — never store tokens or stream URLs. */

const QUALITY_KEY = 'ifilm.qualityPreference';
const SUBTITLE_KEY = 'ifilm.subtitlePreference';
const AUDIO_KEY = 'ifilm.audioPreference';

export type QualityPreference = 'auto' | string; // height label e.g. "720p"

export function readQualityPreference(): QualityPreference {
  try {
    const value = localStorage.getItem(QUALITY_KEY);
    if (!value) return 'auto';
    return value;
  } catch {
    return 'auto';
  }
}

export function writeQualityPreference(value: QualityPreference): void {
  try {
    localStorage.setItem(QUALITY_KEY, value);
  } catch {
    /* ignore */
  }
}

/** Match preferred label against available levels; returns level index or -1 for Auto. */
export function resolveQualityIndex(
  preference: QualityPreference,
  levels: { index: number; label: string }[]
): number {
  if (preference === 'auto' || !levels.length) return -1;
  const match = levels.find((level) => level.label === preference);
  return match ? match.index : -1;
}

export function readSubtitlePreference(): string {
  try {
    return localStorage.getItem(SUBTITLE_KEY) || 'off';
  } catch {
    return 'off';
  }
}

export function writeSubtitlePreference(value: string): void {
  try {
    localStorage.setItem(SUBTITLE_KEY, value);
  } catch {
    /* ignore */
  }
}

export function readAudioPreference(): string {
  try {
    return localStorage.getItem(AUDIO_KEY) || '';
  } catch {
    return '';
  }
}

export function writeAudioPreference(value: string): void {
  try {
    localStorage.setItem(AUDIO_KEY, value);
  } catch {
    /* ignore */
  }
}
