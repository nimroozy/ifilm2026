import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Upload as UploadIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ApiError, adminApi, type MediaCategory } from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock, StatusBadge } from './adminShared';

const CATEGORIES: MediaCategory[] = ['originals', 'posters', 'backdrops', 'trailers', 'subtitles'];

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function MediaUploadPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const ownerType = searchParams.get('owner_type');
  const ownerIdRaw = searchParams.get('owner_id');
  const ownerId = ownerIdRaw ? Number(ownerIdRaw) : null;
  const ownerPreselect = useMemo(() => {
    if ((ownerType === 'movie' || ownerType === 'episode') && ownerId && Number.isFinite(ownerId) && ownerId > 0) {
      return { ownerType, ownerId } as const;
    }
    return null;
  }, [ownerType, ownerId]);

  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<MediaCategory>('originals');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [assets, setAssets] = useState<Awaited<ReturnType<typeof adminApi.listMediaAssets>>['items']>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  async function loadAssets() {
    setLoadingList(true);
    setListError(null);
    try {
      const page = await adminApi.listMediaAssets({ page: 1, page_size: 50 });
      setAssets(page.items);
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : 'Failed to load media assets');
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    void loadAssets();
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) {
      setError('Choose a file to upload');
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      const created = await adminApi.createMediaUploadSession({
        filename: file.name,
        mime_type: file.type || 'application/octet-stream',
        size_bytes: file.size,
        category,
        movie_id: ownerPreselect?.ownerType === 'movie' ? ownerPreselect.ownerId : null,
        episode_id: ownerPreselect?.ownerType === 'episode' ? ownerPreselect.ownerId : null,
      });
      const completed = await adminApi.uploadMediaSessionFile(created.session.id, file, setProgress);
      if (ownerPreselect) {
        navigate(
          ownerPreselect.ownerType === 'movie'
            ? `/admin/movies/${ownerPreselect.ownerId}/edit`
            : `/admin/episodes/${ownerPreselect.ownerId}/edit`,
          { replace: true }
        );
        return;
      }
      navigate(`/admin/media/${completed.media_asset_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-w-0 max-w-full space-y-8" data-testid="media-upload-page">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-foreground">Media Upload</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Stream files into local MEDIA_ROOT storage. Encoding runs through the processing pipeline.
          </p>
        </div>
      </div>

      {ownerPreselect ? (
        <Alert data-testid="upload-owner-preselect">
          <AlertTitle>Linking to {ownerPreselect.ownerType}</AlertTitle>
          <AlertDescription>
            This upload will be associated with {ownerPreselect.ownerType} #{ownerPreselect.ownerId}. After upload you
            will return to the edit page.
          </AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={onSubmit} className="space-y-4 max-w-xl border border-border rounded-lg p-4 bg-card">
        <div className="space-y-2">
          <Label htmlFor="media-file">File</Label>
          <Input
            id="media-file"
            type="file"
            data-testid="media-file-input"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file && (
            <p className="text-xs text-muted-foreground">
              {file.name} · {formatBytes(file.size)} · {file.type || 'unknown type'}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <Label>Category</Label>
          <Select value={category} onValueChange={(v) => setCategory(v as MediaCategory)}>
            <SelectTrigger data-testid="media-category">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Upload error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {busy && (
          <div className="space-y-1" aria-live="polite">
            <div className="h-2 overflow-hidden rounded bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">{progress}%</p>
          </div>
        )}
        <Button type="submit" disabled={busy || !file} data-testid="media-upload-submit">
          <UploadIcon className="me-2 h-4 w-4" />
          {busy ? 'Uploading…' : ownerPreselect ? 'Upload and Link' : 'Start Upload'}
        </Button>
      </form>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Recent assets</h2>
        {loadingList ? <LoadingBlock /> : null}
        {listError ? <ErrorState message={listError} onRetry={loadAssets} /> : null}
        {!loadingList && !listError && assets.length === 0 ? (
          <EmptyState message="No media assets yet." />
        ) : null}
        <ul className="space-y-2">
          {assets.map((asset) => (
            <li key={asset.id} className="flex items-center justify-between gap-3 rounded border border-border p-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{asset.original_filename}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(asset.size_bytes)}
                  {asset.movie_id ? ` · movie #${asset.movie_id}` : ''}
                  {asset.episode_id ? ` · episode #${asset.episode_id}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={asset.upload_status} />
                <Button variant="outline" size="sm" asChild>
                  <Link to={`/admin/media/${asset.id}`}>Open</Link>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
