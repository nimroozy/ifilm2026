import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Eye, Layers, Database, MoreHorizontal } from 'lucide-react';
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
import { adminApi, ApiError, type SeriesDto } from '@/lib/api';
import {
  AdminTableCard,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  PosterThumb,
  StatusBadge,
} from './adminShared';

function SeriesRowActions({
  series,
  onDelete,
}: {
  series: SeriesDto;
  onDelete: (id: number) => void;
}) {
  return (
    <>
      <div className="hidden gap-1 lg:flex">
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/series/${series.id}/edit`} aria-label="Edit">
            <Edit className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/series/${series.id}/seasons`} aria-label="Seasons">
            <Layers className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/series/${series.id}/edit`} aria-label="Manage series publishing">
            <Eye className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 text-destructive"
          onClick={() => onDelete(series.id)}
          aria-label="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="lg:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" aria-label="Row actions">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem asChild>
              <Link to={`/admin/series/${series.id}/edit`}>Edit</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`/admin/series/${series.id}/seasons`}>Seasons</Link>
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => onDelete(series.id)}>
              Archive
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </>
  );
}

export default function SeriesListPage() {
  const [items, setItems] = useState<SeriesDto[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const pageSize = 20;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.listSeries({
        q: q || undefined,
        status: status === 'all' ? undefined : status,
        page,
        page_size: pageSize,
        sort: 'newest',
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setItems([]);
      setError(err instanceof ApiError ? err.message : 'Failed to load series');
    } finally {
      setLoading(false);
    }
  }, [q, status, page]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  async function confirmDelete() {
    if (deleteId == null) return;
    try {
      await adminApi.deleteSeries(deleteId);
      toast.success('Series archived');
      setDeleteId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Delete failed');
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="min-w-0 space-y-4" data-testid="series-list-page">
      <PageHeader
        title="Series"
        description={`${total} total`}
        actions={
          <>
            <Button asChild className="gap-2 shrink-0">
              <Link to="/admin/series/new">
                <Plus className="h-4 w-4" />
                New Series
              </Link>
            </Button>
            <Button asChild variant="outline" className="gap-2 shrink-0">
              <Link to="/admin/tools/tmdb">
                <Database className="h-4 w-4" />
                Import TMDB
              </Link>
            </Button>
          </>
        }
      />

      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] max-w-full flex-1 sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search series..."
            value={q}
            onChange={(e) => {
              setPage(1);
              setQ(e.target.value);
            }}
            className="pl-9"
          />
        </div>
        <Select
          value={status}
          onValueChange={(v) => {
            setPage(1);
            setStatus(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="in_review">In review</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="scheduled">Scheduled</SelectItem>
            <SelectItem value="published">Published</SelectItem>
            <SelectItem value="unpublished">Unpublished</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          message="No series found."
          action={
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button asChild size="sm" className="gap-2">
                <Link to="/admin/series/new">
                  <Plus className="h-4 w-4" />
                  New Series
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline" className="gap-2">
                <Link to="/admin/tools/tmdb">
                  <Database className="h-4 w-4" />
                  Import TMDB
                </Link>
              </Button>
            </div>
          }
        />
      ) : (
        <>
          <ul className="space-y-3 md:hidden" data-testid="series-mobile-list">
            {items.map((s) => (
              <li
                key={s.id}
                className="flex min-w-0 items-start gap-3 rounded-xl border border-border bg-card p-3"
                data-testid={`series-card-${s.id}`}
              >
                <PosterThumb src={s.poster_url || s.poster} alt={s.title} />
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="truncate font-medium text-foreground">{s.title}</p>
                  <StatusBadge status={s.status} />
                  <p className="text-xs text-muted-foreground">
                    {s.season_count ?? s.seasons ?? 0} seasons · {s.episode_count ?? s.episodes ?? 0} episodes
                  </p>
                </div>
                <SeriesRowActions series={s} onDelete={setDeleteId} />
              </li>
            ))}
          </ul>

          <div className="hidden min-w-0 md:block">
            <AdminTableCard minWidthClassName="min-w-[560px]">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow>
                    <TableHead className="w-14">Poster</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead className="hidden lg:table-cell">Seasons</TableHead>
                    <TableHead className="hidden lg:table-cell">Episodes</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="sticky right-0 bg-card text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((s) => (
                    <TableRow key={s.id} data-testid={`series-row-${s.id}`}>
                      <TableCell>
                        <PosterThumb src={s.poster_url || s.poster} alt={s.title} />
                      </TableCell>
                      <TableCell className="max-w-[16rem] truncate font-medium" title={s.title}>
                        {s.title}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">{s.season_count ?? s.seasons ?? 0}</TableCell>
                      <TableCell className="hidden lg:table-cell">{s.episode_count ?? s.episodes ?? 0}</TableCell>
                      <TableCell>
                        <StatusBadge status={s.status} />
                      </TableCell>
                      <TableCell className="sticky right-0 bg-card text-right">
                        <div className="inline-flex justify-end">
                          <SeriesRowActions series={s} onDelete={setDeleteId} />
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

      <AlertDialog open={deleteId != null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive series?</AlertDialogTitle>
            <AlertDialogDescription>
              This soft-deletes the series from the catalog. You can confirm to proceed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Archive</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
