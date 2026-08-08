import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play,
  Plus,
  Share2,
  Check,
  Clapperboard,
  Volume2,
  VolumeX,
  Pause,
  Image as ImageIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ContentShelf, MediaCard, MetaChip, MetaRow, SectionHeader, typography } from '@/design-system';
import { useLang } from '@/components/CustomerLayout';
import type { CatalogMovie } from '@/lib/catalogData';
import {
  formatCatalogTracks,
  hasCatalogTracks,
  movieDetailLanguageBadges,
  resolveAudioAvailability,
  resolveSubtitleAvailability,
} from '@/lib/catalogAvailability';
import {
  canShowPlayButton,
  hasDemoClip,
  isDemoCatalogItem,
  isPublishedCatalogItem,
  MOVIE_HERO_TRAILER_DELAY_MS,
  movieUnavailableLabel,
  shouldAutoplayTrailerHero,
} from '@/lib/catalogPresentation';
import { trailerAutoplayEmbedUrl, trailerEmbedUrl } from '@/lib/trailers';
import { cn } from '@/lib/utils';

type HeroMode = 'backdrop' | 'trailer';

type CastCredit = {
  personId?: number;
  name: string;
  character?: string;
  profileUrl?: string;
  order?: number;
};

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function CastCard({ credit }: { credit: CastCredit }) {
  const initials = credit.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return (
    <div
      className="flex w-[100px] shrink-0 flex-col items-center gap-2 text-center sm:w-[112px]"
      data-testid="cast-card"
    >
      {credit.profileUrl ? (
        <img
          src={credit.profileUrl}
          alt=""
          className="h-20 w-20 rounded-full object-cover ring-1 ring-white/10 sm:h-24 sm:w-24"
          loading="lazy"
          decoding="async"
        />
      ) : (
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-primary/30 to-secondary text-sm font-semibold text-foreground ring-1 ring-white/10 sm:h-24 sm:w-24 sm:text-base">
          {initials || '?'}
        </div>
      )}
      <div className="space-y-0.5">
        <p className="line-clamp-2 text-xs font-medium text-foreground sm:text-sm">{credit.name}</p>
        {credit.character ? (
          <p className="line-clamp-2 text-[11px] text-muted-foreground sm:text-xs">{credit.character}</p>
        ) : null}
      </div>
    </div>
  );
}

async function shareTitle(title: string, url: string) {
  try {
    if (navigator.share) {
      await navigator.share({ title, url });
      return true;
    }
  } catch {
    // user cancelled or unsupported
  }
  try {
    await navigator.clipboard.writeText(url);
    return true;
  } catch {
    return false;
  }
}

function resolveCredits(movie: CatalogMovie): CastCredit[] {
  const structured =
    'credits' in movie && Array.isArray((movie as { credits?: CastCredit[] }).credits)
      ? ((movie as { credits?: CastCredit[] }).credits ?? [])
      : [];
  if (structured.length) {
    return [...structured].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }
  return (movie.cast ?? []).map((name) => ({ name }));
}

export function MovieDetailView({
  movie,
  related,
}: {
  movie: CatalogMovie;
  related: CatalogMovie[];
}) {
  const { t, dir } = useLang();
  const navigate = useNavigate();
  const [shared, setShared] = useState(false);
  const [heroMode, setHeroMode] = useState<HeroMode>('backdrop');
  const [userDismissedTrailer, setUserDismissedTrailer] = useState(false);
  const [trailerMuted, setTrailerMuted] = useState(true);
  const [trailerPaused, setTrailerPaused] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);

  const trailer = trailerEmbedUrl(movie);
  const hasTrailer = Boolean(trailer);
  const playable = canShowPlayButton(movie);
  const demo = hasDemoClip(movie);
  const isDemo = isDemoCatalogItem(movie);
  const published = isPublishedCatalogItem(movie);
  const logoUrl = 'logoUrl' in movie && typeof movie.logoUrl === 'string' ? movie.logoUrl : '';
  const tmdbId = 'tmdbId' in movie ? movie.tmdbId : null;
  const runtimeLabel = movie.duration ? `${movie.duration} ${t.common.min}` : '';
  const imdbLabel = movie.rating ? `IMDb ${Number(movie.rating).toFixed(1)}` : '';
  const credits = resolveCredits(movie);
  const languageBadges = movieDetailLanguageBadges(movie);
  const audioAv = resolveAudioAvailability(movie);
  const subAv = resolveSubtitleAvailability(movie);

  const trailerSrc = useMemo(() => {
    if (!hasTrailer || heroMode !== 'trailer' || trailerPaused) return '';
    if (trailerMuted) return trailerAutoplayEmbedUrl(movie);
    const base = trailerEmbedUrl(movie);
    if (!base) return '';
    try {
      const url = new URL(base);
      url.searchParams.set('autoplay', '1');
      url.searchParams.set('mute', '0');
      url.searchParams.set('rel', '0');
      url.searchParams.set('modestbranding', '1');
      url.searchParams.set('playsinline', '1');
      return url.toString();
    } catch {
      return base;
    }
  }, [hasTrailer, heroMode, movie, trailerMuted, trailerPaused]);

  useEffect(() => {
    const update = () => setReduceMotion(prefersReducedMotion());
    update();
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    setHeroMode('backdrop');
    setUserDismissedTrailer(false);
    setTrailerMuted(true);
    setTrailerPaused(false);
  }, [movie.id]);

  useEffect(() => {
    if (
      !shouldAutoplayTrailerHero({
        hasTrailer,
        reduceMotion,
        userDismissed: userDismissedTrailer,
      })
    ) {
      return;
    }
    const id = window.setTimeout(() => {
      setHeroMode('trailer');
      setTrailerPaused(false);
    }, MOVIE_HERO_TRAILER_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [hasTrailer, reduceMotion, userDismissedTrailer, movie.id]);

  const onShare = async () => {
    const ok = await shareTitle(movie.title, window.location.href);
    if (ok) {
      setShared(true);
      window.setTimeout(() => setShared(false), 2000);
    }
  };

  const startTrailer = () => {
    if (!hasTrailer) return;
    setUserDismissedTrailer(false);
    setHeroMode('trailer');
    setTrailerPaused(false);
  };

  const returnToBackdrop = () => {
    setHeroMode('backdrop');
    setUserDismissedTrailer(true);
    setTrailerPaused(false);
  };

  const unavailableLabel = movieUnavailableLabel({ hasTrailer, published });

  return (
    <div className="min-h-screen bg-background" data-testid="movie-detail" dir={dir}>
      <section
        className="relative -mt-16 min-h-[100svh] w-full overflow-hidden md:-mt-20"
        data-testid="movie-hero"
        data-hero-mode={heroMode}
      >
        <div className="absolute inset-0 bg-[hsl(222,28%,5%)]">
          {movie.backdrop ? (
            <img
              src={movie.backdrop}
              alt=""
              className={cn(
                'h-full w-full object-cover object-top transition-opacity duration-700',
                heroMode === 'trailer' && !trailerPaused ? 'opacity-20' : 'opacity-70'
              )}
              loading="eager"
              decoding="async"
              data-testid="movie-hero-backdrop"
            />
          ) : null}
          {heroMode === 'trailer' && trailerSrc ? (
            <iframe
              key={`${trailerSrc}-${trailerMuted ? 'm' : 'u'}`}
              src={trailerSrc}
              title={`${movie.title} trailer`}
              className="absolute inset-0 h-full w-full scale-[1.15] object-cover"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
              data-testid="youtube-trailer-embed"
              referrerPolicy="strict-origin-when-cross-origin"
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-background/10" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-background via-background/50 to-transparent rtl:bg-gradient-to-l" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-transparent" />
        </div>

        <div className="relative z-10 flex min-h-[100svh] items-end pb-10 pt-28 md:pb-16 md:pt-32">
          <div className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <div className="max-w-3xl space-y-5 animate-lift-in">
              {logoUrl ? (
                <img
                  src={logoUrl}
                  alt={movie.title}
                  className="max-h-20 w-auto max-w-[min(100%,420px)] object-contain drop-shadow-lg md:max-h-28"
                />
              ) : (
                <h1 className={cn(typography.displayTitle, 'text-foreground drop-shadow-md')}>
                  {movie.title}
                </h1>
              )}
              {logoUrl ? <p className="sr-only">{movie.title}</p> : null}
              {movie.originalTitle && movie.originalTitle !== movie.title ? (
                <p className="text-sm text-muted-foreground md:text-base">{movie.originalTitle}</p>
              ) : null}

              <MetaRow
                asChips
                items={[
                  movie.ageRating,
                  movie.year,
                  runtimeLabel,
                  imdbLabel,
                  movie.country,
                  tmdbId ? `TMDB ${tmdbId}` : null,
                ]}
              />

              <div className="flex flex-wrap gap-2">
                {movie.genres.map((genre) => (
                  <Badge key={genre} variant="secondary" className="bg-white/10 text-foreground backdrop-blur-sm">
                    {genre}
                  </Badge>
                ))}
              </div>

              <p className={cn(typography.body, 'max-w-2xl line-clamp-4 md:line-clamp-5')}>
                {movie.description}
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-1" aria-label="Movie actions">
                {playable ? (
                  <Button
                    size="xl"
                    variant="play"
                    className="gap-2"
                    onClick={() => navigate(`/player/movie/${movie.id}`)}
                    aria-label={`Play ${movie.title}`}
                    data-testid="movie-play-button"
                  >
                    <Play className="h-5 w-5 fill-current" />
                    {t.movie.play}
                  </Button>
                ) : null}
                {demo ? (
                  <Button
                    size="xl"
                    variant={playable ? 'glass' : 'play'}
                    className="gap-2"
                    onClick={() => navigate(`/player/movie/${movie.id}`)}
                    aria-label={`Play demo clip for ${movie.title}`}
                    data-testid="movie-demo-button"
                  >
                    <Play className="h-5 w-5 fill-current" />
                    Play Demo Clip
                  </Button>
                ) : null}
                {hasTrailer ? (
                  <Button
                    size="lg"
                    variant="glass"
                    className="gap-2"
                    onClick={startTrailer}
                    aria-label={`Watch trailer for ${movie.title}`}
                    data-testid="movie-trailer-button"
                  >
                    <Clapperboard className="h-5 w-5" />
                    {t.movie.trailer}
                  </Button>
                ) : null}
                {!playable && !demo && !hasTrailer ? (
                  <Badge
                    variant="secondary"
                    className="px-3 py-2 text-sm"
                    data-testid="movie-unavailable"
                  >
                    {unavailableLabel}
                  </Badge>
                ) : null}
                <Button
                  size="lg"
                  variant="outline"
                  disabled
                  title="My List sync lands with watchlist APIs"
                  className="gap-2 opacity-70"
                  data-testid="movie-mylist-button"
                >
                  <Plus className="h-5 w-5" />
                  + My List
                </Button>
                <Button
                  size="lg"
                  variant="ghost"
                  className="gap-2"
                  onClick={() => void onShare()}
                  data-testid="movie-share-button"
                >
                  {shared ? <Check className="h-5 w-5 text-success" /> : <Share2 className="h-5 w-5" />}
                  {shared ? 'Copied' : t.movie.share}
                </Button>
              </div>

              {heroMode === 'trailer' && hasTrailer ? (
                <div
                  className="flex flex-wrap items-center gap-2"
                  data-testid="movie-trailer-controls"
                  aria-label="Trailer controls"
                >
                  <Button
                    size="sm"
                    variant="glass"
                    className="gap-2"
                    onClick={() => setTrailerMuted((v) => !v)}
                    data-testid="trailer-mute-toggle"
                  >
                    {trailerMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                    {trailerMuted ? 'Unmute' : 'Mute'}
                  </Button>
                  <Button
                    size="sm"
                    variant="glass"
                    className="gap-2"
                    onClick={() => setTrailerPaused((v) => !v)}
                    data-testid="trailer-pause-toggle"
                  >
                    <Pause className="h-4 w-4" />
                    {trailerPaused ? 'Resume' : 'Pause'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="gap-2"
                    onClick={returnToBackdrop}
                    data-testid="trailer-return-backdrop"
                  >
                    <ImageIcon className="h-4 w-4" />
                    Show backdrop
                  </Button>
                </div>
              ) : null}

              {isDemo ? (
                <p className="text-xs text-muted-foreground">
                  Demo catalog item: trailer and demo clip access do not indicate full commercial film
                  availability.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className="relative z-10 space-y-12 pb-16 pt-2 md:space-y-16">
        <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8" data-testid="movie-metadata">
          <SectionHeader title={t.movie.genres} className="mb-4 px-0" />
          <MetaRow
            asChips
            items={[
              movie.ageRating,
              movie.year,
              runtimeLabel,
              movie.country,
              movie.language,
              imdbLabel,
              movie.director ? `${t.movie.director}: ${movie.director}` : null,
            ]}
          />
        </section>

        {movie.description ? (
          <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8" data-testid="movie-about">
            <SectionHeader title="About" className="mb-4 px-0" />
            <p className={cn(typography.body, 'max-w-3xl text-foreground/90')}>{movie.description}</p>
          </section>
        ) : null}

        {languageBadges.length ? (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
            data-testid="movie-language-badges"
            aria-label="Audio and subtitle availability"
          >
            <SectionHeader title={`${t.movie.audio} / ${t.movie.subtitles}`} className="mb-4 px-0" />
            <div className="flex flex-wrap gap-2">
              {languageBadges.map((badge) => (
                <span key={badge.key} title={badge.fullLabel}>
                  <MetaChip>{badge.label}</MetaChip>
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {(hasCatalogTracks(movie.audio) ||
          hasCatalogTracks(movie.subtitles) ||
          hasCatalogTracks(movie.dubbed) ||
          movie.qualities?.length) && (
          <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <div
              className="rounded-2xl border border-white/8 bg-card/60 p-5 shadow-lg backdrop-blur-sm"
              data-testid="movie-technical-details"
            >
              <h2 className={cn(typography.sectionTitle, 'mb-4')}>Technical Details</h2>
              <dl className="space-y-3 text-sm">
                {[
                  [
                    'Original',
                    audioAv.original_language
                      ? formatCatalogTracks([audioAv.original_language])
                      : movie.language,
                  ],
                  [t.movie.audio, formatCatalogTracks(audioAv.languages?.length ? audioAv.languages : movie.audio)],
                  [t.movie.dubbed, formatCatalogTracks(audioAv.dubbed_languages?.length ? audioAv.dubbed_languages : [])],
                  [
                    t.movie.subtitles,
                    formatCatalogTracks(subAv.languages?.length ? subAv.languages : movie.subtitles),
                  ],
                  [t.movie.quality, movie.qualities?.join(', ')],
                ]
                  .filter(([, value]) => Boolean(value))
                  .map(([label, value]) => (
                    <div
                      key={String(label)}
                      className="flex justify-between gap-4 border-b border-white/5 pb-2 last:border-0"
                    >
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="text-end font-medium text-foreground">{value}</dd>
                    </div>
                  ))}
              </dl>
            </div>
          </section>
        )}

        {credits.length ? (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
            aria-labelledby="cast-heading"
            data-testid="movie-cast"
          >
            <h2 id="cast-heading" className={cn(typography.sectionTitle, 'mb-5')}>
              {t.movie.cast}
            </h2>
            <div className="flex gap-4 overflow-x-auto pb-2 hide-scrollbar sm:gap-5" dir={dir}>
              {credits.map((person, index) => (
                <CastCard key={`${person.personId ?? person.name}-${index}`} credit={person} />
              ))}
            </div>
          </section>
        ) : null}

        {related.length > 0 ? (
          <div data-testid="movie-similar">
            <ContentShelf title={t.movie.similar}>
              {related.map((item) => (
                <MediaCard
                  key={item.id}
                  title={item.title}
                  imageUrl={item.poster}
                  year={item.year}
                  rating={item.rating}
                  showDemo={hasDemoClip(item)}
                  playable={canShowPlayButton(item) || hasDemoClip(item)}
                  onActivate={() => navigate(`/movie/${item.id}`)}
                />
              ))}
            </ContentShelf>
          </div>
        ) : null}

        <section
          className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
          data-testid="movie-reviews-placeholder"
        >
          <SectionHeader title="Reviews" className="mb-3 px-0" />
          <p className="text-sm text-muted-foreground">Reviews are coming soon.</p>
        </section>
      </div>
    </div>
  );
}
