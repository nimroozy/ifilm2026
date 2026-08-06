import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Eye, Database, MoreHorizontal } from 'lucide-react';
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
import { adminApi, ApiError, type GenreDto, type MovieDto } from '@/lib/api';
import {
  AdminTableCard,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  PosterThumb,
  StatusBadge,
} from './adminShared';

function movieSourceLabel(m: MovieDto): string {
  if (m.has_external_media) return 'External';
  if (m.has_playable_package) return 'Package';
  if (m.tmdb_id) return 'TMDB meta';
  return '—';
}

function MovieRowActions({
  movie,
  onDelete,
}: {
  movie: MovieDto;
  onDelete: (id: number) => void;
}) {
  return (
    <>
      <div className="hidden gap-1 xl:flex" data-testid={`movie-actions-${movie.id}`}>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/movies/${movie.id}/edit`} aria-label="Edit">
            <Edit className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" asChild>
          <Link to={`/admin/movies/${movie.id}/edit?tab=publishing`} aria-label="Manage movie publishing">
            <Eye className="h-3.5 w-3.5" />
          </Link>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 text-destructive"
          onClick={() => onDelete(movie.id)}
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
              <Link to={`/admin/movies/${movie.id}/edit`}>Edit</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`/admin/movies/${movie.id}/edit?tab=publishing`}>Publishing</Link>
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => onDelete(movie.id)}>
              Archive
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </>
  );
}

export default function MoviesListPage() {
  const [items, setItems] = useState<MovieDto[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('all');
  const [genre, setGenre] = useState('all');
  const [year, setYear] = useState('all');
  const [genres, setGenres] = useState<GenreDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const pageSize = 20;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.listMovies({
        q: q || undefined,
        status: status === 'all' ? undefined : status,
        genre: genre === 'all' ? undefined : genre,
        year: year === 'all' ? undefined : Number(year),
        page,
        page_size: pageSize,
        sort: 'newest',
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setItems([]);
      setError(err instanceof ApiError ? err.message : 'Failed to load movies');
    } finally {
      setLoading(false);
    }
  }, [q, status, genre, year, page]);

  useEffect(() => {
    adminApi
      .listGenres({ page_size: 100 })
      .then((g) => setGenres(g.items))
      .catch(() => setGenres([]));
  }, []);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  async function confirmDelete() {
    if (deleteId == null) return;
    try {
      await adminApi.deleteMovie(deleteId);
      toast.success('Movie archived');
      setDeleteId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Delete failed');
    }
  }

  const years = Array.from({ length: 30 }, (_, i) => new Date().getFullYear() - i);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="min-w-0 space-y-4" data-testid="movies-list-page">
      <PageHeader
        title="Movies"
        description={`${total} total`}
        actions={
          <>
            <Button asChild className="gap-2 shrink-0">
              <Link to="/admin/movies/new">
                <Plus className="h-4 w-4" />
                New Movie
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
            placeholder="Search movies..."
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
        <Select
          value={genre}
          onValueChange={(v) => {
            setPage(1);
            setGenre(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[140px]">
            <SelectValue placeholder="Genre" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All genres</SelectItem>
            {genres.map((g) => (
              <SelectItem key={g.id} value={g.slug || g.name}>
                {g.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={year}
          onValueChange={(v) => {
            setPage(1);
            setYear(v);
          }}
        >
          <SelectTrigger className="w-full sm:w-[120px]">
            <SelectValue placeholder="Year" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All years</SelectItem>
            {years.map((y) => (
              <SelectItem key={y} value={String(y)}>
                {y}
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
          message="No movies found."
          action={
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button asChild size="sm" className="gap-2">
                <Link to="/admin/movies/new">
                  <Plus className="h-4 w-4" />
                  New Movie
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
          {/* Mobile / narrow: card list */}
          <ul className="space-y-3 md:hidden" data-testid="movies-mobile-list">
            {items.map((m) => (
              <li
                key={m.id}
                className="flex min-w-0 items-start gap-3 rounded-xl border border-border bg-card p-3"
                data-testid={`movie-card-${m.id}`}
              >
                <PosterThumb src={m.poster_url || m.poster} alt={m.title} />
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="truncate font-medium text-foreground">{m.title}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusBadge status={m.status} />
                    <StatusBadge status={m.playable ? 'playable' : 'unavailable'} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {movieSourceLabel(m)}
                    {m.release_year || m.year ? ` · ${m.release_year ?? m.year}` : ''}
                  </p>
                </div>
                <MovieRowActions movie={m} onDelete={setDeleteId} />
              </li>
            ))}
          </ul>

          {/* Desktop / tablet: responsive table */}
          <div className="hidden min-w-0 md:block" data-testid="movies-table-desktop">
            <AdminTableCard minWidthClassName="min-w-[640px]">
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-card">
                  <TableRow>
                    <TableHead className="w-14">Poster</TableHead>
                    <TableHead className="min-w-[10rem]">Title</TableHead>
                    <TableHead className="hidden lg:table-cell">Year</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Playable</TableHead>
                    <TableHead className="hidden lg:table-cell">Source</TableHead>
                    <TableHead className="hidden xl:table-cell">Updated</TableHead>
                    <TableHead className="hidden 2xl:table-cell">Flags</TableHead>
                    <TableHead className="sticky right-0 bg-card text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((m) => (
                    <TableRow key={m.id} data-testid={`movie-row-${m.id}`}>
                      <TableCell>
                        <PosterThumb src={m.poster_url || m.poster} alt={m.title} />
                      </TableCell>
                      <TableCell className="max-w-[14rem] truncate font-medium" title={m.title}>
                        {m.title}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        {m.release_year ?? m.year ?? '—'}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={m.status} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={m.playable ? 'playable' : 'unavailable'} />
                      </TableCell>
                      <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">
                        {movieSourceLabel(m)}
                      </TableCell>
                      <TableCell className="hidden whitespace-nowrap text-xs text-muted-foreground xl:table-cell">
                        {m.updated_at
                          ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(
                              new Date(m.updated_at)
                            )
                          : '—'}
                      </TableCell>
                      <TableCell className="hidden text-xs text-muted-foreground 2xl:table-cell">
                        {[m.is_featured || m.featured ? 'Featured' : null, m.is_trending ? 'Trending' : null]
                          .filter(Boolean)
                          .join(', ') || '—'}
                      </TableCell>
                      <TableCell className="sticky right-0 bg-card text-right">
                        <div className="inline-flex justify-end">
                          <MovieRowActions movie={m} onDelete={setDeleteId} />
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
            <AlertDialogTitle>Archive movie?</AlertDialogTitle>
            <AlertDialogDescription>
              This soft-deletes the movie from the catalog. You can confirm to proceed.
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
