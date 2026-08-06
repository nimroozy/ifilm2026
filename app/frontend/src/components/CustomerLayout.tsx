import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Home, Film, Tv, Search, User, Bell, Menu, Globe, ChevronDown } from 'lucide-react';
import { translations } from '@/data/mockData';
import { Sheet, SheetContent, SheetTrigger, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { api, tokenStore } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import {
  type AppLocale,
  localeDir,
  readStoredLocale,
  writeStoredLocale,
} from '@/lib/locale';
import { DesktopNav } from '@/components/customer/DesktopNav';
import CustomerFooter from '@/components/customer/CustomerFooter';
import {
  DESKTOP_NAV_ITEMS,
  MOBILE_BOTTOM_NAV,
  FOOTER_COMPANY_PATHS,
  FOOTER_LEGAL_PATHS,
  isNavActive,
  type CustomerNavId,
} from '@/components/customer/navConfig';
import { cn } from '@/lib/utils';

// ============ LANGUAGE CONTEXT ============
type Lang = AppLocale;
interface LangContextType {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: typeof translations.en;
  dir: 'rtl' | 'ltr';
}

const LangContext = createContext<LangContextType>({
  lang: 'en',
  setLang: () => {},
  t: translations.en,
  dir: 'ltr',
});

export const useLang = () => useContext(LangContext);

export function LangProvider({ children }: { children: React.ReactNode }) {
  // Synchronous init from persisted storage — no browser-language default, no fa flash.
  const [lang, setLangState] = useState<Lang>(() => readStoredLocale());
  const dir = localeDir(lang);
  const t = translations[lang];

  const setLang = useCallback((next: Lang) => {
    writeStoredLocale(next);
    setLangState(next);
  }, []);

  // Document lang/dir are owned exclusively by DocumentLangSync (router-aware)
  // so /admin stays LTR without racing window.location vs MemoryRouter.
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  return (
    <LangContext.Provider value={{ lang, setLang, t, dir }}>
      {children}
    </LangContext.Provider>
  );
}

// ============ AUTH CONTEXT ============
type AuthUser = {
  name: string;
  username: string;
  branch: string;
  package: string;
  expiration: string;
  status: string;
  serviceStatus: string;
  maxDevices: number;
  entitlementAllowed?: boolean;
  denialCode?: string | null;
  safeReason?: string | null;
};

interface AuthContextType {
  isLoggedIn: boolean;
  login: (username?: string, password?: string, rememberDevice?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  user: AuthUser | null;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  isLoggedIn: false,
  login: async () => {},
  logout: async () => {},
  user: null,
  refreshProfile: async () => {},
});

export const useAuth = () => useContext(AuthContext);

const mockUser: AuthUser = {
  name: 'Ahmad Karimi',
  username: 'mobin_user_001',
  branch: 'Kabul',
  package: 'Premium 50Mbps',
  expiration: '2025-03-15',
  status: 'active',
  serviceStatus: 'active',
  maxDevices: 3,
  entitlementAllowed: true,
};

function mapSubscriber(me: {
  name: string;
  username: string;
  branch: string;
  package: string;
  expiration: string;
  status: string;
  service_status?: string;
  max_devices?: number;
}, entitlement?: {
  allowed: boolean;
  denial_code?: string | null;
  safe_reason?: string | null;
  max_devices?: number;
} | null): AuthUser {
  return {
    name: me.name || me.username,
    username: me.username,
    branch: me.branch,
    package: me.package,
    expiration: me.expiration,
    status: me.status,
    serviceStatus: me.service_status || 'unknown',
    maxDevices: entitlement?.max_devices ?? me.max_devices ?? 3,
    entitlementAllowed: entitlement?.allowed,
    denialCode: entitlement?.denial_code,
    safeReason: entitlement?.safe_reason,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const mockMode = isMockMode();
  const [user, setUser] = useState<AuthUser | null>(() => (mockMode ? mockUser : null));
  const [isLoggedIn, setIsLoggedIn] = useState(mockMode);

  const refreshProfile = async () => {
    if (mockMode) return;
    if (!tokenStore.get()) {
      setUser(null);
      setIsLoggedIn(false);
      return;
    }
    const me = await api.me();
    let entitlement = null;
    try {
      entitlement = await api.entitlement();
    } catch {
      entitlement = null;
    }
    setUser(mapSubscriber(me, entitlement));
    setIsLoggedIn(true);
  };

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
        await refreshProfile();
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
      await refreshProfile();
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
        /* still clear local state */
      }
      tokenStore.clear();
    }
    setIsLoggedIn(false);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ isLoggedIn, login, logout, user: isLoggedIn ? user : null, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

// ============ CUSTOMER LAYOUT ============
function customerNavLabel(id: CustomerNavId, t: typeof translations.en): string {
  const map: Record<CustomerNavId, string> = {
    home: t.nav.home,
    movies: t.nav.movies,
    series: t.nav.series,
    children: t.nav.children,
    genres: t.nav.genres,
    dubbed: t.nav.dubbed,
    subtitled: t.nav.subtitled,
    newReleases: t.nav.newReleases,
    myList: t.nav.myList,
    search: t.nav.search,
    profile: t.nav.profile,
  };
  return map[id];
}

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  const { t, lang, setLang, dir } = useLang();
  const location = useLocation();
  const navigate = useNavigate();
  const { isLoggedIn, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const langLabel = lang === 'en' ? 'English' : lang === 'fa' ? 'فارسی' : 'پښتو';
  const bottomIcons = {
    home: Home,
    movies: Film,
    series: Tv,
    search: Search,
    profile: User,
  } as const;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header
        className={cn(
          'fixed left-0 right-0 top-0 z-50 transition-all duration-300',
          scrolled
            ? 'bg-background/95 shadow-lg backdrop-blur-md'
            : 'bg-gradient-to-b from-background/80 to-transparent'
        )}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-3 md:h-20">
            <Link
              to="/"
              className="shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="iFilm"
            >
              <span className="font-display text-2xl font-bold tracking-tight text-primary md:text-3xl">
                iFilm
              </span>
            </Link>

            <DesktopNav />

            <div className="flex shrink-0 items-center gap-1 sm:gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => navigate('/search')}
                className="text-foreground/70 hover:text-foreground"
                aria-label={t.nav.search}
              >
                <Search className="h-5 w-5" />
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1 text-foreground/70 hover:text-foreground"
                    aria-label={langLabel}
                  >
                    <Globe className="h-4 w-4" />
                    <span className="hidden text-xs sm:inline">{langLabel}</span>
                    <ChevronDown className="h-3 w-3" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
                  <DropdownMenuItem onClick={() => setLang('fa')}>فارسی (Dari)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('ps')}>پښتو (Pashto)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('en')}>English</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                variant="ghost"
                size="icon"
                className="hidden text-foreground/70 hover:text-foreground sm:flex"
                aria-label={t.nav.notifications}
              >
                <Bell className="h-5 w-5" />
              </Button>

              {isLoggedIn ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-foreground/70 hover:text-foreground"
                      aria-label={t.nav.profile}
                    >
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
                <Button
                  size="sm"
                  onClick={() => navigate('/login')}
                  className="bg-primary text-primary-foreground hover:bg-primary/90"
                >
                  {t.login.signIn}
                </Button>
              )}

              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-foreground/70 md:hidden"
                    aria-label={t.nav.openMenu}
                    data-testid="mobile-nav-trigger"
                  >
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent
                  side={dir === 'rtl' ? 'right' : 'left'}
                  className="overflow-y-auto border-border bg-background"
                  data-testid="mobile-nav-sheet"
                >
                  <SheetTitle className="font-display text-lg text-primary">iFilm</SheetTitle>
                  <SheetDescription className="sr-only">{t.nav.menu}</SheetDescription>
                  <nav aria-label={t.nav.menu} className="mt-6 flex flex-col gap-1">
                    {DESKTOP_NAV_ITEMS.map((item) => {
                      const active = isNavActive(location.pathname, item);
                      return (
                        <Link
                          key={item.path}
                          to={item.path}
                          aria-current={active ? 'page' : undefined}
                          data-testid={`mobile-nav-${item.id}`}
                          data-active={active ? 'true' : 'false'}
                          className={cn(
                            'rounded-lg px-4 py-3 text-base font-medium transition-colors',
                            active
                              ? 'bg-primary/10 text-primary'
                              : 'text-foreground/70 hover:bg-muted hover:text-foreground'
                          )}
                        >
                          {customerNavLabel(item.id, t)}
                        </Link>
                      );
                    })}
                  </nav>
                  <div className="mt-8 border-t border-border pt-4">
                    <p className="px-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t.footer.company}
                    </p>
                    <div className="mt-2 flex flex-col gap-1">
                      {[...FOOTER_COMPANY_PATHS, ...FOOTER_LEGAL_PATHS].map((item) => (
                        <Link
                          key={item.path}
                          to={item.path}
                          data-testid={`mobile-footer-${item.id}`}
                          className="rounded-lg px-4 py-2 text-sm text-foreground/70 hover:bg-muted hover:text-foreground"
                        >
                          {(t.footer as Record<string, string>)[item.id] || item.id}
                        </Link>
                      ))}
                    </div>
                  </div>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-16 md:pb-0 md:pt-20">{children}</main>

      <div className="pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0">
        <CustomerFooter />
      </div>

      <nav
        className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
        aria-label={t.nav.menu}
        data-testid="mobile-bottom-nav"
      >
        <div className="flex h-16 items-center justify-around">
          {MOBILE_BOTTOM_NAV.map((item) => {
            const Icon = bottomIcons[item.id as keyof typeof bottomIcons] || Home;
            const active = isNavActive(location.pathname, item);
            return (
              <Link
                key={item.path}
                to={item.path}
                aria-current={active ? 'page' : undefined}
                data-testid={`bottom-nav-${item.id}`}
                data-active={active ? 'true' : 'false'}
                className={cn(
                  'flex min-w-[3.5rem] flex-col items-center gap-1 px-2 py-2',
                  active ? 'text-primary' : 'text-muted-foreground'
                )}
              >
                <Icon className="h-5 w-5" aria-hidden />
                <span className="text-[10px] font-medium">{customerNavLabel(item.id, t)}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}