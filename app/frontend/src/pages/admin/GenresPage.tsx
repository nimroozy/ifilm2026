import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Trash2, Edit } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
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
import { Alert, AlertDescription } from '@/components/ui/alert';
import { adminApi, ApiError, type GenreDto } from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock } from './adminShared';

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  slug: z.string().optional(),
  description: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export default function GenresPage() {
  const [items, setItems] = useState<GenreDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '', slug: '', description: '' },
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.listGenres({ page_size: 100 });
      setItems(result.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load genres');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onSubmit(values: FormValues) {
    setConflictError(null);
    try {
      if (editId != null) {
        await adminApi.updateGenre(editId, {
          name: values.name,
          slug: values.slug || undefined,
          description: values.description || '',
        });
        toast.success('Genre updated');
      } else {
        await adminApi.createGenre({
          name: values.name,
          slug: values.slug || undefined,
          description: values.description || '',
        });
        toast.success('Genre created');
      }
      form.reset({ name: '', slug: '', description: '' });
      setEditId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed');
    }
  }

  function startEdit(genre: GenreDto) {
    setEditId(genre.id);
    setConflictError(null);
    form.reset({
      name: genre.name,
      slug: genre.slug,
      description: genre.description || '',
    });
  }

  async function confirmDelete() {
    if (deleteId == null) return;
    setConflictError(null);
    try {
      await adminApi.deleteGenre(deleteId);
      toast.success('Genre deleted');
      setDeleteId(null);
      load();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Delete failed';
      if (err instanceof ApiError && err.status === 409) {
        setConflictError(message);
        setDeleteId(null);
      } else {
        toast.error(message);
      }
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-foreground">Genres</h2>
        <p className="text-sm text-muted-foreground">Manage catalog genres and usage.</p>
      </div>

      {conflictError && (
        <Alert variant="destructive" data-testid="genre-conflict-error">
          <AlertDescription>{conflictError}</AlertDescription>
        </Alert>
      )}

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">{editId ? 'Edit genre' : 'Add genre'}</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-wrap gap-3 items-end">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="genre-name" />
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
                      <Input {...field} placeholder="optional" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-[200px]">
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="gap-2 bg-primary text-primary-foreground">
                <Plus className="h-4 w-4" />
                {editId ? 'Update' : 'Add'}
              </Button>
              {editId && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setEditId(null);
                    form.reset({ name: '', slug: '', description: '' });
                  }}
                >
                  Cancel
                </Button>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      {items.length === 0 ? (
        <EmptyState message="No genres yet." />
      ) : (
        <Card className="bg-card border-border">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Movies</TableHead>
                  <TableHead>Series</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((g) => (
                  <TableRow key={g.id} data-testid={`genre-row-${g.id}`}>
                    <TableCell className="font-medium">{g.name}</TableCell>
                    <TableCell className="text-muted-foreground">{g.slug}</TableCell>
                    <TableCell>{g.movie_count ?? 0}</TableCell>
                    <TableCell>{g.series_count ?? 0}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => startEdit(g)}
                          aria-label="Edit genre"
                        >
                          <Edit className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => {
                            setConflictError(null);
                            setDeleteId(g.id);
                          }}
                          aria-label="Delete genre"
                          data-testid={`genre-delete-${g.id}`}
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

      <AlertDialog open={deleteId != null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete genre?</AlertDialogTitle>
            <AlertDialogDescription>
              Genres assigned to movies or series cannot be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} data-testid="genre-delete-confirm">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
