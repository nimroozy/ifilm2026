import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Film,
  Link2,
  Loader2,
  RefreshCw,
  Unlink,
  Upload,
  ExternalLink,
  PlayCircle,
  RotateCcw,
  Cpu,
  Globe,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  adminApi,
  ApiError,
  type MediaAssetDto,
  type MediaPackageDto,
} from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock } from './adminShared';

type OwnerType = 'movie' | 'episode';

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function resolutionLabel(asset: MediaAssetDto): string {
  if (asset.width && asset.height) return `${asset.width}×${asset.height}`;
  return '—';
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function isExternalAsset(asset: MediaAssetDto): boolean {
  return asset.source_type === 'external' || Boolean(asset.external_url);
}

/** Product playability/status labels for the Media tab (avoid conflicting raw states). */
export function mediaAssetStatusLabels(
  asset: MediaAssetDto,
  packages: MediaPackageDto[]
): string[] {
  const labels: string[] = [];
  const external = isExternalAsset(asset);
  const active = packages.find((p) => p.is_active && p.status === 'completed') ?? packages.find((p) => p.is_active);
  const upload = (asset.upload_status || '').toLowerCase();
  const processing = (asset.processing_status || '').toLowerCase();

  if (external) {
    if (asset.external_is_primary) labels.push('External source');
    if (asset.external_protection_mode === 'unprotected_direct' || !asset.external_protection_mode) {
      labels.push('Unprotected direct');
    }
    if (asset.external_validated_at) {
      labels.push('External Validated');
      labels.push('Ready');
    } else {
      labels.push('Validation Failed');
      labels.push('Not Playable');
    }
    return labels;
  }

  if (['failed', 'cancelled', 'deleted'].includes(upload)) {
    labels.push('Not Playable');
    return labels;
  }
  if (upload === 'completed' && (processing === 'ready' || processing === 'completed' || asset.probed_at)) {
    labels.push('Ready');
  } else if (['pending', 'queued', 'running', 'probing', 'encoding', 'processing'].includes(processing) || upload === 'uploading') {
    labels.push('Processing');
  }

  if (active && active.status === 'completed') {
    labels.push('Package Ready');
  } else if (!labels.includes('Processing')) {
    labels.push('Not Playable');
  }

  return labels.length > 0 ? labels : ['Not Playable'];
}

function truncateUrl(url: string, max = 48): string {
  if (url.length <= max) return url;
  return `${url.slice(0, max - 1)}…`;
}

interface MediaLinkingCardProps {
  ownerType: OwnerType;
  ownerId: number;
  contentStatus?: string;
  onChanged?: () => void;
}

export default function MediaLinkingCard({
  ownerType,
  ownerId,
  contentStatus,
  onChanged,
}: MediaLinkingCardProps) {
  const [assets, setAssets] = useState<MediaAssetDto[]>([]);
  const [packagesByAsset, setPackagesByAsset] = useState<Record<string, MediaPackageDto[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [externalOpen, setExternalOpen] = useState(false);
  const [detachTarget, setDetachTarget] = useState<MediaAssetDto | null>(null);
  const [forceUnpublish, setForceUnpublish] = useState(false);

  const uploadHref = `/admin/tools/upload?owner_type=${ownerType}&owner_id=${ownerId}`;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params =
        ownerType === 'movie'
          ? { movie_id: ownerId, page_size: 50 }
          : { episode_id: ownerId, page_size: 50 };
      const page = await adminApi.listMediaAssets(params);
      setAssets(page.items);
      const pkgEntries = await Promise.all(
        page.items.map(async (asset) => {
          try {
            const pkgs = await adminApi.listAssetPackages(asset.id);
            return [asset.id, pkgs.items] as const;
          } catch {
            return [asset.id, [] as MediaPackageDto[]] as const;
          }
        })
      );
      setPackagesByAsset(Object.fromEntries(pkgEntries));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load linked media');
    } finally {
      setLoading(false);
    }
  }, [ownerId, ownerType]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runAction(assetId: string, action: 'probe' | 'encode') {
    setBusyId(assetId);
    try {
      if (action === 'probe') {
        await adminApi.queueMediaProbe(assetId);
        toast.success('Probe queued');
      } else {
        await adminApi.queueMediaEncodeHls(assetId);
        toast.success('HLS encoding queued');
      }
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Action failed');
    } finally {
      setBusyId(null);
    }
  }

  async function confirmDetach() {
    if (!detachTarget) return;
    setBusyId(detachTarget.id);
    try {
      await adminApi.detachMediaAsset(detachTarget.id, { force_unpublish: forceUnpublish });
      toast.success(forceUnpublish ? 'Detached and unpublished' : 'Media detached');
      setDetachTarget(null);
      setForceUnpublish(false);
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Detach failed');
    } finally {
      setBusyId(null);
    }
  }

  const isPublished = contentStatus === 'published';

  return (
    <Card className="bg-card border-border" data-testid="media-linking-card" aria-labelledby="media-linking-title">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle id="media-linking-title" className="flex items-center gap-2 text-base">
            <Film className="h-4 w-4 text-muted-foreground" aria-hidden />
            Media
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={load} aria-label="Refresh media">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            <Button type="button" variant="secondary" size="sm" asChild>
              <Link to={uploadHref} data-testid="media-upload-and-link">
                <Upload className="me-1.5 h-3.5 w-3.5" />
                Upload and Link
              </Link>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setLinkOpen(true)}
              data-testid="media-link-existing"
            >
              <Link2 className="me-1.5 h-3.5 w-3.5" />
              Link Existing Media
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setExternalOpen(true)}
              data-testid="media-external-url"
            >
              <Globe className="me-1.5 h-3.5 w-3.5" />
              External URL
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Link one video asset to this {ownerType}. Detach removes the association only — media files and packages are
          preserved. Publishing still requires an active playable HLS package or validated external media.
        </p>
      </CardHeader>
      <CardContent className="space-y-4" aria-live="polite">
        {loading && assets.length === 0 ? <LoadingBlock rows={3} /> : null}
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {!loading && !error && assets.length === 0 ? (
          <EmptyState
            message={`No media is linked to this ${ownerType}. Use Upload and Link, Link Existing Media, or External URL.`}
          />
        ) : null}

        <ul className="space-y-3">
          {assets.map((asset) => {
            const packages = packagesByAsset[asset.id] ?? [];
            const active = packages.find((p) => p.is_active && p.status === 'completed') ?? packages.find((p) => p.is_active);
            const external = isExternalAsset(asset);
            return (
              <li
                key={asset.id}
                className="rounded-lg border border-border p-3"
                data-testid={`linked-media-${asset.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className="truncate font-medium text-foreground" title={asset.original_filename}>
                      {asset.original_filename}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {external ? <Badge variant="secondary">External</Badge> : null}
                      <Badge variant="outline">{asset.category}</Badge>
                      {mediaAssetStatusLabels(asset, packages).map((label) => (
                        <Badge
                          key={label}
                          variant={
                            label === 'Not Playable' || label === 'Validation Failed'
                              ? 'destructive'
                              : label === 'Package Ready' || label === 'External Validated' || label === 'Ready'
                                ? 'default'
                                : 'secondary'
                          }
                          className={
                            label === 'Package Ready' || label === 'External Validated' || label === 'Ready'
                              ? 'bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/20'
                              : undefined
                          }
                          data-testid={`media-status-${label.toLowerCase().replace(/\s+/g, '-')}`}
                        >
                          {label}
                        </Badge>
                      ))}
                      {external && asset.external_kind ? (
                        <Badge variant="outline">{asset.external_kind.toUpperCase()}</Badge>
                      ) : null}
                    </div>
                    {external ? (
                      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
                        <div>
                          <dt className="inline">Kind </dt>
                          <dd className="inline">{asset.external_kind || '—'}</dd>
                        </div>
                        <div>
                          <dt className="inline">Protection </dt>
                          <dd className="inline">
                            {asset.external_protection_mode === 'unprotected_direct'
                              ? 'Unprotected direct'
                              : asset.external_protection_mode || '—'}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline">Primary </dt>
                          <dd className="inline">{asset.external_is_primary ? 'Yes' : 'No'}</dd>
                        </div>
                        <div>
                          <dt className="inline">Validated </dt>
                          <dd className="inline">{formatDate(asset.external_validated_at)}</dd>
                        </div>
                      </dl>
                    ) : null}
                    {external && (asset.external_url_masked || asset.external_url) ? (
                      <p
                        className="mt-1 truncate text-xs text-muted-foreground"
                        title={asset.external_url_masked || asset.external_url || undefined}
                      >
                        {truncateUrl(asset.external_url_masked || asset.external_url || '')}
                      </p>
                    ) : null}
                    {external ? (
                      <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                        Direct URL exposure: session revoke does not stop CDN playback. Admin/demo only — not
                        packaged-HLS protection.
                      </p>
                    ) : null}
                    {!external ? (
                      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
                        <div>
                          <dt className="inline">Size </dt>
                          <dd className="inline">{formatBytes(asset.size_bytes)}</dd>
                        </div>
                        <div>
                          <dt className="inline">Duration </dt>
                          <dd className="inline">{formatDuration(asset.duration_seconds)}</dd>
                        </div>
                        <div>
                          <dt className="inline">Resolution </dt>
                          <dd className="inline">{resolutionLabel(asset)}</dd>
                        </div>
                        <div>
                          <dt className="inline">Created </dt>
                          <dd className="inline">{formatDate(asset.created_at)}</dd>
                        </div>
                      </dl>
                    ) : null}
                    {active?.id ? (
                      <p className="mt-1 truncate text-xs text-muted-foreground" title={active.id}>
                        Active package: {active.id}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Button type="button" size="sm" variant="outline" asChild>
                      <Link to={`/admin/media/${asset.id}`}>
                        <ExternalLink className="me-1 h-3.5 w-3.5" />
                        View Asset
                      </Link>
                    </Button>
                    {!external ? (
                      <>
                        <Button type="button" size="sm" variant="outline" asChild>
                          <Link to={`/admin/media/processing?media_asset_id=${asset.id}`}>
                            <Cpu className="me-1 h-3.5 w-3.5" />
                            Processing
                          </Link>
                        </Button>
                        <Button type="button" size="sm" variant="outline" asChild>
                          <Link to={`/player/asset/${asset.id}`}>
                            <PlayCircle className="me-1 h-3.5 w-3.5" />
                            Protected Player
                          </Link>
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={busyId === asset.id}
                          onClick={() => runAction(asset.id, 'probe')}
                        >
                          {busyId === asset.id ? <Loader2 className="me-1 h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="me-1 h-3.5 w-3.5" />}
                          Retry Probe
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={busyId === asset.id}
                          onClick={() => runAction(asset.id, 'encode')}
                        >
                          Queue Encoding
                        </Button>
                      </>
                    ) : null}
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={busyId === asset.id}
                      onClick={() => {
                        setForceUnpublish(false);
                        setDetachTarget(asset);
                      }}
                      data-testid={`detach-media-${asset.id}`}
                    >
                      <Unlink className="me-1 h-3.5 w-3.5" />
                      Detach
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>

      <LinkExistingMediaDialog
        open={linkOpen}
        onOpenChange={setLinkOpen}
        ownerType={ownerType}
        ownerId={ownerId}
        onLinked={async () => {
          await load();
          onChanged?.();
        }}
      />

      <ExternalUrlDialog
        open={externalOpen}
        onOpenChange={setExternalOpen}
        ownerType={ownerType}
        ownerId={ownerId}
        onAttached={async () => {
          await load();
          onChanged?.();
        }}
      />

      <AlertDialog
        open={detachTarget !== null}
        onOpenChange={(open) => {
          if (!open && busyId === null) {
            setDetachTarget(null);
            setForceUnpublish(false);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Detach media?</AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block">
                This removes the link from the {ownerType} only. The media file, packages, and processing history are
                kept.
              </span>
              {isPublished ? (
                <span className="block text-amber-500">
                  This {ownerType} is published. Detach is blocked if no remaining playable package exists unless you
                  unpublish.
                </span>
              ) : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {isPublished ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={forceUnpublish}
                onChange={(e) => setForceUnpublish(e.target.checked)}
                data-testid="force-unpublish-detach"
              />
              Unpublish if required to detach
            </label>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busyId !== null}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busyId !== null}
              onClick={(e) => {
                e.preventDefault();
                void confirmDetach();
              }}
            >
              {busyId ? 'Working…' : 'Detach'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function ExternalUrlDialog({
  open,
  onOpenChange,
  ownerType,
  ownerId,
  onAttached,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ownerType: OwnerType;
  ownerId: number;
  onAttached: () => Promise<void>;
}) {
  const [url, setUrl] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setUrl('');
      setAcknowledged(false);
      setSubmitting(false);
    }
  }, [open]);

  async function submit() {
    const trimmed = url.trim();
    if (!trimmed.startsWith('https://')) {
      toast.error('URL must start with https://');
      return;
    }
    if (!acknowledged) {
      toast.error('Acknowledge the unprotected external media warning to continue');
      return;
    }
    setSubmitting(true);
    try {
      await adminApi.attachExternalMedia({
        url: trimmed,
        owner_type: ownerType,
        owner_id: ownerId,
        acknowledge_unprotected_external: true,
      });
      toast.success('External media attached as primary source');
      onOpenChange(false);
      await onAttached();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to attach external media');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="external-url-dialog">
        <DialogHeader>
          <DialogTitle>Attach external URL</DialogTitle>
          <DialogDescription>
            Option A — admin / demo only. The player receives the CDN URL directly after session authorization.
            This is not packaged-HLS protection: revoke does not stop CDN playback, and the URL may appear in
            browser network tools. Attaching activates this source as the sole primary external and deactivates
            any previous primary.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="external-media-url">HTTPS URL</Label>
            <Input
              id="external-media-url"
              type="url"
              placeholder="https://..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              data-testid="external-media-url-input"
              disabled={submitting}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              After save, only a masked host/path is shown. Query tokens are never returned in admin APIs.
            </p>
          </div>
          <label className="flex items-start gap-2 text-sm" data-testid="external-media-ack">
            <input
              type="checkbox"
              className="mt-1"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              disabled={submitting}
            />
            <span>
              I understand this is an unprotected direct external source for admin/demo use, not equivalent to
              session-proxied packaged HLS, and production publish requires a packaged HLS source.
            </span>
          </label>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={submitting} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={submitting || !url.trim() || !acknowledged}
            onClick={() => void submit()}
            data-testid="external-media-submit"
          >
            {submitting ? <Loader2 className="me-1 h-3.5 w-3.5 animate-spin" /> : null}
            Attach primary external
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LinkExistingMediaDialog({
  open,
  onOpenChange,
  ownerType,
  ownerId,
  onLinked,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ownerType: OwnerType;
  ownerId: number;
  onLinked: () => Promise<void>;
}) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<MediaAssetDto[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const pageSize = 10;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.listMediaAssets({
        page,
        page_size: pageSize,
        unassigned: true,
        video_only: true,
        linkable_only: true,
        status: 'completed',
        q: q.trim() || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load assets');
    } finally {
      setLoading(false);
    }
  }, [page, q]);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => {
      void load();
    }, 200);
    return () => window.clearTimeout(handle);
  }, [open, load]);

  async function attach(asset: MediaAssetDto) {
    setBusyId(asset.id);
    try {
      await adminApi.linkMediaAsset(asset.id, { owner_type: ownerType, owner_id: ownerId });
      toast.success('Media linked');
      onOpenChange(false);
      await onLinked();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Link failed');
    } finally {
      setBusyId(null);
    }
  }

  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="link-existing-media-dialog">
        <DialogHeader>
          <DialogTitle>Link existing media</DialogTitle>
          <DialogDescription>
            Only unassigned, completed video assets are listed. Attach is atomic — a conflict means another request won.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="Search filename, id, or checksum…"
            value={q}
            onChange={(e) => {
              setPage(1);
              setQ(e.target.value);
            }}
            data-testid="link-media-search"
          />
          {loading ? <LoadingBlock rows={4} /> : null}
          {error ? <ErrorState message={error} onRetry={load} /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState message="No unassigned video assets. Upload a new file first, then return here." />
          ) : null}
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {items.map((asset) => (
              <li key={asset.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-border p-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{asset.original_filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatBytes(asset.size_bytes)} · {formatDuration(asset.duration_seconds)} · {resolutionLabel(asset)}
                    {asset.probed_at ? ' · probed' : ' · not probed'}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  disabled={busyId === asset.id}
                  onClick={() => void attach(asset)}
                  data-testid={`attach-asset-${asset.id}`}
                >
                  {busyId === asset.id ? <Loader2 className="me-1 h-3.5 w-3.5 animate-spin" /> : null}
                  Attach
                </Button>
              </li>
            ))}
          </ul>
        </div>
        <DialogFooter className="flex items-center justify-between gap-2 sm:justify-between">
          <p className="text-xs text-muted-foreground">
            Page {page} of {pages} · {total} assets
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
