import { describe, it, expect } from 'vitest';
import {
  isNavActive,
  DESKTOP_NAV_ITEMS,
  DESKTOP_NAV_MORE_IDS,
  DESKTOP_NAV_PRIMARY_IDS,
  MOBILE_BOTTOM_NAV,
  WATCHLIST_NAV_ITEM,
} from '@/components/customer/navConfig';
import { FOOTER_SOCIAL_LINKS } from '@/lib/siteLinks';
import { getAppVersion } from '@/lib/appVersion';

describe('customer nav active matching', () => {
  const movies = DESKTOP_NAV_ITEMS.find((i) => i.id === 'movies')!;
  const series = DESKTOP_NAV_ITEMS.find((i) => i.id === 'series')!;
  const home = DESKTOP_NAV_ITEMS.find((i) => i.id === 'home')!;
  const genres = DESKTOP_NAV_ITEMS.find((i) => i.id === 'genres')!;

  it('marks nested movie detail under Movies', () => {
    expect(isNavActive('/movie/12', movies)).toBe(true);
    expect(isNavActive('/movies', movies)).toBe(true);
    expect(isNavActive('/series', movies)).toBe(false);
  });

  it('marks nested series detail under Series', () => {
    expect(isNavActive('/series/5', series)).toBe(true);
    expect(isNavActive('/series', series)).toBe(true);
  });

  it('only marks home for exact /', () => {
    expect(isNavActive('/', home)).toBe(true);
    expect(isNavActive('/movies', home)).toBe(false);
  });

  it('marks genres path', () => {
    expect(isNavActive('/genres', genres)).toBe(true);
  });

  it('keeps G1 primary destinations and More menu destinations', () => {
    expect(DESKTOP_NAV_PRIMARY_IDS).toEqual([
      'home',
      'movies',
      'series',
      'children',
      'genres',
    ]);
    expect(DESKTOP_NAV_MORE_IDS).toEqual([
      'collections',
      'whatToWatch',
      'dubbed',
      'subtitled',
      'newReleases',
      'requestMovie',
    ]);
    const ids = DESKTOP_NAV_ITEMS.map((i) => i.id);
    expect(ids).toEqual(
      expect.arrayContaining(['genres', 'collections', 'dubbed', 'subtitled', 'newReleases'])
    );
    expect(ids).not.toContain('myList');
  });

  it('keeps watchlist as a dedicated nav item outside desktop chrome', () => {
    expect(WATCHLIST_NAV_ITEM.id).toBe('myList');
    expect(isNavActive('/watchlist', WATCHLIST_NAV_ITEM)).toBe(true);
    expect(isNavActive('/movies', WATCHLIST_NAV_ITEM)).toBe(false);
  });

  it('marks collection detail routes as active under Collections', () => {
    const collections = DESKTOP_NAV_ITEMS.find((i) => i.id === 'collections')!;
    expect(isNavActive('/collections', collections)).toBe(true);
    expect(isNavActive('/collections/staff-picks', collections)).toBe(true);
    expect(isNavActive('/movies', collections)).toBe(false);
  });

  it('keeps mobile bottom tabs focused on core destinations', () => {
    expect(MOBILE_BOTTOM_NAV.map((i) => i.id)).toEqual([
      'home',
      'movies',
      'series',
      'search',
      'profile',
    ]);
    expect(MOBILE_BOTTOM_NAV.map((i) => i.id)).not.toContain('requestMovie');
  });

  it('exposes Request Movie in More destinations but not as a primary tab', () => {
    expect(DESKTOP_NAV_MORE_IDS).toContain('requestMovie');
    expect(DESKTOP_NAV_PRIMARY_IDS).not.toContain('requestMovie');
    const item = DESKTOP_NAV_ITEMS.find((i) => i.id === 'requestMovie')!;
    expect(isNavActive('/request', item)).toBe(true);
  });
});

describe('footer social policy', () => {
  it('only exposes real external links (no app stores)', () => {
    expect(FOOTER_SOCIAL_LINKS.length).toBeGreaterThan(0);
    for (const link of FOOTER_SOCIAL_LINKS) {
      expect(link.href.startsWith('https://')).toBe(true);
      expect(link.href.toLowerCase()).not.toMatch(/apps\.apple|play\.google|appstore/);
    }
  });
});

describe('app version helper', () => {
  it('returns null when unset', () => {
    const v = getAppVersion();
    expect(v === null || typeof v === 'string').toBe(true);
  });
});
