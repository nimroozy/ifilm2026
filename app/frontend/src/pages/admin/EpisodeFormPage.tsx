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
import MediaLinkingCard from './MediaLinkingCard';

const schema = z.object({
  episode_number: z.coerce.number().int().min(0).max(10000),
  title: z.string().min(1, 'Title is required'),
  description: z.string().optional(),
  duration_minutes: z.coerce.number().int().min(0).max(10000).optional().or(z.literal('')),
  thumbnail_url: z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: 'URL must start with http:// or https://',
    }),
});

type FormValues = z.infer<typeof schema>;

export default function EpisodeFormPage() {
  const { id } = useParams();
  const episodeId = Number(id);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seasonId, setSeasonId] = useState<number | null>(null);
  const [currentStatus, setCurrentStatus] = useState<CatalogStatus | string>('draft');
  const [mediaRefreshToken, setMediaRefreshToken] = useState(0);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      episode_number: 1,
      title: '',
      description: '',
      duration_minutes: '' as unknown as number,
      thumbnail_url: '',
    },
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const ep = await adminApi.getEpisode(episodeId);
        if (cancelled) return;
        setSeasonId(ep.season_id);
        setCurrentStatus(ep.status);
        form.reset({
          episode_number: ep.episode_number,
          title: ep.title,
          description: ep.description || '',
          duration_minutes: (ep.duration_minutes ?? ep.duration ?? '') as unknown as number,
          thumbnail_url: ep.thumbnail_url || ep.thumbnail || '',
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load episode');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [episodeId, form]);

  async function onSubmit(values: FormValues) {
    try {
      await adminApi.updateEpisode(episodeId, {
        episode_number: Number(values.episode_number),
        title: values.title,
        description: values.description || '',
        duration_minutes:
          values.duration_minutes === '' || values.duration_minutes == null
            ? null
            : Number(values.duration_minutes),
        thumbnail_url: values.thumbnail_url || '',
      });
      toast.success('Episode updated');
      if (seasonId) navigate(`/admin/seasons/${seasonId}/episodes`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed');
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-foreground">Edit Episode</h2>
        {seasonId && (
          <Button variant="outline" asChild>
            <Link to={`/admin/seasons/${seasonId}/episodes`}>Back</Link>
          </Button>
        )}
      </div>

      <PublishingPanel
        entityType="episode"
        entityId={episodeId}
        currentStatus={currentStatus}
        onChanged={setCurrentStatus}
        refreshToken={mediaRefreshToken}
      />

      <MediaLinkingCard
        ownerType="episode"
        ownerId={episodeId}
        contentStatus={String(currentStatus)}
        onChanged={() => setMediaRefreshToken((n) => n + 1)}
      />

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base">Episode details</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="episode_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Episode number</FormLabel>
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
                name="duration_minutes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Duration (minutes)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="thumbnail_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Thumbnail URL</FormLabel>
                    <FormControl>
                      <Input {...field} />
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
