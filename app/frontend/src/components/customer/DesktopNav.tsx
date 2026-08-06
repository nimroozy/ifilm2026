import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { useLang } from '@/components/CustomerLayout';
import {
  DESKTOP_NAV_ITEMS,
  DESKTOP_NAV_PRIMARY_IDS,
  isNavActive,
  type CustomerNavId,
  type CustomerNavItem,
} from '@/components/customer/navConfig';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useMediaQuery } from '@/hooks/use-media-query';
import { cn } from '@/lib/utils';

function navLabel(id: CustomerNavId, t: ReturnType<typeof useLang>['t']): string {
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

function NavLinkItem({
  item,
  label,
  active,
}: {
  item: CustomerNavItem;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      to={item.path}
      aria-current={active ? 'page' : undefined}
      data-testid={`desktop-nav-${item.id}`}
      data-active={active ? 'true' : 'false'}
      className={cn(
        'shrink-0 whitespace-nowrap rounded-md px-2.5 py-2 text-sm font-medium transition-colors lg:px-3',
        active ? 'bg-primary/10 text-primary' : 'text-foreground/70 hover:text-foreground'
      )}
    >
      {label}
    </Link>
  );
}

/**
 * Desktop catalog nav.
 * Below 2xl, secondary destinations collapse into More to avoid header overflow.
 * At 2xl+, all destinations render inline with horizontal scroll as a safety net.
 */
export function DesktopNav({ className }: { className?: string }) {
  const { t, dir } = useLang();
  const location = useLocation();
  const isWide = useMediaQuery('(min-width: 1536px)');

  const items = DESKTOP_NAV_ITEMS;
  const { visible, overflowItems } = useMemo(() => {
    if (isWide) {
      return { visible: items, overflowItems: [] as CustomerNavItem[] };
    }
    return {
      visible: items.filter((item) => DESKTOP_NAV_PRIMARY_IDS.includes(item.id)),
      overflowItems: items.filter((item) => !DESKTOP_NAV_PRIMARY_IDS.includes(item.id)),
    };
  }, [isWide, items]);

  const overflowActive = overflowItems.some((item) => isNavActive(location.pathname, item));

  return (
    <nav
      aria-label={t.nav.menu}
      data-testid="desktop-nav"
      className={cn('hidden min-w-0 flex-1 items-center justify-center md:flex', className)}
    >
      <div
        className="flex max-w-full items-center gap-0.5 overflow-x-auto overscroll-x-contain [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        data-testid="desktop-nav-visible"
      >
        {visible.map((item) => (
          <NavLinkItem
            key={item.id}
            item={item}
            label={navLabel(item.id, t)}
            active={isNavActive(location.pathname, item)}
          />
        ))}
        {overflowItems.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                data-testid="desktop-nav-more"
                aria-haspopup="menu"
                aria-label={t.nav.more}
                className={cn(
                  'shrink-0 gap-1 text-sm font-medium',
                  overflowActive ? 'bg-primary/10 text-primary' : 'text-foreground/70'
                )}
              >
                {t.nav.more}
                <ChevronDown className="h-3 w-3" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'} data-testid="desktop-nav-more-menu">
              {overflowItems.map((item) => {
                const active = isNavActive(location.pathname, item);
                return (
                  <DropdownMenuItem key={item.id} asChild>
                    <Link
                      to={item.path}
                      aria-current={active ? 'page' : undefined}
                      data-testid={`desktop-nav-more-${item.id}`}
                      data-active={active ? 'true' : 'false'}
                      className={cn(active && 'text-primary')}
                    >
                      {navLabel(item.id, t)}
                    </Link>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </nav>
  );
}
