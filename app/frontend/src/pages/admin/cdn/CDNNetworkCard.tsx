import { useCallback, useEffect, useState } from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ApiError } from '@/lib/api';
import { cdnApi, type NetworkSettingsDto } from '@/lib/cdnApi';

const ALLOW_ANY = ['0.0.0.0/0', '::/0'];

export function splitCidrs(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((v) => v.trim())
    .filter(Boolean);
}

export function hasAllowAny(values: string[]): boolean {
  return values.some((v) => ALLOW_ANY.includes(v));
}

export default function CDNNetworkCard({ onSaved }: { onSaved?: (dto: NetworkSettingsDto) => void }) {
  const [saved, setSaved] = useState<NetworkSettingsDto | null>(null);
  const [management, setManagement] = useState('');
  const [serve, setServe] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const dto = await cdnApi.getNetwork();
      setSaved(dto);
      setManagement(dto.management_cidrs.join('\n'));
      setServe(dto.serve_cidrs.join('\n'));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load network policy');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const managementList = splitCidrs(management);
  const serveList = splitCidrs(serve);
  const allowAnyEntered = hasAllowAny(managementList) || hasAllowAny(serveList);

  async function persist(confirmAllowAny: boolean) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const dto = await cdnApi.updateNetwork({ management_cidrs: managementList, serve_cidrs: serveList, confirm_allow_any: confirmAllowAny });
      setSaved(dto);
      setManagement(dto.management_cidrs.join('\n'));
      setServe(dto.serve_cidrs.join('\n'));
      setSuccess(dto.media_port_open ? 'Network policy saved.' : 'Network policy saved. Media port stays closed until serve CIDRs are configured.');
      onSaved?.(dto);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save network policy');
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  }

  function onSave() {
    if (allowAnyEntered) {
      setConfirmOpen(true);
      return;
    }
    void persist(false);
  }

  return (
    <Card data-testid="cdn-network-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          {saved?.provisioning_ready ? <ShieldCheck className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}
          Network policy (firewall)
        </CardTitle>
        <CardDescription>
          Applied to every provisioned server as a default-deny nftables ruleset. Provisioning refuses to run until management CIDRs are set and verifies a fresh SSH login after applying the firewall.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
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
        {saved && !saved.provisioning_ready && (
          <Alert variant="destructive" data-testid="cdn-network-missing">
            <AlertTitle>Management CIDRs required</AlertTitle>
            <AlertDescription>No management networks are configured. Provisioning will fail closed at the firewall step until at least one is saved.</AlertDescription>
          </Alert>
        )}
        {allowAnyEntered && (
          <Alert variant="destructive" data-testid="cdn-network-allow-any-warning">
            <AlertTitle>Allow-any entered</AlertTitle>
            <AlertDescription>0.0.0.0/0 or ::/0 exposes that port to the whole Internet. Use specific networks instead; explicit confirmation is required to save this.</AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="cdn-management-cidrs">Management CIDRs</Label>
            <Textarea
              id="cdn-management-cidrs"
              rows={4}
              value={management}
              onChange={(e) => setManagement(e.target.value)}
              placeholder={'One network per line, e.g.\n203.0.113.10/32'}
              data-testid="cdn-management-cidrs"
            />
            <p className="text-xs text-muted-foreground">Networks allowed to administer CDN servers over SSH. Must include the provisioning worker&apos;s public address. Required.</p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cdn-serve-cidrs">Serve CIDRs</Label>
            <Textarea
              id="cdn-serve-cidrs"
              rows={4}
              value={serve}
              onChange={(e) => setServe(e.target.value)}
              placeholder={'Subscriber networks, e.g.\n103.89.153.0/24\n103.126.4.0/24'}
              data-testid="cdn-serve-cidrs"
            />
            <p className="text-xs text-muted-foreground">Subscriber/client networks allowed to access the CDN media service. Leave empty to keep the media port closed (CDN-P1 default).</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onSave} disabled={busy || managementList.length === 0} data-testid="cdn-network-save">
            Save network policy
          </Button>
          {saved && (
            <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <Badge variant={saved.provisioning_ready ? 'default' : 'destructive'}>{saved.provisioning_ready ? 'SSH restricted' : 'not configured'}</Badge>
              <Badge variant={saved.media_port_open ? 'secondary' : 'outline'} data-testid="cdn-media-port-badge">
                {saved.media_port_open ? 'media port open to serve CIDRs' : 'media port closed'}
              </Badge>
              {saved.source === 'env' && <span>(from server environment)</span>}
            </span>
          )}
        </div>
      </CardContent>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="cdn-network-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Expose a port to the whole Internet?</AlertDialogTitle>
            <AlertDialogDescription>
              You entered 0.0.0.0/0 or ::/0. Every provisioned server will accept that traffic from any source. Only continue if this is a deliberate, reviewed decision.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void persist(true)} data-testid="cdn-network-confirm-action">
              I understand, save anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
