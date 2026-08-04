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
}

/** Netflix-style horizontal rail with desktop peek arrows (only when overflow exists). */
export function ContentShelf({
  title,
  subtitle,
  children,
  className,
  'aria-label': ariaLabel,
  testId = 'content-shelf',
}: ContentShelfProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateOverflow = useCallback(() => {
    const node = scrollRef.current;
    if (!node) {
      setCanScrollLeft(false);
      setCanScrollRight(false);
      return;
    }
    const max = node.scrollWidth - node.clientWidth;
    const overflow = max > 8;
    setCanScrollLeft(overflow && node.scrollLeft > 4);
    setCanScrollRight(overflow && node.scrollLeft < max - 4);
  }, []);

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

  const scroll = (dir: 'left' | 'right') => {
    const node = scrollRef.current;
    if (!node) return;
    const amount = Math.max(320, Math.floor(node.clientWidth * 0.85));
    node.scrollBy({ left: dir === 'left' ? -amount : amount, behavior: 'smooth' });
  };

  const showArrows = canScrollLeft || canScrollRight;

  return (
    <section
      className={cn('relative overflow-x-clip py-4 md:py-6', className)}
      aria-label={ariaLabel || title}
      data-testid={testId}
    >
      <SectionHeader title={title} subtitle={subtitle} />
      <div className="group relative">
        {showArrows && canScrollLeft ? (
          <button
            type="button"
            aria-label="Scroll left"
            onClick={() => scroll('left')}
            className="absolute left-1 top-[38%] z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-background/70 text-foreground opacity-0 shadow-lg backdrop-blur-md transition-opacity duration-normal hover:bg-background/90 group-hover:opacity-100 md:flex"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
        ) : null}
        <div
          ref={scrollRef}
          className="flex gap-3 overflow-x-auto scroll-smooth px-4 pb-2 sm:gap-4 sm:px-6 lg:px-8 hide-scrollbar"
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault();
              scroll('left');
            } else if (event.key === 'ArrowRight') {
              event.preventDefault();
              scroll('right');
            }
          }}
        >
          {children}
        </div>
        {showArrows && canScrollRight ? (
          <button
            type="button"
            aria-label="Scroll right"
            onClick={() => scroll('right')}
            className="absolute right-1 top-[38%] z-10 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/10 bg-background/70 text-foreground opacity-0 shadow-lg backdrop-blur-md transition-opacity duration-normal hover:bg-background/90 group-hover:opacity-100 md:flex"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        ) : null}
      </div>
    </section>
  );
}
