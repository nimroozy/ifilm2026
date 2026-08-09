/** Localize player audio/subtitle track labels from language codes — never trust DB UI text. */

import { normalizeLanguageCode } from '@/lib/catalogAvailability';
import type { translations } from '@/data/translations';

export type PlayerI18n = (typeof translations)['en']['player'];

export type SessionTrackMeta = {
  language_code: string;
  is_dubbed?: boolean;
  label_key?: string | null;
  is_default?: boolean;
};

/**
 * Language-native track identity for the player menu.
 * Remains understandable regardless of page locale (EN/FA/PS UI).
 */
const NATIVE_AUDIO: Record<string, { base: string; dubbed: string }> = {
  en: { base: 'English', dubbed: 'English Dubbed' },
  fa: { base: 'فارسی', dubbed: 'فارسی دوبله' },
  ps: { base: 'پښتو', dubbed: 'پښتو دوبله' },
  prs: { base: 'دری', dubbed: 'دری دوبله' },
};

const NATIVE_SUB: Record<string, string> = {
  en: 'English',
  fa: 'فارسی',
  ps: 'پښتو',
  prs: 'دری',
};

export function localizeAudioTrackName(
  lang: string | null | undefined,
  t: PlayerI18n,
  opts?: { isDubbed?: boolean; fallback?: string }
): string {
  const code = normalizeLanguageCode(lang);
  if (code && NATIVE_AUDIO[code]) {
    return opts?.isDubbed ? NATIVE_AUDIO[code].dubbed : NATIVE_AUDIO[code].base;
  }
  if (opts?.isDubbed && code) {
    return `${code.toUpperCase()} ${t.dubbed}`;
  }
  if (code) return code.toUpperCase();
  return opts?.fallback?.trim() || t.audio;
}

export function localizeSubtitleTrackName(
  lang: string | null | undefined,
  t: PlayerI18n,
  opts?: { fallback?: string }
): string {
  const code = normalizeLanguageCode(lang);
  if (code && NATIVE_SUB[code]) return NATIVE_SUB[code];
  if (code) return code.toUpperCase();
  return opts?.fallback?.trim() || t.subtitles;
}

export function matchSessionAudioMeta(
  lang: string | null | undefined,
  sessionTracks: SessionTrackMeta[] | undefined
): SessionTrackMeta | undefined {
  const code = normalizeLanguageCode(lang);
  if (!code || !sessionTracks?.length) return undefined;
  return sessionTracks.find((track) => normalizeLanguageCode(track.language_code) === code);
}
