import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { adminApi, ApiError, type CatalogStatus } from '@/lib/api';
import { ErrorState, LoadingBlock } from './adminShared';
import PublishingPanel from './PublishingPanel';

const schema = z.object({
  season_number: z.coerce.number().int().min(0).max(500),
  title: z.string().optional(),
  description: z.string().optional(),
  poster_url: z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: 'URL must start with http:// or https://',
    }),
  release_year: z.coerce.number().int().min(1888).max(2100).optional().or(z.literal('')),
});

type FormValues = z.infer<typeof schema>;

export default function SeasonFormPage() {
  const { id } = useParams();
  const seasonId = Number(id);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seriesId, setSeriesId] = useState<number | null>(null);
  const [currentStatus, setCurrentStatus] = useState<CatalogStatus | string>('draft');

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      season_number: 1,
      title: '',
      description: '',
      poster_url: '',
      release_year: '' as unknown as number,
    },
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const season = await adminApi.getSeason(seasonId);
        if (cancelled) return;
        setSeriesId(season.series_id);
        setCurrentStatus(season.status);
        form.reset({
          season_number: season.season_number,
          title: season.title || '',
          description: season.description || '',
          poster_url: season.poster_url || '',
          release_year: (season.release_year ?? '') as unknown as number,
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load season');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [seasonId, form]);

  async function onSubmit(values: FormValues) {
    try {
      await adminApi.updateSeason(seasonId, {
        season_number: Number(values.season_number),
        title: values.title || '',
        description: values.description || '',
        poster_url: values.poster_url || '',
        release_year:
          values.release_year === '' || values.release_year == null
            ? null
            : Number(values.release_year),
      });
      toast.success('Season updated');
      if (seriesId) navigate(`/admin/series/${seriesId}/seasons`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed');
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-foreground">Edit Season</h2>
        <div className="flex gap-2">
          <Button variant="secondary" asChild>
            <Link to={`/admin/seasons/${seasonId}/episodes`}>Episodes</Link>
          </Button>
          {seriesId && (
            <Button variant="outline" asChild>
              <Link to={`/admin/series/${seriesId}/seasons`}>Back</Link>
            </Button>
          )}
        </div>
      </div>

      <PublishingPanel
        entityType="season"
        entityId={seasonId}
        currentStatus={currentStatus}
        onChanged={setCurrentStatus}
      />

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">Season details</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="season_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Season number</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea rows={3} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="poster_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Poster URL</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="release_year"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Release year</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="bg-primary text-primary-foreground">
                Save changes
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
