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

function languageName(code: string | null, t: PlayerI18n): string {
  switch (code) {
    case 'en':
      return t.english;
    case 'fa':
      return t.persian;
    case 'ps':
      return t.pashto;
    case 'prs':
      return t.dari;
    default:
      return code || '';
  }
}

export function localizeAudioTrackName(
  lang: string | null | undefined,
  t: PlayerI18n,
  opts?: { isDubbed?: boolean; fallback?: string }
): string {
  const code = normalizeLanguageCode(lang);
  if (opts?.isDubbed && code === 'fa') return t.persianDub;
  if (opts?.isDubbed && code === 'ps') return t.pashtoDub;
  if (opts?.isDubbed && code) {
    return `${languageName(code, t)} ${t.dubbed}`;
  }
  if (code) return languageName(code, t);
  return opts?.fallback?.trim() || t.audio;
}

export function localizeSubtitleTrackName(
  lang: string | null | undefined,
  t: PlayerI18n,
  opts?: { fallback?: string }
): string {
  const code = normalizeLanguageCode(lang);
  if (code) return languageName(code, t);
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
