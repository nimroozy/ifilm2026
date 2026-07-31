import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
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
      });
      const completed = await adminApi.uploadMediaSessionFile(created.session.id, file, setProgress);
      navigate(`/admin/media/${completed.media_asset_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8" data-testid="media-upload-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-foreground">Media Upload</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Stream files into local MEDIA_ROOT storage. Encoding and CDN are deferred.
          </p>
        </div>
      </div>

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
        {busy && (
          <div className="space-y-1" data-testid="upload-progress">
            <div className="h-2 rounded bg-muted overflow-hidden">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">{progress}%</p>
          </div>
        )}
        {error && (
          <Alert variant="destructive" data-testid="upload-error">
            <AlertTitle>Upload error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" disabled={busy || !file} className="gap-2" data-testid="start-upload">
          <UploadIcon className="h-4 w-4" />
          {busy ? 'Uploading…' : 'Start upload'}
        </Button>
      </form>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent assets</h2>
          <Button variant="outline" size="sm" onClick={() => void loadAssets()}>
            Refresh
          </Button>
        </div>
        {loadingList && <LoadingBlock rows={4} />}
        {listError && <ErrorState message={listError} onRetry={() => void loadAssets()} />}
        {!loadingList && !listError && assets.length === 0 && (
          <EmptyState message="No media assets uploaded yet." />
        )}
        {!loadingList && !listError && assets.length > 0 && (
          <div className="overflow-x-auto border border-border rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="p-3 font-medium">File</th>
                  <th className="p-3 font-medium">Category</th>
                  <th className="p-3 font-medium">Size</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Checksum</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr key={asset.id} className="border-t border-border">
                    <td className="p-3">
                      <Link className="text-primary hover:underline" to={`/admin/media/${asset.id}`}>
                        {asset.original_filename}
                      </Link>
                    </td>
                    <td className="p-3">{asset.category}</td>
                    <td className="p-3">{formatBytes(asset.size_bytes)}</td>
                    <td className="p-3">
                      <StatusBadge status={asset.upload_status} />
                    </td>
                    <td className="p-3 font-mono text-xs truncate max-w-[12rem]">
                      {asset.checksum_sha256 || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
