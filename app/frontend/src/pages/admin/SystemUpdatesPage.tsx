import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  adminApi,
  ApiError,
  type AdminUserDto,
  type SystemPreflightDto,
  type SystemUpdateCheckDto,
  type SystemUpdateJobDto,
  type SystemVersionDto,
} from '@/lib/api';
import { LoadingBlock, ErrorState } from './adminShared';

function hasPerm(admin: AdminUserDto | null, key: string): boolean {
  const perms = admin?.permissions || [];
  return perms.includes(key);
}

export default function SystemUpdatesPage() {
  const [admin, setAdmin] = useState<AdminUserDto | null>(null);
  const [version, setVersion] = useState<SystemVersionDto | null>(null);
  const [check, setCheck] = useState<SystemUpdateCheckDto | null>(null);
  const [preflight, setPreflight] = useState<SystemPreflightDto | null>(null);
  const [history, setHistory] = useState<SystemUpdateJobDto[]>([]);
  const [activeJob, setActiveJob] = useState<SystemUpdateJobDto | null>(null);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const canRead = hasPerm(admin, 'system_updates.read');
  const canManage = hasPerm(admin, 'system_updates.manage');

  const refresh = useCallback(async () => {
    setError(null);
    const me = await adminApi.me();
    setAdmin(me);
    if (!(me.permissions || []).includes('system_updates.read')) {
      setLoading(false);
      return;
    }
    const [v, h] = await Promise.all([
      adminApi.getSystemVersion(),
      adminApi.listSystemUpdateHistory(20),
    ]);
    setVersion(v);
    setHistory(h.items);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh().catch((err) => {
      setError(err instanceof ApiError ? err.message : 'Failed to load system updates');
      setLoading(false);
    });
  }, [refresh]);

  useEffect(() => {
    if (!activeJob || !['queued', 'installing', 'backing_up', 'downloading', 'verifying', 'migrating', 'restarting', 'health_checking', 'rollback_running', 'preflight', 'draining'].includes(activeJob.state)) {
      return;
    }
    const t = window.setInterval(() => {
      adminApi
        .getSystemUpdateJob(activeJob.id)
        .then((job) => {
          setActiveJob(job);
          if (job.finished_at || ['completed', 'failed', 'rolled_back', 'rollback_failed', 'preflight_failed', 'backup_failed', 'verification_failed', 'migration_failed', 'health_check_failed'].includes(job.state)) {
            refresh().catch(() => undefined);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(t);
  }, [activeJob, refresh]);

  async function onCheck() {
    setBusy(true);
    setError(null);
    try {
      const result = await adminApi.checkSystemUpdates();
      setCheck(result);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Check failed');
    } finally {
      setBusy(false);
    }
  }

  async function onPreflight() {
    setBusy(true);
    setError(null);
    try {
      setPreflight(await adminApi.runSystemUpdatePreflight());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Preflight failed');
    } finally {
      setBusy(false);
    }
  }

  async function onBackup() {
    if (!password) {
      setError('Re-enter your admin password to create a backup');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminApi.createSystemUpdateBackup(password);
      setPassword('');
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Backup failed');
    } finally {
      setBusy(false);
    }
  }

  async function onInstall() {
    if (!canManage) return;
    if (!password) {
      setError('Re-enter your admin password to install an update');
      return;
    }
    if (!window.confirm('Install the verified release now? A backup will be created first.')) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await adminApi.installSystemUpdate({
        password,
        confirm: true,
        target_version: check?.latest?.version,
      });
      setActiveJob(job);
      setPassword('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Install failed');
    } finally {
      setBusy(false);
    }
  }

  async function onRollback() {
    if (!canManage || !activeJob) return;
    if (!password) {
      setError('Re-enter your admin password to roll back');
      return;
    }
    if (!window.confirm('Roll back to the previous verified release?')) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await adminApi.rollbackSystemUpdate(activeJob.id, {
        password,
        confirm: true,
      });
      setActiveJob(job);
      setPassword('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Rollback failed');
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <LoadingBlock rows={6} />;
  }

  if (!canRead) {
    return (
      <div className="max-w-xl space-y-3" role="alert">
        <div className="flex items-center gap-2 text-destructive">
          <ShieldAlert className="h-5 w-5" aria-hidden />
          <h2 className="text-lg font-semibold">Permission denied</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          System updates require <code>system_updates.read</code>. Only Super Admins or explicitly
          authorized system administrators may manage updates.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-8" dir="auto">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">System updates</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Signed GitHub Releases only. The web app never runs root shell commands.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={onCheck} disabled={busy} className="gap-2">
          <RefreshCw className="h-4 w-4" aria-hidden />
          Check for Updates
        </Button>
      </div>

      {error && <ErrorState message={error} />}

      <section className="space-y-3" aria-labelledby="installed-heading">
        <h3 id="installed-heading" className="text-lg font-medium">
          Installed release
        </h3>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Version</dt>
            <dd className="font-medium">{version?.version || '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Commit</dt>
            <dd className="font-mono text-xs break-all">{version?.build_commit || '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Channel</dt>
            <dd>{version?.update_channel || 'stable'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Migration head</dt>
            <dd className="font-mono text-xs">{version?.migration_head || '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Deployment mode</dt>
            <dd>{version?.deployment_mode || '—'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Maintenance</dt>
            <dd>{version?.maintenance_mode ? 'on' : 'off'}</dd>
          </div>
        </dl>
      </section>

      <section className="space-y-3" aria-labelledby="latest-heading">
        <h3 id="latest-heading" className="text-lg font-medium">
          Latest available
        </h3>
        {!check ? (
          <p className="text-sm text-muted-foreground">Run Check for Updates to query GitHub Releases.</p>
        ) : !check.update_available ? (
          <p className="text-sm">No update available on channel <strong>{check.channel}</strong>.</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-muted-foreground">Version:</span> {check.latest?.version}
            </p>
            <p>
              <span className="text-muted-foreground">Published:</span> {check.latest?.published_at || '—'}
            </p>
            <div>
              <p className="text-muted-foreground mb-1">Release notes</p>
              <pre className="whitespace-pre-wrap rounded-md bg-muted/40 p-3 text-xs max-h-48 overflow-auto">
                {check.latest?.notes || '(none)'}
              </pre>
            </div>
          </div>
        )}
      </section>

      {canManage && (
        <section className="space-y-4" aria-labelledby="actions-heading">
          <h3 id="actions-heading" className="text-lg font-medium">
            Actions
          </h3>
          <div className="space-y-2 max-w-md">
            <Label htmlFor="reauth-password">Confirm admin password</Label>
            <Input
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Required for backup, install, rollback"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" disabled={busy} onClick={onPreflight}>
              Run Preflight
            </Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={onBackup}>
              Create Backup
            </Button>
            <Button type="button" disabled={busy || !check?.update_available} onClick={onInstall}>
              Install Update
            </Button>
            <Button type="button" variant="destructive" disabled={busy || !activeJob} onClick={onRollback}>
              Roll Back
            </Button>
          </div>
          {preflight && (
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Preflight: {preflight.ok ? 'passed' : 'failed'}
              </p>
              <ul className="text-sm space-y-1">
                {preflight.checks.map((c) => (
                  <li key={c.name} className={c.passed ? 'text-foreground' : 'text-destructive'}>
                    {c.passed ? '✓' : '✗'} {c.name}
                    {c.detail ? ` — ${c.detail}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {activeJob && (
            <div className="text-sm space-y-1" aria-live="polite">
              <p>
                Job <span className="font-mono text-xs">{activeJob.id}</span>: <strong>{activeJob.state}</strong>
              </p>
              {activeJob.backup_id && <p>Backup: {activeJob.backup_id}</p>}
              {activeJob.error_message && <p className="text-destructive">{activeJob.error_message}</p>}
            </div>
          )}
        </section>
      )}

      <section className="space-y-3" aria-labelledby="history-heading">
        <h3 id="history-heading" className="text-lg font-medium">
          Update history
        </h3>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No update jobs recorded yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {history.map((job) => (
              <li key={job.id} className="border-b border-border pb-2">
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  <span className="font-medium">{job.state}</span>
                  <span>
                    {job.current_version || '?'} → {job.target_version || '?'}
                  </span>
                  <span className="text-muted-foreground">{job.started_at}</span>
                </div>
                {job.error_message && <p className="text-destructive text-xs mt-1">{job.error_message}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="text-xs text-muted-foreground pt-4 border-t border-border">
        iFilm {version?.version || '—'} · {version?.build_commit?.slice(0, 8) || '—'} · channel{' '}
        {version?.update_channel || 'stable'}
      </footer>
    </div>
  );
}
