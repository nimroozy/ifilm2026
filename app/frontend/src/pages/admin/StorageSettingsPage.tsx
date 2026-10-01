import { useCallback, useEffect, useState } from 'react';
import { Cloud, KeyRound, RefreshCw, Save, ShieldCheck, Trash2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { ApiError } from '@/lib/api';
import {
  adminApi,
  type R2SettingsDto,
  type R2TestDto,
  type StorageProvider,
} from '@/lib/adminApi';
import { ErrorState, LoadingBlock, PageHeader } from './adminShared';

type FormState = {
  enabled: boolean;
  provider: StorageProvider;
  endpoint_url: string;
  account_id: string;
  bucket: string;
  region: string;
  object_key_prefix: string;
  public_base_url: string;
  artwork_cdn_enabled: boolean;
  access_key_id: string;
  secret_access_key: string;
};

function fromDto(dto: R2SettingsDto): FormState {
  return {
    enabled: dto.enabled,
    provider: dto.provider || 'cloudflare_r2',
    endpoint_url: dto.endpoint_url || '',
    account_id: dto.account_id || '',
    bucket: dto.bucket || '',
    region: dto.region || 'auto',
    object_key_prefix: dto.object_key_prefix || 'ifilm',
    public_base_url: dto.public_base_url || '',
    artwork_cdn_enabled: Boolean(dto.artwork_cdn_enabled),
    access_key_id: '',
    secret_access_key: '',
  };
}

function yesNo(value?: boolean | null): string {
  if (value === null || value === undefined) return '—';
  return value ? 'Yes' : 'No';
}

export default function StorageSettingsPage() {
  const [saved, setSaved] = useState<R2SettingsDto | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [replaceSecret, setReplaceSecret] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [lastTest, setLastTest] = useState<R2TestDto | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const data = await adminApi.getStorage();
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
        public_base_url: form.public_base_url.trim(),
        artwork_cdn_enabled: form.artwork_cdn_enabled,
        ...(form.access_key_id.trim() && form.secret_access_key.trim()
          ? {
              access_key_id: form.access_key_id.trim(),
              secret_access_key: form.secret_access_key.trim(),
            }
          : {}),
      };
      const updated = await adminApi.updateStorage(payload);
      setSaved(updated);
      setForm(fromDto(updated));
      setReplaceSecret(false);
      setConfirmRemove(false);
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
      const result = await adminApi.testStorage();
      setLastTest(result);
      setSaved(result.settings);
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connection test failed');
    } finally {
      setBusy(false);
    }
  }

  async function onRemoveCredentials() {
    if (!form || !confirmRemove) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await adminApi.updateStorage({
        enabled: false,
        provider: form.provider,
        endpoint_url: form.endpoint_url.trim(),
        account_id: form.account_id.trim(),
        bucket: form.bucket.trim(),
        region: form.region.trim() || 'auto',
        object_key_prefix: form.object_key_prefix.trim() || 'ifilm',
        public_base_url: form.public_base_url.trim(),
        artwork_cdn_enabled: false,
        remove_credentials: true,
        confirm: true,
      });
      setSaved(updated);
      setForm(fromDto(updated));
      setConfirmRemove(false);
      setReplaceSecret(false);
      setSuccess('Credentials removed. Storage and artwork CDN publishing are disabled.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove credentials');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={8} />;
  if (!form || !saved) {
    return (
      <ErrorState
        message={error || 'Unable to load storage settings. Sign in with settings permission.'}
        onRetry={load}
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-testid="storage-settings-page" dir="ltr" lang="en">
      <PageHeader
        title="Storage / CDN"
        description="Configure Cloudflare R2 or S3-compatible storage for optional hot-tier media and public website artwork. Full movies stay on the protected playback path. Host flag ENABLE_ARTWORK_CDN_SYNC must also be true to publish images."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {success ? (
        <Alert>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            Connection
          </CardTitle>
          <CardDescription>
            Secrets are encrypted at rest and never returned to the browser. Leave secret fields blank
            to keep the stored credentials.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2 flex items-center justify-between rounded-lg border p-4">
            <div>
              <Label>Enable storage connection</Label>
              <p className="mt-1 text-xs text-muted-foreground">
                Hot-tier / private object use. Does not publish artwork by itself.
              </p>
            </div>
            <Switch
              checked={form.enabled}
              onCheckedChange={(v) => setForm({ ...form, enabled: v })}
              data-testid="storage-enabled"
            />
          </div>

          <div className="sm:col-span-2 flex items-center justify-between rounded-lg border p-4">
            <div>
              <Label>Publish artwork to CDN</Label>
              <p className="mt-1 text-xs text-muted-foreground">
                Posters, backdrops, logos, stills (not HLS / private media). Requires a public CDN base
                URL.
              </p>
            </div>
            <Switch
              checked={form.artwork_cdn_enabled}
              onCheckedChange={(v) => setForm({ ...form, artwork_cdn_enabled: v })}
              data-testid="artwork-cdn-enabled"
            />
          </div>

          <div className="sm:col-span-2">
            <Label>Provider</Label>
            <Select
              value={form.provider}
              onValueChange={(v: StorageProvider) => setForm({ ...form, provider: v })}
            >
              <SelectTrigger data-testid="storage-provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="cloudflare_r2">Cloudflare R2</SelectItem>
                <SelectItem value="s3_compatible">S3-compatible</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="sm:col-span-2">
            <Label>Public artwork CDN base URL</Label>
            <Input
              placeholder="https://cdn.example.com"
              value={form.public_base_url}
              onChange={(e) => setForm({ ...form, public_base_url: e.target.value })}
              data-testid="public-base-url"
            />
          </div>

          <div className="sm:col-span-2">
            <Label>HTTPS endpoint</Label>
            <Input
              value={form.endpoint_url}
              onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
              data-testid="storage-endpoint"
            />
          </div>
          <div>
            <Label>Account ID</Label>
            <Input
              value={form.account_id}
              onChange={(e) => setForm({ ...form, account_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Bucket</Label>
            <Input
              value={form.bucket}
              onChange={(e) => setForm({ ...form, bucket: e.target.value })}
              data-testid="storage-bucket"
            />
          </div>
          <div>
            <Label>Region</Label>
            <Input
              value={form.region}
              onChange={(e) => setForm({ ...form, region: e.target.value })}
            />
          </div>
          <div>
            <Label>Object key prefix</Label>
            <Input
              value={form.object_key_prefix}
              onChange={(e) => setForm({ ...form, object_key_prefix: e.target.value })}
              data-testid="object-key-prefix"
            />
          </div>

          <div className="sm:col-span-2 rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4" />
                  Credentials {saved.credentials_configured ? '(configured)' : '(not configured)'}
                </Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Stored secrets are never prefilled. Toggle replace to enter new keys.
                </p>
              </div>
              <Switch
                checked={replaceSecret || !saved.credentials_configured}
                onCheckedChange={(v) => {
                  setReplaceSecret(v);
                  if (!v) setForm({ ...form, access_key_id: '', secret_access_key: '' });
                }}
                data-testid="replace-credentials"
              />
            </div>
            {(replaceSecret || !saved.credentials_configured) && (
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Access key ID</Label>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={form.access_key_id}
                    onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
                    data-testid="access-key-id"
                  />
                </div>
                <div>
                  <Label>Secret access key</Label>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={form.secret_access_key}
                    onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })}
                    data-testid="secret-access-key"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="sm:col-span-2 flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy || !saved.credentials_configured}
              onClick={() => void onTest()}
              data-testid="test-connection"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Test Connection
            </Button>
            <Button type="button" disabled={busy} onClick={() => void onSave()} data-testid="save-storage">
              <Save className="mr-2 h-4 w-4" />
              Save
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Status
          </CardTitle>
          <CardDescription>Last saved connection probe (secret-free).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
          <div>Credentials configured: {yesNo(saved.credentials_configured)}</div>
          <div>Artwork CDN enabled: {yesNo(saved.artwork_cdn_enabled)}</div>
          <div>Last test OK: {yesNo(lastTest?.ok ?? saved.last_test_ok)}</div>
          <div>Endpoint reachable: {yesNo(lastTest?.reachable ?? saved.last_test_reachable)}</div>
          <div>
            Bucket accessible:{' '}
            {yesNo(lastTest?.bucket_accessible ?? saved.last_test_bucket_accessible)}
          </div>
          <div>Last test time: {lastTest?.tested_at || saved.last_test_at || '—'}</div>
          <div className="sm:col-span-2 text-muted-foreground">
            {lastTest?.message || saved.last_test_message || 'No test recorded yet.'}
          </div>
        </CardContent>
      </Card>

      {saved.credentials_configured ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="h-5 w-5" />
              Remove credentials
            </CardTitle>
            <CardDescription>
              Requires explicit confirmation. Disables storage and artwork CDN publishing.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={confirmRemove}
                onChange={(e) => setConfirmRemove(e.target.checked)}
                data-testid="confirm-remove-credentials"
              />
              I understand credentials will be deleted
            </label>
            <Button
              type="button"
              variant="destructive"
              disabled={busy || !confirmRemove}
              onClick={() => void onRemoveCredentials()}
              data-testid="remove-credentials"
            >
              Remove credentials
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
