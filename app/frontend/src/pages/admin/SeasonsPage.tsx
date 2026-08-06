import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Edit, Trash2, Clapperboard } from 'lucide-react';
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
import { adminApi, ApiError, type SeasonDto, type SeriesDto } from '@/lib/api';
import {
  AdminTableCard,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  StatusBadge,
} from './adminShared';

const createSchema = z.object({
  season_number: z.coerce.number().int().min(0).max(500),
  title: z.string().optional(),
  release_year: z.coerce.number().int().min(1888).max(2100).optional().or(z.literal('')),
});

type CreateValues = z.infer<typeof createSchema>;

export default function SeasonsPage() {
  const { id } = useParams();
  const seriesId = Number(id);
  const [series, setSeries] = useState<SeriesDto | null>(null);
  const [seasons, setSeasons] = useState<SeasonDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { season_number: 1, title: '', release_year: '' as unknown as number },
  });

  const load = useCallback(async () => {
    if (!seriesId) return;
    setLoading(true);
    setError(null);
    try {
      const [s, list] = await Promise.all([adminApi.getSeries(seriesId), adminApi.listSeasons(seriesId)]);
      setSeries(s);
      setSeasons([...list].sort((a, b) => a.season_number - b.season_number));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load seasons');
    } finally {
      setLoading(false);
    }
  }, [seriesId]);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate(values: CreateValues) {
    try {
      await adminApi.createSeason(seriesId, {
        season_number: Number(values.season_number),
        title: values.title || '',
        release_year:
          values.release_year === '' || values.release_year == null
            ? null
            : Number(values.release_year),
      });
      toast.success('Season created');
      form.reset({
        season_number: Number(values.season_number) + 1,
        title: '',
        release_year: '' as unknown as number,
      });
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Create failed');
    }
  }

  async function confirmDelete() {
    if (deleteId == null) return;
    try {
      await adminApi.deleteSeason(deleteId);
      toast.success('Season deleted');
      setDeleteId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Delete failed');
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="min-w-0 max-w-full space-y-4" data-testid="seasons-page">
      <PageHeader
        title="Seasons"
        description={series?.title}
        actions={
          <>
            <Button variant="outline" className="shrink-0" asChild>
              <Link to={`/admin/series/${seriesId}/edit`}>Edit series</Link>
            </Button>
            <Button variant="outline" className="shrink-0" asChild>
              <Link to="/admin/series">Back</Link>
            </Button>
          </>
        }
      />

      <Card className="min-w-0 border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Add season</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onCreate)} className="flex flex-wrap gap-3 items-end">
              <FormField
                control={form.control}
                name="season_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Number</FormLabel>
                    <FormControl>
                      <Input type="number" className="w-24" id="season-number" {...field} data-testid="season-number" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-[160px]">
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="gap-2 bg-primary text-primary-foreground">
                <Plus className="h-4 w-4" />
                Add
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {seasons.length === 0 ? (
        <EmptyState
          message="No seasons yet."
          action={
            <Button
              type="button"
              size="sm"
              className="gap-2"
              data-testid="add-first-season"
              onClick={() => document.getElementById('season-number')?.focus()}
            >
              <Plus className="h-4 w-4" />
              Add First Season
            </Button>
          }
        />
      ) : (
        <AdminTableCard minWidthClassName="min-w-[480px]">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-card">
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Title</TableHead>
                <TableHead className="hidden sm:table-cell">Episodes</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="sticky right-0 bg-card text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {seasons.map((season) => (
                <TableRow key={season.id} data-testid={`season-row-${season.season_number}`}>
                  <TableCell>{season.season_number}</TableCell>
                  <TableCell className="max-w-[14rem] truncate font-medium">
                    {season.title || `Season ${season.season_number}`}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{season.episode_count ?? 0}</TableCell>
                  <TableCell>
                    <StatusBadge status={season.status} />
                  </TableCell>
                  <TableCell className="sticky right-0 bg-card text-right">
                    <div className="inline-flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                        <Link to={`/admin/seasons/${season.id}/edit`} aria-label="Manage season publishing">
                          <Edit className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                        <Link to={`/admin/seasons/${season.id}/episodes`} aria-label="Episodes">
                          <Clapperboard className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive"
                        onClick={() => setDeleteId(season.id)}
                        aria-label="Delete season"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </AdminTableCard>
      )}

      <AlertDialog open={deleteId != null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete season?</AlertDialogTitle>
            <AlertDialogDescription>This removes the season from the series.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
