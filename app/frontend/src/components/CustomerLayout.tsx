import React, { createContext, useContext, useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Home, Film, Tv, Search, User, Bell, Menu, X, Globe, ChevronDown, Baby } from 'lucide-react';
import { translations } from '@/data/mockData';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { api, tokenStore } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';

// ============ LANGUAGE CONTEXT ============
type Lang = 'en' | 'fa' | 'ps';
interface LangContextType {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: typeof translations.en;
  dir: 'rtl' | 'ltr';
}

const LangContext = createContext<LangContextType>({
  lang: 'fa',
  setLang: () => {},
  t: translations.fa,
  dir: 'rtl',
});

export const useLang = () => useContext(LangContext);

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>('fa');
  const dir = lang === 'en' ? 'ltr' : 'rtl';
  const t = translations[lang];

  useEffect(() => {
    document.documentElement.setAttribute('dir', dir);
    document.documentElement.setAttribute('lang', lang);
    // Apply dark mode by default for the streaming platform
    document.documentElement.classList.add('dark');
  }, [dir, lang]);

  return (
    <LangContext.Provider value={{ lang, setLang, t, dir }}>
      {children}
    </LangContext.Provider>
  );
}

// ============ AUTH CONTEXT ============
type AuthUser = { name: string; username: string; branch: string; package: string; expiration: string };

interface AuthContextType {
  isLoggedIn: boolean;
  login: (username?: string, password?: string, rememberDevice?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  user: AuthUser | null;
}

const AuthContext = createContext<AuthContextType>({
  isLoggedIn: false,
  login: async () => {},
  logout: async () => {},
  user: null,
});

export const useAuth = () => useContext(AuthContext);

const mockUser: AuthUser = {
  name: 'Ahmad Karimi',
  username: 'mobin_user_001',
  branch: 'Kabul',
  package: 'Premium 50Mbps',
  expiration: '2025-03-15',
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const mockMode = isMockMode();
  const [user, setUser] = useState<AuthUser | null>(() => (mockMode ? mockUser : null));
  const [isLoggedIn, setIsLoggedIn] = useState(mockMode);

  useEffect(() => {
    if (mockMode) return;
    let cancelled = false;
    (async () => {
      if (!tokenStore.get()) {
        if (!cancelled) {
          setUser(null);
          setIsLoggedIn(false);
        }
        return;
      }
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser({
          name: me.name || me.username,
          username: me.username,
          branch: me.branch,
          package: me.package,
          expiration: me.expiration,
        });
        setIsLoggedIn(true);
      } catch {
        tokenStore.clear();
        if (!cancelled) {
          setUser(null);
          setIsLoggedIn(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mockMode]);

  const login = async (username?: string, password?: string, rememberDevice = false) => {
    if (mockMode) {
      if (username && password && !(username === 'mobin_user_001' && password === 'password')) {
        throw new Error('Invalid username or password');
      }
      setUser(mockUser);
      setIsLoggedIn(true);
      return;
    }

    if (!username || !password) throw new Error('Username and password are required');
    try {
      await api.login(username, password, rememberDevice);
      const me = await api.me();
      setUser({
        name: me.name || me.username,
        username: me.username,
        branch: me.branch,
        package: me.package,
        expiration: me.expiration,
      });
      setIsLoggedIn(true);
    } catch (error) {
      tokenStore.clear();
      setUser(null);
      setIsLoggedIn(false);
      throw error;
    }
  };

  const logout = async () => {
    if (!mockMode) {
      try {
        await api.logout();
      } catch {
        tokenStore.clear();
      }
    }
    setIsLoggedIn(false);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ isLoggedIn, login, logout, user: isLoggedIn ? user : null }}>
      {children}
    </AuthContext.Provider>
  );
}

// ============ CUSTOMER LAYOUT ============
export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  const { t, lang, setLang, dir } = useLang();
  const location = useLocation();
  const navigate = useNavigate();
  const { isLoggedIn, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navItems = [
    { path: '/', label: t.nav.home, icon: Home },
    { path: '/movies', label: t.nav.movies, icon: Film },
    { path: '/series', label: t.nav.series, icon: Tv },
    { path: '/children', label: t.nav.children, icon: Baby },
    { path: '/watchlist', label: t.nav.myList, icon: null },
  ];

  const langLabel = lang === 'en' ? 'English' : lang === 'fa' ? 'فارسی' : 'پښتو';

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop Header */}
      <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled ? 'bg-background/95 backdrop-blur-md shadow-lg' : 'bg-gradient-to-b from-background/80 to-transparent'}`}>
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 md:h-20">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <span className="text-2xl md:text-3xl font-serif text-primary font-bold tracking-tight">Mobin Play</span>
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${location.pathname === item.path ? 'text-primary' : 'text-foreground/70 hover:text-foreground'}`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* Right Actions */}
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={() => navigate('/search')} className="text-foreground/70 hover:text-foreground">
                <Search className="h-5 w-5" />
              </Button>

              {/* Language Switcher */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="text-foreground/70 hover:text-foreground gap-1">
                    <Globe className="h-4 w-4" />
                    <span className="hidden sm:inline text-xs">{langLabel}</span>
                    <ChevronDown className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
                  <DropdownMenuItem onClick={() => setLang('fa')}>فارسی (Dari)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('ps')}>پښتو (Pashto)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('en')}>English</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button variant="ghost" size="icon" className="text-foreground/70 hover:text-foreground hidden sm:flex">
                <Bell className="h-5 w-5" />
              </Button>

              {/* Profile */}
              {isLoggedIn ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="text-foreground/70 hover:text-foreground">
                      <User className="h-5 w-5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
                    <DropdownMenuItem onClick={() => navigate('/profile')}>{t.profile.title}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/devices')}>{t.profile.devices}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/watchlist')}>{t.profile.watchlist}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/history')}>{t.profile.history}</DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => {
                        void logout().finally(() => navigate('/login'));
                      }}
                    >
                      {t.profile.logout}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Button size="sm" onClick={() => navigate('/login')} className="bg-primary text-primary-foreground hover:bg-primary/90">
                  {t.login.signIn}
                </Button>
              )}

              {/* Mobile Menu */}
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="md:hidden text-foreground/70">
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side={dir === 'rtl' ? 'right' : 'left'} className="bg-background border-border">
                  <div className="flex flex-col gap-4 mt-8">
                    {navItems.map((item) => (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`px-4 py-3 rounded-lg text-base font-medium transition-colors ${location.pathname === item.path ? 'bg-primary/10 text-primary' : 'text-foreground/70 hover:text-foreground hover:bg-muted'}`}
                      >
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="pt-16 md:pt-20 pb-20 md:pb-0">
        {children}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden bg-background/95 backdrop-blur-md border-t border-border">
        <div className="flex items-center justify-around h-16">
          {[
            { path: '/', icon: Home, label: t.nav.home },
            { path: '/movies', icon: Film, label: t.nav.movies },
            { path: '/series', icon: Tv, label: t.nav.series },
            { path: '/search', icon: Search, label: t.nav.search },
            { path: '/profile', icon: User, label: t.nav.profile },
          ].map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center gap-1 px-3 py-2 ${location.pathname === item.path ? 'text-primary' : 'text-muted-foreground'}`}
            >
              <item.icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{item.label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}