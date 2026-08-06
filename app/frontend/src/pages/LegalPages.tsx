import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';
import {
  MOBIN_NET_SUPPORT_EMAIL,
  MOBIN_NET_WEBSITE,
  TMDB_WEBSITE,
} from '@/lib/siteLinks';

function LegalShell({
  title,
  children,
  testId,
}: {
  title: string;
  children: ReactNode;
  testId: string;
}) {
  return (
    <div className="min-h-screen" data-testid={testId}>
      <div className="container mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        <article className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h1 className="font-display text-3xl font-bold text-foreground">{title}</h1>
          <div className="mt-4 space-y-4 text-sm leading-relaxed text-muted-foreground">{children}</div>
        </article>
      </div>
    </div>
  );
}

export default function AboutPage() {
  const { t } = useLang();
  return (
    <div className="min-h-screen" data-testid="about-page">
      <div className="container mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h1 className="font-display text-3xl font-bold text-foreground">{t.legal.aboutTitle}</h1>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{t.legal.aboutBody}</p>
        </section>

        <section
          className="mt-6 rounded-lg border border-border bg-card p-6 shadow-sm"
          aria-labelledby="credits-heading"
          data-testid="credits-section"
        >
          <h2 id="credits-heading" className="text-xl font-semibold text-foreground">
            {t.legal.creditsTitle}
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
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
        </section>
      </div>
    </div>
  );
}

export function ContactPage() {
  const { t } = useLang();
  const contactUrl = `${MOBIN_NET_WEBSITE.replace(/\/$/, '')}/contact-us/`;
  return (
    <LegalShell title={t.legal.contactTitle} testId="contact-page">
      <p>{t.legal.contactIntro}</p>
      <p>
        <span className="font-medium text-foreground">{t.legal.contactEmailLabel}: </span>
        <a
          href={`mailto:${MOBIN_NET_SUPPORT_EMAIL}`}
          className="text-primary underline-offset-4 hover:underline"
          data-testid="contact-email"
        >
          {MOBIN_NET_SUPPORT_EMAIL}
        </a>
      </p>
      <p>
        <span className="font-medium text-foreground">{t.legal.contactWebLabel}: </span>
        <a
          href={contactUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline-offset-4 hover:underline"
          data-testid="contact-web"
        >
          mobinnet.af/contact-us
        </a>
      </p>
      <p>
        <Link to="/help" className="text-primary underline-offset-4 hover:underline">
          {t.footer.help}
        </Link>
      </p>
    </LegalShell>
  );
}

export function HelpPage() {
  const { t } = useLang();
  const faqs = [
    { q: t.legal.helpQ1, a: t.legal.helpA1 },
    { q: t.legal.helpQ2, a: t.legal.helpA2 },
    { q: t.legal.helpQ3, a: t.legal.helpA3 },
    { q: t.legal.helpQ4, a: t.legal.helpA4 },
  ];
  return (
    <LegalShell title={t.legal.helpTitle} testId="help-page">
      <p>{t.legal.helpIntro}</p>
      <dl className="space-y-4">
        {faqs.map((item) => (
          <div key={item.q}>
            <dt className="font-medium text-foreground">{item.q}</dt>
            <dd className="mt-1">{item.a}</dd>
          </div>
        ))}
      </dl>
    </LegalShell>
  );
}

export function PrivacyPage() {
  const { t } = useLang();
  return (
    <LegalShell title={t.legal.privacyTitle} testId="privacy-page">
      <p>{t.legal.privacyBody}</p>
    </LegalShell>
  );
}

export function TermsPage() {
  const { t } = useLang();
  return (
    <LegalShell title={t.legal.termsTitle} testId="terms-page">
      <p>{t.legal.termsBody}</p>
    </LegalShell>
  );
}

export function CopyrightPage() {
  const { t } = useLang();
  return (
    <LegalShell title={t.legal.copyrightTitle} testId="copyright-page">
      <p>{t.legal.copyrightBody}</p>
      <p>
        <a
          href={`mailto:${MOBIN_NET_SUPPORT_EMAIL}`}
          className="text-primary underline-offset-4 hover:underline"
        >
          {MOBIN_NET_SUPPORT_EMAIL}
        </a>
      </p>
    </LegalShell>
  );
}
