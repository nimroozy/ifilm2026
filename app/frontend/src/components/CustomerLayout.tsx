import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Home, Film, Tv, Search, User, Menu, Globe, ChevronDown } from 'lucide-react';
import { translations } from '@/data/translations';
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
  DESKTOP_NAV_MORE_IDS,
  DESKTOP_NAV_PRIMARY_IDS,
  MOBILE_BOTTOM_NAV,
  FOOTER_COMPANY_PATHS,
  FOOTER_LEGAL_PATHS,
  isNavActive,
  navItemById,
  type CustomerNavId,
} from '@/components/customer/navConfig';
import { surfaces } from '@/design-system/tokens';
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
  login: (
    username?: string,
    password?: string,
    rememberDevice?: boolean,
    branch?: string,
  ) => Promise<void>;
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

  const refreshEntitlement = async () => {
    if (mockMode || !tokenStore.get()) return;
    try {
      const entitlement = await api.entitlement();
      setUser((prev) =>
        prev
          ? {
              ...prev,
              maxDevices: entitlement.max_devices ?? prev.maxDevices,
              entitlementAllowed: entitlement.allowed,
              denialCode: entitlement.denial_code,
              safeReason: entitlement.safe_reason,
            }
          : prev
      );
    } catch {
      // Player re-checks entitlement; home must not block on this call.
    }
  };

  const refreshProfile = async (opts?: { includeEntitlement?: boolean }) => {
    if (mockMode) return;
    if (!tokenStore.get()) {
      setUser(null);
      setIsLoggedIn(false);
      return;
    }
    // Critical path: /me only. Entitlement is deferred so home/LCP is not blocked
    // by a second authenticated round-trip (Player still enforces entitlement).
    const me = await api.me();
    setUser(mapSubscriber(me, null));
    setIsLoggedIn(true);
    if (opts?.includeEntitlement) {
      await refreshEntitlement();
      return;
    }
    const schedule =
      typeof window !== 'undefined' && 'requestIdleCallback' in window
        ? (cb: () => void) => window.requestIdleCallback(cb, { timeout: 2500 })
        : (cb: () => void) => window.setTimeout(cb, 1200);
    schedule(() => {
      void refreshEntitlement();
    });
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

  const login = async (
    username?: string,
    password?: string,
    rememberDevice = false,
    branch?: string,
  ) => {
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
      if (branch) {
        await api.ispLogin(branch, username, password, rememberDevice);
      } else {
        await api.login(username, password, rememberDevice);
      }
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
    collections: t.nav.collections,
    dubbed: t.nav.dubbed,
    subtitled: t.nav.subtitled,
    newReleases: t.nav.newReleases,
    myList: t.nav.myList,
    whatToWatch: t.nav.whatToWatch,
    requestMovie: t.nav.requestMovie,
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
    const handleScroll = () => setScrolled(window.scrollY > 24);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
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
    <div className="flex min-h-screen flex-col bg-background" data-testid="customer-shell">
      <header
        data-testid="customer-header"
        data-scrolled={scrolled ? 'true' : 'false'}
        className={cn(
          'fixed inset-x-0 top-0 z-40 transition-[background-color,backdrop-filter,box-shadow,border-color] duration-normal',
          scrolled ? surfaces.headerScrolled : surfaces.headerTop
        )}
      >
        <div className="mx-auto w-full max-w-[90rem] px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between gap-3">
            <Link
              to="/"
              className="shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="iFilm"
            >
              <span className="font-display text-2xl font-bold tracking-tight text-primary md:text-[1.75rem]">
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
                data-testid="header-search"
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
                    data-testid="header-language"
                  >
                    <Globe className="h-4 w-4" />
                    <span className="hidden text-xs uppercase sm:inline">{lang}</span>
                    <ChevronDown className="h-3 w-3" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'} data-testid="header-language-menu">
                  <DropdownMenuItem onClick={() => setLang('fa')}>فارسی (Dari)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('ps')}>پښتو (Pashto)</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setLang('en')}>English</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

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
                    <DropdownMenuItem onClick={() => navigate('/request')}>{t.profile.requestMovie}</DropdownMenuItem>
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
                    {DESKTOP_NAV_PRIMARY_IDS.map((id) => {
                      const item = DESKTOP_NAV_ITEMS.find((row) => row.id === id);
                      if (!item) return null;
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
                    <p className="mt-4 px-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {t.nav.more}
                    </p>
                    {DESKTOP_NAV_MORE_IDS.map((id) => {
                      const item = navItemById(id);
                      if (!item) return null;
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

      <main className="flex-1 pb-[calc(4.5rem+env(safe-area-inset-bottom,0px))] pt-16 md:pb-0">
        {children}
      </main>

      <div className="pb-[calc(4.5rem+env(safe-area-inset-bottom,0px))] md:pb-0">
        <CustomerFooter />
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[hsl(222_26%_8%/0.94)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-md md:hidden"
        aria-label={t.nav.menu}
        data-testid="mobile-bottom-nav"
      >
        <div className="flex h-14 items-center justify-around">
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
                  'flex min-h-[44px] min-w-[3.5rem] flex-col items-center justify-center gap-0.5 px-2 py-1',
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