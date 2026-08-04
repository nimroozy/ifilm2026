import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  applyBootstrapDocumentLocale,
  applyDocumentLocale,
  isAppLocale,
  localeDir,
  parseLocale,
  readStoredLocale,
  resolvePublicLocale,
  writeStoredLocale,
} from './locale';

describe('locale persistence', () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = `${LOCALE_STORAGE_KEY}=; path=/; max-age=0`;
    document.documentElement.setAttribute('lang', 'en');
    document.documentElement.setAttribute('dir', 'ltr');
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('defaults to English when nothing is stored', () => {
    expect(readStoredLocale()).toBe('en');
    expect(DEFAULT_LOCALE).toBe('en');
  });

  it('parses only explicit locale codes', () => {
    expect(parseLocale('en')).toBe('en');
    expect(parseLocale('fa')).toBe('fa');
    expect(parseLocale('ps')).toBe('ps');
    expect(parseLocale('English')).toBeNull();
    expect(parseLocale('Persian')).toBeNull();
    expect(parseLocale('fa-IR')).toBeNull();
    expect(parseLocale('')).toBeNull();
    expect(isAppLocale('fa')).toBe(true);
    expect(isAppLocale('xx')).toBe(false);
  });

  it('falls back to English for invalid stored values', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'Persian');
    expect(readStoredLocale()).toBe('en');
    localStorage.setItem(LOCALE_STORAGE_KEY, 'xx');
    expect(readStoredLocale()).toBe('en');
  });

  it('reads and writes localStorage with ifilm.locale', () => {
    writeStoredLocale('fa');
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('fa');
    expect(readStoredLocale()).toBe('fa');
    writeStoredLocale('en');
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    expect(readStoredLocale()).toBe('en');
  });

  it('prefers localStorage over cookie', () => {
    document.cookie = `${LOCALE_STORAGE_KEY}=ps; path=/`;
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en');
    expect(resolvePublicLocale()).toBe('en');
  });

  it('uses cookie when localStorage is empty', () => {
    document.cookie = `${LOCALE_STORAGE_KEY}=ps; path=/`;
    expect(resolvePublicLocale()).toBe('ps');
  });

  it('prefers explicit user preference over storage', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'fa');
    expect(resolvePublicLocale({ userPreference: 'en' })).toBe('en');
    expect(resolvePublicLocale({ userPreference: 'bogus' })).toBe('fa');
  });

  it('maps direction correctly', () => {
    expect(localeDir('en')).toBe('ltr');
    expect(localeDir('fa')).toBe('rtl');
    expect(localeDir('ps')).toBe('rtl');
  });

  it('applyDocumentLocale sets public lang/dir', () => {
    applyDocumentLocale('fa', '/');
    expect(document.documentElement.getAttribute('lang')).toBe('fa');
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    applyDocumentLocale('en', '/movies');
    expect(document.documentElement.getAttribute('lang')).toBe('en');
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
  });

  it('applyDocumentLocale forces admin to en/ltr even when locale is fa', () => {
    applyDocumentLocale('fa', '/admin');
    expect(document.documentElement.getAttribute('lang')).toBe('en');
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
    applyDocumentLocale('ps', '/admin/media');
    expect(document.documentElement.getAttribute('lang')).toBe('en');
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
  });

  it('bootstrap applies stored locale without browser language', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'ps');
    const locale = applyBootstrapDocumentLocale();
    expect(locale).toBe('ps');
    // Without mocking location as /admin, public attrs apply
    expect(document.documentElement.getAttribute('lang')).toBe('ps');
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
  });
});
