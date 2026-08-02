import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Film,
  Tv,
  Tags,
  Upload,
  Cpu,
  PlayCircle,
  Database,
  Server,
  Users,
  Menu,
  LogOut,
  ArrowUpCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { adminApi, tokenStore, type AdminUserDto } from '@/lib/api';

const navItems = [
  { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/movies', label: 'Movies', icon: Film },
  { to: '/admin/series', label: 'Series', icon: Tv },
  { to: '/admin/genres', label: 'Genres', icon: Tags },
  { to: '/admin/tools/upload', label: 'Upload', icon: Upload },
  { to: '/admin/tools/tmdb', label: 'TMDB Import', icon: Database },
  { to: '/admin/media/processing', label: 'Processing', icon: Cpu },
  { to: '/admin/media/playback-sessions', label: 'Playback', icon: PlayCircle },
  { to: '/admin/system/updates', label: 'Updates', icon: ArrowUpCircle },
  { to: '/admin/tools/encoding', label: 'Encoding (legacy)', icon: Film },
  { to: '/admin/tools/cdn', label: 'CDN (soon)', icon: Server },
  { to: '/admin/tools/users', label: 'Users (soon)', icon: Users },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [admin, setAdmin] = useState<AdminUserDto | null>(null);
  const [versionLabel, setVersionLabel] = useState<string | null>(null);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'iFilm Admin';
    return () => {
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .me()
      .then((me) => {
        if (!cancelled) setAdmin(me);
        if ((me.permissions || []).includes('system_updates.read')) {
          return adminApi.getSystemVersion().then((v) => {
            if (!cancelled) setVersionLabel(`${v.version}`);
          });
        }
        return undefined;
      })
      .catch(() => {
        /* RequireAdmin handles auth failures */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function logout() {
    tokenStore.clearAdmin();
    navigate('/admin/login', { replace: true });
  }

  const SidebarContent = () => (
    <div className="flex h-full flex-col text-left" data-testid="admin-sidebar-content">
      <div className="border-b border-border p-4">
        <h2 className="font-serif text-xl font-bold text-primary">iFilm</h2>
        <p className="mt-1 text-xs text-muted-foreground">Admin Panel</p>
      </div>
      {admin && (
        <div className="border-b border-border p-3">
          <p className="truncate text-sm font-medium text-foreground">
            {admin.full_name || admin.username}
          </p>
          <p className="truncate text-xs text-muted-foreground">{admin.role_name || 'Admin'}</p>
        </div>
      )}
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex w-full flex-row items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`
            }
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="space-y-2 border-t border-border p-3">
        {versionLabel && (
          <p className="text-center text-[11px] text-muted-foreground" data-testid="admin-version">
            iFilm {versionLabel}
          </p>
        )}
        <Button variant="outline" size="sm" className="w-full gap-2" onClick={logout}>
          <LogOut className="h-3.5 w-3.5 shrink-0" />
          Logout
        </Button>
        <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate('/')}>
          ← Back to App
        </Button>
      </div>
    </div>
  );

  return (
    <div
      dir="ltr"
      lang="en"
      className="min-h-screen overflow-x-hidden bg-background text-left"
      data-testid="admin-layout-root"
    >
      <aside
        className="fixed left-0 top-0 z-30 hidden h-screen w-64 flex-col border-r border-border bg-card lg:flex"
        data-testid="admin-desktop-sidebar"
      >
        <SidebarContent />
      </aside>

      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent
          side="left"
          dir="ltr"
          lang="en"
          className="w-64 border-r border-border bg-card p-0 text-left"
          data-testid="admin-mobile-drawer"
        >
          <SidebarContent />
        </SheetContent>
      </Sheet>

      <div className="min-h-screen w-full lg:ml-64" data-testid="admin-content-wrapper">
        <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur-md lg:px-6">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open admin menu"
              data-testid="admin-mobile-menu-button"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <h1 className="text-lg font-semibold text-foreground">Catalog Admin</h1>
          </div>
          <div className="flex items-center gap-2">
            {admin?.role_name && (
              <Badge variant="outline" className="text-xs">
                {admin.role_name}
              </Badge>
            )}
          </div>
        </header>
        <main className="p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
