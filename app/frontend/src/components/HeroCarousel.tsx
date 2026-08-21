import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Info, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MetaChip, heroSizing, typography } from '@/design-system';
import { useAuth, useLang } from '@/components/CustomerLayout';
import type { CatalogMovie } from '@/lib/catalogData';
import { canPlayFullMovie, fullMovieUnavailableLabel, hasDemoClip } from '@/lib/catalogPresentation';
import { heroBackdropSrcSet } from '@/lib/imageUrls';
import { WatchlistButton } from '@/components/WatchlistButton';
import { cn } from '@/lib/utils';

const SWIPE_THRESHOLD_PX = 48;

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function formatRuntime(minutes: number | undefined, minLabel: string): string | null {
  if (!minutes || minutes <= 0) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m} ${minLabel}`;
}

/**
 * Cinematic homepage hero — manual navigation only (no autoplay timer).
 */
export function HeroCarousel({ featured }: { featured: CatalogMovie[] }) {
  const { t, dir } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [fadeKey, setFadeKey] = useState(0);
  const touchStartX = useRef<number | null>(null);
  const rtl = dir === 'rtl';

  useEffect(() => {
    const update = () => setReduceMotion(prefersReducedMotion());
    update();
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (current >= featured.length) setCurrent(0);
  }, [featured.length, current]);

  const movie = featured[current] || featured[0];
  const heroImage = movie
    ? heroBackdropSrcSet(movie.backdrop || movie.poster)
    : { src: '', srcSet: '', sizes: '100vw' };
  const heroSrc = heroImage.src;

  useEffect(() => {
    if (!heroSrc || typeof document === 'undefined') return;
    const existing = document.head.querySelector('link[data-hero-preload="1"]');
    if (existing) existing.remove();
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'image';
    link.href = heroSrc;
    if (heroImage.srcSet) link.setAttribute('imagesrcset', heroImage.srcSet);
    if (heroImage.sizes) link.setAttribute('imagesizes', heroImage.sizes);
    link.setAttribute('data-hero-preload', '1');
    document.head.appendChild(link);
    return () => {
      link.remove();
    };
  }, [heroSrc, heroImage.srcSet, heroImage.sizes]);

  // Prefetch only the next slide after idle — never all hero backdrops on first paint.
  useEffect(() => {
    if (featured.length < 2 || typeof window === 'undefined') return;
    const next = featured[(current + 1) % featured.length];
    const nextSrc = heroBackdropSrcSet(next.backdrop || next.poster).src;
    if (!nextSrc) return;
    const warm = () => {
      const img = new Image();
      img.decoding = 'async';
      img.src = nextSrc;
    };
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (typeof w.requestIdleCallback === 'function') {
      const id = w.requestIdleCallback(warm, { timeout: 2500 });
      return () => w.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(warm, 1500);
    return () => window.clearTimeout(id);
  }, [current, featured]);

  if (!movie) {
    return (
      <section className="relative -mt-16 flex h-[40vh] w-full items-center justify-center overflow-hidden bg-muted md:-mt-16">
        <p className="text-muted-foreground">No featured titles yet.</p>
      </section>
    );
  }

  const playable = canPlayFullMovie(movie);
  const demo = hasDemoClip(movie);
  const logoUrl = 'logoUrl' in movie && typeof movie.logoUrl === 'string' ? movie.logoUrl.trim() : '';
  const runtime = formatRuntime(
    typeof movie.duration === 'number' ? movie.duration : undefined,
    t.common.min
  );
  const genres = (movie.genres || []).slice(0, 3);

  const go = (delta: number) => {
    if (!featured.length) return;
    setCurrent((value) => (value + delta + featured.length) % featured.length);
    setFadeKey((k) => k + 1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (featured.length < 2) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      go(rtl ? 1 : -1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      go(rtl ? -1 : 1);
    }
  };

  const onMyListAnonymous = () => {
    navigate('/login');
  };

  return (
    <section
      className={heroSizing.section}
      aria-label="Featured titles"
      aria-roledescription="carousel"
      data-testid="hero-carousel"
      data-autoplay="false"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onTouchStart={(event) => {
        touchStartX.current = event.changedTouches[0]?.clientX ?? null;
      }}
      onTouchEnd={(event) => {
        const start = touchStartX.current;
        touchStartX.current = null;
        if (start == null || featured.length < 2) return;
        const end = event.changedTouches[0]?.clientX;
        if (end == null) return;
        const delta = end - start;
        if (Math.abs(delta) < SWIPE_THRESHOLD_PX) return;
        // Physical swipe: left advances in LTR; reverse in RTL.
        if (delta < 0) go(rtl ? -1 : 1);
        else go(rtl ? 1 : -1);
      }}
    >
      <div className="absolute inset-0 bg-[hsl(222,28%,5%)]">
        <img
          key={`${movie.id}-${fadeKey}`}
          src={heroSrc}
          srcSet={heroImage.srcSet || undefined}
          sizes={heroImage.srcSet ? heroImage.sizes : undefined}
          alt=""
          width={1280}
          height={720}
          className={cn(
            'h-full w-full object-cover object-center opacity-80',
            !reduceMotion && 'animate-fade-in'
          )}
          loading="eager"
          decoding="async"
          data-testid="hero-lcp-image"
          {...({ fetchpriority: 'high' } as object)}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/55 to-transparent rtl:bg-gradient-to-l" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.35)_100%)]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/45 via-transparent to-transparent" />
      </div>

      <div className={cn('relative z-10 flex h-full items-end', heroSizing.contentPad)}>
        <div className="w-full px-4 sm:px-6 lg:px-8">
          <div
            key={movie.id}
            className={cn(
              'max-w-[20rem] space-y-3 sm:max-w-xl md:max-w-2xl md:space-y-5',
              !reduceMotion && 'animate-fade-in'
            )}
          >
            {logoUrl ? (
              <>
                <img
                  src={logoUrl}
                  alt={movie.title}
                  className="max-h-14 w-auto max-w-[min(100%,360px)] object-contain drop-shadow-lg md:max-h-24"
                  data-testid="hero-title-logo"
                />
                <p className="sr-only">{movie.title}</p>
              </>
            ) : (
              <h1
                className={cn(typography.displayTitle, 'max-w-[16ch] text-foreground drop-shadow-lg')}
                data-testid="hero-title-text"
              >
                {movie.title}
              </h1>
            )}

            <div className="flex flex-wrap items-center gap-1.5 md:gap-2">
              {movie.year ? <MetaChip>{movie.year}</MetaChip> : null}
              {movie.rating ? (
                <MetaChip className="text-primary">★ {Number(movie.rating).toFixed(1)}</MetaChip>
              ) : null}
              {runtime ? <MetaChip>{runtime}</MetaChip> : null}
              {genres.slice(0, 2).map((g) => (
                <MetaChip key={g} className="hidden sm:inline-flex">
                  {g}
                </MetaChip>
              ))}
              {genres.slice(0, 1).map((g) => (
                <MetaChip key={`m-${g}`} className="sm:hidden">
                  {g}
                </MetaChip>
              ))}
            </div>

            <p
              className="max-w-xl text-sm leading-relaxed text-foreground/85 line-clamp-2 md:max-w-2xl md:text-base md:leading-relaxed md:text-foreground/90 md:line-clamp-3"
              dir="auto"
              data-testid="hero-synopsis"
            >
              {movie.description}
            </p>

            {/* Mobile: wrap actions so RTL labels are not truncated; Desktop: full-label actions */}
            <div
              className="flex flex-wrap items-center gap-2 pt-0.5 md:gap-3 md:pt-1"
              data-testid="hero-actions"
            >
              {playable || demo ? (
                <Button
                  size="xl"
                  variant="play"
                  onClick={() =>
                    navigate(`/player/movie/${movie.id}`, { state: { autoplay: true } })
                  }
                  className="h-11 min-w-0 gap-2 px-4 sm:px-5 md:h-12 md:px-6"
                  aria-label={
                    demo && !playable
                      ? `${t.hero.playDemoClip} — ${movie.title}`
                      : `${t.hero.play} ${movie.title}`
                  }
                  data-testid="hero-play"
                >
                  <Play className="h-5 w-5 shrink-0 fill-current" />
                  <span>{demo && !playable ? t.hero.playDemoClip : t.hero.play}</span>
                </Button>
              ) : (
                <Badge variant="secondary" className="px-3 py-2 text-sm">
                  {fullMovieUnavailableLabel()}
                </Badge>
              )}
              <Button
                size="lg"
                variant="glass"
                onClick={() => navigate(`/movie/${movie.id}`)}
                className="h-11 min-w-0 gap-2 px-3 md:h-12 md:px-4"
                data-testid="hero-more-info"
              >
                <Info className="h-5 w-5 shrink-0" />
                <span>{t.hero.moreInfo}</span>
              </Button>
              {isLoggedIn ? (
                <>
                  <WatchlistButton movieId={movie.id} iconOnly className="md:hidden" />
                  <WatchlistButton movieId={movie.id} className="hidden h-12 gap-2 md:inline-flex" />
                </>
              ) : (
                <>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-11 w-11 shrink-0 md:hidden"
                    onClick={onMyListAnonymous}
                    data-testid="hero-my-list-signin"
                    aria-label={t.nav.myList}
                    title={t.nav.myList}
                  >
                    <Plus className="h-5 w-5" />
                  </Button>
                  <Button
                    size="lg"
                    variant="outline"
                    className="hidden h-12 gap-2 md:inline-flex"
                    onClick={onMyListAnonymous}
                    data-testid="hero-my-list-signin-desktop"
                    aria-label={t.nav.myList}
                  >
                    <Plus className="h-5 w-5" />
                    {t.nav.myList}
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {featured.length > 1 ? (
        <>
          <button
            type="button"
            aria-label="Previous featured title"
            onClick={() => go(-1)}
            data-testid="hero-prev"
            className="absolute start-3 top-[42%] z-20 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-black/55 text-white shadow-lg backdrop-blur-md transition hover:bg-black/75 hover:border-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:flex"
          >
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
          <button
            type="button"
            aria-label="Next featured title"
            onClick={() => go(1)}
            data-testid="hero-next"
            className="absolute end-3 top-[42%] z-20 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-black/55 text-white shadow-lg backdrop-blur-md transition hover:bg-black/75 hover:border-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:flex"
          >
            <ChevronRight className="h-5 w-5 rtl:rotate-180" />
          </button>
        </>
      ) : null}

      <div
        className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 gap-1.5 md:bottom-7"
        role="tablist"
        aria-label="Featured titles"
        data-testid="hero-dots"
      >
        {featured.map((item, index) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={index === current}
            aria-label={`Show ${item.title}`}
            aria-current={index === current ? 'true' : undefined}
            onClick={() => {
              setCurrent(index);
              setFadeKey((k) => k + 1);
            }}
            className={cn(
              'h-1.5 rounded-full transition-all duration-normal focus-visible:ring-2 focus-visible:ring-ring',
              index === current ? 'w-6 bg-primary/90' : 'w-1.5 bg-white/35 hover:bg-white/55'
            )}
          />
        ))}
      </div>
    </section>
  );
}
