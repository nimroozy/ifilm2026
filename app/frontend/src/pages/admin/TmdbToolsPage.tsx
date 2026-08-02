import { useMemo, useState, type FormEvent } from 'react';
import { Database, Download, ImagePlus, RefreshCw, Search } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ApiError,
  adminApi,
  type TmdbMediaType,
  type TmdbPreviewDto,
  type TmdbSearchResultDto,
  type TmdbTrailerDto,
  type TmdbTranslationDto,
} from '@/lib/api';
import { safeYoutubeEmbedUrl, youtubeEmbedUrlFromKey } from '@/lib/trailers';
import { ErrorState, PosterThumb, StatusBadge } from './adminShared';

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/';
const ARTWORK_KINDS = ['poster', 'backdrop', 'logo'] as const;

function tmdbImage(path?: string | null, size = 'w500'): string {
  return path ? `${TMDB_IMAGE_BASE}${size}${path}` : '';
}

function resultTitle(item: TmdbSearchResultDto, mediaType: TmdbMediaType): string {
  return mediaType === 'movie' ? item.title || item.original_title || `TMDB ${item.id}` : item.name || item.original_name || `TMDB ${item.id}`;
}

function resultYear(item: TmdbSearchResultDto, mediaType: TmdbMediaType): string {
  const date = mediaType === 'movie' ? item.release_date : item.first_air_date;
  return date ? date.slice(0, 4) : 'Year unknown';
}

function translationLabel(item: TmdbTranslationDto): string {
  const country = item.iso_3166_1 ? `-${item.iso_3166_1}` : '';
  return `${item.english_name || item.name || item.iso_639_1 || 'Translation'} (${item.iso_639_1 || '??'}${country})`;
}

function trailerCandidates(preview: TmdbPreviewDto | null): TmdbTrailerDto[] {
  if (!preview) return [];
  const raw = preview.videos?.results || [];
  const videos = raw.filter((item) => {
    const site = (item.site || item.provider || '').toLowerCase();
    const type = (item.type || '').toLowerCase();
    return site === 'youtube' && (!type || type === 'trailer') && Boolean(item.key);
  });
  const selected = preview.selected_trailer;
  const withSelected = selected?.key ? [selected, ...videos] : videos;
  const seen = new Set<string>();
  return withSelected.filter((item) => {
    const key = item.key || item.embed_url || item.title || item.name || '';
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function trailerLabel(item: TmdbTrailerDto): string {
  const title = item.title || item.name || item.key || 'Trailer';
  const official = item.official ? 'Official' : 'Unofficial';
  const lang = item.language || item.iso_639_1 || 'unknown language';
  return `${title} - ${official}, ${lang}`;
}

function previewTitle(preview: TmdbPreviewDto, mediaType: TmdbMediaType, translation?: TmdbTranslationDto): string {
  const data = translation?.data;
  if (mediaType === 'movie') {
    return data?.title || preview.title || preview.original_title || `TMDB ${preview.id}`;
  }
  return data?.name || preview.name || preview.original_name || `TMDB ${preview.id}`;
}

function previewOverview(preview: TmdbPreviewDto, translation?: TmdbTranslationDto): string {
  return translation?.data?.overview || preview.overview || 'No overview returned.';
}

export default function TmdbToolsPage() {
  const [query, setQuery] = useState('');
  const [mediaType, setMediaType] = useState<TmdbMediaType>('movie');
  const [results, setResults] = useState<TmdbSearchResultDto[]>([]);
  const [preview, setPreview] = useState<TmdbPreviewDto | null>(null);
  const [selectedResult, setSelectedResult] = useState<TmdbSearchResultDto | null>(null);
  const [selectedTranslation, setSelectedTranslation] = useState('default');
  const [selectedTrailerKey, setSelectedTrailerKey] = useState('');
  const [forceImport, setForceImport] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [artworkMediaType, setArtworkMediaType] = useState<TmdbMediaType>('movie');
  const [artworkEntityId, setArtworkEntityId] = useState('');
  const [artworkKinds, setArtworkKinds] = useState<Array<(typeof ARTWORK_KINDS)[number]>>(['poster']);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [imported, setImported] = useState<Awaited<ReturnType<typeof adminApi.importTmdbDraft>> | null>(null);
  const [refreshResult, setRefreshResult] = useState<Awaited<ReturnType<typeof adminApi.refreshTmdbDemo>> | null>(null);
  const [artworkChanged, setArtworkChanged] = useState<Record<string, string> | null>(null);

  const translations = preview?.translations?.translations || [];
  const selectedTranslationData = translations.find(
    (item) => `${item.iso_639_1 || ''}-${item.iso_3166_1 || ''}` === selectedTranslation
  );
  const trailers = useMemo(() => trailerCandidates(preview), [preview]);
  const selectedTrailer = trailers.find((item) => item.key === selectedTrailerKey) || trailers[0];
  const selectedEmbed = selectedTrailer
    ? safeYoutubeEmbedUrl(selectedTrailer.embed_url) || youtubeEmbedUrlFromKey(selectedTrailer.key)
    : '';

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setError('Enter a movie or series title to search.');
      return;
    }
    setBusy('search');
    setError(null);
    setNotice(null);
    setPreview(null);
    setSelectedResult(null);
    setImported(null);
    try {
      const response = await adminApi.searchTmdb({ query: query.trim(), media_type: mediaType });
      setResults(response.results || []);
      if (!response.results?.length) setNotice('No TMDB results found.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'TMDB search failed');
    } finally {
      setBusy(null);
    }
  }

  async function onPreview(item: TmdbSearchResultDto) {
    setBusy(`preview-${item.id}`);
    setError(null);
    setNotice(null);
    setImported(null);
    try {
      const response = await adminApi.previewTmdb({ tmdb_id: item.id, media_type: mediaType });
      setSelectedResult(item);
      setPreview(response);
      setSelectedTranslation('default');
      const firstTrailer = trailerCandidates(response)[0];
      setSelectedTrailerKey(firstTrailer?.key || '');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'TMDB preview failed');
    } finally {
      setBusy(null);
    }
  }

  async function onImportDraft() {
    if (!preview) return;
    setBusy('import');
    setError(null);
    setNotice(null);
    try {
      const response = await adminApi.importTmdbDraft({
        tmdb_id: preview.id,
        media_type: mediaType,
        force: forceImport,
      });
      setImported(response);
      setArtworkMediaType(response.result.media_type);
      setArtworkEntityId(String(response.result.entity_id));
      setNotice(`Imported ${previewTitle(preview, mediaType, selectedTranslationData)} as draft.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Draft import failed');
    } finally {
      setBusy(null);
    }
  }

  async function onRefresh() {
    setBusy('refresh');
    setError(null);
    setNotice(null);
    try {
      const response = await adminApi.refreshTmdbDemo({ force: forceRefresh });
      setRefreshResult(response);
      setNotice(`Refreshed ${response.refreshed} TMDB demo item${response.refreshed === 1 ? '' : 's'}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Metadata refresh failed');
    } finally {
      setBusy(null);
    }
  }

  async function onReplaceArtwork(event: FormEvent) {
    event.preventDefault();
    const entityId = Number(artworkEntityId);
    if (!Number.isInteger(entityId) || entityId <= 0) {
      setError('Enter a valid local movie or series ID for artwork replacement.');
      return;
    }
    if (!artworkKinds.length) {
      setError('Select at least one artwork type.');
      return;
    }
    setBusy('artwork');
    setError(null);
    setNotice(null);
    try {
      const response = await adminApi.replaceTmdbArtwork({
        media_type: artworkMediaType,
        entity_id: entityId,
        kinds: artworkKinds,
      });
      setArtworkChanged(response.changed);
      setNotice('Artwork replacement completed.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Artwork replacement failed');
    } finally {
      setBusy(null);
    }
  }

  function toggleArtworkKind(kind: (typeof ARTWORK_KINDS)[number], checked: boolean) {
    setArtworkKinds((current) =>
      checked ? Array.from(new Set([...current, kind])) : current.filter((item) => item !== kind)
    );
  }

  return (
    <div className="space-y-8" data-testid="tmdb-tools-page">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-serif font-bold text-foreground">TMDB tools</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Search TMDB, preview metadata and artwork, then import catalog records as drafts only.
          </p>
        </div>
        <Button variant="outline" onClick={onRefresh} disabled={busy !== null} className="gap-2">
          <RefreshCw className="h-4 w-4" aria-hidden />
          Refresh metadata
        </Button>
      </div>

      {error && <ErrorState message={error} />}
      {notice && (
        <Alert>
          <AlertTitle>TMDB tool update</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
        <div className="space-y-4">
          <form onSubmit={onSearch} className="rounded-lg border border-border bg-card p-4">
            <div className="grid gap-4 md:grid-cols-[160px_minmax(0,1fr)_auto] md:items-end">
              <div className="space-y-2">
                <Label>Type</Label>
                <Select value={mediaType} onValueChange={(value) => setMediaType(value as TmdbMediaType)}>
                  <SelectTrigger aria-label="TMDB media type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="movie">Movie</SelectItem>
                    <SelectItem value="series">Series</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="tmdb-query">Search TMDB</Label>
                <Input
                  id="tmdb-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="e.g. The Kite Runner"
                />
              </div>
              <Button type="submit" disabled={busy !== null} className="gap-2">
                <Search className="h-4 w-4" aria-hidden />
                {busy === 'search' ? 'Searching...' : 'Search'}
              </Button>
            </div>
          </form>

          <div className="rounded-lg border border-border bg-card">
            <div className="border-b border-border p-4">
              <h2 className="font-semibold">Search results</h2>
            </div>
            <div className="divide-y divide-border">
              {results.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">Search results will appear here.</p>
              ) : (
                results.map((item) => (
                  <div key={item.id} className="flex gap-3 p-4">
                    <PosterThumb src={tmdbImage(item.poster_path, 'w185')} alt={resultTitle(item, mediaType)} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium text-foreground">{resultTitle(item, mediaType)}</h3>
                        <Badge variant="outline">{resultYear(item, mediaType)}</Badge>
                        <Badge variant="secondary">TMDB {item.id}</Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {item.overview || 'No overview in search result.'}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant={selectedResult?.id === item.id ? 'default' : 'outline'}
                      onClick={() => onPreview(item)}
                      disabled={busy !== null}
                    >
                      {busy === `preview-${item.id}` ? 'Loading...' : 'Preview'}
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <h2 className="font-semibold">Metadata preview</h2>
            {!preview ? (
              <p className="mt-3 text-sm text-muted-foreground">Choose a search result to preview metadata.</p>
            ) : (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-3">
                  <PosterThumb
                    src={tmdbImage(preview.poster_path, 'w342')}
                    alt={previewTitle(preview, mediaType, selectedTranslationData)}
                    className="aspect-[2/3] w-24 rounded object-cover bg-muted"
                  />
                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold">
                      {previewTitle(preview, mediaType, selectedTranslationData)}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">TMDB {preview.id}</Badge>
                      {mediaType === 'movie' && preview.runtime ? (
                        <Badge variant="outline">{preview.runtime} min</Badge>
                      ) : null}
                      {mediaType === 'series' && (
                        <Badge variant="outline">
                          {preview.number_of_seasons || 0} seasons / {preview.number_of_episodes || 0} episodes
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Translation preview</Label>
                  <Select value={selectedTranslation} onValueChange={setSelectedTranslation}>
                    <SelectTrigger aria-label="Choose TMDB translation">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="default">Default API language</SelectItem>
                      {translations.map((item) => (
                        <SelectItem
                          key={`${item.iso_639_1 || ''}-${item.iso_3166_1 || ''}`}
                          value={`${item.iso_639_1 || ''}-${item.iso_3166_1 || ''}`}
                        >
                          {translationLabel(item)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <p className="text-sm leading-relaxed text-muted-foreground">
                  {previewOverview(preview, selectedTranslationData)}
                </p>

                {preview.backdrop_path && (
                  <img
                    src={tmdbImage(preview.backdrop_path, 'w780')}
                    alt=""
                    className="aspect-video w-full rounded object-cover"
                  />
                )}

                <div className="space-y-2">
                  <Label>Official trailer</Label>
                  {trailers.length ? (
                    <>
                      <Select value={selectedTrailerKey || trailers[0]?.key || ''} onValueChange={setSelectedTrailerKey}>
                        <SelectTrigger aria-label="Choose official trailer">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {trailers.map((item) => (
                            <SelectItem key={item.key || item.embed_url || trailerLabel(item)} value={item.key || ''}>
                              {trailerLabel(item)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {selectedEmbed && (
                        <p className="break-all text-xs text-muted-foreground" data-testid="selected-trailer-url">
                          {selectedEmbed}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">No YouTube trailer returned by TMDB.</p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id="force-import"
                    checked={forceImport}
                    onCheckedChange={(value) => setForceImport(value === true)}
                  />
                  <Label htmlFor="force-import" className="text-sm">
                    Force update existing non-demo match
                  </Label>
                </div>
                <Button onClick={onImportDraft} disabled={busy !== null} className="w-full gap-2">
                  <Download className="h-4 w-4" aria-hidden />
                  {busy === 'import' ? 'Importing...' : 'Import as draft'}
                </Button>
                <p className="text-xs text-muted-foreground">
                  TMDB imports are created as draft records. Use publishing workflow separately after rights review.
                </p>
              </div>
            )}
          </div>

          {imported && (
            <Alert data-testid="tmdb-import-result">
              <Database className="h-4 w-4" aria-hidden />
              <AlertTitle>Draft import complete</AlertTitle>
              <AlertDescription className="space-y-2">
                <p>
                  Local {imported.result.media_type} ID {imported.result.entity_id} is{' '}
                  <StatusBadge status={String(imported.item.status || 'draft')} />.
                </p>
                <p className="text-xs text-muted-foreground">
                  {imported.result.created ? 'Created a new draft.' : 'Updated an existing draft/match.'}
                </p>
              </AlertDescription>
            </Alert>
          )}
        </aside>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">Refresh TMDB demo metadata</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Re-fetch metadata for demo-owned TMDB rows without publishing them.
              </p>
            </div>
            <Button variant="outline" onClick={onRefresh} disabled={busy !== null} className="gap-2">
              <RefreshCw className="h-4 w-4" aria-hidden />
              Refresh
            </Button>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <Checkbox
              id="force-refresh"
              checked={forceRefresh}
              onCheckedChange={(value) => setForceRefresh(value === true)}
            />
            <Label htmlFor="force-refresh" className="text-sm">
              Force refresh
            </Label>
          </div>
          {refreshResult && (
            <p className="mt-3 text-sm text-muted-foreground" data-testid="tmdb-refresh-result">
              Refreshed {refreshResult.refreshed} item{refreshResult.refreshed === 1 ? '' : 's'}.
            </p>
          )}
        </div>

        <form onSubmit={onReplaceArtwork} className="rounded-lg border border-border bg-card p-4">
          <h2 className="font-semibold">Replace artwork selectively</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Pull fresh poster, backdrop, or logo artwork for an existing TMDB-linked local record.
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-[150px_minmax(0,1fr)]">
            <div className="space-y-2">
              <Label>Type</Label>
              <Select value={artworkMediaType} onValueChange={(value) => setArtworkMediaType(value as TmdbMediaType)}>
                <SelectTrigger aria-label="Artwork media type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="movie">Movie</SelectItem>
                  <SelectItem value="series">Series</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="artwork-entity-id">Local entity ID</Label>
              <Input
                id="artwork-entity-id"
                inputMode="numeric"
                value={artworkEntityId}
                onChange={(event) => setArtworkEntityId(event.target.value)}
                placeholder="Movie or series ID"
              />
            </div>
          </div>
          <fieldset className="mt-4 space-y-2">
            <legend className="text-sm font-medium">Artwork to replace</legend>
            <div className="flex flex-wrap gap-4">
              {ARTWORK_KINDS.map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm capitalize">
                  <Checkbox
                    checked={artworkKinds.includes(kind)}
                    onCheckedChange={(value) => toggleArtworkKind(kind, value === true)}
                  />
                  {kind}
                </label>
              ))}
            </div>
          </fieldset>
          <Button type="submit" disabled={busy !== null} className="mt-4 gap-2">
            <ImagePlus className="h-4 w-4" aria-hidden />
            {busy === 'artwork' ? 'Replacing...' : 'Replace selected artwork'}
          </Button>
          {artworkChanged && (
            <div className="mt-3 space-y-1 text-xs text-muted-foreground" data-testid="tmdb-artwork-result">
              {Object.keys(artworkChanged).length ? (
                Object.entries(artworkChanged).map(([field, url]) => (
                  <p key={field}>
                    <span className="font-medium">{field}</span>: {url}
                  </p>
                ))
              ) : (
                <p>No artwork changed; TMDB may not have files for the selected kinds.</p>
              )}
            </div>
          )}
        </form>
      </section>
    </div>
  );
}
