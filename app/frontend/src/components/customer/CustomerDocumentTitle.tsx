import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';

const BRAND = 'iFilm';

type PlayerTitleContextValue = {
  mediaTitle: string | null;
  setMediaTitle: (title: string | null) => void;
};

const PlayerTitleContext = createContext<PlayerTitleContextValue | null>(null);

/** Shares the loaded player title with the document-title effect. */
export function PlayerDocumentTitleProvider({ children }: { children: ReactNode }) {
  const [mediaTitle, setMediaTitleState] = useState<string | null>(null);
  const setMediaTitle = useCallback((title: string | null) => {
    const next = title?.trim() || null;
    setMediaTitleState((current) => (current === next ? current : next));
  }, []);
  const value = useMemo(() => ({ mediaTitle, setMediaTitle }), [mediaTitle, setMediaTitle]);
  return <PlayerTitleContext.Provider value={value}>{children}</PlayerTitleContext.Provider>;
}

export function usePlayerMediaTitle(): string | null {
  return useContext(PlayerTitleContext)?.mediaTitle ?? null;
}

const noopSetPlayerMediaTitle = (_title: string | null) => {};

export function useSetPlayerMediaTitle(): (title: string | null) => void {
  return useContext(PlayerTitleContext)?.setMediaTitle ?? noopSetPlayerMediaTitle;
}

/** Resolve a customer-facing document title for the current path. */
export function resolveCustomerTitle(
  pathname: string,
  t: ReturnType<typeof useLang>['t'],
  mediaTitle?: string | null,
): string {
  const brand = BRAND;
  if (pathname === '/') return brand;
  if (pathname.startsWith('/player/')) {
    const label = mediaTitle?.trim();
    // Valid player routes are never "Page not found". Metadata replaces the
    // generic playback label once the movie or episode title is known.
    if (label && label !== 'Playback') return `${label} · ${brand}`;
    return `Playback · ${brand}`;
  }
  if (pathname.startsWith('/movie/')) return `${t.common.movie} · ${brand}`;
  if (pathname.startsWith('/series/') && pathname !== '/series') return `${t.common.series} · ${brand}`;
  const map: Record<string, string> = {
    '/movies': t.nav.movies,
    '/series': t.nav.series,
    '/children': t.nav.children,
    '/kids': t.nav.children,
    '/genres': t.pages.genresTitle,
    '/dubbed': t.pages.dubbedTitle,
    '/subtitled': t.pages.subtitledTitle,
    '/new-releases': t.pages.newReleasesTitle,
    '/what-to-watch': t.nav.whatToWatch,
    '/request': t.nav.requestMovie,
    '/collections': t.pages.collectionsTitle,
    '/search': t.nav.search,
    '/about': t.legal.aboutTitle,
    '/credits': t.legal.creditsTitle,
    '/contact': t.legal.contactTitle,
    '/help': t.legal.helpTitle,
    '/privacy': t.legal.privacyTitle,
    '/terms': t.legal.termsTitle,
    '/copyright': t.legal.copyrightTitle,
    '/profile': t.profile.title,
    '/devices': t.profile.devices,
    '/watchlist': t.profile.watchlist,
    '/history': t.profile.history,
    '/login': t.login.title,
  };
  const exact = map[pathname];
  if (exact) return `${exact} · ${brand}`;
  return `${t.pages.notFoundTitle} · ${brand}`;
}

/** Sets document.title for customer routes (admin routes manage their own titles). */
export default function CustomerDocumentTitle() {
  const { pathname } = useLocation();
  const { t } = useLang();
  const mediaTitle = usePlayerMediaTitle();

  useEffect(() => {
    if (pathname === '/admin' || pathname.startsWith('/admin/')) return;
    document.title = resolveCustomerTitle(
      pathname,
      t,
      pathname.startsWith('/player/') ? mediaTitle : null,
    );
  }, [pathname, t, mediaTitle]);

  return null;
}
