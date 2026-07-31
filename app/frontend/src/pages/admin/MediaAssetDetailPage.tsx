import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  ApiError,
  adminApi,
  type MediaAssetDto,
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
  const [asset, setAsset] = useState<MediaAssetDto | null>(null);
  const [jobs, setJobs] = useState<ProcessingJobDto[]>([]);
  const [status, setStatus] = useState<ProcessingStatusDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<number | null>(null);

  const activeJob = jobs.find((j) => !TERMINAL.has(j.status)) ?? jobs[0] ?? null;

  const load = useCallback(async () => {
    if (!assetId) return;
    setError(null);
    try {
      const [data, processing, feature] = await Promise.all([
        adminApi.getMediaAsset(assetId),
        adminApi.listAssetProcessingJobs(assetId).catch(() => ({ items: [] as ProcessingJobDto[] })),
        adminApi.getProcessingStatus().catch(() => null),
      ]);
      setAsset(data);
      setJobs(processing.items ?? []);
      setStatus(feature);
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
    const needsPoll = jobs.some((j) => !TERMINAL.has(j.status));
    if (!needsPoll) return;
    pollRef.current = window.setInterval(() => {
      void load();
    }, 3000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [jobs, load]);

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

  if (loading) return <LoadingBlock rows={6} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!asset) return <ErrorState message="Media asset not found" />;

  const featureDisabled = status != null && !status.enabled;
  const missingBinary = status != null && (!status.ffmpeg_available || !status.ffprobe_available);

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

      <section className="border border-border rounded-lg p-4 bg-card space-y-3" data-testid="processing-panel">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-serif font-semibold">Media processing</h2>
          <Button
            size="sm"
            disabled={busy || featureDisabled || asset.upload_status !== 'completed'}
            onClick={() => void queueProbe()}
            data-testid="probe-media"
          >
            Probe media
          </Button>
        </div>

        {featureDisabled && (
          <p className="text-sm text-muted-foreground" data-testid="processing-disabled">
            Media processing is disabled (ENABLE_MEDIA_PROCESSING).
          </p>
        )}
        {missingBinary && !featureDisabled && (
          <p className="text-sm text-destructive" data-testid="processing-missing-binary">
            FFmpeg/ffprobe is not available on this host.
          </p>
        )}
        {actionError && <p className="text-sm text-destructive">{actionError}</p>}

        {activeJob ? (
          <div className="text-sm space-y-2" data-testid="active-job">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={activeJob.status} />
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
                  Retry failed probe
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
          <EmptyState message="No processing jobs yet. Queue a probe to inspect this upload." />
        )}
      </section>
    </div>
  );
}
