import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { useLang } from '@/components/CustomerLayout';
import {
  FOOTER_COMPANY_PATHS,
  FOOTER_DISCOVER_PATHS,
  FOOTER_LEGAL_PATHS,
} from '@/components/customer/navConfig';
import { getAppVersion } from '@/lib/appVersion';
import { FOOTER_SOCIAL_LINKS } from '@/lib/siteLinks';
import { cn } from '@/lib/utils';

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

function FooterSection({
  title,
  testId,
  items,
  t,
  open,
  onToggle,
}: {
  title: string;
  testId: string;
  items: { id: string; path: string }[];
  t: ReturnType<typeof useLang>['t'];
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <nav aria-label={title} data-testid={testId}>
      <button
        type="button"
        className="flex w-full items-center justify-between border-b border-border/60 py-2.5 text-start text-sm font-semibold text-foreground sm:pointer-events-none sm:border-0 sm:py-0 sm:text-xs sm:font-semibold sm:uppercase sm:tracking-wide sm:text-muted-foreground"
        onClick={onToggle}
        aria-expanded={open}
        data-testid={`${testId}-toggle`}
      >
        {title}
        <ChevronDown
          className={cn('h-4 w-4 text-muted-foreground transition sm:hidden', open && 'rotate-180')}
          aria-hidden
        />
      </button>
      <ul
        className={cn(
          'space-y-2 overflow-hidden pb-3 pt-1 sm:mt-3 sm:block sm:pb-0 sm:pt-0',
          open ? 'block' : 'hidden sm:block'
        )}
      >
        {items.map((item) => (
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
  );
}

export default function CustomerFooter() {
  const { t } = useLang();
  const version = getAppVersion();
  const year = new Date().getFullYear();
  const rights = t.footer.rights.replace('{year}', String(year));
  const [openSection, setOpenSection] = useState<string | null>(null);

  const toggle = (id: string) => {
    setOpenSection((prev) => (prev === id ? null : id));
  };

  return (
    <footer
      className="border-t border-border bg-card/40"
      data-testid="customer-footer"
      role="contentinfo"
    >
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-10 lg:px-8">
        <div className="grid gap-1 sm:grid-cols-2 sm:gap-8 lg:grid-cols-4">
          <div className="pb-3 sm:pb-0">
            <p className="font-display text-xl font-bold tracking-tight text-primary">iFilm</p>
            <p
              className="mt-1 max-w-xs text-sm text-muted-foreground"
              data-testid="footer-brand-byline"
            >
              {t.footer.tagline}
            </p>
            {FOOTER_SOCIAL_LINKS.length > 0 ? (
              <div className="mt-3 hidden sm:block" data-testid="footer-social">
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

          <FooterSection
            title={t.footer.discover}
            testId="footer-discover"
            items={FOOTER_DISCOVER_PATHS}
            t={t}
            open={openSection === 'discover'}
            onToggle={() => toggle('discover')}
          />
          <FooterSection
            title={t.footer.company}
            testId="footer-company"
            items={FOOTER_COMPANY_PATHS}
            t={t}
            open={openSection === 'company'}
            onToggle={() => toggle('company')}
          />
          <FooterSection
            title={t.footer.legal}
            testId="footer-legal"
            items={FOOTER_LEGAL_PATHS}
            t={t}
            open={openSection === 'legal'}
            onToggle={() => toggle('legal')}
          />
        </div>

        <div className="mt-5 space-y-2 border-t border-border pt-4 sm:mt-10 sm:space-y-3 sm:pt-6">
          <p className="text-xs text-muted-foreground">
            <Link to="/credits" className="hover:text-primary" data-testid="footer-credits-link">
              {t.footer.credits}
            </Link>
            <span className="mx-2 text-border" aria-hidden>
              ·
            </span>
            <span data-testid="footer-haroon-net">iFilm by Haroon Net</span>
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p data-testid="footer-rights">{rights}</p>
            {version ? (
              <p data-testid="footer-version">
                {t.footer.version} {version}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </footer>
  );
}
