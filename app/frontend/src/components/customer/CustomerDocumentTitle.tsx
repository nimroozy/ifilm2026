import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';

/** Resolve a customer-facing document title for the current path. */
export function resolveCustomerTitle(pathname: string, t: ReturnType<typeof useLang>['t']): string {
  const brand = 'iFilm';
  if (pathname === '/') return brand;
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

  useEffect(() => {
    if (pathname === '/admin' || pathname.startsWith('/admin/')) return;
    document.title = resolveCustomerTitle(pathname, t);
  }, [pathname, t]);

  return null;
}
