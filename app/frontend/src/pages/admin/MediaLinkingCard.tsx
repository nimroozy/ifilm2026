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
import { Badge } from '@/components/ui/badge';
import {
  adminApi,
  ApiError,
  type MediaAssetDto,
  type MediaPackageDto,
} from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock, StatusBadge } from './adminShared';

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
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Link one video asset to this {ownerType}. Detach removes the association only — media files and packages are
          preserved. Publishing still requires an active playable HLS package.
        </p>
      </CardHeader>
      <CardContent className="space-y-4" aria-live="polite">
        {loading && assets.length === 0 ? <LoadingBlock rows={3} /> : null}
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {!loading && !error && assets.length === 0 ? (
          <EmptyState message="No linked media. Upload a new file or link an existing unassigned video asset." />
        ) : null}

        <ul className="space-y-3">
          {assets.map((asset) => {
            const packages = packagesByAsset[asset.id] ?? [];
            const active = packages.find((p) => p.is_active && p.status === 'completed') ?? packages.find((p) => p.is_active);
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
                      <Badge variant="outline">{asset.category}</Badge>
                      <StatusBadge status={asset.upload_status} />
                      <Badge variant="secondary">probe: {asset.probed_at ? 'done' : asset.processing_status}</Badge>
                      <Badge variant="secondary">encode: {asset.processing_status}</Badge>
                      {active ? (
                        <Badge className="bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/20">
                          package: {active.status}
                        </Badge>
                      ) : (
                        <Badge variant="destructive">no active package</Badge>
                      )}
                    </div>
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
