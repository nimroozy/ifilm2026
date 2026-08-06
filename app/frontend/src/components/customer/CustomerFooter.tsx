import { Link } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';
import {
  FOOTER_COMPANY_PATHS,
  FOOTER_DISCOVER_PATHS,
  FOOTER_LEGAL_PATHS,
} from '@/components/customer/navConfig';
import { getAppVersion } from '@/lib/appVersion';
import {
  FOOTER_SOCIAL_LINKS,
  TMDB_WEBSITE,
} from '@/lib/siteLinks';

function footerLabel(
  id: string,
  t: ReturnType<typeof useLang>['t']
): string {
  const nav = t.nav as Record<string, string>;
  const footer = t.footer as Record<string, string>;
  if (id in nav) return nav[id];
  if (id in footer) return footer[id];
  return id;
}

export default function CustomerFooter() {
  const { t } = useLang();
  const version = getAppVersion();
  const year = new Date().getFullYear();
  const rights = t.footer.rights.replace('{year}', String(year));

  return (
    <footer
      className="border-t border-border bg-card/40"
      data-testid="customer-footer"
      role="contentinfo"
    >
      <div className="container mx-auto px-4 py-10 sm:px-6 lg:px-8">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="font-display text-xl font-bold tracking-tight text-primary">iFilm</p>
            <p className="mt-2 max-w-xs text-sm text-muted-foreground">{t.footer.tagline}</p>
            {FOOTER_SOCIAL_LINKS.length > 0 ? (
              <div className="mt-4" data-testid="footer-social">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t.footer.follow}
                </p>
                <ul className="mt-2 flex flex-wrap gap-3">
                  {FOOTER_SOCIAL_LINKS.map((link) => (
                    <li key={link.id}>
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid={`footer-social-${link.id}`}
                        className="text-sm text-foreground/80 underline-offset-4 hover:text-primary hover:underline"
                      >
                        {t.footer[link.labelKey]}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <nav aria-label={t.footer.discover} data-testid="footer-discover">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t.footer.discover}
            </p>
            <ul className="mt-3 space-y-2">
              {FOOTER_DISCOVER_PATHS.map((item) => (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className="text-sm text-foreground/80 hover:text-primary"
                    data-testid={`footer-link-${item.id}`}
                  >
                    {footerLabel(item.id, t)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <nav aria-label={t.footer.company} data-testid="footer-company">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t.footer.company}
            </p>
            <ul className="mt-3 space-y-2">
              {FOOTER_COMPANY_PATHS.map((item) => (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className="text-sm text-foreground/80 hover:text-primary"
                    data-testid={`footer-link-${item.id}`}
                  >
                    {footerLabel(item.id, t)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <nav aria-label={t.footer.legal} data-testid="footer-legal">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t.footer.legal}
            </p>
            <ul className="mt-3 space-y-2">
              {FOOTER_LEGAL_PATHS.map((item) => (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className="text-sm text-foreground/80 hover:text-primary"
                    data-testid={`footer-link-${item.id}`}
                  >
                    {footerLabel(item.id, t)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <div className="mt-10 space-y-3 border-t border-border pt-6">
          <p className="text-xs leading-relaxed text-muted-foreground" data-testid="footer-tmdb">
            {t.footer.tmdbAttribution}{' '}
            <a
              href={TMDB_WEBSITE}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              TMDB
            </a>
            .
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p data-testid="footer-rights">{rights}</p>
            {version ? (
              <p data-testid="footer-version">
                {t.footer.version} {version}
              </p>
            ) : (
              <p data-testid="footer-version" className="sr-only">
                {t.footer.version}
              </p>
            )}
          </div>
        </div>
      </div>
    </footer>
  );
}
