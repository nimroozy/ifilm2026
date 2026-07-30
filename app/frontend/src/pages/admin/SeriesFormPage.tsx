import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { adminApi, ApiError, type GenreDto } from '@/lib/api';
import { csvToList, ErrorState, listToCsv, LoadingBlock, POSTER_FALLBACK } from './adminShared';

export const seriesFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  original_title: z.string().optional(),
  slug: z.string().optional(),
  description: z.string().optional(),
  release_year: z.coerce.number().int().min(1888).max(2100).optional().or(z.literal('')),
  end_year: z.coerce.number().int().min(1888).max(2100).optional().or(z.literal('')),
  age_rating: z.string().optional(),
  language: z.string().optional(),
  country: z.string().optional(),
  imdb_rating: z.coerce.number().min(0).max(10).optional().or(z.literal('')),
  poster_url: z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: 'Poster URL must start with http:// or https://',
    }),
  backdrop_url: z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: 'Backdrop URL must start with http:// or https://',
    }),
  status: z.enum(['draft', 'published', 'archived']),
  airing_status: z.enum(['Ongoing', 'Completed', 'Upcoming']),
  is_featured: z.boolean().default(false),
  is_trending: z.boolean().default(false),
  new_episode: z.boolean().default(false),
  audio: z.string().optional(),
  subtitles: z.string().optional(),
  dubbed: z.string().optional(),
  genre_ids: z.array(z.number()).default([]),
});

export type SeriesFormValues = z.infer<typeof seriesFormSchema>;

function emptyValues(): SeriesFormValues {
  return {
    title: '',
    original_title: '',
    slug: '',
    description: '',
    release_year: '' as unknown as number,
    end_year: '' as unknown as number,
    age_rating: '',
    language: '',
    country: '',
    imdb_rating: '' as unknown as number,
    poster_url: '',
    backdrop_url: '',
    status: 'draft',
    airing_status: 'Ongoing',
    is_featured: false,
    is_trending: false,
    new_episode: false,
    audio: '',
    subtitles: '',
    dubbed: '',
    genre_ids: [],
  };
}

export default function SeriesFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const [genres, setGenres] = useState<GenreDto[]>([]);
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState<string | null>(null);
  const [previewBroken, setPreviewBroken] = useState(false);

  const form = useForm<SeriesFormValues>({
    resolver: zodResolver(seriesFormSchema),
    defaultValues: emptyValues(),
  });

  const posterUrl = form.watch('poster_url');
  useEffect(() => setPreviewBroken(false), [posterUrl]);

  useEffect(() => {
    adminApi
      .listGenres({ page_size: 100 })
      .then((g) => setGenres(g.items))
      .catch(() => setGenres([]));
  }, []);

  useEffect(() => {
    if (!isEdit || !id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const item = await adminApi.getSeries(Number(id));
        if (cancelled) return;
        form.reset({
          title: item.title,
          original_title: item.original_title || '',
          slug: item.slug || '',
          description: item.description || '',
          release_year: (item.release_year ?? item.year ?? '') as unknown as number,
          end_year: (item.end_year ?? '') as unknown as number,
          age_rating: item.age_rating || '',
          language: item.language || '',
          country: item.country || '',
          imdb_rating: (item.imdb_rating ?? item.rating ?? '') as unknown as number,
          poster_url: item.poster_url || item.poster || '',
          backdrop_url: item.backdrop_url || item.backdrop || '',
          status: (item.status as SeriesFormValues['status']) || 'draft',
          airing_status: (item.airing_status as SeriesFormValues['airing_status']) || 'Ongoing',
          is_featured: item.is_featured ?? item.featured ?? false,
          is_trending: item.is_trending ?? false,
          new_episode: item.new_episode ?? false,
          audio: listToCsv(item.audio),
          subtitles: listToCsv(item.subtitles),
          dubbed: listToCsv(item.dubbed),
          genre_ids: Array.isArray(item.genres)
            ? item.genres.filter((g): g is GenreDto => typeof g !== 'string').map((g) => g.id)
            : [],
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load series');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, isEdit, form]);

  const previewSrc = useMemo(() => {
    if (!posterUrl || previewBroken) return POSTER_FALLBACK;
    return posterUrl;
  }, [posterUrl, previewBroken]);

  async function onSubmit(values: SeriesFormValues) {
    const payload = {
      title: values.title,
      original_title: values.original_title || '',
      slug: values.slug || undefined,
      description: values.description || '',
      release_year:
        values.release_year === '' || values.release_year == null
          ? null
          : Number(values.release_year),
      end_year:
        values.end_year === '' || values.end_year == null ? null : Number(values.end_year),
      age_rating: values.age_rating || '',
      language: values.language || '',
      country: values.country || '',
      imdb_rating:
        values.imdb_rating === '' || values.imdb_rating == null ? null : Number(values.imdb_rating),
      poster_url: values.poster_url || '',
      backdrop_url: values.backdrop_url || '',
      status: values.status,
      airing_status: values.airing_status,
      is_featured: values.is_featured,
      is_trending: values.is_trending,
      new_episode: values.new_episode,
      audio: csvToList(values.audio || ''),
      subtitles: csvToList(values.subtitles || ''),
      dubbed: csvToList(values.dubbed || ''),
      genre_ids: values.genre_ids,
    };

    try {
      if (isEdit && id) {
        await adminApi.updateSeries(Number(id), payload);
        toast.success('Series updated');
        navigate('/admin/series');
      } else {
        const created = await adminApi.createSeries(payload);
        toast.success('Series created');
        navigate(`/admin/series/${created.id}/seasons`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Save failed');
    }
  }

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{isEdit ? 'Edit Series' : 'New Series'}</h2>
          <p className="text-sm text-muted-foreground">Manage seasons after creating the series.</p>
        </div>
        <div className="flex gap-2">
          {isEdit && id && (
            <Button variant="secondary" asChild>
              <Link to={`/admin/series/${id}/seasons`}>Seasons</Link>
            </Button>
          )}
          <Button variant="outline" asChild>
            <Link to="/admin/series">Back</Link>
          </Button>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6" noValidate>
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Basics</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input {...field} data-testid="series-title" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="original_title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Original title</FormLabel>
                    <FormControl>
                      <Input {...field} />
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
              <FormField
                control={form.control}
                name="end_year"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>End year</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="imdb_rating"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>IMDb rating</FormLabel>
                    <FormControl>
                      <Input type="number" step="0.1" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Catalog status</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="draft">Draft</SelectItem>
                        <SelectItem value="published">Published</SelectItem>
                        <SelectItem value="archived">Archived</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="airing_status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Airing status</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Ongoing">Ongoing</SelectItem>
                        <SelectItem value="Completed">Completed</SelectItem>
                        <SelectItem value="Upcoming">Upcoming</SelectItem>
                      </SelectContent>
                    </Select>
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
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Artwork & flags</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-[120px_1fr]">
              <img
                src={previewSrc}
                alt="Poster preview"
                className="w-[100px] h-[150px] rounded object-cover bg-muted"
                onError={() => setPreviewBroken(true)}
              />
              <div className="space-y-4">
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
                  name="backdrop_url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Backdrop URL</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex flex-wrap gap-6">
                  <FormField
                    control={form.control}
                    name="is_featured"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2 space-y-0">
                        <FormControl>
                          <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">Featured</FormLabel>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="is_trending"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2 space-y-0">
                        <FormControl>
                          <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">Trending</FormLabel>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="new_episode"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2 space-y-0">
                        <FormControl>
                          <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">New episode badge</FormLabel>
                      </FormItem>
                    )}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Genres & audio</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="genre_ids"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Genres</FormLabel>
                    <div className="flex flex-wrap gap-3">
                      {genres.map((g) => {
                        const checked = field.value.includes(g.id);
                        return (
                          <label key={g.id} className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(v) => {
                                if (v) field.onChange([...field.value, g.id]);
                                else field.onChange(field.value.filter((x) => x !== g.id));
                              }}
                            />
                            {g.name}
                          </label>
                        );
                      })}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {(
                [
                  ['audio', 'Audio (comma-separated)'],
                  ['subtitles', 'Subtitles (comma-separated)'],
                  ['dubbed', 'Dubbed (comma-separated)'],
                ] as const
              ).map(([name, label]) => (
                <FormField
                  key={name}
                  control={form.control}
                  name={name}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{label}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ))}
            </CardContent>
          </Card>

          <Button
            type="submit"
            className="bg-primary text-primary-foreground"
            disabled={form.formState.isSubmitting}
            data-testid="series-save"
          >
            {form.formState.isSubmitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create series'}
          </Button>
        </form>
      </Form>
    </div>
  );
}
