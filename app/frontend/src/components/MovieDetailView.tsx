import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play,
  Share2,
  Check,
  Clapperboard,
  Volume2,
  VolumeX,
  Pause,
  Image as ImageIcon,
  RotateCcw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ContentShelf, MediaCard, MetaChip, MetaRow, SectionHeader, typography, heroSizing } from '@/design-system';
import { useLang } from '@/components/CustomerLayout';
import { WatchlistButton } from '@/components/WatchlistButton';
import type { CatalogMovie } from '@/lib/catalogData';
import type { WatchProgressDto } from '@/lib/api';
import {
  movieDetailTrackGroups,
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
import { heroBackdropSrcSet } from '@/lib/imageUrls';
import { cn } from '@/lib/utils';

type HeroMode = 'backdrop' | 'trailer';

type CastCredit = {
  personId?: number;
  name: string;
  character?: string;
  profileUrl?: string;
  order?: number;
};

export type MovieWatchState =
  | { kind: 'continue'; progress: WatchProgressDto }
  | { kind: 'completed'; progress: WatchProgressDto }
  | null;

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
      className="flex w-[104px] shrink-0 flex-col gap-2 text-start sm:w-[120px]"
      data-testid="cast-card"
    >
      {credit.profileUrl ? (
        <img
          src={credit.profileUrl}
          alt=""
          className="aspect-[2/3] w-full rounded-xl object-cover ring-1 ring-white/10"
          loading="lazy"
          decoding="async"
        />
      ) : (
        <div className="flex aspect-[2/3] w-full items-center justify-center rounded-xl bg-gradient-to-br from-primary/30 to-secondary text-sm font-semibold text-foreground ring-1 ring-white/10 sm:text-base">
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

function formatRuntime(minutes: number, minLabel: string): string {
  if (!minutes) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h <= 0) return `${m} ${minLabel}`;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function MovieDetailView({
  movie,
  related,
  recommended = [],
  watchState = null,
}: {
  movie: CatalogMovie;
  related: CatalogMovie[];
  recommended?: CatalogMovie[];
  watchState?: MovieWatchState;
}) {
  const { t, dir } = useLang();
  const navigate = useNavigate();
  const [shared, setShared] = useState(false);
  const [heroMode, setHeroMode] = useState<HeroMode>('backdrop');
  const [userDismissedTrailer, setUserDismissedTrailer] = useState(false);
  const [trailerMuted, setTrailerMuted] = useState(true);
  const [trailerPaused, setTrailerPaused] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [overviewExpanded, setOverviewExpanded] = useState(false);

  const trailer = trailerEmbedUrl(movie);
  const hasTrailer = Boolean(trailer);
  const playable = canShowPlayButton(movie);
  const demo = hasDemoClip(movie);
  const isDemo = isDemoCatalogItem(movie);
  const published = isPublishedCatalogItem(movie);
  const logoUrl = 'logoUrl' in movie && typeof movie.logoUrl === 'string' ? movie.logoUrl : '';
  const writer =
    'writer' in movie && typeof (movie as { writer?: string }).writer === 'string'
      ? (movie as { writer?: string }).writer
      : '';
  const runtimeLabel = formatRuntime(movie.duration || 0, t.common.min);
  const ratingLabel = movie.rating ? `★ ${Number(movie.rating).toFixed(1)}` : '';
  const credits = resolveCredits(movie).slice(0, 16);
  const trackGroups = movieDetailTrackGroups(movie, {
    dubbed: t.movie.dubbed,
    subtitled: t.nav.subtitled,
    multiAudio: 'Multi Audio',
    persianDubbed: t.player.persianDub,
    pashtoDubbed: t.player.pashtoDub,
    english: t.player.english,
    persian: t.player.persian === 'Persian' ? 'فارسی' : t.player.persian,
    pashto: t.player.pashto === 'Pashto' ? 'پښتو' : t.player.pashto,
    audio: t.movie.audio,
    subtitles: t.movie.subtitles,
  });
  const heroBackdrop = heroBackdropSrcSet(movie.backdrop);
  const [trailerReady, setTrailerReady] = useState(false);

  const trailerSrc = useMemo(() => {
    if (!hasTrailer || !trailerReady || heroMode !== 'trailer' || trailerPaused) return '';
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
      url.searchParams.set('controls', '0');
      url.searchParams.set('disablekb', '1');
      url.searchParams.set('fs', '0');
      url.searchParams.set('iv_load_policy', '3');
      return url.toString();
    } catch {
      return base;
    }
  }, [hasTrailer, trailerReady, heroMode, movie, trailerMuted, trailerPaused]);

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
    setTrailerReady(false);
    setOverviewExpanded(false);
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
    const warmMs = Math.max(0, MOVIE_HERO_TRAILER_DELAY_MS - 1000);
    const warmId = window.setTimeout(() => setTrailerReady(true), warmMs);
    const id = window.setTimeout(() => {
      setTrailerReady(true);
      setHeroMode('trailer');
      setTrailerPaused(false);
    }, MOVIE_HERO_TRAILER_DELAY_MS);
    return () => {
      window.clearTimeout(warmId);
      window.clearTimeout(id);
    };
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
    setTrailerReady(true);
    setHeroMode('trailer');
    setTrailerPaused(false);
  };

  const returnToBackdrop = () => {
    setHeroMode('backdrop');
    setUserDismissedTrailer(true);
    setTrailerPaused(false);
  };

  const goPlay = (startOver = false) => {
    navigate(`/player/movie/${movie.id}`, {
      state: { autoplay: true, startOver },
    });
  };

  const unavailableLabel = movieUnavailableLabel({ hasTrailer, published });
  const progressPercent =
    watchState?.kind === 'continue' ? Math.round(watchState.progress.progress_percent || 0) : null;

  const similarIds = new Set(related.map((m) => m.id));
  const recommendedUnique = recommended.filter((m) => m.id !== movie.id && !similarIds.has(m.id));

  return (
    <div className="min-h-screen bg-background" data-testid="movie-detail" dir={dir}>
      <section
        className={cn(heroSizing.section, 'md:min-h-[560px]')}
        data-testid="movie-hero"
        data-hero-mode={heroMode}
      >
        <div className="absolute inset-0 bg-[hsl(222,28%,5%)]">
          {heroBackdrop.src ? (
            <img
              src={heroBackdrop.src}
              srcSet={heroBackdrop.srcSet || undefined}
              sizes={heroBackdrop.srcSet ? heroBackdrop.sizes : undefined}
              alt=""
              className={cn(
                'h-full w-full object-cover object-center transition-opacity duration-700',
                !reduceMotion && heroMode === 'trailer' && !trailerPaused ? 'opacity-25' : 'opacity-80'
              )}
              loading="eager"
              decoding="async"
              data-testid="movie-hero-backdrop"
              {...({ fetchpriority: 'high' } as object)}
            />
          ) : null}
          {heroMode === 'trailer' && trailerSrc ? (
            <iframe
              key={`${trailerSrc}-${trailerMuted ? 'm' : 'u'}`}
              src={trailerSrc}
              title={`${movie.title} trailer`}
              className="pointer-events-none absolute inset-0 h-full w-full scale-[1.22] object-cover"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              tabIndex={-1}
              data-testid="youtube-trailer-embed"
              referrerPolicy="strict-origin-when-cross-origin"
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/55 to-transparent rtl:bg-gradient-to-l" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.35)_100%)]" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/45 via-transparent to-transparent" />
        </div>

        <div className={cn('relative z-10 flex h-full items-end', heroSizing.contentPad)}>
          <div className="w-full px-4 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-6xl">
              <div
                className={cn(
                  'max-w-[20rem] space-y-3 sm:max-w-xl md:max-w-2xl md:space-y-4',
                  !reduceMotion && 'animate-fade-in'
                )}
              >
                {logoUrl ? (
                  <>
                    <img
                      src={logoUrl}
                      alt={movie.title}
                      className="max-h-14 w-auto max-w-[min(100%,360px)] object-contain drop-shadow-lg md:max-h-24"
                      data-testid="movie-title-logo"
                    />
                    <p className="sr-only">{movie.title}</p>
                  </>
                ) : (
                  <h1
                    className={cn(typography.displayTitle, 'max-w-[16ch] text-foreground drop-shadow-lg')}
                    data-testid="movie-title-text"
                  >
                    {movie.title}
                  </h1>
                )}

                {movie.originalTitle && movie.originalTitle !== movie.title ? (
                  <p className="text-sm text-muted-foreground">{movie.originalTitle}</p>
                ) : null}

                {/* Desktop: actions near title; mobile order enforced via flex order utilities */}
                <div className="flex flex-col gap-3">
                  <div
                    className="order-1 flex flex-wrap items-center gap-2 sm:gap-3"
                    aria-label="Movie actions"
                    data-testid="movie-actions"
                  >
                    {playable && watchState?.kind === 'continue' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goPlay(false)}
                        aria-label={`Continue watching ${movie.title}`}
                        data-testid="movie-continue-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        {t.movie.continueWatching}
                        {progressPercent != null ? (
                          <span className="ms-1 text-xs font-semibold opacity-80">{progressPercent}%</span>
                        ) : null}
                      </Button>
                    ) : null}
                    {playable && watchState?.kind === 'completed' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goPlay(true)}
                        aria-label={`Watch ${movie.title} again`}
                        data-testid="movie-watch-again-button"
                      >
                        <RotateCcw className="h-5 w-5" />
                        {t.movie.watchAgain}
                      </Button>
                    ) : null}
                    {playable && !watchState ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goPlay(false)}
                        aria-label={`Play ${movie.title}`}
                        data-testid="movie-play-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        {t.movie.play}
                      </Button>
                    ) : null}
                    {demo && !playable ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goPlay(false)}
                        aria-label={`Play demo clip for ${movie.title}`}
                        data-testid="movie-demo-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        Play Demo Clip
                      </Button>
                    ) : null}
                    <WatchlistButton movieId={movie.id} />
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
                      <span data-testid="movie-unavailable">
                        <MetaChip>{unavailableLabel}</MetaChip>
                      </span>
                    ) : null}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-11 w-11 shrink-0"
                      onClick={() => void onShare()}
                      data-testid="movie-share-button"
                      aria-label={shared ? 'Copied' : t.movie.share}
                      title={shared ? 'Copied' : t.movie.share}
                    >
                      {shared ? <Check className="h-5 w-5 text-success" /> : <Share2 className="h-5 w-5" />}
                    </Button>
                  </div>

                  <div className="order-2 space-y-2" data-testid="movie-hero-meta">
                    <MetaRow
                      asChips
                      items={[movie.year, runtimeLabel, ratingLabel, ...movie.genres.slice(0, 3)]}
                    />
                    {(trackGroups.audio.length > 0 || trackGroups.subtitles.length > 0) && (
                      <div
                        className="flex flex-col gap-1.5 text-sm text-foreground/90"
                        data-testid="movie-track-meta"
                      >
                        {trackGroups.audio.length ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-muted-foreground">{t.movie.audio}:</span>
                            {trackGroups.audio.map((b) => (
                              <MetaChip key={b.key}>{b.label}</MetaChip>
                            ))}
                          </div>
                        ) : null}
                        {trackGroups.subtitles.length ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-muted-foreground">{t.movie.subtitles}:</span>
                            {trackGroups.subtitles.map((b) => (
                              <MetaChip key={b.key}>{b.label}</MetaChip>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    )}
                    {watchState?.kind === 'continue' && progressPercent != null ? (
                      <div
                        className="h-1 max-w-xs overflow-hidden rounded-full bg-white/15"
                        data-testid="movie-continue-progress"
                        aria-hidden="true"
                      >
                        <div className="h-full bg-primary" style={{ width: `${progressPercent}%` }} />
                      </div>
                    ) : null}
                  </div>
                </div>

                {/* Overview in hero on desktop; mobile shows again below for order */}
                {movie.description ? (
                  <div className="hidden md:block" data-testid="movie-hero-overview">
                    <p className={cn(typography.bodySm, 'max-w-xl', !overviewExpanded && 'line-clamp-3')}>
                      {movie.description}
                    </p>
                    {movie.description.length > 160 ? (
                      <button
                        type="button"
                        className="mt-1 text-sm font-medium text-primary"
                        onClick={() => setOverviewExpanded((v) => !v)}
                      >
                        {overviewExpanded ? 'Show less' : 'More'}
                      </button>
                    ) : null}
                  </div>
                ) : null}

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
        </div>
      </section>

      <div className="relative z-10 space-y-10 pb-20 pt-2 md:space-y-14">
        {/* Mobile overview after actions/meta */}
        {movie.description ? (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 md:hidden"
            data-testid="movie-about"
          >
            <SectionHeader title={t.movie.overview} className="mb-3 px-0" />
            <p
              className={cn(
                typography.body,
                'max-w-3xl text-foreground/90',
                !overviewExpanded && 'line-clamp-5'
              )}
            >
              {movie.description}
            </p>
            {movie.description.length > 160 ? (
              <button
                type="button"
                className="mt-2 text-sm font-medium text-primary"
                onClick={() => setOverviewExpanded((v) => !v)}
                data-testid="movie-overview-more-mobile"
              >
                {overviewExpanded ? 'Show less' : 'More'}
              </button>
            ) : null}
          </section>
        ) : null}

        {/* Desktop overview section if not expanded in hero — show full */}
        {movie.description ? (
          <section
            className="container mx-auto hidden max-w-6xl px-4 sm:px-6 lg:px-8 md:block"
            data-testid="movie-about-desktop"
          >
            <SectionHeader title={t.movie.overview} className="mb-3 px-0" />
            <p className={cn(typography.body, 'max-w-3xl text-foreground/90')}>{movie.description}</p>
          </section>
        ) : null}

        {(movie.director || writer) && (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
            data-testid="movie-crew"
          >
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              {movie.director ? (
                <div>
                  <dt className="text-muted-foreground">{t.movie.director}</dt>
                  <dd className="font-medium text-foreground">{movie.director}</dd>
                </div>
              ) : null}
              {writer ? (
                <div>
                  <dt className="text-muted-foreground">{t.movie.writer}</dt>
                  <dd className="font-medium text-foreground">{writer}</dd>
                </div>
              ) : null}
            </dl>
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
            <div
              className="flex gap-4 overflow-x-auto pb-2 hide-scrollbar sm:gap-5"
              dir={dir}
              data-testid="movie-cast-rail"
            >
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

        {recommendedUnique.length > 0 ? (
          <div data-testid="movie-recommendations">
            <ContentShelf title={t.movie.recommendations}>
              {recommendedUnique.map((item) => (
                <MediaCard
                  key={`rec-${item.id}`}
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
      </div>
    </div>
  );
}
