import { useCallback, useEffect, useState } from 'react';
import { Globe, KeyRound, Plug, RefreshCw, Save, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ApiError, type AdminUserDto } from '@/lib/api';
import { adminApi, type PortalIntegrationDto, type PortalConnectionTestDto } from '@/lib/adminApi';
import { ErrorState, LoadingBlock, PageHeader } from './adminShared';

function hasPerm(admin: AdminUserDto | null, key: string): boolean {
  return (admin?.permissions || []).includes(key);
}

type FormState = {
  enabled: boolean;
  base_url: string;
  api_prefix: string;
  client: string;
  request_source: string;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  entitlement_ttl_seconds: number;
  token: string;
};

function fromDto(dto: PortalIntegrationDto): FormState {
  return {
    enabled: dto.enabled,
    base_url: dto.base_url,
    api_prefix: dto.api_prefix,
    client: dto.client,
    request_source: dto.request_source,
    connect_timeout_seconds: dto.connect_timeout_seconds,
    read_timeout_seconds: dto.read_timeout_seconds,
    entitlement_ttl_seconds: dto.entitlement_ttl_seconds,
    token: '',
  };
}

export default function PortalSettingsPage() {
  const [admin, setAdmin] = useState<AdminUserDto | null>(null);
  const [saved, setSaved] = useState<PortalIntegrationDto | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [lastTest, setLastTest] = useState<PortalConnectionTestDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [replaceToken, setReplaceToken] = useState(false);

  const canManage = hasPerm(admin, 'settings');

  const load = useCallback(async () => {
    setError(null);
    const me = await adminApi.me();
    setAdmin(me);
    if (!hasPerm(me, 'settings')) {
      setLoading(false);
      return;
    }
    const data = await adminApi.getPortalIntegration();
    setSaved(data);
    setForm(fromDto(data));
    setLoading(false);
  }, []);

  useEffect(() => {
    load().catch((err) => {
      setError(err instanceof ApiError ? err.message : 'Failed to load Portal settings');
      setLoading(false);
    });
  }, [load]);

  async function onSave() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Record<string, unknown> = {
        enabled: form.enabled,
        base_url: form.base_url,
        api_prefix: form.api_prefix,
        client: form.client,
        request_source: form.request_source,
        connect_timeout_seconds: form.connect_timeout_seconds,
        read_timeout_seconds: form.read_timeout_seconds,
        entitlement_ttl_seconds: form.entitlement_ttl_seconds,
      };
      if (form.token.trim()) {
        payload.token = form.token.trim();
      }
      const updated = await adminApi.updatePortalIntegration(payload);
      setSaved(updated);
      setForm(fromDto(updated));
      setReplaceToken(false);
      setSuccess('Portal settings saved.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  async function onTest() {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await adminApi.testPortalConnection();
      setLastTest(result);
      await load();
      setSuccess(result.message || (result.ok ? 'Connection test passed.' : 'Connection test failed.'));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connection test failed');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={8} />;

  if (!canManage) {
    return (
      <ErrorState message="You do not have permission to manage Portal integration settings." />
    );
  }

  if (!form || !saved) {
    return <ErrorState message={error || 'Unable to load Portal settings.'} onRetry={load} />;
  }

  const tokenStatus = saved.token_configured ? 'Configured' : 'Not configured';
  const enableBlocked = form.enabled && !saved.token_configured && !form.token.trim();

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-testid="portal-settings-page">
      <PageHeader
        title="Portal Integration"
        description="Configure Mobin Net portal.mns.af Voice AI subscriber authentication. Service tokens are stored encrypted on the server and never returned to the browser."
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      {enableBlocked && (
        <Alert variant="destructive">
          <AlertTitle>Token required</AlertTitle>
          <AlertDescription>
            Portal authentication cannot be enabled without a configured service token. Add a
            token and run Test Connection before enabling.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Globe className="h-5 w-5" />
            Portal Connection
          </CardTitle>
          <CardDescription>Backend-only integration with portal.mns.af Voice AI.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
            <div>
              <Label htmlFor="portal-enabled">Portal Authentication Enabled</Label>
              <p className="text-xs text-muted-foreground">Controls ISP login via portal lookup.</p>
            </div>
            <Switch
              id="portal-enabled"
              checked={form.enabled}
              onCheckedChange={(checked) => setForm({ ...form, enabled: checked })}
              data-testid="portal-enabled-switch"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="portal-base-url">Portal Base URL</Label>
              <Input
                id="portal-base-url"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="portal-api-prefix">API Prefix</Label>
              <Input
                id="portal-api-prefix"
                value={form.api_prefix}
                onChange={(e) => setForm({ ...form, api_prefix: e.target.value })}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <KeyRound className="h-5 w-5" />
            Authentication
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/40 p-3">
            <span className="text-sm text-muted-foreground">Service token status</span>
            <span className="font-medium" data-testid="portal-token-status">
              {tokenStatus}
            </span>
          </div>
          {!replaceToken ? (
            <Button variant="outline" type="button" onClick={() => setReplaceToken(true)}>
              Replace Token
            </Button>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="portal-token">New Service Token</Label>
              <Input
                id="portal-token"
                type="password"
                autoComplete="new-password"
                value={form.token}
                onChange={(e) => setForm({ ...form, token: e.target.value })}
                placeholder="Paste new Voice AI bearer (never shown again)"
                data-testid="portal-token-input"
              />
              <p className="text-xs text-muted-foreground">
                Leave blank when saving other fields to preserve the existing token.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Plug className="h-5 w-5" />
            Client Identification
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="portal-client">Client ID</Label>
            <Input
              id="portal-client"
              value={form.client}
              onChange={(e) => setForm({ ...form, client: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="portal-source">Request Source</Label>
            <Input
              id="portal-source"
              value={form.request_source}
              onChange={(e) => setForm({ ...form, request_source: e.target.value })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Shield className="h-5 w-5" />
            Advanced
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="portal-connect-timeout">Connect Timeout (s)</Label>
            <Input
              id="portal-connect-timeout"
              type="number"
              min={1}
              max={60}
              value={form.connect_timeout_seconds}
              onChange={(e) =>
                setForm({ ...form, connect_timeout_seconds: Number(e.target.value) || 3 })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="portal-read-timeout">Read Timeout (s)</Label>
            <Input
              id="portal-read-timeout"
              type="number"
              min={1}
              max={120}
              value={form.read_timeout_seconds}
              onChange={(e) =>
                setForm({ ...form, read_timeout_seconds: Number(e.target.value) || 5 })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="portal-ttl">Entitlement TTL (s)</Label>
            <Input
              id="portal-ttl"
              type="number"
              min={60}
              value={form.entitlement_ttl_seconds}
              onChange={(e) =>
                setForm({ ...form, entitlement_ttl_seconds: Number(e.target.value) || 900 })
              }
            />
          </div>
        </CardContent>
      </Card>

      <Card data-testid="portal-status-card">
        <CardHeader>
          <CardTitle className="text-lg">Status</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Enabled</span>
            <span>{saved.enabled ? 'Yes' : 'No'}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Token</span>
            <span data-testid="portal-status-token">{tokenStatus}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Last test</span>
            <span>
              {saved.last_test_at
                ? `${saved.last_test_ok ? 'Pass' : 'Fail'} (${saved.last_test_at})`
                : 'Never'}
            </span>
          </div>
          {lastTest && (
            <>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">Portal reachable</span>
                <span>{lastTest.portal_reachable ? 'Yes' : 'No'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">Credential accepted</span>
                <span>{lastTest.credential_accepted ? 'Yes' : 'No'}</span>
              </div>
            </>
          )}
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Last updated</span>
            <span>{saved.updated_at || '—'}</span>
          </div>
          {saved.config_source && (
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Config source</span>
              <span>{saved.config_source}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onSave} disabled={busy || enableBlocked} className="gap-2">
          <Save className="h-4 w-4" />
          Save Changes
        </Button>
        <Button variant="secondary" onClick={onTest} disabled={busy} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Test Connection
        </Button>
      </div>
    </div>
  );
}
