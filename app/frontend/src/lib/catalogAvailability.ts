/**
 * Customer-facing audio/subtitle availability helpers.
 *
 * Prefer structured `audio_availability` / `subtitle_availability` from the API.
 * Fall back to legacy string arrays only when structured fields are absent.
 *
 * Catalog admin metadata is a claim — never imply selectable packaged tracks
 * unless `selectable_in_player` is true.
 */

export type AvailabilitySource =
  | 'media_probe'
  | 'package_manifest'
  | 'admin_metadata'
  | 'tmdb_metadata'
  | 'unknown';

export type AudioAvailability = {
  original_language?: string | null;
  languages?: string[];
  dubbed_languages?: string[];
  track_count?: number | null;
  source?: AvailabilitySource | string;
  selectable_in_player?: boolean;
};

export type SubtitleAvailability = {
  languages?: string[];
  track_count?: number | null;
  source?: AvailabilitySource | string;
  selectable_in_player?: boolean;
};

export type CatalogAvailabilityFields = {
  audio?: string[] | null;
  subtitles?: string[] | null;
  dubbed?: string[] | null;
  audioAvailability?: AudioAvailability | null;
  subtitleAvailability?: SubtitleAvailability | null;
  language?: string | null;
};

const LABEL_EN: Record<string, string> = {
  en: 'English',
  fa: 'Persian',
  prs: 'Dari',
  ps: 'Pashto',
  ar: 'Arabic',
  hi: 'Hindi',
  ur: 'Urdu',
  ko: 'Korean',
  ja: 'Japanese',
  zh: 'Chinese',
  tr: 'Turkish',
  ru: 'Russian',
};

const ALIAS: Record<string, string> = {
  en: 'en',
  eng: 'en',
  english: 'en',
  fa: 'fa',
  fas: 'fa',
  per: 'fa',
  persian: 'fa',
  farsi: 'fa',
  prs: 'prs',
  dari: 'prs',
  ps: 'ps',
  pus: 'ps',
  pashto: 'ps',
  pushto: 'ps',
  ar: 'ar',
  ara: 'ar',
  arabic: 'ar',
  hi: 'hi',
  hin: 'hi',
  hindi: 'hi',
  ur: 'ur',
  urd: 'ur',
  urdu: 'ur',
};

export function normalizeLanguageCode(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === 'object' && value !== null) {
    const obj = value as Record<string, unknown>;
    for (const key of ['iso_639_1', 'iso_639_3', 'english_name', 'name']) {
      if (obj[key]) return normalizeLanguageCode(obj[key]);
    }
    return null;
  }
  const raw = String(value).trim();
  if (!raw) return null;
  const key = raw.toLowerCase().replace('_', '-');
  const primary = key.split('-', 1)[0];
  if (ALIAS[primary]) return ALIAS[primary];
  if (ALIAS[key]) return ALIAS[key];
  const slug = primary.replace(/[^a-z0-9]/g, '').slice(0, 16);
  return slug || null;
}

export function languageDisplayName(code: string | null | undefined, locale = 'en'): string {
  if (!code) return '';
  void locale;
  return LABEL_EN[code] || code;
}

export function compactLanguageBadge(code: string): string {
  const upper = code.toUpperCase();
  if (code === 'prs') return 'PRS';
  if (code === 'fa') return 'FA';
  if (code === 'ps') return 'PS';
  if (code === 'en') return 'EN';
  return upper.slice(0, 3);
}

export function hasCatalogTracks(list: string[] | null | undefined): boolean {
  return Array.isArray(list) && list.some((item) => Boolean(item && String(item).trim()));
}

export function formatCatalogTracks(list: string[] | null | undefined): string {
  if (!hasCatalogTracks(list)) return '';
  return (list as string[])
    .map((item) => {
      const code = normalizeLanguageCode(item);
      return code ? languageDisplayName(code) : String(item).trim();
    })
    .filter(Boolean)
    .join(', ');
}

export function resolveAudioAvailability(item: CatalogAvailabilityFields): AudioAvailability {
  if (item.audioAvailability) return item.audioAvailability;
  const languages = (item.audio || []).map(normalizeLanguageCode).filter(Boolean) as string[];
  const dubbed = (item.dubbed || []).map(normalizeLanguageCode).filter(Boolean) as string[];
  const original = normalizeLanguageCode(item.language);
  return {
    original_language: original,
    languages,
    dubbed_languages: dubbed.filter((c) => c !== original),
    track_count: null,
    source: languages.length || dubbed.length ? 'admin_metadata' : original ? 'unknown' : 'unknown',
    selectable_in_player: false,
  };
}

export function resolveSubtitleAvailability(item: CatalogAvailabilityFields): SubtitleAvailability {
  if (item.subtitleAvailability) return item.subtitleAvailability;
  const languages = (item.subtitles || []).map(normalizeLanguageCode).filter(Boolean) as string[];
  return {
    languages,
    track_count: null,
    source: languages.length ? 'admin_metadata' : 'unknown',
    selectable_in_player: false,
  };
}

export function itemIsDubbed(item: CatalogAvailabilityFields): boolean {
  const audio = resolveAudioAvailability(item);
  return Array.isArray(audio.dubbed_languages) && audio.dubbed_languages.length > 0;
}

export function itemIsSubtitled(item: CatalogAvailabilityFields): boolean {
  const subs = resolveSubtitleAvailability(item);
  return (
    (Array.isArray(subs.languages) && subs.languages.length > 0) ||
    (typeof subs.track_count === 'number' && subs.track_count > 0)
  );
}

export type AvailabilityBadge = {
  key: string;
  label: string;
  fullLabel: string;
};

/** Compact high-value card badges. Max 2 + overflow. */
export function catalogAvailabilityBadges(
  item: CatalogAvailabilityFields,
  labels: { dubbed: string; subtitled: string; multiAudio: string }
): { badges: AvailabilityBadge[]; overflow: number } {
  const audio = resolveAudioAvailability(item);
  const subs = resolveSubtitleAvailability(item);
  const badges: AvailabilityBadge[] = [];

  for (const code of audio.dubbed_languages || []) {
    const short = compactLanguageBadge(code);
    badges.push({
      key: `dub-${code}`,
      label: `${short} Dub`,
      fullLabel: `${languageDisplayName(code)} ${labels.dubbed}`,
    });
  }
  for (const code of (subs.languages || []).slice(0, 2)) {
    const short = compactLanguageBadge(code);
    badges.push({
      key: `sub-${code}`,
      label: `${short} Sub`,
      fullLabel: `${languageDisplayName(code)} ${labels.subtitled}`,
    });
  }
  if ((audio.languages || []).length > 1 && !(audio.dubbed_languages || []).length) {
    badges.push({
      key: 'multi-audio',
      label: labels.multiAudio,
      fullLabel: labels.multiAudio,
    });
  }

  const visible = badges.slice(0, 2);
  const overflow = Math.max(0, badges.length - visible.length);
  return { badges: visible, overflow };
}

/** @deprecated Prefer catalogAvailabilityBadges */
export function catalogAvailabilityBadge(
  item: CatalogAvailabilityFields,
  labels: { dubbed: string; subtitled: string; audio: string }
): string | undefined {
  if (itemIsDubbed(item)) return labels.dubbed;
  if (itemIsSubtitled(item)) return labels.subtitled;
  const audio = resolveAudioAvailability(item);
  if ((audio.languages || []).length) return labels.audio;
  return undefined;
}

/** Detail-page language badges: e.g. FA Dub, EN Audio, FA Subtitle. */
export function movieDetailLanguageBadges(item: CatalogAvailabilityFields): AvailabilityBadge[] {
  const audio = resolveAudioAvailability(item);
  const subs = resolveSubtitleAvailability(item);
  const badges: AvailabilityBadge[] = [];
  const seen = new Set<string>();

  for (const code of audio.dubbed_languages || []) {
    const short = compactLanguageBadge(code);
    const key = `dub-${code}`;
    if (seen.has(key)) continue;
    seen.add(key);
    badges.push({
      key,
      label: `${short} Dub`,
      fullLabel: `${languageDisplayName(code)} Dub`,
    });
  }
  for (const code of audio.languages || []) {
    const short = compactLanguageBadge(code);
    const key = `audio-${code}`;
    if (seen.has(key) || seen.has(`dub-${code}`)) continue;
    seen.add(key);
    badges.push({
      key,
      label: `${short} Audio`,
      fullLabel: `${languageDisplayName(code)} Audio`,
    });
  }
  for (const code of subs.languages || []) {
    const short = compactLanguageBadge(code);
    const key = `sub-${code}`;
    if (seen.has(key)) continue;
    seen.add(key);
    badges.push({
      key,
      label: `${short} Subtitle`,
      fullLabel: `${languageDisplayName(code)} Subtitle`,
    });
  }
  return badges;
}

export function catalogAvailabilityChips(
  item: CatalogAvailabilityFields,
  labels: { dubbed: string; subtitled: string; audio: string; original?: string }
): string[] {
  const audio = resolveAudioAvailability(item);
  const subs = resolveSubtitleAvailability(item);
  const chips: string[] = [];
  if (audio.original_language) {
    chips.push(
      `${labels.original || 'Original'}: ${languageDisplayName(audio.original_language)}`
    );
  }
  if ((audio.languages || []).length) {
    chips.push(`${labels.audio}: ${formatCatalogTracks(audio.languages)}`);
  }
  if ((audio.dubbed_languages || []).length) {
    chips.push(`${labels.dubbed}: ${formatCatalogTracks(audio.dubbed_languages)}`);
  }
  if ((subs.languages || []).length) {
    chips.push(`${labels.subtitled}: ${formatCatalogTracks(subs.languages)}`);
  }
  return chips;
}
