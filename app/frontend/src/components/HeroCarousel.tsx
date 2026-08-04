import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Info, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MetaChip, typography } from '@/design-system';
import { useLang } from '@/components/CustomerLayout';
import type { CatalogMovie } from '@/lib/catalogData';
import { canPlayFullMovie, fullMovieUnavailableLabel, hasDemoClip } from '@/lib/catalogPresentation';
import { trailerEmbedUrl } from '@/lib/trailers';
import { cn } from '@/lib/utils';

const AUTOPLAY_MS = 8000;

/** Full-bleed Netflix-style featured carousel. */
export function HeroCarousel({ featured }: { featured: CatalogMovie[] }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [current, setCurrent] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused || featured.length < 2) return;
    const id = window.setInterval(() => {
      setCurrent((value) => (value + 1) % featured.length);
    }, AUTOPLAY_MS);
    return () => window.clearInterval(id);
  }, [paused, featured.length]);

  const movie = featured[current] || featured[0];
  if (!movie) {
    return (
      <section className="relative -mt-16 flex h-[40vh] w-full items-center justify-center overflow-hidden bg-muted md:-mt-20">
        <p className="text-muted-foreground">No featured titles yet.</p>
      </section>
    );
  }

  const playable = canPlayFullMovie(movie);
  const demo = hasDemoClip(movie);
  const trailerHref = trailerEmbedUrl(movie) || null;
  const logoUrl = 'logoUrl' in movie && typeof movie.logoUrl === 'string' ? movie.logoUrl : '';

  const go = (delta: number) => {
    if (!featured.length) return;
    setCurrent((value) => (value + delta + featured.length) % featured.length);
  };

  return (
    <section
      className="relative -mt-16 h-[78vh] w-full overflow-hidden md:-mt-20 md:h-[90vh]"
      aria-label="Featured titles"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setPaused(false);
        }
      }}
    >
      <div className="absolute inset-0 bg-[hsl(222,28%,5%)]">
        <img
          key={movie.id}
          src={movie.backdrop || movie.poster}
          alt=""
          className="h-full w-full object-cover object-center opacity-75 animate-fade-in"
          loading="eager"
          decoding="async"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/55 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-transparent" />
      </div>

      <div className="relative z-10 flex h-full items-end pb-20 md:pb-28">
        <div className="container mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <div key={movie.id} className="max-w-2xl space-y-5 animate-lift-in">
            <p className={typography.eyebrow}>iFilm</p>
            {logoUrl ? (
              <img
                src={logoUrl}
                alt={movie.title}
                className="max-h-16 w-auto max-w-[min(100%,380px)] object-contain drop-shadow-lg md:max-h-24"
              />
            ) : (
              <h1 className={cn(typography.displayTitle, 'max-w-[16ch] text-foreground drop-shadow-lg')}>
                {movie.title}
              </h1>
            )}
            {logoUrl ? <p className="sr-only">{movie.title}</p> : null}

            <div className="flex flex-wrap items-center gap-2">
              {movie.ageRating ? <MetaChip>{movie.ageRating}</MetaChip> : null}
              {movie.year ? <MetaChip>{movie.year}</MetaChip> : null}
              {movie.duration ? <MetaChip>{movie.duration} {t.common.min}</MetaChip> : null}
              {movie.rating ? <MetaChip>★ {Number(movie.rating).toFixed(1)}</MetaChip> : null}
            </div>

            <p className="max-w-xl text-sm leading-relaxed text-foreground/90 line-clamp-3 md:text-base md:line-clamp-4">
              {movie.description}
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              {playable || demo ? (
                <Button
                  size="xl"
                  variant="play"
                  onClick={() => navigate(`/player/movie/${movie.id}`)}
                  className="gap-2"
                  aria-label={demo && !playable ? `Play demo clip for ${movie.title}` : `Play ${movie.title}`}
                >
                  <Play className="h-5 w-5 fill-current" />
                  {demo && !playable ? 'Play Demo Clip' : t.hero.play}
                </Button>
              ) : (
                <Badge variant="secondary" className="px-3 py-2 text-sm">
                  {fullMovieUnavailableLabel()}
                </Badge>
              )}
              <Button size="lg" variant="glass" onClick={() => navigate(`/movie/${movie.id}`)} className="gap-2">
                <Info className="h-5 w-5" />
                {t.hero.moreInfo}
              </Button>
              {trailerHref ? (
                <Button size="lg" variant="outline" asChild className="gap-2">
                  <a href={trailerHref} target="_blank" rel="noopener noreferrer">
                    Trailer
                  </a>
                </Button>
              ) : null}
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
            className="absolute left-3 top-1/2 z-20 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-background/50 text-foreground backdrop-blur-md transition hover:bg-background/80 md:flex"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            aria-label="Next featured title"
            onClick={() => go(1)}
            className="absolute right-3 top-1/2 z-20 hidden h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-background/50 text-foreground backdrop-blur-md transition hover:bg-background/80 md:flex"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </>
      ) : null}

      <div
        className="absolute bottom-7 left-1/2 z-20 flex -translate-x-1/2 gap-2"
        role="tablist"
        aria-label="Featured titles"
      >
        {featured.map((item, index) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={index === current}
            aria-label={`Show ${item.title}`}
            onClick={() => setCurrent(index)}
            className={cn(
              'h-2 rounded-full transition-all duration-normal focus-visible:ring-2 focus-visible:ring-ring',
              index === current ? 'w-8 bg-primary' : 'w-2 bg-foreground/35 hover:bg-foreground/55'
            )}
          />
        ))}
      </div>
    </section>
  );
}
