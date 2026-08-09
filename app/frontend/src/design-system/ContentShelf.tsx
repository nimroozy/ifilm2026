import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SectionHeader } from '@/design-system/SectionHeader';

export interface ContentShelfProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  'aria-label'?: string;
  testId?: string;
  /** Optional See all destination. */
  seeAllHref?: string;
  seeAllLabel?: string;
}

/** Avoid importing CustomerLayout (circular). Track document dir for RTL rails. */
function useDocumentDir(): 'rtl' | 'ltr' {
  const [dir, setDir] = useState<'rtl' | 'ltr'>(() =>
    typeof document !== 'undefined' && document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
  );
  useEffect(() => {
    const el = document.documentElement;
    const sync = () => setDir(el.dir === 'rtl' ? 'rtl' : 'ltr');
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(el, { attributes: true, attributeFilter: ['dir'] });
    return () => mo.disconnect();
  }, []);
  return dir;
}

/** Streaming carousel rail — manual scroll only; RTL-aware arrows. */
export function ContentShelf({
  title,
  subtitle,
  children,
  className,
  'aria-label': ariaLabel,
  testId = 'content-shelf',
  seeAllHref,
  seeAllLabel,
}: ContentShelfProps) {
  const rtl = useDocumentDir() === 'rtl';
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollStart, setCanScrollStart] = useState(false);
  const [canScrollEnd, setCanScrollEnd] = useState(false);

  const updateOverflow = useCallback(() => {
    const node = scrollRef.current;
    if (!node) {
      setCanScrollStart(false);
      setCanScrollEnd(false);
      return;
    }
    const max = node.scrollWidth - node.clientWidth;
    const overflow = max > 8;
    // In RTL, scrollLeft semantics vary; use abs + compare to ends.
    const left = node.scrollLeft;
    if (rtl) {
      // Most Chromium: scrollLeft is 0 or negative at start.
      setCanScrollStart(overflow && Math.abs(left) > 4);
      setCanScrollEnd(overflow && Math.abs(left) < max - 4);
    } else {
      setCanScrollStart(overflow && left > 4);
      setCanScrollEnd(overflow && left < max - 4);
    }
  }, [rtl]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    updateOverflow();
    const onScroll = () => updateOverflow();
    node.addEventListener('scroll', onScroll, { passive: true });
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => updateOverflow()) : null;
    ro?.observe(node);
    window.addEventListener('resize', updateOverflow);
    return () => {
      node.removeEventListener('scroll', onScroll);
      ro?.disconnect();
      window.removeEventListener('resize', updateOverflow);
    };
  }, [updateOverflow, children]);

  const scrollByDir = (towardEnd: boolean) => {
    const node = scrollRef.current;
    if (!node) return;
    const amount = Math.max(320, Math.floor(node.clientWidth * 0.85));
    const sign = towardEnd ? 1 : -1;
    // Physical left is negative scrollLeft delta in LTR; invert for RTL.
    const delta = (rtl ? -sign : sign) * amount;
    node.scrollBy({ left: delta, behavior: 'smooth' });
  };

  const showArrows = canScrollStart || canScrollEnd;

  return (
    <section
      className={cn('relative overflow-x-clip py-3 md:py-5', className)}
      aria-label={ariaLabel || title}
      data-testid={testId}
    >
      <SectionHeader title={title} subtitle={subtitle} seeAllHref={seeAllHref} seeAllLabel={seeAllLabel} />
      <div className="group relative">
        {showArrows && canScrollStart ? (
          <button
            type="button"
            aria-label="Scroll previous"
            onClick={() => scrollByDir(false)}
            data-testid="shelf-scroll-prev"
            className="absolute start-1 top-[38%] z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-background/70 text-foreground opacity-0 shadow-lg backdrop-blur-md transition-opacity duration-normal hover:bg-background/90 group-hover:opacity-100 md:flex"
          >
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
        ) : null}
        <div
          ref={scrollRef}
          className="flex gap-3.5 overflow-x-auto scroll-smooth scroll-ps-4 scroll-pe-4 px-4 pb-2 sm:gap-5 sm:px-6 lg:px-8 hide-scrollbar snap-x snap-mandatory md:snap-none"
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault();
              scrollByDir(rtl);
            } else if (event.key === 'ArrowRight') {
              event.preventDefault();
              scrollByDir(!rtl);
            }
          }}
        >
          {children}
        </div>
        {showArrows && canScrollEnd ? (
          <button
            type="button"
            aria-label="Scroll next"
            onClick={() => scrollByDir(true)}
            data-testid="shelf-scroll-next"
            className="absolute end-1 top-[38%] z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-background/70 text-foreground opacity-0 shadow-lg backdrop-blur-md transition-opacity duration-normal hover:bg-background/90 group-hover:opacity-100 md:flex"
          >
            <ChevronRight className="h-5 w-5 rtl:rotate-180" />
          </button>
        ) : null}
      </div>
    </section>
  );
}
