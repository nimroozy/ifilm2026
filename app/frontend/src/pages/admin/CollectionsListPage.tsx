import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Plus,
  Search,
  Edit,
  Trash2,
  Eye,
  UploadCloud,
  Undo2,
  Archive,
  MoreHorizontal,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { adminApi, ApiError, type CollectionDto } from '@/lib/api';
import {
  AdminTableCard,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  PosterThumb,
  StatusBadge,
} from './adminShared';
import { COLLECTION_TYPE_LABELS, collectionStatusActions, collectionTypeLabel } from './collectionsShared';

function CollectionRowActions({
  collection,
  onAction,
  busy,
}: {
  collection: CollectionDto;
  onAction: (action: 'publish' | 'unpublish' | 'archive' | 'delete', collection: CollectionDto) => void;
  busy: boolean;
}) {
  const { canPublish, canUnpublish, canRestore, canArchive } = collectionStatusActions(collection.status);
  return (
    <>
      <div className="hidden gap-1 xl:flex" data-testid={`collection-actions-${collection.id}`}>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/collections/${collection.id}/edit`} aria-label="Edit">
            <Edit className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/collections/${collection.id}/edit?tab=preview`} aria-label="Preview">
            <Eye className="h-3.5 w-3.5" />
          </Link>
        </Button>
        {canPublish ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            disabled={busy}
            onClick={() => onAction('publish', collection)}
            aria-label="Publish"
          >
            <UploadCloud className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        {canUnpublish ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            disabled={busy}
            onClick={() => onAction('unpublish', collection)}
            aria-label="Unpublish"
          >
            <Undo2 className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        {canRestore ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            disabled={busy}
            onClick={() => onAction('unpublish', collection)}
            aria-label="Restore to draft"
          >
            <Undo2 className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        {canArchive ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-destructive"
            disabled={busy}
            onClick={() => onAction('archive', collection)}
            aria-label="Archive"
          >
            <Archive className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 text-destructive"
          disabled={busy}
          onClick={() => onAction('delete', collection)}
          aria-label="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="xl:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" aria-label="Row actions">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[10rem]">
            <DropdownMenuItem asChild>
              <Link to={`/admin/collections/${collection.id}/edit`}>Edit</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`/admin/collections/${collection.id}/edit?tab=preview`}>Preview</Link>
            </DropdownMenuItem>
            {canPublish ? (
              <DropdownMenuItem onClick={() => onAction('publish', collection)}>Publish</DropdownMenuItem>
            ) : null}
            {canUnpublish ? (
              <DropdownMenuItem onClick={() => onAction('unpublish', collection)}>Unpublish</DropdownMenuItem>
            ) : null}
            {canRestore ? (
              <DropdownMenuItem onClick={() => onAction('unpublish', collection)}>
                Restore to draft
              </DropdownMenuItem>
            ) : null}
            {canArchive ? (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => onAction('archive', collection)}
              >
                Archive
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onAction('delete', collection)}
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </>
  );
}

export default function CollectionsListPage() {
  const [items, setItems] = useState<CollectionDto[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('all');
  const [type, setType] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CollectionDto | null>(null);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const pageSize = 20;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.listCollections({
        q: q || undefined,
        status: status === 'all' ? undefined : status,
        collection_type: type === 'all' ? undefined : type,
        page,
        page_size: pageSize,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setItems([]);
      setError(err instanceof ApiError ? err.message : 'Failed to load collections');
    } finally {
      setLoading(false);
    }
  }, [q, status, type, page]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  async function runAction(action: 'publish' | 'unpublish' | 'archive' | 'delete', collection: CollectionDto) {
    setWorkingId(collection.id);
    try {
      if (action === 'publish') {
        await adminApi.publishCollection(collection.id, collection.updated_at);
        toast.success('Collection published');
      } else if (action === 'unpublish') {
        await adminApi.unpublishCollection(collection.id, collection.updated_at);
        toast.success('Collection moved to draft');
      } else if (action === 'archive') {
        await adminApi.archiveCollection(collection.id, collection.updated_at);
        toast.success('Collection archived');
      } else {
        await adminApi.deleteCollection(collection.id);
        toast.success('Collection deleted');
        setDeleteTarget(null);
      }
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `${action} failed`);
    } finally {
      setWorkingId(null);
    }
  }

  function onAction(action: 'publish' | 'unpublish' | 'archive' | 'delete', collection: CollectionDto) {
    if (action === 'delete') {
      setDeleteTarget(collection);
      return;
    }
    void runAction(action, collection);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="min-w-0 space-y-4" dir="ltr" lang="en" data-testid="collections-list-page">
      <PageHeader
        title="Collections"
        description={`${total} total`}
        actions={
          <Button asChild className="gap-2 shrink-0">
            <Link to="/admin/collections/new">
              <Plus className="h-4 w-4" />
              New Collection
            </Link>
          </Button>
        }
      />

      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] max-w-full flex-1 sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search collections..."
            value={q}
            onChange={(e) => {
              setPage(1);
              setQ(e.target.value);
            }}
            className="pl-9"
            data-testid="collections-search"
          />
        </div>
        <Select
          value={status}
          onValueChange={(v) => {
            setPage(1);
            setStatus(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[140px]" data-testid="collections-status-filter">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="published">Published</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={type}
          onValueChange={(v) => {
            setPage(1);
            setType(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[160px]" data-testid="collections-type-filter">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {Object.entries(COLLECTION_TYPE_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          message="No collections found."
          action={
            <Button asChild size="sm" className="gap-2">
              <Link to="/admin/collections/new">
                <Plus className="h-4 w-4" />
                New Collection
              </Link>
            </Button>
          }
        />
      ) : (
        <>
          {/* Mobile / narrow: card list */}
          <ul className="space-y-3 md:hidden" data-testid="collections-mobile-list">
            {items.map((c) => (
              <li
                key={c.id}
                className="flex min-w-0 items-start gap-3 rounded-xl border border-border bg-card p-3"
                data-testid={`collection-card-${c.id}`}
              >
                <PosterThumb src={c.poster_url} alt={c.title} />
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="truncate font-medium text-foreground">{c.title}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusBadge status={c.status} />
                    {c.is_featured ? <StatusBadge status="published" /> : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {collectionTypeLabel(c.collection_type)} · {c.item_count ?? 0} items
                  </p>
                </div>
                <CollectionRowActions collection={c} onAction={onAction} busy={workingId === c.id} />
              </li>
            ))}
          </ul>

          {/* Desktop / tablet: responsive table */}
          <div className="hidden min-w-0 md:block" data-testid="collections-table-desktop">
            <AdminTableCard minWidthClassName="min-w-[640px]">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow>
                    <TableHead className="w-14">Art</TableHead>
                    <TableHead className="min-w-[10rem]">Title</TableHead>
                    <TableHead className="hidden lg:table-cell">Type</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden lg:table-cell">Items</TableHead>
                    <TableHead className="hidden xl:table-cell">Featured</TableHead>
                    <TableHead className="sticky right-0 bg-card text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((c) => (
                    <TableRow key={c.id} data-testid={`collection-row-${c.id}`}>
                      <TableCell>
                        <PosterThumb src={c.poster_url} alt={c.title} />
                      </TableCell>
                      <TableCell className="max-w-[16rem] truncate font-medium" title={c.title}>
                        {c.title}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">{collectionTypeLabel(c.collection_type)}</TableCell>
                      <TableCell>
                        <StatusBadge status={c.status} />
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">{c.item_count ?? 0}</TableCell>
                      <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">
                        {c.is_featured ? 'Yes' : '—'}
                      </TableCell>
                      <TableCell className="sticky right-0 bg-card text-right">
                        <div className="inline-flex justify-end">
                          <CollectionRowActions collection={c} onAction={onAction} busy={workingId === c.id} />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </AdminTableCard>
          </div>
        </>
      )}

      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}

      <AlertDialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete collection?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the collection from admin and customer views. Movies and series inside it are never
              deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && runAction('delete', deleteTarget)}
              data-testid="collection-delete-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
