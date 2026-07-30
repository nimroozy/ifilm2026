import { useState } from 'react';
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
import { devices, watchHistory, movies, series } from '@/data/mockData';

// ============ LOGIN PAGE ============
export function LoginPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setTimeout(() => {
      if (username === 'mobin_user_001' && password === 'password') {
        login();
        navigate('/');
      } else {
        setError('Invalid username or password');
      }
      setLoading(false);
    }, 1000);
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
              <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="username">{t.login.username}</Label>
              <Input id="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="mobin_user_001" className="bg-background border-border" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t.login.password}</Label>
              <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" className="bg-background border-border" />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="remember" />
              <Label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer">{t.login.remember}</Label>
            </div>
            <Button type="submit" className="w-full bg-primary text-primary-foreground hover:bg-primary/90" disabled={loading}>
              {loading ? 'Signing in...' : t.login.signIn}
            </Button>
            <Button type="button" variant="outline" className="w-full" onClick={() => navigate('/')}>
              {t.login.support}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground text-center mt-4">Demo: mobin_user_001 / password</p>
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

  if (!user) return <div className="min-h-screen flex items-center justify-center"><Button onClick={() => navigate('/login')}>{t.login.signIn}</Button></div>;

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.profile.title}</h1>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* User Info Card */}
          <Card className="bg-card border-border md:col-span-1">
            <CardContent className="pt-6">
              <div className="flex flex-col items-center text-center">
                <div className="w-20 h-20 rounded-full bg-primary/20 flex items-center justify-center mb-4">
                  <User className="h-10 w-10 text-primary" />
                </div>
                <h3 className="text-lg font-semibold text-foreground">{user.name}</h3>
                <p className="text-sm text-muted-foreground">@{user.username}</p>
                <div className="w-full mt-4 space-y-3 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground">Branch:</span><span className="text-foreground">{user.branch}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Package:</span><Badge variant="secondary">{user.package}</Badge></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Status:</span><Badge className="bg-green-500/20 text-green-400">Active</Badge></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Expires:</span><span className="text-foreground">{user.expiration}</span></div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Quick Links */}
          <div className="md:col-span-2 space-y-4">
            {[
              { label: t.profile.devices, path: '/devices', count: '3 devices' },
              { label: t.profile.watchlist, path: '/watchlist', count: '12 items' },
              { label: t.profile.history, path: '/history', count: '24 watched' },
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
  const [deviceList, setDeviceList] = useState(devices);

  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'mobile': return Smartphone;
      case 'tablet': return Tablet;
      case 'tv': return Tv;
      default: return Monitor;
    }
  };

  const removeDevice = (id: number) => {
    setDeviceList(prev => prev.filter(d => d.id !== id));
  };

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.profile.devices}</h1>

        <div className="space-y-3">
          {deviceList.map(device => {
            const Icon = getDeviceIcon(device.type);
            return (
              <Card key={device.id} className="bg-card border-border">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <Icon className="h-6 w-6 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-foreground">{device.name}</h3>
                      {device.current && <Badge className="bg-green-500/20 text-green-400 text-[10px]">Current</Badge>}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mt-1">
                      <span>{device.browser}</span>
                      <span>•</span>
                      <span>{device.lastActive}</span>
                      <span>•</span>
                      <span>IP: {device.ip}</span>
                    </div>
                  </div>
                  {!device.current && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive hover:bg-destructive/10">
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
                          <AlertDialogAction onClick={() => removeDevice(device.id)} className="bg-destructive text-destructive-foreground">{t.common.remove}</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
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
                  <div className="relative w-[100px] md:w-[140px] flex-shrink-0 cursor-pointer" onClick={() => navigate(`/player/${item.contentId}`)}>
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