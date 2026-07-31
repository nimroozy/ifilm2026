import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Monitor, Smartphone, Tablet, Tv, Trash2, Clock, Play, Star, X, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import { useLang, useAuth } from '@/components/CustomerLayout';
import { devices, episodes, watchHistory, movies, series } from '@/data/mockData';
import { api, ApiError, tokenStore, type DeviceDto, type WatchProgressDto } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.details;
    if (detail && typeof detail === 'object' && detail !== null && 'code' in detail) {
      const code = String((detail as { code?: string }).code || '');
      const message = String((detail as { message?: string }).message || error.message);
      switch (code) {
        case 'account_suspended':
          return 'Your account is suspended. Contact support.';
        case 'account_disabled':
          return 'Your account is disabled.';
        case 'service_expired':
          return 'Your service has expired. Contact support to renew.';
        case 'device_limit_exceeded':
          return 'Too many devices. Remove a device and try again.';
        case 'provider_unavailable':
          return 'Sign-in is temporarily unavailable. Try again later.';
        case 'rate_limited':
          return 'Too many attempts. Wait a moment and try again.';
        default:
          return message || 'Invalid username or password';
      }
    }
    if (error.status === 401) return 'Invalid username or password';
    if (error.status === 429) return 'Too many attempts. Wait a moment and try again.';
    if (error.status === 503) return 'Sign-in is temporarily unavailable. Try again later.';
  }
  return 'Invalid username or password';
}

// ============ LOGIN PAGE ============
export function LoginPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const mockMode = isMockMode();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username, password, remember);
      navigate('/');
    } catch (err) {
      setError(loginErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <Card className="w-full max-w-md bg-card border-border">
        <CardHeader className="text-center">
          <h1 className="text-3xl font-serif font-bold text-primary mb-2">Mobin Play</h1>
          <CardTitle className="text-xl text-foreground">{t.login.title}</CardTitle>
          <p className="text-sm text-muted-foreground mt-2">{t.login.note}</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive text-sm" role="alert">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="username">{t.login.username}</Label>
              <Input id="username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" className="bg-background border-border" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t.login.password}</Label>
              <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" className="bg-background border-border" />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="remember" checked={remember} onCheckedChange={(v) => setRemember(v === true)} />
              <Label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer">{t.login.remember}</Label>
            </div>
            <Button type="submit" className="w-full bg-primary text-primary-foreground hover:bg-primary/90" disabled={loading}>
              {loading ? 'Signing in...' : t.login.signIn}
            </Button>
            <Button type="button" variant="outline" className="w-full" onClick={() => navigate('/')}>
              {t.login.support}
            </Button>
          </form>
          {mockMode && (
            <p className="text-xs text-muted-foreground text-center mt-4">Demo: mobin_user_001 / password</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ============ PROFILE PAGE ============
export function ProfilePage() {
  const { t } = useLang();
  const { user } = useAuth();
  const navigate = useNavigate();
  const mockMode = isMockMode();
  const [deviceCount, setDeviceCount] = useState<string>(mockMode ? '3 devices' : '…');

  useEffect(() => {
    if (mockMode || !user) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listDevices();
        if (!cancelled) setDeviceCount(`${list.length} / ${user.maxDevices} devices`);
      } catch {
        if (!cancelled) setDeviceCount(`${user.maxDevices} max`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mockMode, user]);

  if (!user) return <div className="min-h-screen flex items-center justify-center"><Button onClick={() => navigate('/login')}>{t.login.signIn}</Button></div>;

  const statusLabel = user.status || 'unknown';
  const statusClass =
    statusLabel === 'active' && user.entitlementAllowed !== false
      ? 'bg-green-500/20 text-green-400'
      : 'bg-amber-500/20 text-amber-300';

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.profile.title}</h1>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="bg-card border-border md:col-span-1">
            <CardContent className="pt-6">
              <div className="flex flex-col items-center text-center">
                <div className="w-20 h-20 rounded-full bg-primary/20 flex items-center justify-center mb-4">
                  <User className="h-10 w-10 text-primary" />
                </div>
                <h3 className="text-lg font-semibold text-foreground">{user.name}</h3>
                <p className="text-sm text-muted-foreground">@{user.username}</p>
                <div className="w-full mt-4 space-y-3 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground">Branch:</span><span className="text-foreground">{user.branch || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Package:</span><Badge variant="secondary">{user.package || '—'}</Badge></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Status:</span><Badge className={statusClass}>{statusLabel}</Badge></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Service:</span><span className="text-foreground">{user.serviceStatus}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Expires:</span><span className="text-foreground">{user.expiration || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Entitlement:</span><span className="text-foreground">{user.entitlementAllowed === false ? 'Denied' : user.entitlementAllowed ? 'Allowed' : '—'}</span></div>
                  {user.safeReason && (
                    <p className="text-xs text-muted-foreground text-start pt-1">{user.safeReason}</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="md:col-span-2 space-y-4">
            {[
              { label: t.profile.devices, path: '/devices', count: deviceCount },
              { label: t.profile.watchlist, path: '/watchlist', count: mockMode ? '12 items' : 'Open' },
              { label: t.profile.history, path: '/history', count: mockMode ? '24 watched' : 'Open' },
            ].map(item => (
              <Card key={item.path} className="bg-card border-border hover:bg-card/80 cursor-pointer transition-colors" onClick={() => navigate(item.path)}>
                <CardContent className="flex items-center justify-between py-4">
                  <span className="font-medium text-foreground">{item.label}</span>
                  <span className="text-sm text-muted-foreground">{item.count} →</span>
                </CardContent>
              </Card>
            ))}

            <Card className="bg-card border-border">
              <CardHeader><CardTitle className="text-base">{t.profile.settings}</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Language</span>
                  <Badge variant="outline">فارسی</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Subtitle</span>
                  <Badge variant="outline">English</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Quality</span>
                  <Badge variant="outline">Auto</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Auto-play</span>
                  <Badge variant="outline">On</Badge>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ DEVICE MANAGEMENT PAGE ============
export function DevicesPage() {
  const { t } = useLang();
  const { user } = useAuth();
  const mockMode = isMockMode();
  const [deviceList, setDeviceList] = useState<DeviceDto[]>([]);
  const [loading, setLoading] = useState(!mockMode);
  const [error, setError] = useState('');

  const loadDevices = useCallback(async () => {
    if (mockMode) {
      setDeviceList(
        devices.map((d) => ({
          id: d.id,
          client_device_id: `mock-${d.id}`,
          name: d.name,
          device_type: d.type,
          browser: d.browser,
          ip: d.ip,
          last_seen_at: d.lastActive,
          current: d.current,
        })),
      );
      setLoading(false);
      return;
    }
    if (!tokenStore.get()) {
      setError('Sign in required');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const list = await api.listDevices();
      setDeviceList(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load devices');
      setDeviceList([]);
    } finally {
      setLoading(false);
    }
  }, [mockMode]);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'mobile': return Smartphone;
      case 'tablet': return Tablet;
      case 'tv': return Tv;
      default: return Monitor;
    }
  };

  const removeDevice = async (id: number) => {
    if (mockMode) {
      setDeviceList(prev => prev.filter(d => d.id !== id));
      return;
    }
    await api.revokeDevice(id);
    await loadDevices();
  };

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-2">{t.profile.devices}</h1>
        {user && (
          <p className="text-sm text-muted-foreground mb-6">
            Device limit: {user.maxDevices}
            {user.safeReason ? ` — ${user.safeReason}` : ''}
          </p>
        )}
        {error && (
          <div className="mb-4 text-sm text-destructive" role="alert">{error}</div>
        )}
        {loading ? (
          <p className="text-muted-foreground">Loading devices…</p>
        ) : (
        <div className="space-y-3">
          {deviceList.length === 0 && (
            <p className="text-muted-foreground">No active devices.</p>
          )}
          {deviceList.map(device => {
            const Icon = getDeviceIcon(device.device_type);
            return (
              <Card key={device.id} className="bg-card border-border">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Icon className="h-6 w-6 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-foreground">{device.name || 'Device'}</h3>
                      {device.current && <Badge className="bg-green-500/20 text-green-400 text-[10px]">Current</Badge>}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mt-1">
                      <span>{device.browser || device.device_type}</span>
                      {device.last_seen_at && (
                        <>
                          <span>•</span>
                          <span>{device.last_seen_at}</span>
                        </>
                      )}
                      {device.ip && (
                        <>
                          <span>•</span>
                          <span>IP: {device.ip}</span>
                        </>
                      )}
                    </div>
                  </div>
                  {!device.current && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive hover:bg-destructive/10" aria-label={`Remove ${device.name}`}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Remove Device</AlertDialogTitle>
                          <AlertDialogDescription>Are you sure you want to remove "{device.name}"? This device will be logged out.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
                          <AlertDialogAction onClick={() => void removeDevice(device.id)} className="bg-destructive text-destructive-foreground">{t.common.remove}</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
        )}
      </div>
    </div>
  );
}

// ============ WATCHLIST PAGE ============
export function WatchlistPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [watchlist, setWatchlist] = useState(() => [...movies.slice(0, 5), ...series.slice(0, 3)]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.profile.watchlist}</h1>

        {watchlist.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p className="text-lg">Your watchlist is empty</p>
            <Button className="mt-4" onClick={() => navigate('/movies')}>Browse Movies</Button>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {watchlist.map((item: any) => (
              <div key={`${item.type}-${item.id}`} className="group relative">
                <div onClick={() => navigate(item.type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)} className="cursor-pointer">
                  <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                    <img src={item.poster} alt={item.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                      <Play className="h-10 w-10 text-white fill-white" />
                    </div>
                  </div>
                  <h3 className="text-sm font-medium text-foreground truncate">{item.title}</h3>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute top-2 right-2 h-7 w-7 bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => setWatchlist(prev => prev.filter(w => w.id !== item.id || w.type !== item.type))}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ WATCH HISTORY PAGE ============
export function HistoryPage() {
  return isMockMode() ? <MockHistoryPage /> : <ApiHistoryPage />;
}

function mockHistoryPlayerPath(item: (typeof watchHistory)[number]): string {
  if (item.type === 'movie') return `/player/movie/${item.contentId}`;
  const match = item.episode?.match(/^S(\d+)E(\d+)$/i);
  const episode = match
    ? episodes.find(
        (candidate) =>
          candidate.seriesId === item.contentId &&
          candidate.season === Number(match[1]) &&
          candidate.episode === Number(match[2])
      )
    : undefined;
  return episode ? `/player/episode/${episode.id}` : `/series/${item.contentId}`;
}

function MockHistoryPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [history, setHistory] = useState(watchHistory);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground">{t.profile.history}</h1>
          {history.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm">Clear All</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear Watch History</AlertDialogTitle>
                  <AlertDialogDescription>This will remove all items from your watch history. This action cannot be undone.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => setHistory([])} className="bg-destructive text-destructive-foreground">{t.common.delete}</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>

        {history.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">No watch history yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {history.map(item => (
              <Card key={item.id} className="bg-card border-border">
                <CardContent className="flex items-center gap-4 py-3">
                  <div className="relative w-[100px] md:w-[140px] flex-shrink-0 cursor-pointer" onClick={() => navigate(mockHistoryPlayerPath(item))}>
                    <img src={item.poster} alt={item.title} className="w-full aspect-video rounded object-cover" />
                    {item.progress < 100 && (
                      <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted"><div className="h-full bg-primary" style={{ width: `${item.progress}%` }} /></div>
                    )}
                    <div className="absolute inset-0 flex items-center justify-center bg-black/20 rounded">
                      <Play className="h-6 w-6 text-white fill-white" />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-foreground text-sm">{item.title}</h3>
                    {item.episode && <p className="text-xs text-muted-foreground">{item.episode}</p>}
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <span>{item.watchedAt}</span>
                      <span>•</span>
                      <span>{item.progress}%</span>
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setHistory(prev => prev.filter(h => h.id !== item.id))} className="text-muted-foreground hover:text-destructive">
                    <X className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ApiHistoryPage() {
  const { t } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const [history, setHistory] = useState<WatchProgressDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removingAssetId, setRemovingAssetId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const loadHistory = useCallback(async () => {
    if (!isLoggedIn || !tokenStore.get()) {
      setHistory([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const page = await api.listWatchHistory({ page: 1, page_size: 100 });
      setHistory(page.items);
    } catch {
      setHistory([]);
      setError('Unable to load watch history.');
    } finally {
      setLoading(false);
    }
  }, [isLoggedIn]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const removeItem = async (item: WatchProgressDto) => {
    setRemovingAssetId(item.media_asset_id);
    setError(null);
    try {
      await api.deleteWatchHistoryItem(item.media_asset_id);
      setHistory((current) =>
        current.filter((candidate) => candidate.media_asset_id !== item.media_asset_id)
      );
    } catch {
      setError('Unable to remove this history item.');
    } finally {
      setRemovingAssetId(null);
    }
  };

  const clearAll = async () => {
    setClearing(true);
    setError(null);
    try {
      await api.clearWatchHistory();
      setHistory([]);
    } catch {
      setError('Unable to clear watch history.');
    } finally {
      setClearing(false);
    }
  };

  if (!isLoggedIn || !tokenStore.get()) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-4">
        <p className="text-muted-foreground">Sign in to view your watch history.</p>
        <Button onClick={() => navigate('/login')}>{t.login.signIn}</Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <div className="flex items-center justify-between gap-4 mb-6">
          <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground">
            {t.profile.history}
          </h1>
          {history.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" disabled={clearing}>
                  Clear All
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear Watch History</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will remove all items from your watch history. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => void clearAll()}
                    className="bg-destructive text-destructive-foreground"
                  >
                    {t.common.delete}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>

        {error && (
          <div
            className="mb-4 flex flex-wrap items-center gap-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive"
            role="alert"
          >
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
            {history.length === 0 && (
              <Button variant="outline" size="sm" onClick={() => void loadHistory()}>
                Retry
              </Button>
            )}
          </div>
        )}

        {loading ? (
          <div className="py-20 text-center text-muted-foreground" role="status">
            Loading watch history…
          </div>
        ) : history.length === 0 && !error ? (
          <div className="text-center py-20 text-muted-foreground">
            <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg">No watch history yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {history.map((item) => {
              const canPlay = item.available && Boolean(item.player_path);
              const progress = Math.min(100, Math.max(0, item.progress_percent || 0));
              return (
                <Card key={item.media_asset_id} className="bg-card border-border">
                  <CardContent className="flex items-center gap-4 py-3">
                    <button
                      type="button"
                      className="relative w-[100px] md:w-[140px] flex-shrink-0 overflow-hidden rounded bg-muted text-start disabled:cursor-default"
                      onClick={() => canPlay && navigate(item.player_path)}
                      disabled={!canPlay}
                      aria-label={canPlay ? `Resume ${item.title}` : `${item.title || 'Title'} unavailable`}
                    >
                      {item.poster_url ? (
                        <img
                          src={item.poster_url}
                          alt=""
                          className="w-full aspect-video object-cover"
                        />
                      ) : (
                        <span className="flex aspect-video items-center justify-center px-2 text-center text-xs text-muted-foreground">
                          {item.available ? item.title : 'Unavailable'}
                        </span>
                      )}
                      {!item.completed && (
                        <span className="absolute bottom-0 left-0 right-0 h-1 bg-muted">
                          <span className="block h-full bg-primary" style={{ width: `${progress}%` }} />
                        </span>
                      )}
                      {canPlay && (
                        <span className="absolute inset-0 flex items-center justify-center bg-black/20">
                          <Play className="h-6 w-6 text-white fill-white" />
                        </span>
                      )}
                    </button>

                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium text-foreground text-sm">
                          {item.title || 'Unavailable'}
                        </h3>
                        {!item.available && <Badge variant="secondary">Unavailable</Badge>}
                      </div>
                      {item.subtitle && (
                        <p className="text-xs text-muted-foreground">{item.subtitle}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
                        {item.last_watched_at && <span>{formatHistoryDate(item.last_watched_at)}</span>}
                        {item.last_watched_at && <span>•</span>}
                        <span>{Math.round(progress)}%</span>
                      </div>
                      {canPlay && (
                        <Button
                          variant="link"
                          size="sm"
                          className="h-auto p-0 mt-1"
                          onClick={() => navigate(item.player_path)}
                        >
                          {item.completed ? 'Watch Again' : 'Resume'}
                        </Button>
                      )}
                    </div>

                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void removeItem(item)}
                      disabled={removingAssetId === item.media_asset_id}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={`Remove ${item.title || 'unavailable title'} from watch history`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function formatHistoryDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}