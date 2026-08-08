import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  ApiError,
  adminApi,
  type MediaAssetDto,
  type MediaAssetUsageDto,
  type MediaPackageDto,
  type ProcessingJobDto,
  type ProcessingStatusDto,
} from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock, StatusBadge } from './adminShared';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

export default function MediaAssetDetailPage() {
  const { assetId = '' } = useParams();
  const navigate = useNavigate();
  const [asset, setAsset] = useState<MediaAssetDto | null>(null);
  const [jobs, setJobs] = useState<ProcessingJobDto[]>([]);
  const [packages, setPackages] = useState<MediaPackageDto[]>([]);
  const [status, setStatus] = useState<ProcessingStatusDto | null>(null);
  const [usages, setUsages] = useState<MediaAssetUsageDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const pollRef = useRef<number | null>(null);

  const activeJob = jobs.find((j) => !TERMINAL.has(j.status)) ?? jobs[0] ?? null;
  const canEncode =
    asset?.upload_status === 'completed' &&
    asset.probed_at != null &&
    (asset.height ?? 0) > 0 &&
    (asset.width ?? 0) > 0;

  const load = useCallback(async () => {
    if (!assetId) return;
    setError(null);
    try {
      const [data, processing, feature, pkgs, usage] = await Promise.all([
        adminApi.getMediaAsset(assetId),
        adminApi.listAssetProcessingJobs(assetId).catch(() => ({ items: [] as ProcessingJobDto[] })),
        adminApi.getProcessingStatus().catch(() => null),
        adminApi.listAssetPackages(assetId).catch(() => ({ items: [] as MediaPackageDto[] })),
        adminApi.getMediaAssetUsages(assetId).catch(() => ({ asset_id: assetId, usages: [] as MediaAssetUsageDto[] })),
      ]);
      setAsset(data);
      setJobs(processing.items ?? []);
      setStatus(feature);
      setPackages(pkgs.items ?? []);
      setUsages(usage.usages ?? []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load media asset');
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    const needsPoll =
      jobs.some((j) => !TERMINAL.has(j.status)) ||
      packages.some((p) => !TERMINAL.has(p.status));
    if (!needsPoll) return;
    pollRef.current = window.setInterval(() => {
      void load();
    }, 3000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [jobs, packages, load]);

  async function queueProbe() {
    if (!assetId) return;
    setBusy(true);
    setActionError(null);
    try {
      await adminApi.queueMediaProbe(assetId);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to queue probe');
    } finally {
      setBusy(false);
    }
  }

  async function queueEncode() {
    if (!assetId) return;
    setBusy(true);
    setActionError(null);
    try {
      await adminApi.queueMediaEncodeHls(assetId);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to queue HLS encode');
    } finally {
      setBusy(false);
    }
  }

  async function retryJob(jobId: string) {
    setBusy(true);
    setActionError(null);
    try {
      await adminApi.retryProcessingJob(jobId);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to retry job');
    } finally {
      setBusy(false);
    }
  }

  async function cancelJob(jobId: string) {
    setBusy(true);
    setActionError(null);
    try {
      await adminApi.cancelProcessingJob(jobId);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to cancel job');
    } finally {
      setBusy(false);
    }
  }

  async function deleteAsset() {
    if (!assetId || !confirmDelete) return;
    setBusy(true);
    setActionError(null);
    try {
      await adminApi.deleteMediaAsset(assetId, true);
      navigate('/admin/tools/upload', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.details && typeof err.details === 'object') {
        const detail = err.details as { message?: string; usages?: MediaAssetUsageDto[] };
        setUsages(detail.usages ?? usages);
        setActionError(detail.message || err.message);
      } else {
        setActionError(err instanceof ApiError ? err.message : 'Failed to delete media');
      }
      setConfirmDelete(false);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={6} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!asset) return <ErrorState message="Media asset not found" />;

  const featureDisabled = status != null && !status.enabled;
  const hlsDisabled = status != null && status.enabled && !status.hls_encoding_enabled;
  const missingBinary =
    status != null &&
    (!status.ffprobe_available || (status.hls_encoding_enabled && !status.ffmpeg_available));

  return (
    <div className="space-y-6 max-w-3xl" data-testid="media-asset-detail">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            <Link to="/admin/tools/upload" className="hover:underline">
              ← Uploads
            </Link>
            {' · '}
            <Link to="/admin/media/processing" className="hover:underline">
              Processing jobs
            </Link>
          </p>
          <h1 className="text-2xl font-serif font-bold mt-1">{asset.original_filename}</h1>
        </div>
        <StatusBadge status={asset.upload_status} />
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm border border-border rounded-lg p-4 bg-card">
        <div>
          <dt className="text-muted-foreground">Upload status</dt>
          <dd>{asset.upload_status}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Processing status</dt>
          <dd data-testid="processing-status">{asset.processing_status}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Container</dt>
          <dd>{asset.container_format || '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Duration</dt>
          <dd>{formatDuration(asset.duration_seconds)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Resolution</dt>
          <dd>
            {asset.width && asset.height ? `${asset.width}×${asset.height}` : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Video codec</dt>
          <dd>{asset.video_codec || '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Audio codec</dt>
          <dd>{asset.audio_codec || '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Audio / subtitle streams</dt>
          <dd>
            {asset.audio_stream_count ?? '—'} / {asset.subtitle_stream_count ?? '—'}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Last probe</dt>
          <dd>{asset.probed_at ? new Date(asset.probed_at).toLocaleString() : '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Size</dt>
          <dd>{formatBytes(asset.size_bytes)}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground">SHA256</dt>
          <dd className="font-mono text-xs break-all">{asset.checksum_sha256 || '—'}</dd>
        </div>
      </dl>

      <section className="border border-border rounded-lg p-4 bg-card space-y-3" data-testid="media-delete-panel">
        <h2 className="font-serif font-semibold">Delete media</h2>
        <p className="text-sm text-muted-foreground">
          Linked or in-use assets cannot be deleted. Unlink/archive first. Path traversal outside MEDIA_ROOT is rejected.
        </p>
        {usages.length > 0 ? (
          <div className="text-sm" data-testid="media-usages">
            <p className="font-medium mb-1">Used by:</p>
            <ul className="list-disc ps-5 space-y-1">
              {usages.map((u) => (
                <li key={`${u.kind}-${u.id}`}>
                  {u.kind}: {u.label || u.id}
                  {u.status ? ` (${u.status})` : ''}
                  {u.is_active ? ' · active' : ''}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No catalog links or active packages.</p>
        )}
        {!confirmDelete ? (
          <Button
            size="sm"
            variant="destructive"
            disabled={busy || asset.upload_status === 'deleted'}
            onClick={() => setConfirmDelete(true)}
            data-testid="delete-media"
          >
            Delete
          </Button>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="destructive" disabled={busy} onClick={() => void deleteAsset()} data-testid="confirm-delete-media">
              Confirm delete
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
          </div>
        )}
      </section>

      <section className="border border-border rounded-lg p-4 bg-card space-y-3" data-testid="processing-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-serif font-semibold">Media processing</h2>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy || featureDisabled || asset.upload_status !== 'completed'}
              onClick={() => void queueProbe()}
              data-testid="probe-media"
            >
              Probe media
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy || featureDisabled || hlsDisabled || !canEncode}
              onClick={() => void queueEncode()}
              data-testid="encode-hls"
            >
              Encode HLS
            </Button>
          </div>
        </div>

        {featureDisabled && (
          <p className="text-sm text-muted-foreground" data-testid="processing-disabled">
            Media processing is disabled (ENABLE_MEDIA_PROCESSING).
          </p>
        )}
        {hlsDisabled && (
          <p className="text-sm text-muted-foreground" data-testid="hls-encoding-disabled">
            HLS encoding is disabled (ENABLE_HLS_ENCODING). Probe remains available.
          </p>
        )}
        {missingBinary && !featureDisabled && (
          <p className="text-sm text-destructive" data-testid="processing-missing-binary">
            {status?.hls_encoding_enabled
              ? 'FFmpeg/ffprobe is not available on this host.'
              : 'ffprobe is not available on this host.'}
          </p>
        )}
        {!canEncode && !featureDisabled && asset.upload_status === 'completed' && (
          <p className="text-sm text-muted-foreground" data-testid="encode-requires-probe">
            HLS encode requires a successful probe with video dimensions.
          </p>
        )}
        {actionError && <p className="text-sm text-destructive">{actionError}</p>}

        {activeJob ? (
          <div className="text-sm space-y-2" data-testid="active-job">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={activeJob.status} />
              <span className="text-muted-foreground">{activeJob.job_type}</span>
              <span className="text-muted-foreground">{activeJob.progress_percent}%</span>
              <span>{activeJob.current_step || '—'}</span>
            </div>
            <p className="font-mono text-xs break-all">Job {activeJob.id}</p>
            {activeJob.error_message && (
              <p className="text-destructive" data-testid="job-error">
                {activeJob.error_message}
              </p>
            )}
            <div className="flex gap-2">
              {activeJob.status === 'failed' && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void retryJob(activeJob.id)}
                  data-testid="retry-probe"
                >
                  Retry failed job
                </Button>
              )}
              {!TERMINAL.has(activeJob.status) && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void cancelJob(activeJob.id)}
                  data-testid="cancel-probe"
                >
                  Cancel active job
                </Button>
              )}
            </div>
          </div>
        ) : (
          <EmptyState message="No processing jobs yet. Queue a probe, then encode HLS." />
        )}
      </section>

      <section className="border border-border rounded-lg p-4 bg-card space-y-3" data-testid="packages-panel">
        <h2 className="font-serif font-semibold">HLS packages</h2>
        {packages.length === 0 ? (
          <EmptyState message="No packages yet. Encode HLS after a successful probe." />
        ) : (
          <ul className="space-y-3 text-sm">
            {packages.map((pkg) => (
              <li
                key={pkg.id}
                className="border border-border rounded-md p-3 space-y-2"
                data-testid="package-row"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={pkg.status} />
                  {pkg.is_active ? (
                    <span className="text-xs text-primary font-medium">Active</span>
                  ) : null}
                  <span>{pkg.package_type}</span>
                  <span className="text-muted-foreground font-mono text-xs">{pkg.id}</span>
                </div>
                {pkg.status === 'completed' ? (
                  <>
                    <p>
                      Renditions:{' '}
                      {pkg.renditions.map((r) => r.label).join(', ') || pkg.rendition_count}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Filesystem paths are not exposed. Use Playback sessions for protected URLs.
                    </p>
                    {pkg.is_active ? (
                      <Button asChild size="sm" variant="secondary">
                        <Link to={`/player/asset/${assetId}`} data-testid="admin-play-test">
                          Open protected player
                        </Link>
                      </Button>
                    ) : null}
                  </>
                ) : (
                  <p className="text-muted-foreground">
                    Package output is hidden until validation and promotion complete.
                    {pkg.error_message ? ` ${pkg.error_message}` : ''}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
