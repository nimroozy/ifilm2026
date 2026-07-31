import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Film,
  Tv,
  Tags,
  Upload,
  Cpu,
  Server,
  Users,
  Menu,
  LogOut,
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
  { to: '/admin/tools/encoding', label: 'Encoding (soon)', icon: Cpu },
  { to: '/admin/tools/cdn', label: 'CDN (soon)', icon: Server },
  { to: '/admin/tools/users', label: 'Users (soon)', icon: Users },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [admin, setAdmin] = useState<AdminUserDto | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .me()
      .then((me) => {
        if (!cancelled) setAdmin(me);
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
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-border">
        <h2 className="text-xl font-serif font-bold text-primary">Mobin Play</h2>
        <p className="text-xs text-muted-foreground mt-1">Admin Panel</p>
      </div>
      {admin && (
        <div className="p-3 border-b border-border">
          <p className="text-sm font-medium text-foreground truncate">{admin.full_name || admin.username}</p>
          <p className="text-xs text-muted-foreground truncate">{admin.role_name || 'Admin'}</p>
        </div>
      )}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-border space-y-2">
        <Button variant="outline" size="sm" className="w-full gap-2" onClick={logout}>
          <LogOut className="h-3.5 w-3.5" />
          Logout
        </Button>
        <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate('/')}>
          ← Back to App
        </Button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex">
      <aside className="hidden lg:flex w-64 border-r border-border flex-col fixed h-full bg-card">
        <SidebarContent />
      </aside>

      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-64 p-0 bg-card">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      <div className="flex-1 lg:ml-64">
        <header className="sticky top-0 z-40 bg-background/95 backdrop-blur-md border-b border-border px-4 lg:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen(true)}
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
