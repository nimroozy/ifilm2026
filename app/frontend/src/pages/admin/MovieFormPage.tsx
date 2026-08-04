import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { adminApi, ApiError, type CatalogStatus, type GenreDto } from '@/lib/api';
import { csvToList, ErrorState, listToCsv, LoadingBlock, POSTER_FALLBACK } from './adminShared';
import PublishingPanel from './PublishingPanel';
import MediaLinkingCard from './MediaLinkingCard';

export const movieFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  original_title: z.string().optional(),
  slug: z.string().optional(),
  description: z.string().optional(),
  release_year: z.coerce.number().int().min(1888).max(2100).optional().or(z.literal('')),
  duration_minutes: z.coerce.number().int().min(0).max(10000).optional().or(z.literal('')),
  age_rating: z.string().optional(),
  language: z.string().optional(),
  country: z.string().optional(),
  imdb_rating: z.coerce.number().min(0).max(10).optional().or(z.literal('')),
  imdb_id: z.string().optional(),
  tmdb_id: z.coerce.number().int().optional().or(z.literal('')),
  trailer_url: z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: 'Trailer URL must start with http:// or https://',
    }),
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
  is_featured: z.boolean().default(false),
  is_trending: z.boolean().default(false),
  director: z.string().optional(),
  producer: z.string().optional(),
  writer: z.string().optional(),
  studio: z.string().optional(),
  cast: z.string().optional(),
  audio: z.string().optional(),
  subtitles: z.string().optional(),
  qualities: z.string().optional(),
  dubbed: z.string().optional(),
  genre_ids: z.array(z.number()).default([]),
});

export type MovieFormValues = z.infer<typeof movieFormSchema>;

function emptyValues(): MovieFormValues {
  return {
    title: '',
    original_title: '',
    slug: '',
    description: '',
    release_year: '' as unknown as number,
    duration_minutes: '' as unknown as number,
    age_rating: '',
    language: '',
    country: '',
    imdb_rating: '' as unknown as number,
    imdb_id: '',
    tmdb_id: '' as unknown as number,
    trailer_url: '',
    poster_url: '',
    backdrop_url: '',
    is_featured: false,
    is_trending: false,
    director: '',
    producer: '',
    writer: '',
    studio: '',
    cast: '',
    audio: '',
    subtitles: '',
    qualities: '',
    dubbed: '',
    genre_ids: [],
  };
}

function GeneralFields({
  form,
}: {
  form: UseFormReturn<MovieFormValues>;
}) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">General</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem className="sm:col-span-2">
              <FormLabel>Title</FormLabel>
              <FormControl>
                <Input {...field} data-testid="movie-title" />
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
                <Input {...field} placeholder="auto from title if empty" />
              </FormControl>
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
          name="language"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Language</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="country"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Country</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="age_rating"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Age rating</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex flex-wrap items-center gap-6 sm:col-span-2">
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
        </div>
      </CardContent>
    </Card>
  );
}

function MetadataFields({
  form,
  genres,
}: {
  form: UseFormReturn<MovieFormValues>;
  genres: GenreDto[];
}) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Metadata</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="director"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Director</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="producer"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Producer</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="writer"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Writer</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="studio"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Studio</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="imdb_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>IMDb ID</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="tt1234567" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="tmdb_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>TMDB ID</FormLabel>
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
            name="trailer_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Trailer URL</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="https://..." />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="cast"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Cast (comma-separated)</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
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
                          else field.onChange(field.value.filter((id) => id !== g.id));
                        }}
                      />
                      {g.name}
                    </label>
                  );
                })}
                {genres.length === 0 && (
                  <p className="text-sm text-muted-foreground">No genres yet.</p>
                )}
              </div>
              <FormMessage />
            </FormItem>
          )}
        />
        {(
          [
            ['audio', 'Audio (comma-separated)'],
            ['subtitles', 'Subtitles (comma-separated)'],
            ['qualities', 'Qualities (comma-separated)'],
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
  );
}

function ArtworkFields({
  form,
  previewSrc,
  onPreviewError,
}: {
  form: UseFormReturn<MovieFormValues>;
  previewSrc: string;
  onPreviewError: () => void;
}) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base">Artwork</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-[120px_1fr]">
        <img
          src={previewSrc}
          alt="Poster preview"
          className="w-[100px] h-[150px] rounded object-cover bg-muted"
          onError={onPreviewError}
        />
        <div className="space-y-4">
          <FormField
            control={form.control}
            name="poster_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Poster URL</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="https://..." data-testid="movie-poster-url" />
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
                  <Input {...field} placeholder="https://..." />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function FormActions({
  form,
  isEdit,
}: {
  form: UseFormReturn<MovieFormValues>;
  isEdit: boolean;
}) {
  return (
    <div className="flex gap-3">
      <Button
        type="submit"
        className="bg-primary text-primary-foreground"
        disabled={form.formState.isSubmitting}
        data-testid="movie-save"
      >
        {form.formState.isSubmitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create movie'}
      </Button>
      <Button type="button" variant="outline" asChild>
        <Link to="/admin/movies">Cancel</Link>
      </Button>
    </div>
  );
}

export default function MovieFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const [genres, setGenres] = useState<GenreDto[]>([]);
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState<string | null>(null);
  const [previewBroken, setPreviewBroken] = useState(false);
  const [currentStatus, setCurrentStatus] = useState<CatalogStatus | string>('draft');
  const [mediaRefreshToken, setMediaRefreshToken] = useState(0);

  const form = useForm<MovieFormValues>({
    resolver: zodResolver(movieFormSchema),
    defaultValues: emptyValues(),
  });

  const posterUrl = form.watch('poster_url');
  const slugValue = form.watch('slug');

  useEffect(() => {
    setPreviewBroken(false);
  }, [posterUrl]);

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
        const movie = await adminApi.getMovie(Number(id));
        if (cancelled) return;
        setCurrentStatus(movie.status);
        form.reset({
          title: movie.title,
          original_title: movie.original_title || '',
          slug: movie.slug || '',
          description: movie.description || '',
          release_year: (movie.release_year ?? movie.year ?? '') as unknown as number,
          duration_minutes: (movie.duration_minutes ?? movie.duration ?? '') as unknown as number,
          age_rating: movie.age_rating || '',
          language: movie.language || '',
          country: movie.country || '',
          imdb_rating: (movie.imdb_rating ?? movie.rating ?? '') as unknown as number,
          imdb_id: movie.imdb_id || '',
          tmdb_id: (movie.tmdb_id ?? '') as unknown as number,
          trailer_url: movie.trailer_url || '',
          poster_url: movie.poster_url || movie.poster || '',
          backdrop_url: movie.backdrop_url || movie.backdrop || '',
          is_featured: movie.is_featured ?? movie.featured ?? false,
          is_trending: movie.is_trending ?? false,
          director: movie.director || '',
          producer: movie.producer || '',
          writer: movie.writer || '',
          studio: movie.studio || '',
          cast: listToCsv(movie.cast),
          audio: listToCsv(movie.audio),
          subtitles: listToCsv(movie.subtitles),
          qualities: listToCsv(movie.qualities),
          dubbed: listToCsv(movie.dubbed),
          genre_ids: Array.isArray(movie.genres)
            ? movie.genres
                .filter((g): g is GenreDto => typeof g !== 'string')
                .map((g) => g.id)
            : [],
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load movie');
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

  async function onSubmit(values: MovieFormValues) {
    const payload = {
      title: values.title,
      original_title: values.original_title || '',
      slug: values.slug || undefined,
      description: values.description || '',
      release_year:
        values.release_year === '' || values.release_year == null
          ? null
          : Number(values.release_year),
      duration_minutes:
        values.duration_minutes === '' || values.duration_minutes == null
          ? null
          : Number(values.duration_minutes),
      age_rating: values.age_rating || '',
      language: values.language || '',
      country: values.country || '',
      imdb_rating:
        values.imdb_rating === '' || values.imdb_rating == null ? null : Number(values.imdb_rating),
      imdb_id: values.imdb_id || null,
      tmdb_id:
        values.tmdb_id === '' || values.tmdb_id == null ? null : Number(values.tmdb_id),
      trailer_url: values.trailer_url || '',
      poster_url: values.poster_url || '',
      backdrop_url: values.backdrop_url || '',
      is_featured: values.is_featured,
      is_trending: values.is_trending,
      director: values.director || '',
      producer: values.producer || '',
      writer: values.writer || '',
      studio: values.studio || '',
      cast: csvToList(values.cast || ''),
      audio: csvToList(values.audio || ''),
      subtitles: csvToList(values.subtitles || ''),
      qualities: csvToList(values.qualities || ''),
      dubbed: csvToList(values.dubbed || ''),
      genre_ids: values.genre_ids,
    };

    try {
      if (isEdit && id) {
        await adminApi.updateMovie(Number(id), payload);
        toast.success('Movie updated');
      } else {
        const created = await adminApi.createMovie(payload);
        toast.success('Movie created');
        navigate(`/admin/movies/${created.id}/edit`, { replace: true });
        return;
      }
      navigate('/admin/movies');
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
          <h2 className="text-xl font-semibold text-foreground">{isEdit ? 'Edit Movie' : 'New Movie'}</h2>
          <p className="text-sm text-muted-foreground">Artwork is URL-based (uploads disabled).</p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/admin/movies">Back</Link>
        </Button>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6" noValidate>
          {isEdit && id ? (
            <Tabs defaultValue="general" className="space-y-4">
              <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1">
                <TabsTrigger value="general">General</TabsTrigger>
                <TabsTrigger value="metadata">Metadata</TabsTrigger>
                <TabsTrigger value="artwork">Artwork</TabsTrigger>
                <TabsTrigger value="media">Media</TabsTrigger>
                <TabsTrigger value="publishing">Publishing</TabsTrigger>
                <TabsTrigger value="seo">SEO</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>

              <TabsContent value="general" className="space-y-4">
                <GeneralFields form={form} />
              </TabsContent>

              <TabsContent value="metadata" className="space-y-4">
                <MetadataFields form={form} genres={genres} />
              </TabsContent>

              <TabsContent value="artwork" className="space-y-4">
                <ArtworkFields
                  form={form}
                  previewSrc={previewSrc}
                  onPreviewError={() => setPreviewBroken(true)}
                />
              </TabsContent>

              <TabsContent value="media" className="space-y-4">
                <MediaLinkingCard
                  ownerType="movie"
                  ownerId={Number(id)}
                  contentStatus={String(currentStatus)}
                  onChanged={() => setMediaRefreshToken((n) => n + 1)}
                />
              </TabsContent>

              <TabsContent value="publishing" className="space-y-4">
                <PublishingPanel
                  entityType="movie"
                  entityId={Number(id)}
                  currentStatus={currentStatus}
                  onChanged={setCurrentStatus}
                  refreshToken={mediaRefreshToken}
                />
              </TabsContent>

              <TabsContent value="seo" className="space-y-4">
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle className="text-base">SEO</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-muted-foreground">
                    <p>
                      Public URL slug:{' '}
                      <span className="font-mono text-foreground">{slugValue || '(auto from title)'}</span>
                    </p>
                    <p>
                      Edit the slug on the General tab. Keep it stable after publish so catalog and share links stay
                      consistent.
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="history" className="space-y-4">
                <Card className="bg-card border-border">
                  <CardHeader>
                    <CardTitle className="text-base">History</CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    Publication history is available under Publishing.
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          ) : (
            <>
              <GeneralFields form={form} />
              <MetadataFields form={form} genres={genres} />
              <ArtworkFields
                form={form}
                previewSrc={previewSrc}
                onPreviewError={() => setPreviewBroken(true)}
              />
            </>
          )}

          <FormActions form={form} isEdit={isEdit} />
        </form>
      </Form>
    </div>
  );
}
