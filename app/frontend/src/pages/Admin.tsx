import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LayoutDashboard, Film, Tv, Upload, Cpu, Server, Users, GitBranch, BarChart3, Settings, Menu, X, ChevronDown, Activity, HardDrive, Eye, AlertTriangle, CheckCircle, XCircle, Clock, TrendingUp, Play, Pause, RotateCcw, Trash2, Plus, Edit, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { adminApi, type ManagedCDNNodeDto, type CDNPrefixRouteDto } from '@/lib/adminApi';
import { useLang } from '@/components/CustomerLayout';
import { movies, series, branches, users, encodingJobs, adminRoles, systemAlerts } from '@/data/mockData';

// ============ ADMIN LAYOUT ============
export default function AdminPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('dashboard');
  const [selectedRole, setSelectedRole] = useState(adminRoles[0]);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const navItems = [
    { id: 'dashboard', label: t.admin.dashboard, icon: LayoutDashboard },
    { id: 'movies', label: t.admin.movies, icon: Film },
    { id: 'series', label: t.admin.series, icon: Tv },
    { id: 'upload', label: t.admin.upload, icon: Upload },
    { id: 'encoding', label: t.admin.encoding, icon: Cpu },
    { id: 'cdn', label: t.admin.cdn, icon: Server },
    { id: 'users', label: t.admin.users, icon: Users },
    { id: 'branches', label: t.admin.branches, icon: GitBranch },
    { id: 'reports', label: t.admin.reports, icon: BarChart3 },
    { id: 'settings', label: t.admin.settings, icon: Settings },
  ];

  const visibleNav = navItems.filter(item => selectedRole.permissions.includes(item.id));

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-border">
        <h2 className="text-xl font-display font-bold text-primary">iFilm</h2>
        <p className="text-xs text-muted-foreground mt-1">Admin Panel</p>
      </div>
      <div className="p-3 border-b border-border">
        <Select value={String(selectedRole.id)} onValueChange={v => setSelectedRole(adminRoles.find(r => r.id === Number(v)) || adminRoles[0])}>
          <SelectTrigger className="w-full text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {adminRoles.map(role => <SelectItem key={role.id} value={String(role.id)}>{role.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {visibleNav.map(item => (
          <button
            key={item.id}
            onClick={() => { setActiveSection(item.id); setSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${activeSection === item.id ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </button>
        ))}
      </nav>
      <div className="p-3 border-t border-border">
        <Button variant="outline" size="sm" className="w-full" onClick={() => navigate('/')}>← Back to App</Button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-64 border-r border-border flex-col fixed h-full bg-card">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-64 p-0 bg-card">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* Main Content */}
      <div className="flex-1 lg:ml-64">
        {/* Top Bar */}
        <header className="sticky top-0 z-40 bg-background/95 backdrop-blur-md border-b border-border px-4 lg:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)}>
              <Menu className="h-5 w-5" />
            </Button>
            <h1 className="text-lg font-semibold text-foreground capitalize">{activeSection}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{selectedRole.name}</Badge>
          </div>
        </header>

        {/* Content Area */}
        <main className="p-4 lg:p-6">
          {activeSection === 'dashboard' && <DashboardSection />}
          {activeSection === 'movies' && <MoviesSection />}
          {activeSection === 'series' && <SeriesSection />}
          {activeSection === 'upload' && <UploadSection />}
          {activeSection === 'encoding' && <EncodingSection />}
          {activeSection === 'cdn' && <CDNSection />}
          {activeSection === 'users' && <UsersSection />}
          {activeSection === 'branches' && <BranchesSection />}
          {activeSection === 'reports' && <ReportsSection />}
          {activeSection === 'settings' && <SettingsSection />}
        </main>
      </div>
    </div>
  );
}

// ============ DASHBOARD ============
function DashboardSection() {
  const stats = [
    { label: 'Total Movies', value: movies.length, icon: Film, color: 'text-blue-500' },
    { label: 'Total Series', value: series.length, icon: Tv, color: 'text-purple-500' },
    { label: 'Active Users', value: '8,940', icon: Users, color: 'text-green-500' },
    { label: 'Concurrent Viewers', value: '2,886', icon: Eye, color: 'text-primary' },
    { label: 'Total Storage', value: '78.5 TB', icon: HardDrive, color: 'text-orange-500' },
    { label: 'Encoding Queue', value: encodingJobs.filter(j => j.status === 'processing').length, icon: Cpu, color: 'text-cyan-500' },
    { label: 'CDN Health', value: '95%', icon: Activity, color: 'text-emerald-500' },
    { label: 'Failed Jobs', value: encodingJobs.filter(j => j.status === 'failed').length, icon: AlertTriangle, color: 'text-destructive' },
  ];

  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map(stat => (
          <Card key={stat.label} className="bg-card border-border">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
                <span className="text-2xl font-bold text-foreground">{stat.value}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-2">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Alerts */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-base">System Alerts</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {systemAlerts.map(alert => (
            <div key={alert.id} className={`flex items-center gap-3 p-2 rounded-lg text-sm ${alert.type === 'error' ? 'bg-destructive/10' : alert.type === 'warning' ? 'bg-yellow-500/10' : alert.type === 'success' ? 'bg-green-500/10' : 'bg-blue-500/10'}`}>
              {alert.type === 'error' ? <XCircle className="h-4 w-4 text-destructive" /> : alert.type === 'warning' ? <AlertTriangle className="h-4 w-4 text-yellow-500" /> : alert.type === 'success' ? <CheckCircle className="h-4 w-4 text-green-500" /> : <Activity className="h-4 w-4 text-blue-500" />}
              <span className="flex-1 text-foreground">{alert.message}</span>
              <span className="text-xs text-muted-foreground">{alert.time}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Popular Content */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-base">Popular Content</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow><TableHead>Title</TableHead><TableHead>Type</TableHead><TableHead>Views</TableHead><TableHead>Rating</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {[...movies].sort((a, b) => b.views - a.views).slice(0, 5).map(m => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.title}</TableCell>
                  <TableCell><Badge variant="secondary">Movie</Badge></TableCell>
                  <TableCell>{m.views.toLocaleString()}</TableCell>
                  <TableCell><span className="flex items-center gap-1"><TrendingUp className="h-3 w-3 text-primary" />{m.rating}</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ MOVIES MANAGEMENT ============
function MoviesSection() {
  const [search, setSearch] = useState('');
  const filtered = movies.filter(m => !search || m.title.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search movies..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Button className="bg-primary text-primary-foreground gap-2"><Plus className="h-4 w-4" />Add Movie</Button>
      </div>
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Title</TableHead><TableHead>Year</TableHead><TableHead>Rating</TableHead><TableHead>Genres</TableHead><TableHead>Status</TableHead><TableHead>Actions</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {filtered.slice(0, 15).map(m => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.title}</TableCell>
                  <TableCell>{m.year}</TableCell>
                  <TableCell>{m.rating}</TableCell>
                  <TableCell className="text-xs">{m.genres.slice(0, 2).join(', ')}</TableCell>
                  <TableCell><Badge className="bg-green-500/20 text-green-600 text-xs">Published</Badge></TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7"><Edit className="h-3.5 w-3.5" /></Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ SERIES MANAGEMENT ============
function SeriesSection() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Input placeholder="Search series..." className="max-w-sm" />
        <Button className="bg-primary text-primary-foreground gap-2"><Plus className="h-4 w-4" />Add Series</Button>
      </div>
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Title</TableHead><TableHead>Seasons</TableHead><TableHead>Episodes</TableHead><TableHead>Status</TableHead><TableHead>Rating</TableHead><TableHead>Actions</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {series.map(s => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.title}</TableCell>
                  <TableCell>{s.seasons}</TableCell>
                  <TableCell>{s.episodes}</TableCell>
                  <TableCell><Badge variant={s.status === 'Ongoing' ? 'default' : 'secondary'}>{s.status}</Badge></TableCell>
                  <TableCell>{s.rating}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7"><Edit className="h-3.5 w-3.5" /></Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ UPLOAD CENTER ============
function UploadSection() {
  const [isDragging, setIsDragging] = useState(false);

  return (
    <div className="space-y-6">
      {/* Drop Zone */}
      <Card className={`bg-card border-2 border-dashed transition-colors ${isDragging ? 'border-primary bg-primary/5' : 'border-border'}`}>
        <CardContent className="py-12 text-center"
          onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={e => { e.preventDefault(); setIsDragging(false); }}
        >
          <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium text-foreground mb-2">Drag and drop media files</h3>
          <p className="text-sm text-muted-foreground mb-4">Supports MP4, MKV, AVI up to 50GB</p>
          <Button className="bg-primary text-primary-foreground">Select Files</Button>
        </CardContent>
      </Card>

      {/* Upload Queue */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-base">Upload Queue</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {[
            { name: 'the_healer_s02e06.mkv', size: '4.2 GB', progress: 67, status: 'uploading' },
            { name: 'night_watch_s01e09.mp4', size: '3.8 GB', progress: 100, status: 'completed' },
            { name: 'new_movie_raw.mkv', size: '12.5 GB', progress: 23, status: 'uploading' },
          ].map((file, i) => (
            <div key={i} className="flex items-center gap-4 p-3 rounded-lg bg-muted/50">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{file.name}</p>
                <p className="text-xs text-muted-foreground">{file.size}</p>
              </div>
              <div className="w-32">
                <Progress value={file.progress} className="h-2" />
              </div>
              <span className="text-xs text-muted-foreground w-10">{file.progress}%</span>
              <Badge variant={file.status === 'completed' ? 'default' : 'secondary'} className="text-xs">{file.status}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ============ ENCODING QUEUE ============
function EncodingSection() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-card border-border"><CardContent className="pt-4"><p className="text-2xl font-bold">{encodingJobs.filter(j => j.status === 'processing').length}</p><p className="text-xs text-muted-foreground">Processing</p></CardContent></Card>
        <Card className="bg-card border-border"><CardContent className="pt-4"><p className="text-2xl font-bold">{encodingJobs.filter(j => j.status === 'waiting').length}</p><p className="text-xs text-muted-foreground">Waiting</p></CardContent></Card>
        <Card className="bg-card border-border"><CardContent className="pt-4"><p className="text-2xl font-bold">{encodingJobs.filter(j => j.status === 'completed').length}</p><p className="text-xs text-muted-foreground">Completed</p></CardContent></Card>
        <Card className="bg-card border-border"><CardContent className="pt-4"><p className="text-2xl font-bold text-destructive">{encodingJobs.filter(j => j.status === 'failed').length}</p><p className="text-xs text-muted-foreground">Failed</p></CardContent></Card>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Job ID</TableHead><TableHead>Title</TableHead><TableHead>Stage</TableHead><TableHead>Progress</TableHead><TableHead>Worker</TableHead><TableHead>ETA</TableHead><TableHead>Status</TableHead><TableHead>Actions</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {encodingJobs.map(job => (
                <TableRow key={job.id}>
                  <TableCell className="font-mono text-xs">{job.id}</TableCell>
                  <TableCell className="font-medium text-sm">{job.title}</TableCell>
                  <TableCell className="text-xs">{job.stage}</TableCell>
                  <TableCell><div className="flex items-center gap-2"><Progress value={job.progress} className="h-2 w-16" /><span className="text-xs">{job.progress}%</span></div></TableCell>
                  <TableCell className="text-xs">{job.worker}</TableCell>
                  <TableCell className="text-xs">{job.eta}</TableCell>
                  <TableCell>
                    <Badge variant={job.status === 'completed' ? 'default' : job.status === 'failed' ? 'destructive' : job.status === 'processing' ? 'secondary' : 'outline'} className="text-xs">
                      {job.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {job.status === 'failed' && <Button variant="ghost" size="icon" className="h-7 w-7"><RotateCcw className="h-3.5 w-3.5" /></Button>}
                      {job.status === 'processing' && <Button variant="ghost" size="icon" className="h-7 w-7"><Pause className="h-3.5 w-3.5" /></Button>}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ CDN MANAGEMENT ============
function CDNSection() {
  const [nodes, setNodes] = useState<ManagedCDNNodeDto[]>([]);
  const [routes, setRoutes] = useState<CDNPrefixRouteDto[]>([]);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', role: 'cache' as 'main'|'cache', host: '', ssh_port: 22, ssh_username: 'root', credential_type: 'password' as 'password'|'private_key', credential: '', location: '', branch: '', notes: '', cache_limit_gb: 500, is_default: false });
  const [route, setRoute] = useState({ cidr: '', node_id: '', priority: 100 });
  const refresh = () => Promise.all([adminApi.listCDNNodes(), adminApi.listCDNRoutes()]).then(([n, r]) => { setNodes(n); setRoutes(r); }).catch(e => setError(e?.response?.data?.detail || 'Unable to load CDN management. Sign in with CDN permission.'));
  useEffect(() => { void refresh(); }, []);
  const addNode = async () => { setError(''); try { await adminApi.createCDNNode({ ...form, enabled: true, cache_limit_bytes: form.cache_limit_gb * 1024 ** 3 }); setShowForm(false); setForm({ ...form, name: '', host: '', credential: '', notes: '' }); await refresh(); } catch (e: any) { setError(e?.response?.data?.detail || 'Unable to add server'); } };
  const action = async (node: ManagedCDNNodeDto, name: string) => { if (!window.confirm(`${name} ${node.name}? This action is recorded and may change the server.`)) return; await adminApi.cdnNodeAction(node.id, name); await refresh(); };
  const addRoute = async () => { try { await adminApi.createCDNRoute({ ...route, enabled: true }); setRoute({ cidr: '', node_id: '', priority: 100 }); await refresh(); } catch (e: any) { setError(e?.response?.data?.detail || 'Unable to add route'); } };
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><div><h2 className="text-xl font-semibold">CDN Servers</h2><p className="text-sm text-muted-foreground">Main origins, branch caches, health and safe provisioning.</p></div><Button onClick={() => setShowForm(!showForm)}><Plus className="h-4 w-4 mr-2" />Add server</Button></div>
      {error && <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
      {showForm && <Card><CardHeader><CardTitle className="text-base">New Debian 13 CDN server</CardTitle></CardHeader><CardContent className="grid gap-4 md:grid-cols-2">
        <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({...form, name:e.target.value})} placeholder="Nimruz Cache" /></div>
        <div><Label>Role</Label><Select value={form.role} onValueChange={(v:'main'|'cache')=>setForm({...form,role:v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="main">Main CDN</SelectItem><SelectItem value="cache">Cache</SelectItem></SelectContent></Select></div>
        <div><Label>IP or hostname</Label><Input value={form.host} onChange={e=>setForm({...form,host:e.target.value})} placeholder="cdn-nimruz.example.com" /></div>
        <div><Label>SSH port</Label><Input type="number" value={form.ssh_port} onChange={e=>setForm({...form,ssh_port:Number(e.target.value)})} /></div>
        <div><Label>SSH username</Label><Input value={form.ssh_username} onChange={e=>setForm({...form,ssh_username:e.target.value})} /></div>
        <div><Label>Credential</Label><Select value={form.credential_type} onValueChange={(v:'password'|'private_key')=>setForm({...form,credential_type:v})}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="private_key">Private key (recommended)</SelectItem><SelectItem value="password">Password (bootstrap only)</SelectItem></SelectContent></Select></div>
        <div className="md:col-span-2"><Label>{form.credential_type === 'private_key' ? 'SSH private key' : 'SSH password'}</Label><Textarea value={form.credential} onChange={e=>setForm({...form,credential:e.target.value})} className="font-mono" /><p className="text-xs text-muted-foreground mt-1">Encrypted before storage and never returned to this page.</p></div>
        <div><Label>Location / branch</Label><Input value={form.location} onChange={e=>setForm({...form,location:e.target.value})} placeholder="Nimruz" /></div>
        <div><Label>Movie cache limit (GB)</Label><Input type="number" value={form.cache_limit_gb} onChange={e=>setForm({...form,cache_limit_gb:Number(e.target.value)})} /></div>
        <div className="md:col-span-2 flex items-center gap-2"><Switch checked={form.is_default} onCheckedChange={v=>setForm({...form,is_default:v})} disabled={form.role !== 'main'} /><Label>Default Main CDN fallback</Label></div>
        <div className="md:col-span-2 flex justify-end gap-2"><Button variant="outline" onClick={()=>setShowForm(false)}>Cancel</Button><Button onClick={addNode}>Save server</Button></div>
      </CardContent></Card>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {nodes.map(node => (
          <Card key={node.id} className="bg-card border-border">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium text-foreground">{node.name}</h3>
                <div className="flex gap-2"><Badge variant="outline">{node.role === 'main' ? 'Main CDN' : 'Cache'}</Badge><Badge variant={node.health_status === 'online' ? 'default' : 'secondary'}>{node.health_status}</Badge></div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm"><span className="text-muted-foreground">Host</span><span>{node.host}:{node.ssh_port}</span><span className="text-muted-foreground">Location</span><span>{node.location || '—'}</span><span className="text-muted-foreground">Provisioning</span><span>{node.provision_status}</span><span className="text-muted-foreground">Disk free</span><span>{node.disk_free_bytes ? `${(node.disk_free_bytes/1024**3).toFixed(1)} GB` : 'Awaiting heartbeat'}</span><span className="text-muted-foreground">Cache objects / hit</span><span>{node.cached_objects.toLocaleString()} / {node.hit_rate ?? '—'}%</span><span className="text-muted-foreground">Version / RTT</span><span>{node.software_version || '—'} / {node.rtt_ms ?? '—'} ms</span></div>
              <div className="flex flex-wrap gap-2 mt-4"><Button size="sm" variant="outline" onClick={()=>action(node,'provision')}>Provision</Button><Button size="sm" variant="outline" onClick={()=>action(node,'upgrade')}>Upgrade</Button><Button size="sm" variant="outline" onClick={()=>action(node,'drain')}>Drain</Button><Button size="sm" variant="outline" onClick={()=>action(node,'clear-cache')}>Clear cache</Button><Button size="sm" variant="destructive" onClick={()=>action(node,'disable')}>Disable</Button></div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card><CardHeader><CardTitle className="text-base">IP-prefix routing</CardTitle><p className="text-sm text-muted-foreground">Longest prefix wins, then lowest priority number; otherwise the default Main CDN is used.</p></CardHeader><CardContent className="space-y-4"><div className="grid gap-3 md:grid-cols-4"><Input placeholder="103.126.4.0/24" value={route.cidr} onChange={e=>setRoute({...route,cidr:e.target.value})}/><Select value={route.node_id} onValueChange={v=>setRoute({...route,node_id:v})}><SelectTrigger><SelectValue placeholder="Preferred server" /></SelectTrigger><SelectContent>{nodes.map(n=><SelectItem key={n.id} value={n.id}>{n.name}</SelectItem>)}</SelectContent></Select><Input type="number" value={route.priority} onChange={e=>setRoute({...route,priority:Number(e.target.value)})}/><Button onClick={addRoute}>Add routing rule</Button></div><Table><TableHeader><TableRow><TableHead>Prefix</TableHead><TableHead>Preferred server</TableHead><TableHead>Priority</TableHead><TableHead>Status</TableHead></TableRow></TableHeader><TableBody>{routes.map(r=><TableRow key={r.id}><TableCell className="font-mono">{r.cidr}</TableCell><TableCell>{r.node_name}</TableCell><TableCell>{r.priority}</TableCell><TableCell><Badge variant={r.enabled?'default':'secondary'}>{r.enabled?'Enabled':'Disabled'}</Badge></TableCell></TableRow>)}</TableBody></Table></CardContent></Card>
    </div>
  );
}

// ============ USERS MANAGEMENT ============
function UsersSection() {
  const [search, setSearch] = useState('');
  const filtered = users.filter(u => !search || u.name.toLowerCase().includes(search.toLowerCase()) || u.username.includes(search));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search users..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
        </div>
      </div>
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Username</TableHead><TableHead>Name</TableHead><TableHead>Branch</TableHead><TableHead>Status</TableHead><TableHead>Package</TableHead><TableHead>Devices</TableHead><TableHead>Last Active</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(user => (
                <TableRow key={user.id}>
                  <TableCell className="font-mono text-xs">{user.username}</TableCell>
                  <TableCell className="font-medium">{user.name}</TableCell>
                  <TableCell>{user.branch}</TableCell>
                  <TableCell><Badge variant={user.status === 'active' ? 'default' : user.status === 'expired' ? 'secondary' : 'destructive'} className="text-xs">{user.status}</Badge></TableCell>
                  <TableCell className="text-xs">{user.package}</TableCell>
                  <TableCell>{user.devices}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{user.lastActivity}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ BRANCHES ============
function BranchesSection() {
  return (
    <div className="space-y-4">
      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Branch</TableHead><TableHead>Code</TableHead><TableHead>CDN</TableHead><TableHead>Active Users</TableHead><TableHead>Viewers</TableHead><TableHead>Traffic</TableHead><TableHead>CDN Status</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {branches.map(branch => (
                <TableRow key={branch.id}>
                  <TableCell className="font-medium">{branch.name}</TableCell>
                  <TableCell className="font-mono text-xs">{branch.code}</TableCell>
                  <TableCell className="text-sm">{branch.cdn}</TableCell>
                  <TableCell>{branch.activeUsers.toLocaleString()}</TableCell>
                  <TableCell>{branch.concurrentViewers.toLocaleString()}</TableCell>
                  <TableCell>{branch.streamingTraffic}</TableCell>
                  <TableCell><Badge variant={branch.cdnStatus === 'healthy' ? 'default' : 'destructive'} className="text-xs">{branch.cdnStatus}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ============ REPORTS ============
function ReportsSection() {
  const reportTypes = [
    { name: 'Popular Movies', description: 'Most watched movies this month', icon: Film },
    { name: 'Popular Series', description: 'Most watched series this month', icon: Tv },
    { name: 'Watch Time', description: 'Total viewing hours by branch', icon: Clock },
    { name: 'Concurrent Viewers', description: 'Peak concurrent viewers over time', icon: Eye },
    { name: 'Traffic by Branch', description: 'Streaming traffic distribution', icon: GitBranch },
    { name: 'Traffic by CDN', description: 'CDN node utilization', icon: Server },
    { name: 'Quality Usage', description: 'Video quality preferences', icon: Activity },
    { name: 'Device Types', description: 'User device distribution', icon: Users },
    { name: 'Failed Playback', description: 'Playback error analysis', icon: AlertTriangle },
    { name: 'Search Terms', description: 'Most searched content', icon: Search },
    { name: 'Storage Growth', description: 'Storage usage over time', icon: HardDrive },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {reportTypes.map(report => (
          <Card key={report.name} className="bg-card border-border hover:bg-card/80 cursor-pointer transition-colors">
            <CardContent className="pt-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <report.icon className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-medium text-foreground text-sm">{report.name}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{report.description}</p>
                </div>
              </div>
              <Button variant="outline" size="sm" className="w-full mt-3 text-xs">Export CSV</Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ SETTINGS ============
function SettingsSection() {
  const [r2, setR2] = useState({ enabled: false, endpoint_url: '', account_id: '', bucket: '', region: 'auto', access_key_id: '', secret_access_key: '', credentials_configured: false });
  const [message, setMessage] = useState('');
  useEffect(() => { adminApi.getR2().then(v => setR2({...r2, ...v, account_id:v.account_id || ''})).catch(()=>setMessage('Sign in with Settings permission to manage R2.')); }, []);
  const saveR2 = async () => { try { const saved = await adminApi.updateR2(r2); setR2({...r2, ...saved, access_key_id:'', secret_access_key:''}); setMessage('R2 settings saved securely.'); } catch (e:any) { setMessage(e?.response?.data?.detail || 'Unable to save R2 settings'); } };
  const settingsGroups = [
    { title: 'General', items: ['Platform Name', 'Default Language', 'Maintenance Mode'] },
    { title: 'Playback', items: ['Default Quality', 'Auto-play', 'Skip Intro Duration', 'Buffer Size'] },
    { title: 'Users', items: ['Max Devices per User', 'Session Timeout', 'Registration Mode'] },
    { title: 'CDN', items: ['Routing Strategy', 'Cache TTL', 'Sync Interval', 'Failover Mode'] },
    { title: 'Content', items: ['Age Rating System', 'Default Subtitle', 'Thumbnail Generation'] },
  ];

  return (
    <div className="space-y-6">
      <Card className="bg-card border-border"><CardHeader><CardTitle className="text-base">Cloudflare R2 hot tier</CardTitle><p className="text-sm text-muted-foreground">Optional private object-storage tier. Playback still requires iFilm entitlement and short-lived signed grants.</p></CardHeader><CardContent className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2 flex items-center justify-between rounded-lg border p-3"><div><Label>Enable R2 hot tier</Label><p className="text-xs text-muted-foreground">Credentials are encrypted and never returned.</p></div><Switch checked={r2.enabled} onCheckedChange={v=>setR2({...r2,enabled:v})}/></div>
        <div><Label>HTTPS endpoint</Label><Input value={r2.endpoint_url} onChange={e=>setR2({...r2,endpoint_url:e.target.value})} placeholder="https://ACCOUNT.r2.cloudflarestorage.com" /></div>
        <div><Label>Account ID</Label><Input value={r2.account_id} onChange={e=>setR2({...r2,account_id:e.target.value})} autoComplete="off" /></div>
        <div><Label>Bucket</Label><Input value={r2.bucket} onChange={e=>setR2({...r2,bucket:e.target.value})} /></div>
        <div><Label>Region</Label><Input value={r2.region} onChange={e=>setR2({...r2,region:e.target.value})} /></div>
        <div><Label>Access key ID {r2.credentials_configured && '(leave blank to keep existing)'}</Label><Input type="password" value={r2.access_key_id} onChange={e=>setR2({...r2,access_key_id:e.target.value})} autoComplete="new-password" /></div>
        <div><Label>Secret access key</Label><Input type="password" value={r2.secret_access_key} onChange={e=>setR2({...r2,secret_access_key:e.target.value})} autoComplete="new-password" /></div>
        <div className="md:col-span-2 flex items-center justify-between"><span className="text-sm text-muted-foreground">{message || (r2.credentials_configured ? 'Credentials configured' : 'Credentials not configured')}</span><Button onClick={saveR2}>Save R2 settings</Button></div>
      </CardContent></Card>
      {settingsGroups.map(group => (
        <Card key={group.title} className="bg-card border-border">
          <CardHeader><CardTitle className="text-base">{group.title}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {group.items.map(item => (
              <div key={item} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <span className="text-sm text-foreground">{item}</span>
                <Badge variant="outline" className="text-xs">Configured</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
