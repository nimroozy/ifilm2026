import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ApiError, adminApi, type ProcessingJobDto, type ProcessingStatusDto } from '@/lib/api';
import {
  AdminTableCard,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  StatusBadge,
} from './adminShared';

const STATUSES = ['queued', 'running', 'retry_wait', 'completed', 'failed', 'cancelled'];

export default function MediaProcessingJobsPage() {
  const [jobs, setJobs] = useState<ProcessingJobDto[]>([]);
  const [status, setStatus] = useState<ProcessingStatusDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [jobType, setJobType] = useState<string>('all');
  const [assetFilter, setAssetFilter] = useState('');

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, feature] = await Promise.all([
        adminApi.listProcessingJobs({
          page: 1,
          page_size: 50,
          status: statusFilter === 'all' ? undefined : statusFilter,
          job_type: jobType === 'all' ? undefined : jobType,
          media_asset_id: assetFilter.trim() || undefined,
        }),
        adminApi.getProcessingStatus().catch(() => null),
      ]);
      setJobs(list.items);
      setStatus(feature);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load processing jobs');
    } finally {
      setLoading(false);
    }
  }, [assetFilter, jobType, statusFilter]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    const active = jobs.some((j) => !['completed', 'failed', 'cancelled'].includes(j.status));
    if (!active) return;
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, [jobs, load]);

  if (loading) return <LoadingBlock rows={8} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;

  return (
    <div className="min-w-0 max-w-full space-y-6" data-testid="processing-jobs-page">
      <PageHeader
        title="Media processing"
        description="Probe and HLS encode jobs for completed uploads"
        actions={
          <Button variant="outline" size="sm" className="shrink-0" onClick={() => void load()}>
            Refresh
          </Button>
        }
      />

      {status && !status.enabled && (
        <p className="text-sm text-muted-foreground" data-testid="processing-disabled">
          Processing is disabled. Set ENABLE_MEDIA_PROCESSING=true and run the media-processing worker.
        </p>
      )}

      <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-3">
        <div className="min-w-0">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label>Job type</Label>
          <Select value={jobType} onValueChange={setJobType}>
            <SelectTrigger>
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="probe">probe</SelectItem>
              <SelectItem value="encode_hls">encode_hls</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label>Media asset ID</Label>
          <Input
            value={assetFilter}
            onChange={(e) => setAssetFilter(e.target.value)}
            placeholder="Filter by asset UUID"
            className="w-full max-w-full"
          />
        </div>
      </div>

      {jobs.length === 0 ? (
        <EmptyState message="No jobs yet. Queue a probe from a media asset detail page." />
      ) : (
        <AdminTableCard minWidthClassName="min-w-[640px]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-card text-left">
              <tr>
                <th className="p-3">Job</th>
                <th className="p-3">File</th>
                <th className="hidden p-3 md:table-cell">Type</th>
                <th className="p-3">Status</th>
                <th className="p-3">Progress</th>
                <th className="hidden p-3 lg:table-cell">Attempts</th>
                <th className="hidden p-3 xl:table-cell">Worker</th>
                <th className="hidden p-3 lg:table-cell">Error</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-t border-border" data-testid="processing-job-row">
                  <td className="p-3 font-mono text-xs">
                    <Link className="hover:underline" to={`/admin/media/${job.media_asset_id}`}>
                      {job.id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="max-w-[10rem] truncate p-3" title={job.media_asset?.original_filename || undefined}>
                    {job.media_asset?.original_filename || job.media_asset_id.slice(0, 8)}
                  </td>
                  <td className="hidden p-3 md:table-cell">{job.job_type}</td>
                  <td className="p-3">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="p-3">
                    {job.progress_percent}% {job.current_step ? `· ${job.current_step}` : ''}
                  </td>
                  <td className="hidden p-3 lg:table-cell">
                    {job.attempt_count}/{job.max_attempts}
                  </td>
                  <td className="hidden p-3 font-mono text-xs xl:table-cell">{job.worker_id || '—'}</td>
                  <td className="hidden max-w-[14rem] truncate p-3 text-destructive lg:table-cell">
                    {job.error_message || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AdminTableCard>
      )}
    </div>
  );
}
