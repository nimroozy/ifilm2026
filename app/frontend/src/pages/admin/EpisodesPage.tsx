import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Edit, Trash2, Eye } from 'lucide-react';
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
import { adminApi, ApiError, type EpisodeDto, type SeasonDto } from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock, StatusBadge } from './adminShared';

const createSchema = z.object({
  episode_number: z.coerce.number().int().min(0).max(10000),
  title: z.string().min(1, 'Title is required'),
  duration_minutes: z.coerce.number().int().min(0).max(10000).optional().or(z.literal('')),
});

type CreateValues = z.infer<typeof createSchema>;

export default function EpisodesPage() {
  const { id } = useParams();
  const seasonId = Number(id);
  const [season, setSeason] = useState<SeasonDto | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      episode_number: 1,
      title: '',
      duration_minutes: '' as unknown as number,
    },
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, list] = await Promise.all([
        adminApi.getSeason(seasonId),
        adminApi.listEpisodes(seasonId),
      ]);
      setSeason(s);
      setEpisodes([...list].sort((a, b) => a.episode_number - b.episode_number));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load episodes');
    } finally {
      setLoading(false);
    }
  }, [seasonId]);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate(values: CreateValues) {
    try {
      await adminApi.createEpisode(seasonId, {
        episode_number: Number(values.episode_number),
        title: values.title,
        duration_minutes:
          values.duration_minutes === '' || values.duration_minutes == null
            ? null
            : Number(values.duration_minutes),
      });
      toast.success('Episode created');
      form.reset({
        episode_number: Number(values.episode_number) + 1,
        title: '',
        duration_minutes: '' as unknown as number,
      });
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Create failed');
    }
  }

  async function confirmDelete() {
    if (deleteId == null) return;
    try {
      await adminApi.deleteEpisode(deleteId);
      toast.success('Episode deleted');
      setDeleteId(null);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Delete failed');
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Episodes</h2>
          <p className="text-sm text-muted-foreground">
            Season {season?.season_number}
            {season?.title ? ` — ${season.title}` : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/admin/seasons/${seasonId}/edit`}>Edit season</Link>
          </Button>
          {season && (
            <Button variant="outline" asChild>
              <Link to={`/admin/series/${season.series_id}/seasons`}>Back to seasons</Link>
            </Button>
          )}
        </div>
      </div>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">Add episode</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onCreate)} className="flex flex-wrap gap-3 items-end">
              <FormField
                control={form.control}
                name="episode_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Number</FormLabel>
                    <FormControl>
                      <Input type="number" className="w-24" id="episode-number" {...field} data-testid="episode-number" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem className="flex-1 min-w-[180px]">
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="episode-title" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="duration_minutes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Minutes</FormLabel>
                    <FormControl>
                      <Input type="number" className="w-24" {...field} value={field.value ?? ''} />
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

      {episodes.length === 0 ? (
        <EmptyState
          message="No episodes yet."
          action={
            <Button
              type="button"
              size="sm"
              className="gap-2"
              data-testid="add-first-episode"
              onClick={() => document.getElementById('episode-number')?.focus()}
            >
              <Plus className="h-4 w-4" />
              Add First Episode
            </Button>
          }
        />
      ) : (
        <Card className="bg-card border-border">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {episodes.map((ep) => (
                  <TableRow key={ep.id} data-testid={`episode-row-${ep.episode_number}`}>
                    <TableCell>{ep.episode_number}</TableCell>
                    <TableCell className="font-medium">{ep.title}</TableCell>
                    <TableCell>{ep.duration_minutes ?? ep.duration ?? '—'} min</TableCell>
                    <TableCell>
                      <StatusBadge status={ep.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                          <Link to={`/admin/episodes/${ep.id}/edit`} aria-label="Edit episode">
                            <Edit className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                          <Link
                            to={`/admin/episodes/${ep.id}/edit`}
                            aria-label="Manage episode publishing"
                          >
                            <Eye className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => setDeleteId(ep.id)}
                          aria-label="Delete episode"
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
            <AlertDialogTitle>Delete episode?</AlertDialogTitle>
            <AlertDialogDescription>This removes the episode from the season.</AlertDialogDescription>
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
