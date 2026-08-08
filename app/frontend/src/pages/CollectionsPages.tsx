import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useLang } from '@/components/CustomerLayout';
import {
  fetchCollection,
  fetchCollections,
  mapCollectionItems,
  type CatalogCollection,
} from '@/lib/catalogData';
import { ApiError } from '@/lib/api';
import { CollectionItemsGrid } from '@/components/collections/CollectionItemsGrid';
import NotFoundPage from '@/pages/NotFoundPage';

function PageLoading() {
  return (
    <div className="container mx-auto space-y-4 px-4 pb-8 pt-6 sm:px-6 lg:px-8" data-testid="collections-loading">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function PageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3" data-testid="collections-error">
      <p className="text-muted-foreground">{message}</p>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}

/** Public, published-only collections index. Empty collections are excluded server-side. */
export function CollectionsIndexPage() {
  const { t } = useLang();
  const [collections, setCollections] = useState<CatalogCollection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await fetchCollections({ page_size: 100 });
      // Defensive client-side filter — never show a collection with no visible items.
      setCollections(page.items.filter((c) => (c.item_count ?? 0) > 0));
    } catch (err) {
      setCollections([]);
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load collections'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen" data-testid="collections-index-page">
      <div className="container mx-auto px-4 pb-8 pt-6 sm:px-6 lg:px-8">
        <h1 className="font-serif text-2xl font-bold text-foreground md:text-3xl">
          {t.pages.collectionsTitle}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{t.pages.collectionsSubtitle}</p>

        {loading ? (
          <PageLoading />
        ) : error ? (
          <PageError message={error} onRetry={load} />
        ) : collections.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground" data-testid="collections-empty">
            {t.pages.collectionEmpty}
          </div>
        ) : (
          <ul className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3" data-testid="collections-grid">
            {collections.map((collection) => (
              <li key={collection.id}>
                <Link
                  to={`/collections/${collection.slug}`}
                  data-testid={`collection-card-${collection.slug}`}
                  className="group flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="aspect-[16/9] w-full overflow-hidden bg-muted">
                    {collection.backdrop_url || collection.poster_url ? (
                      <img
                        src={collection.backdrop_url || collection.poster_url}
                        alt=""
                        loading="lazy"
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                        {collection.title}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-1 flex-col gap-1.5 p-4">
                    <h2 className="text-base font-semibold text-foreground">{collection.title}</h2>
                    {collection.short_description || collection.description ? (
                      <p className="line-clamp-2 text-sm text-muted-foreground">
                        {collection.short_description || collection.description}
                      </p>
                    ) : null}
                    <p className="mt-auto pt-2 text-xs font-medium text-muted-foreground">
                      {t.pages.collectionItems.replace('{count}', String(collection.item_count ?? 0))}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Public collection detail — 404s via the shared NotFoundPage for unknown/unpublished slugs. */
export function CollectionDetailPage() {
  const { slug } = useParams();
  const { t } = useLang();
  const navigate = useNavigate();
  const [collection, setCollection] = useState<CatalogCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const result = await fetchCollection(slug);
      setCollection(result);
    } catch (err) {
      setCollection(null);
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
      } else {
        setError(
          err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Failed to load collection'
        );
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <PageLoading />;
  if (notFound) return <NotFoundPage />;
  if (error || !collection) return <PageError message={error || 'Collection not found'} onRetry={load} />;

  const items = mapCollectionItems(collection.items);
  const availabilityLabels = {
    dubbed: t.movie.dubbed,
    subtitled: t.nav.subtitled,
    multiAudio: 'Multi Audio',
  };

  return (
    <div className="min-h-screen" data-testid="collection-detail-page">
      {collection.backdrop_url ? (
        <div className="relative h-[32vh] md:h-[42vh]">
          <img src={collection.backdrop_url} alt="" className="h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
        </div>
      ) : null}

      <div
        className={`container mx-auto px-4 pb-10 sm:px-6 lg:px-8 ${
          collection.backdrop_url ? '-mt-16 relative z-10' : 'pt-6'
        }`}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          {collection.poster_url ? (
            <img
              src={collection.poster_url}
              alt=""
              className="mx-auto w-[140px] shrink-0 rounded-lg shadow-xl sm:mx-0 md:w-[180px]"
            />
          ) : null}
          <div className="flex-1 space-y-2 text-center sm:text-left">
            <h1 className="font-serif text-2xl font-bold text-foreground md:text-3xl">
              {collection.title}
            </h1>
            {collection.description || collection.short_description ? (
              <p className="mx-auto max-w-2xl text-sm text-foreground/80 sm:mx-0">
                {collection.description || collection.short_description}
              </p>
            ) : null}
            <p className="text-xs font-medium text-muted-foreground" data-testid="collection-item-count">
              {t.pages.collectionItems.replace('{count}', String(collection.item_count ?? items.length))}
            </p>
          </div>
        </div>

        <div className="mt-8">
          {items.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground" data-testid="collection-detail-empty">
              {t.pages.collectionEmpty}
            </div>
          ) : (
            <CollectionItemsGrid
              items={items}
              availabilityLabels={availabilityLabels}
              onActivateMovie={(id) => navigate(`/movie/${id}`)}
              onActivateSeries={(id) => navigate(`/series/${id}`)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
