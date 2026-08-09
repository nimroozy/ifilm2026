/** Shared customer navigation paths and active-route helpers. */

export type CustomerNavId =
  | 'home'
  | 'movies'
  | 'series'
  | 'children'
  | 'genres'
  | 'collections'
  | 'dubbed'
  | 'subtitled'
  | 'newReleases'
  | 'myList'
  | 'whatToWatch'
  | 'requestMovie'
  | 'search'
  | 'profile';

export type CustomerNavItem = {
  id: CustomerNavId;
  path: string;
  /** Match nested detail routes (e.g. /movie/:id → movies). */
  matchPrefixes?: string[];
};

/** Always-visible desktop primary destinations (G1 Header V2). */
export const DESKTOP_NAV_PRIMARY_IDS: CustomerNavId[] = [
  'home',
  'movies',
  'series',
  'children',
  'genres',
];

/**
 * Desktop/mobile More menu — product-owner approved destinations only.
 * Uses real routes; no fake links.
 */
export const DESKTOP_NAV_MORE_IDS: CustomerNavId[] = [
  'collections',
  'whatToWatch',
  'dubbed',
  'subtitled',
  'newReleases',
  'requestMovie',
];

/** Full catalog destinations for sheet/footer discovery (excludes My List — profile owns that). */
export const DESKTOP_NAV_ITEMS: CustomerNavItem[] = [
  { id: 'home', path: '/' },
  { id: 'movies', path: '/movies', matchPrefixes: ['/movie/'] },
  { id: 'series', path: '/series', matchPrefixes: ['/series/'] },
  { id: 'children', path: '/children' },
  { id: 'genres', path: '/genres' },
  { id: 'collections', path: '/collections', matchPrefixes: ['/collections/'] },
  { id: 'whatToWatch', path: '/what-to-watch' },
  { id: 'dubbed', path: '/dubbed' },
  { id: 'subtitled', path: '/subtitled' },
  { id: 'newReleases', path: '/new-releases' },
  { id: 'requestMovie', path: '/request' },
];

/** @deprecated Prefer DESKTOP_NAV_MORE_IDS — kept for tests migrating off myList-in-nav. */
export const WATCHLIST_NAV_ITEM: CustomerNavItem = {
  id: 'myList',
  path: '/watchlist',
};

export const MOBILE_BOTTOM_NAV: CustomerNavItem[] = [
  { id: 'home', path: '/' },
  { id: 'movies', path: '/movies', matchPrefixes: ['/movie/'] },
  { id: 'series', path: '/series', matchPrefixes: ['/series/'] },
  { id: 'search', path: '/search' },
  { id: 'profile', path: '/profile' },
];

export const FOOTER_DISCOVER_PATHS = [
  { id: 'genres' as const, path: '/genres' },
  { id: 'collections' as const, path: '/collections' },
  { id: 'whatToWatch' as const, path: '/what-to-watch' },
  { id: 'requestMovie' as const, path: '/request' },
  { id: 'dubbed' as const, path: '/dubbed' },
  { id: 'subtitled' as const, path: '/subtitled' },
  { id: 'newReleases' as const, path: '/new-releases' },
  { id: 'children' as const, path: '/children' },
];

export const FOOTER_COMPANY_PATHS = [
  { id: 'about' as const, path: '/about' },
  { id: 'contact' as const, path: '/contact' },
  { id: 'help' as const, path: '/help' },
];

export const FOOTER_LEGAL_PATHS = [
  { id: 'privacy' as const, path: '/privacy' },
  { id: 'terms' as const, path: '/terms' },
  { id: 'copyright' as const, path: '/copyright' },
  { id: 'credits' as const, path: '/credits' },
];

export function navItemById(id: CustomerNavId): CustomerNavItem | undefined {
  if (id === 'myList') return WATCHLIST_NAV_ITEM;
  return DESKTOP_NAV_ITEMS.find((item) => item.id === id);
}

export function isNavActive(pathname: string, item: CustomerNavItem): boolean {
  if (item.path === '/') return pathname === '/';
  if (pathname === item.path) return true;
  if (pathname.startsWith(`${item.path}/`)) return true;
  return (item.matchPrefixes || []).some(
    (prefix) => pathname === prefix.slice(0, -1) || pathname.startsWith(prefix)
  );
}
