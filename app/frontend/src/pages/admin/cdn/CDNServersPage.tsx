import { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw, Server } from 'lucide-react';
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
import { Textarea } from '@/components/ui/textarea';
import { ApiError } from '@/lib/api';
import { cdnApi, type CDNNodeDto, type CDNNodePayload, type NodeAction, type ProvisionRunDto, type SSHTestDto } from '@/lib/cdnApi';
import { AdminTableCard, EmptyState, ErrorState, LoadingBlock, PageHeader } from '../adminShared';
import CDNNetworkCard from './CDNNetworkCard';
import { KeyValue, NodeBadges, formatAge, formatBytes, formatDate, formatPercent } from './cdnShared';

type FormState = {
  name: string;
  role: 'main' | 'cache';
  host: string;
  ssh_port: number;
  ssh_username: string;
  credential_type: 'password' | 'private_key';
  credential: string;
  branch: string;
  location: string;
  notes: string;
  priority: number;
  serve_base_url: string;
  storage_limit_gb: number;
  high_watermark_pct: number;
  low_watermark_pct: number;
  is_default: boolean;
  enabled: boolean;
};

const blankForm: FormState = {
  name: '',
  role: 'cache',
  host: '',
  ssh_port: 22,
  ssh_username: 'root',
  credential_type: 'password',
  credential: '',
  branch: '',
  location: '',
  notes: '',
  priority: 100,
  serve_base_url: '',
  storage_limit_gb: 500,
  high_watermark_pct: 90,
  low_watermark_pct: 80,
  is_default: false,
  enabled: true,
};

function toForm(node: CDNNodeDto): FormState {
  return {
    name: node.name,
    role: node.role,
    host: node.host,
    ssh_port: node.ssh_port,
    ssh_username: node.ssh_username,
    credential_type: node.credential_type === 'private_key' ? 'private_key' : 'password',
    credential: '',
    branch: node.branch || '',
    location: node.location || '',
    notes: node.notes || '',
    priority: node.priority,
    serve_base_url: node.serve_base_url || '',
    storage_limit_gb: node.cache_limit_bytes ? Math.round(node.cache_limit_bytes / 1024 ** 3) : 0,
    high_watermark_pct: node.high_watermark_pct,
    low_watermark_pct: node.low_watermark_pct,
    is_default: node.is_default,
    enabled: node.enabled,
  };
}

function toPayload(form: FormState): CDNNodePayload {
  const payload: CDNNodePayload = {
    name: form.name.trim(),
    role: form.role,
    host: form.host.trim(),
    ssh_port: Number(form.ssh_port) || 22,
    ssh_username: form.ssh_username.trim(),
    credential_type: form.credential_type,
    branch: form.branch.trim(),
    location: form.location.trim(),
    notes: form.notes.trim(),
    priority: Number(form.priority) || 100,
    serve_base_url: form.serve_base_url.trim(),
    cache_limit_bytes: form.storage_limit_gb > 0 ? Math.round(form.storage_limit_gb * 1024 ** 3) : null,
    high_watermark_pct: Number(form.high_watermark_pct) || 90,
    low_watermark_pct: Number(form.low_watermark_pct) || 80,
    is_default: form.is_default,
    enabled: form.enabled,
  };
  if (form.credential.trim()) payload.credential = form.credential;
  return payload;
}

type PendingAction = { node: CDNNodeDto; action: NodeAction | 'delete' };

const ACTION_COPY: Record<NodeAction | 'delete', { title: string; description: string; destructive?: boolean }> = {
  provision: { title: 'Provision server', description: 'Connects over SSH with the pinned host key, installs the iFilm CDN node on Debian 13, configures the firewall and service, verifies health, then rotates to a generated key.' },
  reprovision: { title: 'Re-provision server', description: 'Runs the full provisioning again. Existing cache contents are preserved. The service restarts.' },
  upgrade: { title: 'Upgrade node software', description: 'Uploads the current node bundle, re-installs configuration and restarts the service.' },
  drain: { title: 'Drain server', description: 'Stops new cache fills and removes the server from routing. Cached objects keep serving until traffic subsides.' },
  undrain: { title: 'Stop draining', description: 'Returns the server to routing.' },
  disable: { title: 'Disable server', description: 'Removes the server from routing and blocks its node API access until re-enabled.', destructive: true },
  enable: { title: 'Enable server', description: 'Allows routing and node API access again.' },
  'clear-cache': { title: 'Clear cache', description: 'Stops the node service, deletes every cached object, and restarts. Subscribers will refill from origin.', destructive: true },
  delete: { title: 'Delete server', description: 'Removes the server, its credentials and routing rules from central. The remote machine is not modified.', destructive: true },
};

export default function CDNServersPage() {
  const [nodes, setNodes] = useState<CDNNodeDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<'new' | CDNNodeDto | null>(null);
  const [form, setForm] = useState<FormState>(blankForm);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<ProvisionRunDto[]>([]);
  const [sshResult, setSshResult] = useState<SSHTestDto | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [tokenReveal, setTokenReveal] = useState<string | null>(null);

  const selected = nodes.find((n) => n.id === selectedId) || null;

  const load = useCallback(async () => {
    try {
      const list = await cdnApi.listNodes();
      setNodes(list);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load CDN servers');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRuns = useCallback(async (id: string) => {
    try {
      setRuns(await cdnApi.provisionRuns(id));
    } catch {
      setRuns([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (selectedId) void loadRuns(selectedId);
  }, [selectedId, loadRuns]);

  function startNew() {
    setForm(blankForm);
    setEditing('new');
    setSshResult(null);
  }

  function startEdit(node: CDNNodeDto) {
    setForm(toForm(node));
    setEditing(node);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (editing === 'new') {
        const created = await cdnApi.createNode(toPayload(form));
        if (created.heartbeat_token) setTokenReveal(created.heartbeat_token);
        setSelectedId(created.node.id);
        setNotice(`Server ${created.node.name} added. Run Test SSH, pin the host key, then Provision.`);
      } else if (editing) {
        await cdnApi.updateNode(editing.id, toPayload(form));
        setNotice('Server updated.');
      }
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save server');
    } finally {
      setBusy(false);
    }
  }

  async function testSsh(node: CDNNodeDto) {
    setBusy(true);
    setError(null);
    setSshResult(null);
    try {
      const result = await cdnApi.testSsh(node.id);
      setSshResult(result);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Test SSH failed');
    } finally {
      setBusy(false);
    }
  }

  async function pinObserved(node: CDNNodeDto, fingerprint: string) {
    setBusy(true);
    setError(null);
    try {
      await cdnApi.pinHostKey(node.id, fingerprint);
      setNotice(`Host key pinned for ${node.name}.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to pin host key');
    } finally {
      setBusy(false);
    }
  }

  async function runPending() {
    if (!pending) return;
    const { node, action } = pending;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (action === 'delete') {
        await cdnApi.deleteNode(node.id);
        if (selectedId === node.id) setSelectedId(null);
        setNotice(`Server ${node.name} deleted.`);
      } else {
        await cdnApi.nodeAction(node.id, action);
        setNotice(`${ACTION_COPY[action].title} requested for ${node.name}.`);
      }
      setPending(null);
      await load();
      if (selectedId && action !== 'delete') await loadRuns(selectedId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed');
      setPending(null);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={6} />;
  if (error && nodes.length === 0 && !editing) return <ErrorState message={error} onRetry={load} />;

  const canProvision = (node: CDNNodeDto) => Boolean(node.ssh_host_key_fingerprint) && (node.credential_configured || node.managed_key_configured);

  return (
    <div className="space-y-6" data-testid="cdn-servers-page">
      <PageHeader
        title="CDN Servers"
        description="Main CDN origins and branch caches. Add a fresh Debian 13 server, test SSH, pin its host key, then provision automatically."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={load} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <Button size="sm" onClick={startNew} className="gap-2" data-testid="cdn-add-server">
              <Plus className="h-4 w-4" />
              Add server
            </Button>
          </>
        }
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert>
          <AlertTitle>Done</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      {tokenReveal && (
        <Alert data-testid="cdn-token-reveal">
          <AlertTitle>One-time node token</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>Provisioning installs this automatically. Copy it only if you install the node by hand; it will not be shown again.</p>
            <code className="block break-all rounded bg-muted p-2 font-mono text-xs">{tokenReveal}</code>
            <Button size="sm" variant="outline" onClick={() => setTokenReveal(null)}>
              Dismiss
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <CDNNetworkCard />

      {editing && (
        <Card data-testid="cdn-server-form">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Server className="h-5 w-5" />
              {editing === 'new' ? 'Add Debian 13 server' : `Edit ${editing.name}`}
            </CardTitle>
            <CardDescription>SSH credentials are encrypted at rest and never shown again. Leave the credential blank when editing to keep the stored one.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="node-name">Name</Label>
              <Input id="node-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="node-name" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-role">Role</Label>
              <Select value={form.role} onValueChange={(v: 'main' | 'cache') => setForm({ ...form, role: v, is_default: v === 'main' ? form.is_default : false })}>
                <SelectTrigger id="node-role" data-testid="node-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="main">MAIN_CDN</SelectItem>
                  <SelectItem value="cache">CACHE</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-host">IP or hostname</Label>
              <Input id="node-host" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="103.126.4.10" data-testid="node-host" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-serve-url">Serve base URL (used in CDN-P2)</Label>
              <Input id="node-serve-url" value={form.serve_base_url} onChange={(e) => setForm({ ...form, serve_base_url: e.target.value })} placeholder="https://cache-nimruz.example:8443" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-ssh-user">SSH username</Label>
              <Input id="node-ssh-user" value={form.ssh_username} onChange={(e) => setForm({ ...form, ssh_username: e.target.value })} data-testid="node-ssh-username" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-ssh-port">SSH port</Label>
              <Input id="node-ssh-port" type="number" min={1} max={65535} value={form.ssh_port} onChange={(e) => setForm({ ...form, ssh_port: Number(e.target.value) })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-cred-type">Bootstrap credential type</Label>
              <Select value={form.credential_type} onValueChange={(v: 'password' | 'private_key') => setForm({ ...form, credential_type: v })}>
                <SelectTrigger id="node-cred-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="password">Password (rotated to a generated key after provisioning)</SelectItem>
                  <SelectItem value="private_key">Private key</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-credential">{form.credential_type === 'password' ? 'SSH password' : 'SSH private key (PEM)'}</Label>
              {form.credential_type === 'password' ? (
                <Input id="node-credential" type="password" autoComplete="new-password" value={form.credential} onChange={(e) => setForm({ ...form, credential: e.target.value })} data-testid="node-credential" />
              ) : (
                <Textarea id="node-credential" value={form.credential} onChange={(e) => setForm({ ...form, credential: e.target.value })} rows={4} data-testid="node-credential" />
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-branch">Branch / site</Label>
              <Input id="node-branch" value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })} placeholder="nimruz" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-location">Location</Label>
              <Input id="node-location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Zaranj" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-storage">Storage / cache limit (GB)</Label>
              <Input id="node-storage" type="number" min={1} value={form.storage_limit_gb} onChange={(e) => setForm({ ...form, storage_limit_gb: Number(e.target.value) })} data-testid="node-storage-limit" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-priority">Priority (lower wins)</Label>
              <Input id="node-priority" type="number" min={0} value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-high">High watermark %</Label>
              <Input id="node-high" type="number" min={1} max={100} value={form.high_watermark_pct} onChange={(e) => setForm({ ...form, high_watermark_pct: Number(e.target.value) })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="node-low">Low watermark %</Label>
              <Input id="node-low" type="number" min={1} max={100} value={form.low_watermark_pct} onChange={(e) => setForm({ ...form, low_watermark_pct: Number(e.target.value) })} />
            </div>
            <div className="space-y-1 md:col-span-2">
              <Label htmlFor="node-notes">Notes</Label>
              <Textarea id="node-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} />
            </div>
            <div className="flex items-center gap-2">
              <Switch id="node-enabled" checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
              <Label htmlFor="node-enabled">Enabled</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="node-default" checked={form.is_default} disabled={form.role !== 'main'} onCheckedChange={(v) => setForm({ ...form, is_default: v })} />
              <Label htmlFor="node-default">Default Main CDN</Label>
            </div>
            <div className="flex gap-2 md:col-span-2">
              <Button onClick={save} disabled={busy || !form.name.trim() || !form.host.trim()} data-testid="node-save">
                {editing === 'new' ? 'Save server' : 'Save changes'}
              </Button>
              <Button variant="ghost" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {nodes.length === 0 && !editing ? (
        <EmptyState message="No CDN servers yet. Add a fresh Debian 13 server to get started." />
      ) : (
        <AdminTableCard minWidthClassName="min-w-[960px]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Server</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Branch</TableHead>
                <TableHead>Heartbeat</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Cache</TableHead>
                <TableHead>Hit ratio</TableHead>
                <TableHead>Provisioning</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {nodes.map((node) => (
                <TableRow key={node.id} data-testid={`cdn-node-row-${node.id}`} className={selectedId === node.id ? 'bg-muted/40' : undefined}>
                  <TableCell>
                    <button type="button" className="text-left font-medium underline-offset-2 hover:underline" onClick={() => setSelectedId(node.id)} data-testid={`cdn-node-select-${node.id}`}>
                      {node.name}
                    </button>
                    <div className="text-xs text-muted-foreground">
                      {node.host}:{node.ssh_port} · {node.ssh_username}
                    </div>
                  </TableCell>
                  <TableCell>
                    <NodeBadges node={node} />
                  </TableCell>
                  <TableCell>{node.branch || node.location || '—'}</TableCell>
                  <TableCell>{formatAge(node.heartbeat_age_seconds)}</TableCell>
                  <TableCell className="font-mono text-xs">{node.software_version || '—'}</TableCell>
                  <TableCell className="text-xs">
                    {formatBytes(node.cache_used_bytes)} / {formatBytes(node.cache_limit_bytes)}
                    <div className="text-muted-foreground">{formatPercent(node.cache_utilization_pct)}</div>
                  </TableCell>
                  <TableCell>{formatPercent(node.hit_rate)}</TableCell>
                  <TableCell>
                    <Badge variant={node.provision_status === 'ready' ? 'default' : node.provision_status === 'failed' ? 'destructive' : 'secondary'}>{node.provision_status}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      <Button size="sm" variant="outline" onClick={() => startEdit(node)}>
                        Edit
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setSelectedId(node.id)}>
                        Details
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </AdminTableCard>
      )}

      {selected && (
        <Card data-testid="cdn-node-detail">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-lg">
              <span className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                {selected.name}
              </span>
              <NodeBadges node={selected} />
            </CardTitle>
            <CardDescription>
              {selected.host}:{selected.ssh_port} · {selected.role_label} · priority {selected.priority}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex flex-wrap gap-2" data-testid="cdn-node-actions">
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => testSsh(selected)} data-testid="cdn-action-test-ssh">
                Test SSH
              </Button>
              <Button size="sm" disabled={busy || !canProvision(selected)} onClick={() => setPending({ node: selected, action: selected.provision_status === 'ready' ? 'reprovision' : 'provision' })} data-testid="cdn-action-provision">
                {selected.provision_status === 'ready' ? 'Re-provision' : 'Provision'}
              </Button>
              <Button size="sm" variant="outline" disabled={busy || selected.provision_status !== 'ready'} onClick={() => setPending({ node: selected, action: 'upgrade' })}>
                Upgrade
              </Button>
              {selected.draining ? (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending({ node: selected, action: 'undrain' })}>
                  Undrain
                </Button>
              ) : (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending({ node: selected, action: 'drain' })}>
                  Drain
                </Button>
              )}
              {selected.enabled ? (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending({ node: selected, action: 'disable' })} data-testid="cdn-action-disable">
                  Disable
                </Button>
              ) : (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending({ node: selected, action: 'enable' })}>
                  Enable
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={busy || selected.provision_status !== 'ready'} onClick={() => setPending({ node: selected, action: 'clear-cache' })}>
                Clear Cache
              </Button>
              <Button size="sm" variant="destructive" disabled={busy} onClick={() => setPending({ node: selected, action: 'delete' })} data-testid="cdn-action-delete">
                Delete
              </Button>
            </div>

            {!selected.ssh_host_key_fingerprint && (
              <Alert>
                <AlertTitle>Host key not pinned</AlertTitle>
                <AlertDescription>Run Test SSH, verify the fingerprint with the server owner, then pin it. Provisioning refuses unpinned or changed host keys.</AlertDescription>
              </Alert>
            )}

            {sshResult && (
              <Card data-testid="cdn-ssh-result">
                <CardHeader>
                  <CardTitle className="text-base">Test SSH result</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <KeyValue label="Result" value={<Badge variant={sshResult.ok ? 'default' : 'destructive'}>{sshResult.ok ? 'OK' : sshResult.code}</Badge>} />
                  <KeyValue label="Detail" value={sshResult.detail} />
                  {sshResult.host_key_fingerprint && (
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span className="text-muted-foreground">Observed host key</span>
                      <span className="font-mono text-xs" data-testid="cdn-ssh-fingerprint">{sshResult.host_key_fingerprint}</span>
                      {sshResult.host_key_fingerprint !== selected.ssh_host_key_fingerprint && (
                        <Button size="sm" variant="outline" disabled={busy} onClick={() => pinObserved(selected, sshResult.host_key_fingerprint!)} data-testid="cdn-pin-host-key">
                          Pin this host key
                        </Button>
                      )}
                    </div>
                  )}
                  <KeyValue label="OS" value={sshResult.os_release || '—'} />
                  <KeyValue label="Debian 13" value={sshResult.debian13 === undefined ? '—' : sshResult.debian13 ? 'Yes' : 'No'} />
                  <KeyValue label="Privileged (root/sudo)" value={sshResult.privileged === undefined ? '—' : sshResult.privileged ? 'Yes' : 'No'} />
                  <KeyValue label="Disk free" value={formatBytes(sshResult.disk_free_bytes)} />
                </CardContent>
              </Card>
            )}

            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Status</h3>
                <KeyValue label="State" value={selected.state} />
                <KeyValue label="Provisioning" value={selected.provision_status} />
                <KeyValue label="Provisioned at" value={formatDate(selected.provisioned_at)} />
                <KeyValue label="Last heartbeat" value={`${formatAge(selected.heartbeat_age_seconds)} (${formatDate(selected.last_heartbeat_at)})`} />
                <KeyValue label="Software version" value={selected.software_version || '—'} mono />
                <KeyValue label="OS" value={selected.os_release || '—'} />
                <KeyValue label="Last error" value={selected.last_error ? `${selected.last_error} (${formatDate(selected.last_error_at)})` : '—'} />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Capacity</h3>
                <KeyValue label="Total disk" value={formatBytes(selected.disk_total_bytes)} />
                <KeyValue label="Used disk" value={formatBytes(selected.disk_used_bytes)} />
                <KeyValue label="Free disk" value={formatBytes(selected.disk_free_bytes)} />
                <KeyValue label="Configured cache limit" value={formatBytes(selected.cache_limit_bytes)} />
                <KeyValue label="Cache utilisation" value={`${formatBytes(selected.cache_used_bytes)} (${formatPercent(selected.cache_utilization_pct)})`} />
                <KeyValue label="Watermarks" value={`${selected.high_watermark_pct}% high · ${selected.low_watermark_pct}% low`} />
                <KeyValue label="Cached objects / titles" value={`${selected.cached_objects} / ${selected.cached_titles}`} />
                <KeyValue label="Hits / misses" value={`${selected.cache_hits} / ${selected.cache_misses} (${formatPercent(selected.hit_rate)})`} />
                <KeyValue label="Bandwidth" value={formatBytes(selected.bandwidth_bytes)} />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Access</h3>
                <KeyValue label="Bootstrap credential" value={selected.credential_configured ? `stored (${selected.credential_type})` : selected.managed_key_configured ? 'retired' : 'missing'} />
                <KeyValue label="Managed key" value={selected.managed_key_configured ? selected.managed_key_fingerprint || 'installed' : 'not yet installed'} mono />
                <KeyValue label="Pinned host key" value={selected.ssh_host_key_fingerprint || 'not pinned'} mono />
                <KeyValue label="Node token" value={selected.heartbeat_token_configured ? 'issued (hash stored)' : 'none'} />
                <KeyValue label="Serve base URL" value={selected.serve_base_url || '—'} mono />
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">Notes</h3>
                <p className="text-sm text-muted-foreground">{selected.notes || '—'}</p>
              </div>
            </div>

            <div className="space-y-2" data-testid="cdn-provision-runs">
              <h3 className="text-sm font-semibold">Provisioning runs</h3>
              {runs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No runs yet.</p>
              ) : (
                runs.slice(0, 5).map((run) => (
                  <details key={run.id} className="rounded-md border border-border p-2 text-sm">
                    <summary className="flex cursor-pointer flex-wrap items-center gap-2">
                      <Badge variant={run.status === 'completed' ? 'default' : run.status === 'failed' ? 'destructive' : 'secondary'}>{run.status}</Badge>
                      <span className="font-medium">{run.action}</span>
                      <span className="text-muted-foreground">step {run.step || '—'} · attempt {run.attempt}</span>
                      {run.error_code && <Badge variant="outline">{run.error_code}</Badge>}
                      <span className="ml-auto text-xs text-muted-foreground">{formatDate(run.created_at)}</span>
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 font-mono text-xs">{run.log}</pre>
                  </details>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent data-testid="cdn-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{pending ? `${ACTION_COPY[pending.action].title}: ${pending.node.name}` : ''}</AlertDialogTitle>
            <AlertDialogDescription>{pending ? ACTION_COPY[pending.action].description : ''}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={runPending} data-testid="cdn-confirm-action">
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
