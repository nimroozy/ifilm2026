import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  adminApi,
  ApiError,
  type CollectionDto,
  type CollectionItemDto,
  type CollectionPickerResultDto,
  type CollectionPublicDto,
  type MovieDto,
  type SeriesDto,
} from '@/lib/api';
import { mapCollectionItems } from '@/lib/catalogData';
import { CollectionItemsGrid } from '@/components/collections/CollectionItemsGrid';
import { ErrorState, LoadingBlock, POSTER_FALLBACK, PosterThumb, StatusBadge } from './adminShared';
import {
  COLLECTION_TYPE_LABELS,
  COLLECTION_TYPES,
  collectionFormSchema,
  collectionStatusActions,
  type CollectionFormValues,
} from './collectionsShared';

const COLLECTION_TABS = ['details', 'artwork', 'items', 'publishing', 'preview'] as const;
type CollectionTab = (typeof COLLECTION_TABS)[number];

function tabFromSearch(raw: string | null): CollectionTab {
  if (raw && (COLLECTION_TABS as readonly string[]).includes(raw)) return raw as CollectionTab;
  return 'details';
}

const FIELD_TAB: Partial<Record<keyof CollectionFormValues, CollectionTab>> = {
  title: 'details',
  slug: 'details',
  description: 'details',
  short_description: 'details',
  collection_type: 'details',
  visibility: 'details',
  sort_order: 'details',
  is_featured: 'details',
  poster_url: 'artwork',
  backdrop_url: 'artwork',
};

function emptyValues(): CollectionFormValues {
  return {
    title: '',
    slug: '',
    description: '',
    short_description: '',
    collection_type: 'editorial',
    visibility: 'public',
    poster_url: '',
    backdrop_url: '',
    sort_order: '' as unknown as number,
    is_featured: false,
  };
}

function DetailsFields({ form }: { form: UseFormReturn<CollectionFormValues> }) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Details</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Title</FormLabel>
              <FormControl>
                <Input {...field} data-testid="collection-title" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="slug"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Slug</FormLabel>
              <FormControl>
                <Input {...field} placeholder="auto from title if empty" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="collection_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Type</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger data-testid="collection-type-select">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {COLLECTION_TYPES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {COLLECTION_TYPE_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="short_description"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Short description</FormLabel>
              <FormControl>
                <Input {...field} placeholder="Shown on cards and shelves (optional)" />
              </FormControl>
              <p className="text-xs text-muted-foreground">Up to 240 characters.</p>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea rows={4} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="visibility"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Visibility</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="public">Public</SelectItem>
                  <SelectItem value="unlisted">Unlisted</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="sort_order"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Sort order</FormLabel>
              <FormControl>
                <Input type="number" {...field} value={field.value ?? ''} />
              </FormControl>
              <p className="text-xs text-muted-foreground">Lower numbers appear first among collections.</p>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="is_featured"
          render={({ field }) => (
            <FormItem className="flex items-center gap-2 space-y-0 sm:col-span-2">
              <FormControl>
                <Checkbox checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
              <FormLabel className="!mt-0">Featured on homepage</FormLabel>
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}

function ArtworkFields({
  form,
  posterPreview,
  onPosterError,
}: {
  form: UseFormReturn<CollectionFormValues>;
  posterPreview: string;
  onPosterError: () => void;
}) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Artwork</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-[120px_1fr]">
        <img
          src={posterPreview}
          alt="Poster preview"
          className="w-[100px] h-[150px] rounded object-cover bg-muted"
          onError={onPosterError}
        />
        <div className="space-y-4">
          <FormField
            control={form.control}
            name="poster_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Poster URL</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="https://..." data-testid="collection-poster-url" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="backdrop_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Backdrop URL</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="https://..." data-testid="collection-backdrop-url" />
                </FormControl>
                <p className="text-xs text-muted-foreground">
                  Shown as a hero banner on the public collection page when set.
                </p>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </CardContent>
    </Card>
  );
}

/** Item picker + ordered item list. Only available once a collection exists (edit mode). */
function ItemsTab({
  collectionId,
  items,
  onChanged,
}: {
  collectionId: number;
  items: CollectionItemDto[];
  onChanged: (collection: CollectionDto) => void;
}) {
  const [query, setQuery] = useState('');
  const [contentType, setContentType] = useState<'all' | 'movie' | 'series'>('all');
  const [publishedOnly, setPublishedOnly] = useState(true);
  const [results, setResults] = useState<CollectionPickerResultDto | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const sortedItems = useMemo(() => [...items].sort((a, b) => a.position - b.position), [items]);
  const existingMovieIds = useMemo(
    () => new Set(sortedItems.filter((i) => i.content_type === 'movie').map((i) => i.movie_id)),
    [sortedItems]
  );
  const existingSeriesIds = useMemo(
    () => new Set(sortedItems.filter((i) => i.content_type === 'series').map((i) => i.series_id)),
    [sortedItems]
  );

  const runSearch = useCallback(async () => {
    setSearching(true);
    setSearchError(null);
    try {
      const result = await adminApi.collectionPicker({
        q: query || undefined,
        content_type: contentType === 'all' ? undefined : contentType,
        published_only: publishedOnly,
        page_size: 20,
      });
      setResults(result);
    } catch (err) {
      setResults(null);
      setSearchError(err instanceof ApiError ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  }, [query, contentType, publishedOnly]);

  useEffect(() => {
    const t = window.setTimeout(runSearch, 300);
    return () => window.clearTimeout(t);
  }, [runSearch]);

  async function refreshCollection() {
    const updated = await adminApi.getCollection(collectionId);
    onChanged(updated);
  }

  async function addItem(kind: 'movie' | 'series', id: number) {
    const key = `${kind}-${id}`;
    setPendingKey(key);
    try {
      await adminApi.addCollectionItem(collectionId, kind === 'movie' ? { movie_id: id } : { series_id: id });
      toast.success('Item added');
      await refreshCollection();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to add item');
    } finally {
      setPendingKey(null);
    }
  }

  async function removeItem(item: CollectionItemDto) {
    setPendingKey(`remove-${item.id}`);
    try {
      await adminApi.removeCollectionItem(collectionId, item.id);
      toast.success('Item removed');
      await refreshCollection();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to remove item');
    } finally {
      setPendingKey(null);
    }
  }

  async function moveItem(index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= sortedItems.length) return;
    const reordered = [...sortedItems];
    const [moved] = reordered.splice(index, 1);
    reordered.splice(targetIndex, 0, moved);
    const itemIds = reordered.map((i) => i.id);
    setPendingKey(`move-${moved.id}`);
    try {
      const updated = await adminApi.reorderCollectionItems(collectionId, itemIds);
      onChanged(updated);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to reorder items');
    } finally {
      setPendingKey(null);
    }
  }

  function itemLabel(item: CollectionItemDto): string {
    if (item.content_type === 'movie') return item.movie?.title || item.custom_title || `Movie #${item.movie_id}`;
    return item.series?.title || item.custom_title || `Series #${item.series_id}`;
  }

  function itemPoster(item: CollectionItemDto): string | undefined {
    return item.content_type === 'movie' ? item.movie?.poster_url : item.series?.poster_url;
  }

  return (
    <div className="space-y-4">
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">Current items ({sortedItems.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {sortedItems.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="collection-items-empty">
              No items yet. Use the picker below to add movies or series.
            </p>
          ) : (
            <ul className="space-y-2" data-testid="collection-items-list">
              {sortedItems.map((item, index) => (
                <li
                  key={item.id}
                  className="flex items-center gap-3 rounded-lg border border-border p-2"
                  data-testid={`collection-item-${item.id}`}
                >
                  <PosterThumb src={itemPoster(item)} alt={itemLabel(item)} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-foreground">{itemLabel(item)}</p>
                    <p className="text-xs capitalize text-muted-foreground">{item.content_type}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      disabled={index === 0 || pendingKey != null}
                      onClick={() => moveItem(index, -1)}
                      aria-label={`Move ${itemLabel(item)} up`}
                      data-testid={`collection-item-up-${item.id}`}
                    >
                      <ArrowUp className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      disabled={index === sortedItems.length - 1 || pendingKey != null}
                      onClick={() => moveItem(index, 1)}
                      aria-label={`Move ${itemLabel(item)} down`}
                      data-testid={`collection-item-down-${item.id}`}
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive"
                      disabled={pendingKey != null}
                      onClick={() => removeItem(item)}
                      aria-label={`Remove ${itemLabel(item)}`}
                      data-testid={`collection-item-remove-${item.id}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">Add items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Search movies or series..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="max-w-xs"
              data-testid="collection-picker-search"
            />
            <Select value={contentType} onValueChange={(v) => setContentType(v as typeof contentType)}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                <SelectItem value="movie">Movies</SelectItem>
                <SelectItem value="series">Series</SelectItem>
              </SelectContent>
            </Select>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox checked={publishedOnly} onCheckedChange={(v) => setPublishedOnly(Boolean(v))} />
              Published only
            </label>
          </div>

          {searching ? (
            <LoadingBlock rows={3} />
          ) : searchError ? (
            <ErrorState message={searchError} onRetry={runSearch} />
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2" data-testid="collection-picker-results">
              {(results?.movies ?? []).map((movie: MovieDto) => {
                const already = existingMovieIds.has(movie.id);
                const key = `movie-${movie.id}`;
                return (
                  <li
                    key={key}
                    className="flex items-center gap-2 rounded-lg border border-border p-2"
                    data-testid={`picker-movie-${movie.id}`}
                  >
                    <img
                      src={movie.poster_url || POSTER_FALLBACK}
                      alt=""
                      className="h-12 w-9 shrink-0 rounded object-cover bg-muted"
                    />
                    <span className="min-w-0 flex-1 truncate text-sm">{movie.title}</span>
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      className="h-7 w-7 shrink-0"
                      disabled={already || pendingKey === key}
                      onClick={() => addItem('movie', movie.id)}
                      aria-label={`Add ${movie.title}`}
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                );
              })}
              {(results?.series ?? []).map((series: SeriesDto) => {
                const already = existingSeriesIds.has(series.id);
                const key = `series-${series.id}`;
                return (
                  <li
                    key={key}
                    className="flex items-center gap-2 rounded-lg border border-border p-2"
                    data-testid={`picker-series-${series.id}`}
                  >
                    <img
                      src={series.poster_url || POSTER_FALLBACK}
                      alt=""
                      className="h-12 w-9 shrink-0 rounded object-cover bg-muted"
                    />
                    <span className="min-w-0 flex-1 truncate text-sm">{series.title}</span>
                    <Button
                      type="button"
                      size="icon"
                      variant="outline"
                      className="h-7 w-7 shrink-0"
                      disabled={already || pendingKey === key}
                      onClick={() => addItem('series', series.id)}
                      aria-label={`Add ${series.title}`}
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                );
              })}
              {results && results.movies.length === 0 && results.series.length === 0 ? (
                <li className="text-sm text-muted-foreground sm:col-span-2">No matches found.</li>
              ) : null}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PublishingTab({
  collection,
  onChanged,
}: {
  collection: CollectionDto;
  onChanged: (collection: CollectionDto) => void;
}) {
  const [working, setWorking] = useState<'publish' | 'unpublish' | 'archive' | null>(null);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const { canPublish, canUnpublish, canRestore, canArchive } = collectionStatusActions(collection.status);

  async function run(action: 'publish' | 'unpublish' | 'archive') {
    setWorking(action);
    try {
      let updated: CollectionDto;
      if (action === 'publish') updated = await adminApi.publishCollection(collection.id, collection.updated_at);
      else if (action === 'unpublish')
        updated = await adminApi.unpublishCollection(collection.id, collection.updated_at);
      else updated = await adminApi.archiveCollection(collection.id, collection.updated_at);
      onChanged(updated);
      toast.success(
        action === 'publish' ? 'Collection published' : action === 'unpublish' ? 'Collection moved to draft' : 'Collection archived'
      );
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `${action} failed`);
    } finally {
      setWorking(null);
      setConfirmArchive(false);
    }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Publishing</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">Current status:</span>
          <StatusBadge status={collection.status} />
        </div>
        <p className="text-sm text-muted-foreground">
          {collection.item_count ?? collection.items.length} item(s) in this collection
          {(collection.item_count ?? collection.items.length) === 0
            ? ' — publishing an empty collection will hide it from customers automatically.'
            : '.'}
        </p>
        <div className="flex flex-wrap gap-3">
          {canPublish ? (
            <Button
              type="button"
              disabled={working != null}
              onClick={() => run('publish')}
              data-testid="collection-publish"
            >
              {working === 'publish' ? 'Publishing…' : 'Publish'}
            </Button>
          ) : null}
          {canUnpublish ? (
            <Button
              type="button"
              variant="outline"
              disabled={working != null}
              onClick={() => run('unpublish')}
              data-testid="collection-unpublish"
            >
              {working === 'unpublish' ? 'Unpublishing…' : 'Unpublish'}
            </Button>
          ) : null}
          {canRestore ? (
            <Button
              type="button"
              variant="outline"
              disabled={working != null}
              onClick={() => run('unpublish')}
              data-testid="collection-restore"
            >
              {working === 'unpublish' ? 'Restoring…' : 'Restore to draft'}
            </Button>
          ) : null}
          {canArchive ? (
            <Button
              type="button"
              variant="outline"
              className="text-destructive"
              disabled={working != null}
              onClick={() => setConfirmArchive(true)}
              data-testid="collection-archive"
            >
              Archive
            </Button>
          ) : null}
        </div>
      </CardContent>

      <AlertDialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive this collection?</AlertDialogTitle>
            <AlertDialogDescription>
              Archived collections are removed from customer-facing pages. You can restore them to draft later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => run('archive')}>Archive</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function PreviewTab({ collectionId }: { collectionId: number }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<CollectionPublicDto | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.previewCollection(collectionId);
      setPreview(result);
    } catch (err) {
      setPreview(null);
      setError(err instanceof ApiError ? err.message : 'Failed to load preview');
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingBlock rows={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!preview) return null;

  const items = mapCollectionItems(preview.items);

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Public preview</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {preview.backdrop_url ? (
          <img src={preview.backdrop_url} alt="" className="h-40 w-full rounded-lg object-cover" />
        ) : null}
        <div>
          <h3 className="text-lg font-semibold text-foreground">{preview.title}</h3>
          {preview.description || preview.short_description ? (
            <p className="text-sm text-muted-foreground">{preview.description || preview.short_description}</p>
          ) : null}
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="collection-preview-empty">
            No visible items yet — add published movies or series in the Items tab.
          </p>
        ) : (
          <CollectionItemsGrid
            items={items}
            availabilityLabels={{ dubbed: 'Dubbed', subtitled: 'Subtitled', multiAudio: 'Multi Audio' }}
            onActivateMovie={() => {}}
            onActivateSeries={() => {}}
            data-testid="collection-preview-grid"
          />
        )}
      </CardContent>
    </Card>
  );
}

function FormActions({ form, isEdit }: { form: UseFormReturn<CollectionFormValues>; isEdit: boolean }) {
  return (
    <div className="flex gap-3">
      <Button
        type="submit"
        className="bg-primary text-primary-foreground"
        disabled={form.formState.isSubmitting}
        data-testid="collection-save"
      >
        {form.formState.isSubmitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create collection'}
      </Button>
      <Button type="button" variant="outline" asChild>
        <Link to="/admin/collections">Cancel</Link>
      </Button>
    </div>
  );
}

export default function CollectionFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = tabFromSearch(searchParams.get('tab'));
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState<string | null>(null);
  const [posterBroken, setPosterBroken] = useState(false);
  const [collection, setCollection] = useState<CollectionDto | null>(null);

  const form = useForm<CollectionFormValues>({
    resolver: zodResolver(collectionFormSchema),
    defaultValues: emptyValues(),
  });

  const posterUrl = form.watch('poster_url');
  const isDirty = form.formState.isDirty;

  const blocker = useBlocker(isDirty);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    const leave = window.confirm('You have unsaved changes. Leave this page?');
    if (leave) blocker.proceed();
    else blocker.reset();
  }, [blocker]);

  function setActiveTab(tab: string) {
    const next = tabFromSearch(tab);
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === 'details') params.delete('tab');
        else params.set('tab', next);
        return params;
      },
      { replace: true }
    );
  }

  useEffect(() => {
    setPosterBroken(false);
  }, [posterUrl]);

  function applyToForm(c: CollectionDto) {
    form.reset({
      title: c.title,
      slug: c.slug || '',
      description: c.description || '',
      short_description: c.short_description || '',
      collection_type: (c.collection_type as CollectionFormValues['collection_type']) || 'editorial',
      visibility: (c.visibility as CollectionFormValues['visibility']) || 'public',
      poster_url: c.poster_url || '',
      backdrop_url: c.backdrop_url || '',
      sort_order: (c.sort_order ?? '') as unknown as number,
      is_featured: c.is_featured ?? false,
    });
  }

  useEffect(() => {
    if (!isEdit || !id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await adminApi.getCollection(Number(id));
        if (cancelled) return;
        setCollection(result);
        applyToForm(result);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load collection');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isEdit]);

  const posterPreview = useMemo(() => {
    if (!posterUrl || posterBroken) return POSTER_FALLBACK;
    return posterUrl;
  }, [posterUrl, posterBroken]);

  /** Updates the working collection (e.g. after item add/reorder/publish) without touching form dirty state. */
  function handleCollectionMetadataChange(updated: CollectionDto) {
    setCollection(updated);
  }

  async function onSubmit(values: CollectionFormValues) {
    const payload = {
      title: values.title,
      slug: values.slug || undefined,
      description: values.description || '',
      short_description: values.short_description || '',
      collection_type: values.collection_type,
      visibility: values.visibility,
      poster_url: values.poster_url || '',
      backdrop_url: values.backdrop_url || '',
      sort_order: values.sort_order === '' || values.sort_order == null ? undefined : Number(values.sort_order),
      is_featured: values.is_featured,
    };

    try {
      if (isEdit && id) {
        const updated = await adminApi.updateCollection(Number(id), {
          ...payload,
          expected_updated_at: collection?.updated_at,
        });
        setCollection(updated);
        form.reset(values);
        toast.success('Collection updated');
      } else {
        const created = await adminApi.createCollection(payload);
        toast.success('Collection created');
        navigate(`/admin/collections/${created.id}/edit`, { replace: true });
        return;
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Save failed';
      toast.error(message);
      if (message.toLowerCase().includes('slug')) {
        setActiveTab('details');
      }
    }
  }

  function onInvalid(errors: Record<string, unknown>) {
    const first = Object.keys(errors)[0] as keyof CollectionFormValues | undefined;
    if (first && FIELD_TAB[first]) {
      setActiveTab(FIELD_TAB[first]!);
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;

  return (
    <div className="space-y-4 max-w-4xl" dir="ltr" lang="en" data-testid="collection-form-page">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{isEdit ? 'Edit Collection' : 'New Collection'}</h2>
          <p className="text-sm text-muted-foreground">Artwork is URL-based (uploads disabled).</p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/admin/collections">Back</Link>
        </Button>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-6" noValidate>
          {isEdit && id && collection ? (
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
              <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 overflow-x-auto">
                <TabsTrigger value="details">Details</TabsTrigger>
                <TabsTrigger value="artwork">Artwork</TabsTrigger>
                <TabsTrigger value="items">Items</TabsTrigger>
                <TabsTrigger value="publishing">Publishing</TabsTrigger>
                <TabsTrigger value="preview">Preview</TabsTrigger>
              </TabsList>

              <TabsContent value="details" className="space-y-4">
                <DetailsFields form={form} />
              </TabsContent>

              <TabsContent value="artwork" className="space-y-4">
                <ArtworkFields form={form} posterPreview={posterPreview} onPosterError={() => setPosterBroken(true)} />
              </TabsContent>

              <TabsContent value="items" className="space-y-4">
                <ItemsTab
                  collectionId={Number(id)}
                  items={collection.items}
                  onChanged={handleCollectionMetadataChange}
                />
              </TabsContent>

              <TabsContent value="publishing" className="space-y-4">
                <PublishingTab collection={collection} onChanged={handleCollectionMetadataChange} />
              </TabsContent>

              <TabsContent value="preview" className="space-y-4">
                <PreviewTab collectionId={Number(id)} />
              </TabsContent>
            </Tabs>
          ) : (
            <>
              <DetailsFields form={form} />
              <ArtworkFields form={form} posterPreview={posterPreview} onPosterError={() => setPosterBroken(true)} />
            </>
          )}

          <FormActions form={form} isEdit={isEdit} />
        </form>
      </Form>
    </div>
  );
}
