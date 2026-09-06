import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import { cdnApi, type CDNNodeDto } from '@/lib/cdnApi';
import { AdminTableCard, EmptyState, ErrorState, LoadingBlock, PageHeader } from '../adminShared';
import { NodeBadges, formatAge, formatBytes, formatPercent } from './cdnShared';

export default function CDNHealthPage() {
  const [nodes, setNodes] = useState<CDNNodeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setNodes(await cdnApi.listNodes());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load CDN health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (loading) return <LoadingBlock rows={6} />;
  if (error && nodes.length === 0) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-6" data-testid="cdn-health-page">
      <PageHeader
        title="CDN Health / Metrics"
        description="Live node metrics reported by heartbeats every 30 seconds. Nodes without a fresh heartbeat are excluded from routing."
        actions={
          <Button variant="outline" size="sm" onClick={load} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />
      {nodes.length === 0 ? (
        <EmptyState message="No CDN servers registered yet." />
      ) : (
        <AdminTableCard minWidthClassName="min-w-[1100px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Server</TableHead>
                <TableHead>Heartbeat</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Disk</TableHead>
                <TableHead>Cache utilisation</TableHead>
                <TableHead>Objects</TableHead>
                <TableHead>Hits / misses</TableHead>
                <TableHead>Hit ratio</TableHead>
                <TableHead>Bandwidth</TableHead>
                <TableHead>Last error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {nodes.map((node) => (
                <TableRow key={node.id} data-testid={`cdn-health-row-${node.id}`}>
                  <TableCell>
                    <div className="font-medium">{node.name}</div>
                    <div className="text-xs text-muted-foreground">{node.host}</div>
                    <div className="mt-1">
                      <NodeBadges node={node} />
                    </div>
                  </TableCell>
                  <TableCell>{formatAge(node.heartbeat_age_seconds)}</TableCell>
                  <TableCell className="font-mono text-xs">{node.software_version || '—'}</TableCell>
                  <TableCell>
                    <div className="text-xs">
                      {formatBytes(node.disk_used_bytes)} / {formatBytes(node.disk_total_bytes)}
                    </div>
                    <div className="text-xs text-muted-foreground">free {formatBytes(node.disk_free_bytes)}</div>
                  </TableCell>
                  <TableCell className="min-w-[160px]">
                    <Progress value={Math.min(100, node.cache_utilization_pct ?? 0)} className="h-2" />
                    <div className="mt-1 text-xs text-muted-foreground">
                      {formatBytes(node.cache_used_bytes)} of {formatBytes(node.cache_limit_bytes)} ({formatPercent(node.cache_utilization_pct)})
                    </div>
                  </TableCell>
                  <TableCell>{node.cached_objects}</TableCell>
                  <TableCell>
                    {node.cache_hits} / {node.cache_misses}
                  </TableCell>
                  <TableCell>{formatPercent(node.hit_rate)}</TableCell>
                  <TableCell>{formatBytes(node.bandwidth_bytes)}</TableCell>
                  <TableCell className="max-w-[220px] truncate text-xs text-destructive" title={node.last_error || ''}>
                    {node.last_error || '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </AdminTableCard>
      )}
    </div>
  );
}
