/** Public UI locale persistence. Stable key + explicit codes only. */

export const LOCALE_STORAGE_KEY = 'ifilm.locale';
export const LOCALE_COOKIE_KEY = 'ifilm.locale';

export type AppLocale = 'en' | 'fa' | 'ps';

export const DEFAULT_LOCALE: AppLocale = 'en';

const ALLOWED: ReadonlySet<string> = new Set(['en', 'fa', 'ps']);

export function isAppLocale(value: unknown): value is AppLocale {
  return typeof value === 'string' && ALLOWED.has(value);
}

export function parseLocale(value: unknown): AppLocale | null {
  return isAppLocale(value) ? value : null;
}

export function localeDir(locale: AppLocale): 'ltr' | 'rtl' {
  return locale === 'en' ? 'ltr' : 'rtl';
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const prefix = `${name}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined') return;
  // 1 year; SameSite=Lax so it survives restarts without being sent cross-site.
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

/**
 * Resolve public locale without using browser language.
 * Priority: localStorage → cookie → English default.
 * (Authenticated backend preference can be layered on later via override.)
 */
export function resolvePublicLocale(options?: {
  /** Explicit backend preference when the user has saved one. */
  userPreference?: unknown;
}): AppLocale {
  const fromUser = parseLocale(options?.userPreference);
  if (fromUser) return fromUser;

  try {
    if (typeof localStorage !== 'undefined') {
      const fromStorage = parseLocale(localStorage.getItem(LOCALE_STORAGE_KEY));
      if (fromStorage) return fromStorage;
    }
  } catch {
    // private mode / blocked storage
  }

  const fromCookie = parseLocale(readCookie(LOCALE_COOKIE_KEY));
  if (fromCookie) return fromCookie;

  return DEFAULT_LOCALE;
}

export function readStoredLocale(): AppLocale {
  return resolvePublicLocale();
}

export function writeStoredLocale(locale: AppLocale): void {
  if (!isAppLocale(locale)) return;
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    }
  } catch {
    // ignore
  }
  try {
    writeCookie(LOCALE_COOKIE_KEY, locale);
  } catch {
    // ignore
  }
}

export function isAdminPath(pathname: string = typeof location !== 'undefined' ? location.pathname : ''): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/');
}

/** Apply documentElement lang/dir for the current path (admin forced EN/LTR). */
export function applyDocumentLocale(locale: AppLocale, pathname?: string): void {
  if (typeof document === 'undefined') return;
  if (isAdminPath(pathname)) {
    document.documentElement.setAttribute('lang', 'en');
    document.documentElement.setAttribute('dir', 'ltr');
    return;
  }
  document.documentElement.setAttribute('lang', locale);
  document.documentElement.setAttribute('dir', localeDir(locale));
}

/** Synchronous bootstrap before React paint — no browser-language detection. */
export function applyBootstrapDocumentLocale(): AppLocale {
  const locale = readStoredLocale();
  applyDocumentLocale(locale);
  return locale;
}
