import { useCallback, useEffect, useState } from 'react';
import { Plus, Search, Trash2 } from 'lucide-react';
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ApiError } from '@/lib/api';
import { cdnApi, type CDNNodeDto, type CDNRouteDto, type RouteLookupDto } from '@/lib/cdnApi';
import { AdminTableCard, EmptyState, ErrorState, LoadingBlock, PageHeader } from '../adminShared';
import { NodeStateBadge, RoleBadge } from './cdnShared';

const STAGE_LABELS: Record<string, string> = {
  preferred_rule: 'Preferred rule',
  next_matching_rule: 'Next matching rule',
  same_branch_cache: 'Same-branch cache',
  default_main: 'Default Main CDN',
  secondary_main: 'Secondary Main CDN',
  central: 'Central iFilm',
};

const emptyForm = { cidr: '', node_id: '', priority: 100, enabled: true, notes: '' };

export default function CDNRoutingPage() {
  const [routes, setRoutes] = useState<CDNRouteDto[]>([]);
  const [nodes, setNodes] = useState<CDNNodeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CDNRouteDto | null>(null);
  const [testIp, setTestIp] = useState('');
  const [lookup, setLookup] = useState<RouteLookupDto | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, n] = await Promise.all([cdnApi.listRoutes(), cdnApi.listNodes()]);
      setRoutes(r);
      setNodes(n);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load routing rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function addRule() {
    setBusy(true);
    setError(null);
    try {
      await cdnApi.createRoute({ cidr: form.cidr.trim(), node_id: form.node_id, priority: Number(form.priority) || 100, enabled: form.enabled, notes: form.notes.trim() || null });
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to add routing rule');
    } finally {
      setBusy(false);
    }
  }

  async function toggle(route: CDNRouteDto, enabled: boolean) {
    try {
      await cdnApi.updateRoute(route.id, { enabled });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to update rule');
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    try {
      await cdnApi.deleteRoute(pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to delete rule');
    }
  }

  async function runLookup() {
    setError(null);
    try {
      setLookup(await cdnApi.lookupRoute(testIp.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Lookup failed');
    }
  }

  if (loading) return <LoadingBlock rows={6} />;
  if (error && routes.length === 0 && nodes.length === 0) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-6" data-testid="cdn-routing-page">
      <PageHeader
        title="CDN Routing"
        description="Subscriber IP prefix → preferred server. Longest prefix wins; equal prefixes use the lower priority number. Ineligible servers fall back to the next matching rule, a same-branch cache, the Main CDN, then central iFilm."
      />
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Add rule</CardTitle>
          <CardDescription>Example: 103.126.4.0/24 → Nimruz Cache.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-5">
          <div className="space-y-1">
            <Label htmlFor="route-cidr">CIDR prefix</Label>
            <Input id="route-cidr" placeholder="103.126.4.0/24" value={form.cidr} onChange={(e) => setForm({ ...form, cidr: e.target.value })} data-testid="route-cidr" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="route-node">Preferred server</Label>
            <Select value={form.node_id} onValueChange={(v) => setForm({ ...form, node_id: v })}>
              <SelectTrigger id="route-node" data-testid="route-node">
                <SelectValue placeholder="Choose server" />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((n) => (
                  <SelectItem key={n.id} value={n.id}>
                    {n.name} ({n.role === 'main' ? 'Main CDN' : 'Cache'})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="route-priority">Priority (lower wins)</Label>
            <Input id="route-priority" type="number" min={0} value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="route-notes">Notes</Label>
            <Input id="route-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="flex items-end gap-3">
            <div className="flex items-center gap-2 pb-2">
              <Switch id="route-enabled" checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
              <Label htmlFor="route-enabled">Enabled</Label>
            </div>
            <Button onClick={addRule} disabled={busy || !form.cidr.trim() || !form.node_id} className="gap-2" data-testid="route-add">
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {routes.length === 0 ? (
        <EmptyState message="No routing rules. Unmatched subscribers use the default Main CDN, then central playback." />
      ) : (
        <AdminTableCard minWidthClassName="min-w-[820px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prefix</TableHead>
                <TableHead>Preferred server</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Notes</TableHead>
                <TableHead>Enabled</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {routes.map((route) => (
                <TableRow key={route.id} data-testid={`route-row-${route.id}`}>
                  <TableCell className="font-mono">{route.cidr}</TableCell>
                  <TableCell>
                    <span className="mr-2">{route.node_name}</span>
                    {route.node_role && <RoleBadge role={route.node_role} />}
                  </TableCell>
                  <TableCell>{route.priority}</TableCell>
                  <TableCell className="max-w-[240px] truncate text-muted-foreground">{route.notes || '—'}</TableCell>
                  <TableCell>
                    <Switch checked={route.enabled} onCheckedChange={(v) => toggle(route, v)} aria-label={`Toggle ${route.cidr}`} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => setPendingDelete(route)} aria-label={`Delete ${route.cidr}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </AdminTableCard>
      )}

      <Card data-testid="route-tester">
        <CardHeader>
          <CardTitle className="text-lg">Routing tester</CardTitle>
          <CardDescription>Shows the matched CIDR, the selected server and the full fallback chain for a client IP.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Input placeholder="103.126.4.55" value={testIp} onChange={(e) => setTestIp(e.target.value)} className="max-w-xs" data-testid="route-test-ip" />
            <Button variant="secondary" onClick={runLookup} disabled={!testIp.trim()} className="gap-2" data-testid="route-test-run">
              <Search className="h-4 w-4" />
              Lookup
            </Button>
          </div>
          {lookup && (
            <div className="space-y-3" data-testid="route-test-result">
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <span className="text-muted-foreground">Client IP:</span> <span className="font-mono">{lookup.client_ip}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Matched CIDR:</span> <span className="font-mono">{lookup.matched_cidr || 'none'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Selected:</span>{' '}
                  <span className="font-medium">{lookup.selected ? `${lookup.selected.name} (${lookup.selected.host})` : 'Central iFilm playback'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Reason:</span> <Badge variant="outline">{STAGE_LABELS[lookup.reason] || lookup.reason}</Badge>
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead>Server</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lookup.chain.map((entry, index) => (
                    <TableRow key={`${entry.stage}-${entry.node_id ?? 'central'}-${index}`}>
                      <TableCell>{STAGE_LABELS[entry.stage] || entry.stage}</TableCell>
                      <TableCell>
                        {entry.node_name}
                        {entry.matched_cidr ? <span className="ml-2 font-mono text-xs text-muted-foreground">{entry.matched_cidr}</span> : null}
                      </TableCell>
                      <TableCell>{entry.role === 'central' ? <Badge variant="outline">CENTRAL</Badge> : <NodeStateBadge state={entry.state} />}</TableCell>
                      <TableCell>
                        <Badge variant={entry.eligible ? 'default' : 'secondary'}>{entry.eligible ? 'eligible' : entry.reason}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {!lookup.edge_routing_enabled && (
                <p className="text-xs text-muted-foreground">Edge routing is disabled (CDN-P1): this decision is informational; players still use central playback.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete routing rule?</AlertDialogTitle>
            <AlertDialogDescription>
              Subscribers in {pendingDelete?.cidr} will fall back to broader rules or the Main CDN. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} data-testid="route-delete-confirm">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
