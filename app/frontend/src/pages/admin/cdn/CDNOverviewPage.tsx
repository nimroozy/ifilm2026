import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { cdnApi, type CDNOverviewDto } from '@/lib/cdnApi';
import { ErrorState, LoadingBlock, PageHeader } from '../adminShared';
import { KeyValue, NodeStateBadge, StatTile, formatBytes, formatDate, formatPercent } from './cdnShared';

export default function CDNOverviewPage() {
  const [data, setData] = useState<CDNOverviewDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setData(await cdnApi.overview());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load CDN overview');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingBlock rows={6} />;
  if (!data) return <ErrorState message={error || 'Unable to load CDN overview.'} onRetry={load} />;

  const { totals, storage, cache, flags, main_cdn: mainCdn } = data;

  return (
    <div className="space-y-6" data-testid="cdn-overview-page">
      <PageHeader
        title="CDN Overview"
        description="Main CDN origins and branch caches managed from central. Customer playback always falls back to central iFilm."
        actions={
          <Button variant="outline" size="sm" onClick={load} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {flags.enable_cdn_edge_routing ? null : (
        <Alert data-testid="cdn-edge-routing-notice">
          <AlertTitle>Edge playback not enabled</AlertTitle>
          <AlertDescription>
            CDN-P1 manages servers, routing rules and caches. Customer playback continues to use{' '}
            <code className="font-mono text-xs">{flags.customer_playback_route}</code> until CDN-P2 enables edge routing.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total nodes" value={totals.nodes} hint={`${totals.main_nodes} main · ${totals.cache_nodes} cache`} testId="cdn-stat-nodes" />
        <StatTile label="Online" value={totals.online} hint={`${totals.offline} offline · ${totals.draining} draining`} testId="cdn-stat-online" />
        <StatTile label="Cache hit ratio" value={formatPercent(cache.hit_rate)} hint={`${cache.hits} hits · ${cache.misses} misses`} testId="cdn-stat-hit-ratio" />
        <StatTile label="Routing rules" value={totals.routes} hint={`${totals.routes_enabled} enabled`} testId="cdn-stat-routes" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Main CDN</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <KeyValue label="Status" value={mainCdn.default_node ? <NodeStateBadge state={mainCdn.status} /> : <Badge variant="destructive">Not configured</Badge>} />
            <KeyValue label="Default node" value={mainCdn.default_node ? `${mainCdn.default_node.name} (${mainCdn.default_node.host})` : '—'} />
            <KeyValue label="Secondary mains online" value={mainCdn.secondary_online} />
            <KeyValue label="Final fallback" value="central iFilm playback (always)" />
            <KeyValue label="Provisioning" value={`${totals.provisioning} running · ${totals.failed} failed · ${totals.disabled} disabled`} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">CDN storage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <KeyValue label="Total disk" value={formatBytes(storage.disk_total_bytes)} />
            <KeyValue label="Used" value={formatBytes(storage.disk_used_bytes)} />
            <KeyValue label="Free" value={formatBytes(storage.disk_free_bytes)} />
            <KeyValue label="Configured cache limit" value={formatBytes(storage.cache_limit_bytes)} />
            <KeyValue label="Cache in use" value={formatBytes(storage.cache_used_bytes)} />
            <KeyValue label="Bandwidth served" value={formatBytes(cache.bandwidth_bytes)} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Feature flags</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          <KeyValue label="Node API (heartbeat + origin)" value={flags.enable_cdn_node_api ? 'Enabled' : 'Disabled'} />
          <KeyValue label="Provisioning worker" value={flags.enable_cdn_provisioning ? 'Enabled' : 'Disabled'} />
          <KeyValue label="Edge routing" value={flags.enable_cdn_edge_routing ? 'Enabled' : `Disabled — ${flags.edge_routing_phase}`} />
          <KeyValue label="Integration secrets key" value={flags.integration_secrets_configured ? 'Configured' : 'Missing'} />
          <KeyValue label="Edge-grant public key" value={flags.edge_grant_public_key_configured ? 'Configured' : 'Not configured'} />
          <KeyValue label="Heartbeat stale after" value={`${flags.heartbeat_stale_seconds}s`} />
        </CardContent>
      </Card>

      <Card data-testid="cdn-recent-failures">
        <CardHeader>
          <CardTitle className="text-lg">Recent provisioning failures (24h)</CardTitle>
        </CardHeader>
        <CardContent>
          {data.recent_provisioning_failures.length === 0 ? (
            <p className="text-sm text-muted-foreground">No failures recorded.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.recent_provisioning_failures.map((run) => (
                <li key={run.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-2">
                  <span>
                    <Link to="/admin/cdn/servers" className="font-medium underline-offset-2 hover:underline">
                      {run.node_name}
                    </Link>{' '}
                    · {run.action} · step <span className="font-mono text-xs">{run.step || '—'}</span>
                  </span>
                  <span className="text-muted-foreground">
                    <Badge variant="destructive">{run.error_code || 'failed'}</Badge> {formatDate(run.finished_at || run.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
