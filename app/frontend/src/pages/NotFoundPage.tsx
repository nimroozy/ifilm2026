import { Link } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';

export default function NotFoundPage() {
  const { t } = useLang();
  return (
    <div className="min-h-[50vh]" data-testid="not-found-page">
      <div className="container mx-auto flex max-w-lg flex-col items-center px-4 py-20 text-center sm:px-6">
        <p className="font-mono text-sm text-muted-foreground">404</p>
        <h1 className="mt-2 font-display text-3xl font-bold text-foreground">{t.pages.notFoundTitle}</h1>
        <p className="mt-3 text-sm text-muted-foreground">{t.pages.notFoundBody}</p>
        <Link
          to="/"
          className="mt-8 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid="not-found-home"
        >
          {t.nav.home}
        </Link>
      </div>
    </div>
  );
}
