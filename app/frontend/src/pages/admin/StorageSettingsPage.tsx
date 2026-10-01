import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  Cloud,
  KeyRound,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { ApiError } from '@/lib/api';
import {
  adminApi,
  type ArtworkPublishingStatus,
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
  endpoint_override: boolean;
};

function derivedR2Endpoint(accountId: string): string {
  const id = accountId.trim();
  return id ? `https://${id}.r2.cloudflarestorage.com` : '';
}

function fromDto(dto: R2SettingsDto): FormState {
  const accountId = dto.account_id || '';
  const derived = derivedR2Endpoint(accountId);
  const endpoint = dto.endpoint_url || '';
  const isR2 = (dto.provider || 'cloudflare_r2') === 'cloudflare_r2';
  return {
    enabled: dto.enabled,
    provider: dto.provider || 'cloudflare_r2',
    endpoint_url: endpoint,
    account_id: accountId,
    bucket: dto.bucket || '',
    region: dto.region || 'auto',
    object_key_prefix: dto.object_key_prefix || 'ifilm',
    public_base_url: dto.public_base_url || '',
    artwork_cdn_enabled: Boolean(dto.artwork_cdn_enabled),
    access_key_id: '',
    secret_access_key: '',
    endpoint_override: Boolean(isR2 && endpoint && derived && endpoint !== derived),
  };
}

function publishingLabel(status?: ArtworkPublishingStatus | null): string {
  if (status === 'active') return 'ACTIVE';
  if (status === 'blocked_by_server_capability') return 'BLOCKED BY SERVER CAPABILITY';
  return 'DISABLED';
}

function publishingBadgeVariant(
  status?: ArtworkPublishingStatus | null,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'active') return 'default';
  if (status === 'blocked_by_server_capability') return 'destructive';
  return 'secondary';
}

function StatusChip({
  label,
  value,
}: {
  label: string;
  value: boolean | null | undefined;
}) {
  const text = value === null || value === undefined ? '—' : value ? 'Yes' : 'No';
  const variant =
    value === true ? 'default' : value === false ? 'secondary' : 'outline';
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2">
      <span className="text-sm text-muted-foreground">{label}</span>
      <Badge variant={variant} data-testid={`status-chip-${label}`}>
        {text}
      </Badge>
    </div>
  );
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
  const [showAdvanced, setShowAdvanced] = useState(false);
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

  const derivedEndpoint = useMemo(
    () => (form ? derivedR2Endpoint(form.account_id) : ''),
    [form],
  );

  function buildPayload(formState: FormState) {
    const isR2 = formState.provider === 'cloudflare_r2';
    const endpoint = isR2
      ? formState.endpoint_override && formState.endpoint_url.trim()
        ? formState.endpoint_url.trim()
        : derivedR2Endpoint(formState.account_id)
      : formState.endpoint_url.trim();
    return {
      enabled: formState.enabled,
      provider: formState.provider,
      endpoint_url: endpoint,
      account_id: formState.account_id.trim(),
      bucket: formState.bucket.trim(),
      region: isR2 ? 'auto' : formState.region.trim() || 'auto',
      object_key_prefix: formState.object_key_prefix.trim() || 'ifilm',
      public_base_url: formState.public_base_url.trim(),
      artwork_cdn_enabled: formState.artwork_cdn_enabled,
      ...(formState.access_key_id.trim() && formState.secret_access_key.trim()
        ? {
            access_key_id: formState.access_key_id.trim(),
            secret_access_key: formState.secret_access_key.trim(),
          }
        : {}),
    };
  }

  async function onSave() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await adminApi.updateStorage(buildPayload(form));
      setSaved(updated);
      setForm(fromDto(updated));
      setReplaceSecret(false);
      setConfirmRemove(false);
      setSuccess(
        'Settings saved. Secrets stay encrypted and are never returned. Next: Test Connection, then enable artwork publishing.',
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  async function onSaveAndTest() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await adminApi.updateStorage(buildPayload(form));
      setSaved(updated);
      setForm(fromDto(updated));
      setReplaceSecret(false);
      setConfirmRemove(false);
      const result = await adminApi.testStorage();
      setLastTest(result);
      setSaved(result.settings);
      setForm(fromDto(result.settings));
      setSuccess(result.message || 'Saved and tested successfully.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save & Test failed');
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
        ...buildPayload({ ...form, enabled: false, artwork_cdn_enabled: false }),
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

  const isR2 = form.provider === 'cloudflare_r2';
  const publishingStatus = saved.artwork_publishing_status;

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-testid="storage-settings-page" dir="ltr" lang="en">
      <PageHeader
        title="Storage / CDN"
        description="Configure Cloudflare R2 (or S3-compatible) for public website artwork. Full movies stay on the protected playback path. Host capability ENABLE_ARTWORK_CDN_SYNC must also be enabled for publishing to become active."
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
            Recommended flow: enter configuration → Save (or Save &amp; Test) → Test Connection →
            enable artwork publishing. Secrets are encrypted at rest and never returned to the
            browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2 space-y-3 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Artwork CDN</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Public posters, backdrops, logos, and stills only. Does not enable private/hot-tier
                movie storage.
              </p>
            </div>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="artwork-cdn-enabled">Publish public artwork through CDN</Label>
              <Switch
                id="artwork-cdn-enabled"
                checked={form.artwork_cdn_enabled}
                onCheckedChange={(v) => setForm({ ...form, artwork_cdn_enabled: v })}
                data-testid="artwork-cdn-enabled"
              />
            </div>
          </div>

          <div className="sm:col-span-2 space-y-3 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">Object storage / hot tier</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Optional private/hot-tier object storage. Artwork publishing does not require this
                toggle.
              </p>
            </div>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="storage-enabled">Enable private/hot-tier object storage</Label>
              <Switch
                id="storage-enabled"
                checked={form.enabled}
                onCheckedChange={(v) => setForm({ ...form, enabled: v })}
                data-testid="storage-enabled"
              />
            </div>
          </div>

          <div className="sm:col-span-2">
            <Label>Provider</Label>
            <Select
              value={form.provider}
              onValueChange={(v: StorageProvider) =>
                setForm({
                  ...form,
                  provider: v,
                  region: v === 'cloudflare_r2' ? 'auto' : form.region,
                  endpoint_override: v === 'cloudflare_r2' ? false : form.endpoint_override,
                })
              }
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

          {isR2 ? (
            <>
              <div className="sm:col-span-2">
                <Label>Cloudflare Account ID</Label>
                <Input
                  value={form.account_id}
                  onChange={(e) => setForm({ ...form, account_id: e.target.value })}
                  data-testid="account-id"
                  placeholder="Your Cloudflare account id"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Endpoint is derived automatically as{' '}
                  <code className="text-[11px]">https://&lt;ACCOUNT_ID&gt;.r2.cloudflarestorage.com</code>
                </p>
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
                <Label>Public artwork CDN URL</Label>
                <Input
                  placeholder="https://cdn.example.com"
                  value={form.public_base_url}
                  onChange={(e) => setForm({ ...form, public_base_url: e.target.value })}
                  data-testid="public-base-url"
                />
              </div>
            </>
          ) : (
            <>
              <div className="sm:col-span-2">
                <Label>HTTPS endpoint</Label>
                <Input
                  value={form.endpoint_url}
                  onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                  data-testid="storage-endpoint"
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
                  data-testid="storage-region"
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Object key prefix</Label>
                <Input
                  value={form.object_key_prefix}
                  onChange={(e) => setForm({ ...form, object_key_prefix: e.target.value })}
                  data-testid="object-key-prefix"
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Public artwork CDN URL</Label>
                <Input
                  placeholder="https://cdn.example.com"
                  value={form.public_base_url}
                  onChange={(e) => setForm({ ...form, public_base_url: e.target.value })}
                  data-testid="public-base-url"
                />
              </div>
            </>
          )}

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

          {isR2 ? (
            <div className="sm:col-span-2">
              <Button
                type="button"
                variant="ghost"
                className="w-full justify-between px-2"
                onClick={() => setShowAdvanced((v) => !v)}
                data-testid="toggle-advanced"
              >
                <span>Advanced</span>
                <ChevronDown className={`h-4 w-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              </Button>
              {showAdvanced ? (
                <div className="mt-3 grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <Label>Derived endpoint</Label>
                    <Input
                      value={
                        form.endpoint_override ? form.endpoint_url : derivedEndpoint || form.endpoint_url
                      }
                      readOnly={!form.endpoint_override}
                      onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                      data-testid="storage-endpoint"
                    />
                    <label className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={form.endpoint_override}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            endpoint_override: e.target.checked,
                            endpoint_url: e.target.checked
                              ? form.endpoint_url || derivedEndpoint
                              : derivedEndpoint,
                          })
                        }
                        data-testid="endpoint-override"
                      />
                      Override endpoint (advanced)
                    </label>
                  </div>
                  <div>
                    <Label>Region</Label>
                    <Input value="auto" readOnly data-testid="storage-region" />
                  </div>
                  <div>
                    <Label>Object key prefix</Label>
                    <Input
                      value={form.object_key_prefix}
                      onChange={(e) => setForm({ ...form, object_key_prefix: e.target.value })}
                      data-testid="object-key-prefix"
                    />
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

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
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void onSaveAndTest()}
              data-testid="save-and-test"
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Save &amp; Test
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
          <CardDescription>
            Runtime publishing status (secret-free). Saved admin toggle is not shown as active when
            the host kill switch blocks publishing.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-3">
            <span className="text-sm font-medium">Artwork publishing</span>
            <Badge
              variant={publishingBadgeVariant(publishingStatus)}
              data-testid="artwork-publishing-status"
            >
              {publishingLabel(publishingStatus)}
            </Badge>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <StatusChip label="Credentials configured" value={saved.credentials_configured} />
            <StatusChip label="Admin artwork requested" value={saved.artwork_cdn_requested ?? saved.artwork_cdn_enabled} />
            <StatusChip label="Host capability" value={saved.artwork_cdn_host_capability} />
            <StatusChip label="Effective" value={saved.artwork_cdn_effective} />
            <StatusChip label="Last test OK" value={lastTest?.ok ?? saved.last_test_ok} />
            <StatusChip label="Endpoint reachable" value={lastTest?.reachable ?? saved.last_test_reachable} />
            <StatusChip
              label="Bucket accessible"
              value={lastTest?.bucket_accessible ?? saved.last_test_bucket_accessible}
            />
            <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
              <span className="text-muted-foreground">Last test time</span>
              <span>{lastTest?.tested_at || saved.last_test_at || '—'}</span>
            </div>
          </div>
          <p className="text-sm text-muted-foreground" data-testid="last-test-message">
            {lastTest?.message || saved.last_test_message || 'No test recorded yet.'}
          </p>
        </CardContent>
      </Card>

      {saved.credentials_configured ? (
        <Card className="border-destructive/40">
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
