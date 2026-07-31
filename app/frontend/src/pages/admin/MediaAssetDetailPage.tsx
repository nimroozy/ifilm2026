import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, adminApi, type MediaAssetDto } from '@/lib/api';
import { ErrorState, LoadingBlock, StatusBadge } from './adminShared';

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function MediaAssetDetailPage() {
  const { assetId = '' } = useParams();
  const [asset, setAsset] = useState<MediaAssetDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!assetId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.getMediaAsset(assetId);
      setAsset(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load media asset');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [assetId]);

  if (loading) return <LoadingBlock rows={6} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!asset) return <ErrorState message="Media asset not found" />;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="media-asset-detail">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            <Link to="/admin/tools/upload" className="hover:underline">
              ← Uploads
            </Link>
          </p>
          <h1 className="text-2xl font-serif font-bold mt-1">{asset.original_filename}</h1>
        </div>
        <StatusBadge status={asset.upload_status} />
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm border border-border rounded-lg p-4 bg-card">
        <div>
          <dt className="text-muted-foreground">Asset ID</dt>
          <dd className="font-mono text-xs break-all">{asset.id}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Category</dt>
          <dd>{asset.category}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">MIME</dt>
          <dd>{asset.mime_type}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Size</dt>
          <dd>{formatBytes(asset.size_bytes)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Storage backend</dt>
          <dd>{asset.storage_backend}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Processing</dt>
          <dd>{asset.processing_status}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">Storage path</dt>
          <dd className="font-mono text-xs break-all">{asset.storage_path || '—'}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">SHA256</dt>
          <dd className="font-mono text-xs break-all">{asset.checksum_sha256 || '—'}</dd>
        </div>
      </dl>
    </div>
  );
}
