import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Film,
  Tv,
  Tags,
  Bookmark,
  Upload,
  Cpu,
  PlayCircle,
  Database,
  Menu,
  LogOut,
  ArrowUpCircle,
  HardDrive,
  Sparkles,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { adminApi, tokenStore, type AdminUserDto } from '@/lib/api';

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const navGroups: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    label: 'Catalog',
    items: [
      { to: '/admin/movies', label: 'Movies', icon: Film },
      { to: '/admin/series', label: 'Series', icon: Tv },
      { to: '/admin/genres', label: 'Genres', icon: Tags },
      { to: '/admin/collections', label: 'Collections', icon: Bookmark },
    ],
  },
  {
    label: 'Media',
    items: [
      { to: '/admin/tools/upload', label: 'Upload', icon: Upload },
      { to: '/admin/media/storage-health', label: 'Storage Health', icon: HardDrive },
      { to: '/admin/media/processing', label: 'Processing', icon: Cpu },
      { to: '/admin/media/playback-sessions', label: 'Playback Sessions', icon: PlayCircle },
    ],
  },
  {
    label: 'Metadata',
    items: [
      { to: '/admin/tools/tmdb', label: 'TMDB Import', icon: Database },
      { to: '/admin/tools/recommendations', label: 'Recommendations', icon: Sparkles },
    ],
  },
  {
    label: 'System',
    items: [{ to: '/admin/system/updates', label: 'Updates', icon: ArrowUpCircle }],
  },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [admin, setAdmin] = useState<AdminUserDto | null>(null);
  const [versionLabel, setVersionLabel] = useState<string | null>(null);
  const [envBadge, setEnvBadge] = useState<string | null>(null);

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
            if (!cancelled) {
              const label = String(v.version || '').trim();
              setVersionLabel(label && label !== 'undefined' ? label : null);
              setEnvBadge(v.deployment_mode || v.update_channel || null);
            }
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
        <h2 className="font-display text-xl font-bold tracking-tight text-foreground">iFilm</h2>
        <p className="mt-1 text-xs text-muted-foreground">Content Operations</p>
        {envBadge ? (
          <Badge variant="outline" className="mt-2 text-[10px] uppercase" data-testid="admin-env-badge">
            {envBadge}
          </Badge>
        ) : null}
      </div>
      {admin && (
        <div className="border-b border-border p-3">
          <p className="truncate text-sm font-medium text-foreground">
            {admin.full_name || admin.username}
          </p>
          <p className="truncate text-xs text-muted-foreground">{admin.role_name || 'Admin'}</p>
        </div>
      )}
      <nav className="flex-1 space-y-4 overflow-y-auto p-2" aria-label="Admin">
        {navGroups.map((group) => (
          <div key={group.label}>
            <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `flex w-full flex-row items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      isActive
                        ? 'bg-primary/15 text-primary'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
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
      className="min-h-screen bg-background text-left"
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

      {/*
        Use padding (not margin) so main content width stays within the viewport.
        `w-full` + `lg:ml-64` previously made content 100vw+16rem and clipped actions.
      */}
      <div
        className="flex min-h-screen min-w-0 w-full max-w-full flex-col lg:pl-64"
        data-testid="admin-content-wrapper"
      >
        <header className="sticky top-0 z-40 flex h-14 min-w-0 items-center justify-between gap-3 border-b border-border bg-background/95 px-4 backdrop-blur-md lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0 lg:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open admin menu"
              data-testid="admin-mobile-menu-button"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <h1 className="truncate text-lg font-semibold text-foreground">iFilm Admin</h1>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {admin?.role_name && (
              <Badge variant="outline" className="text-xs">
                {admin.role_name}
              </Badge>
            )}
          </div>
        </header>
        <main className="min-w-0 max-w-full flex-1 overflow-x-hidden p-4 sm:p-5 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
