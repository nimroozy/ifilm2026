import { useEffect, useState } from 'react';
import { Cloud } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { ApiError } from '@/lib/api';
import { adminApi, type R2SettingsPayload } from '@/lib/adminApi';
import { LoadingBlock, PageHeader } from './adminShared';

export default function R2SettingsPage() {
  const [form, setForm] = useState<R2SettingsPayload | null>(null);
  const [configured, setConfigured] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    adminApi
      .getR2()
      .then((v) => {
        setConfigured(v.credentials_configured);
        setForm({
          enabled: v.enabled,
          endpoint_url: v.endpoint_url,
          account_id: v.account_id || '',
          bucket: v.bucket,
          region: v.region,
          public_base_url: v.public_base_url || '',
          artwork_cdn_enabled: Boolean(v.artwork_cdn_enabled),
        });
      })
      .catch((e) => setMessage(e instanceof ApiError ? e.message : 'Unable to load R2 settings'));
  }, []);

  if (!form) {
    return message ? (
      <Alert variant="destructive">
        <AlertDescription>{message}</AlertDescription>
      </Alert>
    ) : (
      <LoadingBlock rows={6} />
    );
  }

  const save = async () => {
    setBusy(true);
    setMessage('');
    try {
      const saved = await adminApi.updateR2(form);
      setConfigured(saved.credentials_configured);
      setForm({
        ...form,
        access_key_id: '',
        secret_access_key: '',
        public_base_url: saved.public_base_url || '',
        artwork_cdn_enabled: Boolean(saved.artwork_cdn_enabled),
      });
      setMessage('R2 settings saved securely.');
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="Cloudflare R2"
        description="Optional R2 bucket for public artwork/trailers (CDN) and a private movie hot tier. Full movies stay session-protected on the origin. Host flag ENABLE_ARTWORK_CDN_SYNC must also be true to publish images."
      />
      {message && (
        <Alert>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            R2 connection
          </CardTitle>
          <CardDescription>Secrets are encrypted and never returned to the browser.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2 flex items-center justify-between rounded-lg border p-4">
            <Label>Enable R2 movie hot tier</Label>
            <Switch checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
          </div>
          <div className="sm:col-span-2 flex items-center justify-between rounded-lg border p-4">
            <div>
              <Label>Publish artwork to R2 CDN</Label>
              <p className="text-xs text-muted-foreground mt-1">
                Posters, backdrops, logos, stills (and optional trailer files). Requires public CDN URL.
              </p>
            </div>
            <Switch
              checked={Boolean(form.artwork_cdn_enabled)}
              onCheckedChange={(v) => setForm({ ...form, artwork_cdn_enabled: v })}
            />
          </div>
          <div className="sm:col-span-2">
            <Label>Public CDN base URL</Label>
            <Input
              placeholder="https://cdn.example.com"
              value={form.public_base_url || ''}
              onChange={(e) => setForm({ ...form, public_base_url: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <Label>HTTPS endpoint</Label>
            <Input
              value={form.endpoint_url}
              onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
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
            <Input value={form.bucket} onChange={(e) => setForm({ ...form, bucket: e.target.value })} />
          </div>
          <div>
            <Label>Region</Label>
            <Input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
          </div>
          <div>
            <Label>Access key {configured && '(leave blank to keep)'}</Label>
            <Input
              type="password"
              autoComplete="new-password"
              value={form.access_key_id || ''}
              onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <Label>Secret key</Label>
            <Input
              type="password"
              autoComplete="new-password"
              value={form.secret_access_key || ''}
              onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2 flex justify-end">
            <Button disabled={busy} onClick={save}>
              Save settings
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
