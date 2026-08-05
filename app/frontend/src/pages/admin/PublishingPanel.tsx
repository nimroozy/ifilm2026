import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, PackageCheck, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
import { Input } from '@/components/ui/input';
import {
  adminApi,
  ApiError,
  type CatalogEntityType,
  type CatalogStatus,
  type PublicationHistoryEventDto,
  type PublicationReadinessDto,
} from '@/lib/api';
import { ErrorState, LoadingBlock, StatusBadge } from './adminShared';

type ConfirmAction = 'publish' | 'schedule' | 'unpublish' | 'archive';
type ImmediateAction = 'submit_review' | 'approve';
type WorkflowAction = ConfirmAction | ImmediateAction;

interface PublishingPanelProps {
  entityType: CatalogEntityType;
  entityId: number;
  currentStatus: CatalogStatus | string;
  onChanged: (status: CatalogStatus) => void;
  /** Increment to force a readiness reload after media link/detach. */
  refreshToken?: number;
  /** Switch parent movie editor to the Media tab when remediation needs it. */
  onOpenMediaTab?: () => void;
}

const actionLabels: Record<WorkflowAction, string> = {
  submit_review: 'Submit for Review',
  approve: 'Approve',
  publish: 'Publish',
  schedule: 'Schedule',
  unpublish: 'Unpublish',
  archive: 'Archive',
};

function formatTimestamp(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export default function PublishingPanel({
  entityType,
  entityId,
  currentStatus,
  onChanged,
  refreshToken = 0,
  onOpenMediaTab,
}: PublishingPanelProps) {
  const [readiness, setReadiness] = useState<PublicationReadinessDto | null>(null);
  const [history, setHistory] = useState<PublicationHistoryEventDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<WorkflowAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scheduleAt, setScheduleAt] = useState('');
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextReadiness, nextHistory] = await Promise.all([
        adminApi.getPublicationReadiness(entityType, entityId),
        adminApi.getPublicationHistory(entityType, entityId),
      ]);
      setReadiness(nextReadiness);
      setHistory(nextHistory);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load publishing information');
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  useEffect(() => {
    load();
  }, [load, refreshToken]);

  const isAllowed = (action: WorkflowAction) =>
    Boolean(readiness?.allowed_actions.includes(action));

  async function runAction(action: WorkflowAction) {
    setWorking(action);
    try {
      let result;
      if (action === 'submit_review') {
        result = await adminApi.submitReview(entityType, entityId);
      } else if (action === 'approve') {
        result = await adminApi.approve(entityType, entityId);
      } else if (action === 'publish') {
        result = await adminApi.publish(entityType, entityId);
      } else if (action === 'schedule') {
        const scheduledPublishAt = new Date(scheduleAt).toISOString();
        result = await adminApi.schedule(entityType, entityId, scheduledPublishAt);
      } else if (action === 'unpublish') {
        result = await adminApi.unpublish(entityType, entityId);
      } else {
        result = await adminApi.archive(entityType, entityId);
      }
      toast.success(`${actionLabels[action]} completed`);
      onChanged(result.status);
      if (action === 'schedule') setScheduleAt('');
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : `${actionLabels[action]} failed`);
    } finally {
      setWorking(null);
      setConfirmAction(null);
    }
  }

  function requestConfirmation(action: ConfirmAction) {
    if (action === 'schedule') {
      const timestamp = new Date(scheduleAt).getTime();
      if (!scheduleAt || Number.isNaN(timestamp) || timestamp <= Date.now()) {
        toast.error('Choose a future publication date and time');
        return;
      }
    }
    setConfirmAction(action);
  }

  if (loading && !readiness) {
    return (
      <Card className="bg-card border-border" aria-label="Publishing workflow">
        <CardContent className="pt-6">
          <LoadingBlock rows={3} />
        </CardContent>
      </Card>
    );
  }

  if (error && !readiness) {
    return <ErrorState message={error} onRetry={load} />;
  }

  const status = readiness?.status || currentStatus;
  const timestamps = [
    ['Submitted for review', readiness?.submitted_for_review_at],
    ['Approved', readiness?.approved_at],
    ['Scheduled', readiness?.scheduled_publish_at],
    ['Published', readiness?.published_at],
    ['Unpublished', readiness?.unpublished_at],
    ['Archived', readiness?.archived_at],
  ].filter(([, value]) => value);

  return (
    <Card className="bg-card border-border" aria-labelledby="publishing-panel-title">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle id="publishing-panel-title" className="text-base">
            Publishing workflow
          </CardTitle>
          <div className="flex items-center gap-2">
            <StatusBadge status={status} />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={load}
              disabled={loading || working !== null}
              aria-label="Refresh publishing information"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6" aria-live="polite">
        {error && <ErrorState message={error} onRetry={load} />}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-border p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              {readiness?.ready ? (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
              )}
              {readiness?.ready ? 'Ready to publish' : 'Not ready to publish'}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Readiness is evaluated by the publishing service.
            </p>
          </div>
          <div className="rounded-md border border-border p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <PackageCheck className="h-4 w-4 text-muted-foreground" />
              {readiness?.playable
                ? readiness.package_status === 'external'
                  ? 'External media playable'
                  : 'Playable package available'
                : 'Not playable'}
            </div>
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 text-xs text-muted-foreground">
              <dt>Package</dt>
              <dd className="truncate" title={readiness?.active_package_id || undefined}>
                {readiness?.active_package_id || '—'}
              </dd>
              <dt>Status</dt>
              <dd>{readiness?.package_status || '—'}</dd>
            </dl>
          </div>
        </div>

        {readiness && readiness.issues.length > 0 && (
          <Alert variant="destructive" data-testid="readiness-issues">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Readiness issues</AlertTitle>
            <AlertDescription>
              <ul className="mt-2 list-disc space-y-1 ps-5">
                {readiness.issues.map((issue, index) => (
                  <li key={`${issue.code}-${index}`}>
                    {issue.message}
                    {issue.field ? (
                      <span className="text-xs opacity-80"> ({issue.field})</span>
                    ) : null}
                  </li>
                ))}
              </ul>
              {(entityType === 'movie' || entityType === 'episode') &&
              readiness.issues.some((i) =>
                [
                  'no_media_asset',
                  'no_active_hls_package',
                  'media_asset_unusable',
                  'external_not_validated',
                ].includes(i.code)
              ) ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="secondary" asChild>
                    <Link
                      to={`/admin/tools/upload?owner_type=${entityType}&owner_id=${entityId}`}
                      data-testid="readiness-upload-link"
                    >
                      Upload and Link
                    </Link>
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    data-testid="readiness-open-media"
                    onClick={() => {
                      if (onOpenMediaTab) onOpenMediaTab();
                      else document.getElementById('media-linking-title')?.scrollIntoView({ behavior: 'smooth' });
                    }}
                  >
                    Open Media tab
                  </Button>
                  {readiness.issues.some((i) => i.code === 'external_not_validated' || i.code === 'no_media_asset') ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      data-testid="readiness-external-media"
                      onClick={() => onOpenMediaTab?.()}
                    >
                      Validate external media
                    </Button>
                  ) : null}
                  <Button type="button" size="sm" variant="outline" asChild>
                    <Link to="/admin/media/processing">View Processing</Link>
                  </Button>
                </div>
              ) : null}
            </AlertDescription>
          </Alert>
        )}

        <section aria-labelledby="publishing-actions-title" className="space-y-3">
          <h3 id="publishing-actions-title" className="text-sm font-medium">
            Actions
          </h3>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={!isAllowed('submit_review') || working !== null}
              onClick={() => runAction('submit_review')}
            >
              {working === 'submit_review' ? 'Submitting…' : actionLabels.submit_review}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={!isAllowed('approve') || working !== null}
              onClick={() => runAction('approve')}
            >
              {working === 'approve' ? 'Approving…' : actionLabels.approve}
            </Button>
            <Button
              type="button"
              disabled={!isAllowed('publish') || working !== null}
              onClick={() => requestConfirmation('publish')}
            >
              {actionLabels.publish}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!isAllowed('unpublish') || working !== null}
              onClick={() => requestConfirmation('unpublish')}
            >
              {actionLabels.unpublish}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={!isAllowed('archive') || working !== null}
              onClick={() => requestConfirmation('archive')}
            >
              {actionLabels.archive}
            </Button>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="space-y-1 text-sm">
              <span className="block text-muted-foreground">Publication date and time</span>
              <Input
                type="datetime-local"
                value={scheduleAt}
                onChange={(event) => setScheduleAt(event.target.value)}
                disabled={!isAllowed('schedule') || working !== null}
                className="w-auto"
                dir="ltr"
              />
            </label>
            <Button
              type="button"
              variant="outline"
              disabled={!isAllowed('schedule') || !scheduleAt || working !== null}
              onClick={() => requestConfirmation('schedule')}
            >
              {actionLabels.schedule}
            </Button>
          </div>
        </section>

        {timestamps.length > 0 && (
          <section aria-labelledby="publishing-timestamps-title">
            <h3 id="publishing-timestamps-title" className="mb-2 text-sm font-medium">
              Timestamps
            </h3>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              {timestamps.map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-3 rounded border p-2">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd>{formatTimestamp(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <section aria-labelledby="publication-history-title">
          <h3 id="publication-history-title" className="mb-2 flex items-center gap-2 text-sm font-medium">
            <Clock className="h-4 w-4" />
            Publication history
          </h3>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No publication events yet.</p>
          ) : (
            <ol className="space-y-2">
              {history.map((event) => (
                <li key={event.id} className="rounded border border-border p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      <StatusBadge status={event.from_status} />{' '}
                      <span aria-hidden="true">→</span>{' '}
                      <StatusBadge status={event.to_status} />
                    </span>
                    <time className="text-xs text-muted-foreground" dateTime={event.created_at}>
                      {formatTimestamp(event.created_at)}
                    </time>
                  </div>
                  {event.reason && <p className="mt-2 text-muted-foreground">{event.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </section>
      </CardContent>

      <AlertDialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open && working === null) setConfirmAction(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction ? `${actionLabels[confirmAction]} this ${entityType}?` : 'Confirm action'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === 'schedule'
                ? `Publication will be scheduled for ${formatTimestamp(
                    scheduleAt ? new Date(scheduleAt).toISOString() : null
                  )}.`
                : 'This changes customer catalog availability and records a publication event.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={working !== null}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!confirmAction || working !== null}
              onClick={(event) => {
                event.preventDefault();
                if (confirmAction) runAction(confirmAction);
              }}
            >
              {working && confirmAction === working
                ? 'Working…'
                : confirmAction
                  ? `Confirm ${actionLabels[confirmAction]}`
                  : 'Confirm'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
