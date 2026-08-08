import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ApiError, adminApi, type MediaStorageHealthDto } from '@/lib/api';
import { ErrorState, LoadingBlock, StatusBadge } from './adminShared';

export default function MediaStorageHealthPage() {
  const [report, setReport] = useState<MediaStorageHealthDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleanupMsg, setCleanupMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await adminApi.getMediaStorageHealth({ include_orphans: true }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load storage health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function cleanupTemps() {
    setBusy(true);
    setCleanupMsg(null);
    try {
      const result = await adminApi.cleanupStaleTempUploads(86400);
      setCleanupMsg(`Removed ${result.removed} of ${result.scanned} stale temp files`);
      await load();
    } catch (err) {
      setCleanupMsg(err instanceof ApiError ? err.message : 'Cleanup failed');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={6} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!report) return <ErrorState message="No report" />;

  const { summary } = report;

  return (
    <div className="space-y-6" data-testid="media-storage-health-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            <Link to="/admin/tools/upload" className="hover:underline">
              ← Uploads
            </Link>
          </p>
          <h1 className="text-2xl font-serif font-bold mt-1">Media Storage Health</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Read-only consistency check. Orphan files are listed but never auto-deleted.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void load()} disabled={busy}>
            Refresh
          </Button>
          <Button variant="outline" onClick={() => void cleanupTemps()} disabled={busy} data-testid="temp-cleanup">
            Clean stale temps
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <StatusBadge status={report.ok ? 'healthy' : 'attention'} />
        <span className="text-sm text-muted-foreground">
          {report.ok ? 'No missing DB-backed files detected' : 'Issues detected — review sections below'}
        </span>
      </div>
      {cleanupMsg ? <p className="text-sm text-muted-foreground">{cleanupMsg}</p> : null}

      <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        {(
          [
            ['Healthy', summary.healthy],
            ['Missing files', summary.missing_files],
            ['Size mismatches', summary.size_mismatches],
            ['Orphan files', summary.orphan_files],
            ['Duplicate hashes', summary.duplicate_hashes],
            ['Failed probes', summary.failed_probes],
            ['Stuck uploads', summary.stuck_uploads],
            ['Bad paths', summary.bad_paths],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded border border-border p-3 bg-card">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-xl font-semibold">{value}</dd>
          </div>
        ))}
      </dl>

      {(
        [
          ['Missing files', report.missing_files],
          ['Orphan files', report.orphan_files],
          ['Duplicate hashes', report.duplicate_hashes],
          ['Failed probes', report.failed_probes],
          ['Stuck uploads', report.stuck_uploads],
        ] as const
      ).map(([title, rows]) => (
        <section key={title} className="space-y-2">
          <h2 className="font-semibold">{title}</h2>
          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">None</p>
          ) : (
            <ul className="space-y-1 text-xs font-mono border border-border rounded p-3 bg-card max-h-64 overflow-auto">
              {rows.map((row, idx) => (
                <li key={`${title}-${idx}`}>{JSON.stringify(row)}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
