import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Eye, EyeOff } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
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
import { EmptyState, ErrorState, LoadingBlock, PosterThumb, StatusBadge } from './adminShared';

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

  async function togglePublish(movie: MovieDto) {
    try {
      if (movie.status === 'published') {
        await adminApi.unpublishMovie(movie.id);
        toast.success('Movie unpublished');
      } else {
        await adminApi.publishMovie(movie.id);
        toast.success('Movie published');
      }
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Publish action failed');
    }
  }

  const years = Array.from({ length: 30 }, (_, i) => new Date().getFullYear() - i);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Movies</h2>
          <p className="text-sm text-muted-foreground">{total} total</p>
        </div>
        <Button asChild className="bg-primary text-primary-foreground gap-2">
          <Link to="/admin/movies/new">
            <Plus className="h-4 w-4" />
            Add Movie
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
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
          <SelectTrigger className="w-[140px]">
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
          value={genre}
          onValueChange={(v) => {
            setPage(1);
            setGenre(v);
          }}
        >
          <SelectTrigger className="w-[140px]">
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
          <SelectTrigger className="w-[120px]">
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
        <EmptyState message="No movies found." />
      ) : (
        <Card className="bg-card border-border">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Poster</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Year</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Flags</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((m) => (
                  <TableRow key={m.id} data-testid={`movie-row-${m.id}`}>
                    <TableCell>
                      <PosterThumb src={m.poster_url || m.poster} alt={m.title} />
                    </TableCell>
                    <TableCell className="font-medium">{m.title}</TableCell>
                    <TableCell>{m.release_year ?? m.year ?? '—'}</TableCell>
                    <TableCell>
                      <StatusBadge status={m.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {[m.is_featured || m.featured ? 'Featured' : null, m.is_trending ? 'Trending' : null]
                        .filter(Boolean)
                        .join(', ') || '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                          <Link to={`/admin/movies/${m.id}/edit`} aria-label="Edit">
                            <Edit className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => togglePublish(m)}
                          aria-label={m.status === 'published' ? 'Unpublish' : 'Publish'}
                        >
                          {m.status === 'published' ? (
                            <EyeOff className="h-3.5 w-3.5" />
                          ) : (
                            <Eye className="h-3.5 w-3.5" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => setDeleteId(m.id)}
                          aria-label="Delete"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-end gap-2">
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
