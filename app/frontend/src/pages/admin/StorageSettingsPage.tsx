import { useCallback, useEffect, useState } from 'react';
import { Cloud, KeyRound, RefreshCw, Save, ShieldCheck } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { ApiError } from '@/lib/api';
import { cdnApi, type StorageProvider, type StorageSettingsDto, type StorageTestDto } from '@/lib/cdnApi';
import { ErrorState, LoadingBlock, PageHeader } from './adminShared';
import { KeyValue, formatDate } from './cdn/cdnShared';

type FormState = {
  enabled: boolean;
  provider: StorageProvider;
  endpoint_url: string;
  account_id: string;
  bucket: string;
  region: string;
  object_key_prefix: string;
  access_key_id: string;
  secret_access_key: string;
};

function fromDto(dto: StorageSettingsDto): FormState {
  return {
    enabled: dto.enabled,
    provider: dto.provider || 'cloudflare_r2',
    endpoint_url: dto.endpoint_url || '',
    account_id: dto.account_id || '',
    bucket: dto.bucket || '',
    region: dto.region || 'auto',
    object_key_prefix: dto.object_key_prefix || 'ifilm',
    access_key_id: '',
    secret_access_key: '',
  };
}

function yesNo(value?: boolean | null): string {
  if (value === null || value === undefined) return '—';
  return value ? 'Yes' : 'No';
}

export default function StorageSettingsPage() {
  const [saved, setSaved] = useState<StorageSettingsDto | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [replaceSecret, setReplaceSecret] = useState(false);
  const [lastTest, setLastTest] = useState<StorageTestDto | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const data = await cdnApi.getStorage();
    setSaved(data);
    setForm(fromDto(data));
    setLoading(false);
  }, []);

  useEffect(() => {
    load().catch((err) => {
      setError(err instanceof ApiError ? err.message : 'Failed to load storage settings');
      setLoading(false);
    });
  }, [load]);

  async function onSave() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = {
        enabled: form.enabled,
        provider: form.provider,
        endpoint_url: form.endpoint_url.trim(),
        account_id: form.account_id.trim(),
        bucket: form.bucket.trim(),
        region: form.region.trim() || 'auto',
        object_key_prefix: form.object_key_prefix.trim() || 'ifilm',
        ...(form.access_key_id.trim() && form.secret_access_key.trim()
          ? { access_key_id: form.access_key_id.trim(), secret_access_key: form.secret_access_key.trim() }
          : {}),
      };
      const updated = await cdnApi.updateStorage(payload);
      setSaved(updated);
      setForm(fromDto(updated));
      setReplaceSecret(false);
      setSuccess('Storage settings saved. Secrets are encrypted at rest and never returned.');
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
      const result = await cdnApi.testStorage();
      setLastTest(result);
      setSaved(result.settings);
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connection test failed');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={8} />;
  if (!form || !saved) {
    return <ErrorState message={error || 'Unable to load storage settings. Sign in with the cdn.secrets permission.'} onRetry={load} />;
  }

  const secretEntered = Boolean(form.access_key_id.trim() && form.secret_access_key.trim());
  const enableBlocked = form.enabled && !saved.credentials_configured && !secretEntered;
  const halfSecret = Boolean(form.access_key_id.trim()) !== Boolean(form.secret_access_key.trim());

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-testid="storage-settings-page">
      <PageHeader
        title="Storage / R2"
        description="Optional S3-compatible or Cloudflare R2 object storage used by the central server. Buckets stay private; players never receive storage URLs or credentials."
      />

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {success && (
        <Alert>
          <AlertTitle>Done</AlertTitle>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}
      {enableBlocked && (
        <Alert variant="destructive">
          <AlertTitle>Credentials required</AlertTitle>
          <AlertDescription>Storage cannot be enabled until an access key and secret key are saved.</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Cloud className="h-5 w-5" />
            Connection
          </CardTitle>
          <CardDescription>Endpoint and bucket used for durable media objects.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-4">
            <div>
              <Label htmlFor="storage-enabled">Enabled</Label>
              <p className="text-xs text-muted-foreground">Turn on only after a successful connection test.</p>
            </div>
            <Switch id="storage-enabled" checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} data-testid="storage-enabled-switch" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="storage-provider">Provider</Label>
              <Select value={form.provider} onValueChange={(v: StorageProvider) => setForm({ ...form, provider: v })}>
                <SelectTrigger id="storage-provider" data-testid="storage-provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cloudflare_r2">Cloudflare R2</SelectItem>
                  <SelectItem value="s3_compatible">S3-compatible (MinIO, Ceph, AWS)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="storage-region">Region</Label>
              <Input id="storage-region" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="auto" />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="storage-endpoint">Endpoint URL (https)</Label>
              <Input
                id="storage-endpoint"
                value={form.endpoint_url}
                onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                placeholder="https://ACCOUNT_ID.r2.cloudflarestorage.com"
                data-testid="storage-endpoint"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="storage-bucket">Bucket</Label>
              <Input id="storage-bucket" value={form.bucket} onChange={(e) => setForm({ ...form, bucket: e.target.value })} data-testid="storage-bucket" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="storage-prefix">Object key prefix</Label>
              <Input id="storage-prefix" value={form.object_key_prefix} onChange={(e) => setForm({ ...form, object_key_prefix: e.target.value })} placeholder="ifilm" />
            </div>
            {form.provider === 'cloudflare_r2' && (
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="storage-account">Account ID (optional)</Label>
                <Input id="storage-account" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} autoComplete="off" />
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <KeyRound className="h-5 w-5" />
            Credentials
          </CardTitle>
          <CardDescription>Encrypted with the server integration key. Leave blank to keep the existing secret.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/40 p-3">
            <span className="text-sm text-muted-foreground">Secret status</span>
            <span className="font-medium" data-testid="storage-secret-status">
              {saved.credentials_configured ? 'Configured' : 'Not configured'}
            </span>
          </div>
          {!replaceSecret && saved.credentials_configured ? (
            <Button variant="outline" type="button" onClick={() => setReplaceSecret(true)} data-testid="storage-replace-secret">
              Replace Secret
            </Button>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="storage-access-key">Access Key ID</Label>
                <Input
                  id="storage-access-key"
                  type="password"
                  autoComplete="new-password"
                  value={form.access_key_id}
                  onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
                  data-testid="storage-access-key"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="storage-secret-key">Secret Access Key</Label>
                <Input
                  id="storage-secret-key"
                  type="password"
                  autoComplete="new-password"
                  value={form.secret_access_key}
                  onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })}
                  data-testid="storage-secret-key"
                />
              </div>
              {halfSecret && (
                <p className="text-xs text-destructive sm:col-span-2">Enter both the access key and the secret key to replace credentials.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card data-testid="storage-status-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ShieldCheck className="h-5 w-5" />
            Status
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          <KeyValue label="Configured" value={saved.credentials_configured ? 'Yes' : 'No'} />
          <KeyValue label="Enabled" value={saved.enabled ? 'Yes' : 'No'} />
          <KeyValue label="Reachable" value={yesNo(lastTest?.reachable ?? saved.last_test_reachable)} />
          <KeyValue label="Bucket accessible" value={yesNo(lastTest?.bucket_accessible ?? saved.last_test_bucket_accessible)} />
          <KeyValue label="Last tested" value={formatDate(lastTest?.tested_at ?? saved.last_test_at)} />
          <KeyValue
            label="Last result"
            value={
              saved.last_test_at || lastTest ? (
                <span data-testid="storage-last-result">
                  {(lastTest?.ok ?? saved.last_test_ok) ? 'Pass' : 'Fail'}
                  {lastTest?.message || saved.last_test_message ? ` — ${lastTest?.message || saved.last_test_message}` : ''}
                </span>
              ) : (
                'Never tested'
              )
            }
          />
          <KeyValue label="Last updated" value={formatDate(saved.updated_at)} />
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Button onClick={onSave} disabled={busy || enableBlocked || halfSecret} className="gap-2" data-testid="storage-save">
          <Save className="h-4 w-4" />
          Save
        </Button>
        <Button variant="secondary" onClick={onTest} disabled={busy || !saved.credentials_configured} className="gap-2" data-testid="storage-test">
          <RefreshCw className="h-4 w-4" />
          Test Connection
        </Button>
      </div>
    </div>
  );
}
