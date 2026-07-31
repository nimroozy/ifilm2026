import { useCallback, useEffect, useState } from 'react';
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
import {
  ApiError,
  adminApi,
  type PlaybackSessionDto,
  type StreamingStatusDto,
} from '@/lib/api';
import { EmptyState, ErrorState, LoadingBlock, StatusBadge } from './adminShared';

const STATUSES = ['active', 'revoked', 'expired'];

export default function PlaybackSessionsPage() {
  const [sessions, setSessions] = useState<PlaybackSessionDto[]>([]);
  const [status, setStatus] = useState<StreamingStatusDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [assetFilter, setAssetFilter] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [list, feature] = await Promise.all([
        adminApi.listPlaybackSessions({
          page: 1,
          page_size: 50,
          status: statusFilter === 'all' ? undefined : statusFilter,
          media_asset_id: assetFilter.trim() || undefined,
        }),
        adminApi.getStreamingStatus().catch(() => null),
      ]);
      setSessions(list.items);
      setStatus(feature);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load playback sessions');
    } finally {
      setLoading(false);
    }
  }, [assetFilter, statusFilter]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  async function revoke(sessionId: string) {
    setBusyId(sessionId);
    setFlash(null);
    try {
      await adminApi.revokePlaybackSession(sessionId);
      setFlash('Session revoked');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Revoke failed');
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingBlock rows={8} />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-6" data-testid="playback-sessions-page">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-serif font-bold">Playback sessions</h1>
          <p className="text-sm text-muted-foreground">
            Protected HLS session inspection and revocation (raw tokens never shown)
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      {status && !status.enabled && (
        <p className="text-sm text-muted-foreground" data-testid="streaming-disabled">
          Local streaming is disabled. Set ENABLE_LOCAL_STREAMING=true and configure
          PLAYBACK_TOKEN_SECRET.
        </p>
      )}

      {status?.enabled && (
        <p className="text-xs text-muted-foreground" data-testid="streaming-principals">
          Supported principals: {status.supported_principals.join(', ')}. {status.subscriber_entitlement}
        </p>
      )}

      {flash && <p className="text-sm text-primary">{flash}</p>}

      <div className="flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
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
        <div className="space-y-1">
          <Label htmlFor="asset-filter">Asset ID</Label>
          <Input
            id="asset-filter"
            value={assetFilter}
            onChange={(e) => setAssetFilter(e.target.value)}
            placeholder="Filter by media asset"
            className="w-[280px]"
          />
        </div>
      </div>

      {sessions.length === 0 ? (
        <EmptyState message="No playback sessions. Create a session for an asset with an active HLS package." />
      ) : (
        <div className="overflow-x-auto border border-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left">
              <tr>
                <th className="p-3 font-medium">Session</th>
                <th className="p-3 font-medium">Asset</th>
                <th className="p-3 font-medium">Package</th>
                <th className="p-3 font-medium">Principal</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium">Expires</th>
                <th className="p-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => (
                <tr key={session.id} className="border-t border-border" data-testid={`session-row-${session.id}`}>
                  <td className="p-3 font-mono text-xs">{session.id.slice(0, 8)}…</td>
                  <td className="p-3 font-mono text-xs">{session.media_asset_id.slice(0, 8)}…</td>
                  <td className="p-3 font-mono text-xs">{session.media_package_id.slice(0, 8)}…</td>
                  <td className="p-3">
                    {session.principal_type}:{session.principal_id}
                  </td>
                  <td className="p-3">
                    <StatusBadge status={session.status} />
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">
                    {session.expires_at ? new Date(session.expires_at).toLocaleString() : '—'}
                  </td>
                  <td className="p-3">
                    {session.status === 'active' ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === session.id}
                        onClick={() => void revoke(session.id)}
                      >
                        Revoke
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
