import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play,
  RotateCcw,
  Clapperboard,
  Volume2,
  VolumeX,
  Pause,
  Image as ImageIcon,
  ChevronDown,
  Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ContentShelf, MediaCard, MetaChip, MetaRow, SectionHeader, typography, heroSizing } from '@/design-system';
import { useLang } from '@/components/CustomerLayout';
import { WatchlistButton } from '@/components/WatchlistButton';
import { CastRail, type CastCredit } from '@/components/CastRail';
import type { CatalogSeries } from '@/lib/catalogData';
import type { WatchProgressDto } from '@/lib/api';
import { movieDetailTrackGroups } from '@/lib/catalogAvailability';
import { hasDemoClip, isDemoCatalogItem } from '@/lib/catalogPresentation';
import { trailerAutoplayEmbedUrl, trailerEmbedUrl } from '@/lib/trailers';
import { heroBackdropSrcSet, sizedArtworkUrl } from '@/lib/imageUrls';
import { cn } from '@/lib/utils';
import {
  buildEpisodeProgressMap,
  episodePlayerPath,
  formatEpisodeCode,
  isEpisodePlayable,
  type SeriesHeroCta,
} from '@/lib/seriesDetailPlayback';

type HeroMode = 'backdrop' | 'trailer';

export type SeriesEpisodeView = {
  id: number;
  seriesId: number;
  seasonId: number;
  season: number;
  episode: number;
  title: string;
  duration: number;
  description: string;
  thumbnail: string;
  status: string;
  playable: boolean;
  hasDemoClip: boolean;
  hasPlayablePackage?: boolean;
  hasExternalMedia?: boolean;
  demoOwned?: boolean;
  audioAvailability?: unknown;
  subtitleAvailability?: unknown;
};

export type SeriesSeasonView = {
  number: number;
  episodeCount: number;
  id?: number;
  status?: string;
};

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function seasonLabel(
  t: { seasonN: string; seasonWithCount: string },
  n: number,
  count?: number
): string {
  if (count != null && count > 0) {
    return t.seasonWithCount.replace('{n}', String(n)).replace('{count}', String(count));
  }
  return t.seasonN.replace('{n}', String(n));
}

function EpisodeRow({
  episode,
  seriesId,
  seriesPoster,
  progress,
  onPlay,
  labels,
}: {
  episode: SeriesEpisodeView;
  seriesId: number;
  seriesPoster: string;
  progress?: WatchProgressDto | null;
  onPlay: (ep: SeriesEpisodeView, startOver?: boolean) => void;
  labels: {
    play: string;
    resume: string;
    watchAgain: string;
    min: string;
    unavailable: string;
    audio: string;
    subtitles: string;
    dubbed: string;
    subtitled: string;
    english: string;
    persian: string;
    pashto: string;
    persianDubbed: string;
    pashtoDubbed: string;
  };
}) {
  const code = formatEpisodeCode(episode.season, episode.episode);
  const playable = isEpisodePlayable(episode);
  const incomplete = progress && !progress.completed && (progress.progress_percent || 0) > 0;
  const completed = progress?.completed;
  const percent = incomplete ? Math.round(progress.progress_percent || 0) : 0;
  const actionLabel = incomplete
    ? labels.resume
    : completed
      ? labels.watchAgain
      : labels.play;
  const tracks = movieDetailTrackGroups(episode as never, {
    dubbed: labels.dubbed,
    subtitled: labels.subtitled,
    persianDubbed: labels.persianDubbed,
    pashtoDubbed: labels.pashtoDubbed,
    english: labels.english,
    persian: labels.persian,
    pashto: labels.pashto,
    audio: labels.audio,
    subtitles: labels.subtitles,
  });
  const trackLine = [...tracks.audio, ...tracks.subtitles].map((b) => b.label).join(' · ');

  return (
    <article
      className="grid grid-cols-1 gap-3 border-b border-border/60 py-4 sm:grid-cols-[168px_1fr_auto] sm:items-start sm:gap-4"
      data-testid={`episode-row-${episode.id}`}
      data-episode-code={code}
    >
      <img
        src={sizedArtworkUrl(episode.thumbnail || seriesPoster, 'backdrop', 'card')}
        alt=""
        className="aspect-video w-full rounded-lg object-cover bg-muted sm:w-[168px]"
        loading="lazy"
        decoding="async"
      />
      <div className="min-w-0 space-y-1.5">
        <h3 className="text-sm font-semibold text-foreground sm:text-base">
          <span className="text-primary">{code}</span>
          <span className="mx-1.5 text-muted-foreground">·</span>
          {episode.title}
        </h3>
        <p className="text-xs text-muted-foreground">
          {episode.duration ? `${episode.duration} ${labels.min}` : null}
          {trackLine ? ` · ${trackLine}` : null}
          {!playable ? ` · ${labels.unavailable}` : null}
        </p>
        {episode.description ? (
          <p className="line-clamp-3 text-sm text-foreground/80">{episode.description}</p>
        ) : null}
        {incomplete ? (
          <div
            className="h-0.5 max-w-xs overflow-hidden rounded-full bg-white/15"
            data-testid={`episode-progress-${episode.id}`}
            aria-hidden="true"
          >
            <div className="h-full bg-primary" style={{ width: `${percent}%` }} />
          </div>
        ) : null}
        {hasDemoClip(episode) && !episode.playable ? (
          <MetaChip>Demo Clip</MetaChip>
        ) : null}
      </div>
      <div className="sm:self-center">
        {playable ? (
          <Button
            size="lg"
            variant="play"
            className="gap-2"
            onClick={() => onPlay(episode, Boolean(completed))}
            aria-label={`${actionLabel} ${code} ${episode.title}`}
            data-testid={`episode-play-${episode.id}`}
          >
            {completed ? <RotateCcw className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
            {actionLabel}
          </Button>
        ) : (
          <MetaChip>{labels.unavailable}</MetaChip>
        )}
      </div>
    </article>
  );
}

export function SeriesDetailView({
  series,
  seasons,
  episodes,
  selectedSeason,
  onSeasonChange,
  seasonLoading = false,
  recommended = [],
  heroCta,
  progressByEpisode,
  catalogEpisodesForCta = [],
}: {
  series: CatalogSeries;
  seasons: SeriesSeasonView[];
  episodes: SeriesEpisodeView[];
  selectedSeason: number;
  onSeasonChange: (season: number) => void;
  seasonLoading?: boolean;
  recommended?: CatalogSeries[];
  heroCta: SeriesHeroCta<SeriesEpisodeView>;
  progressByEpisode: Map<number, WatchProgressDto>;
  /** Episodes known across seasons for CTA resolution (optional display only). */
  catalogEpisodesForCta?: SeriesEpisodeView[];
}) {
  const { t, dir } = useLang();
  const navigate = useNavigate();
  const [heroMode, setHeroMode] = useState<HeroMode>('backdrop');
  const [trailerMuted, setTrailerMuted] = useState(true);
  const [trailerPaused, setTrailerPaused] = useState(false);
  const [trailerReady, setTrailerReady] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [overviewExpanded, setOverviewExpanded] = useState(false);
  const [seasonSheetOpen, setSeasonSheetOpen] = useState(false);

  const trailer = trailerEmbedUrl(series);
  const hasTrailer = Boolean(trailer);
  const isDemo = isDemoCatalogItem(series);
  const logoUrl = 'logoUrl' in series && typeof series.logoUrl === 'string' ? series.logoUrl : '';
  const credits: CastCredit[] = (
    'credits' in series && Array.isArray(series.credits) ? series.credits : []
  )
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .slice(0, 16);

  const yearLabel =
    series.endYear && series.endYear !== series.year
      ? `${series.year}–${series.endYear}`
      : series.year
        ? String(series.year)
        : '';
  const seasonsLabel = series.seasons > 0 ? `${series.seasons} ${t.common.season}` : '';
  const ratingLabel = series.rating ? `★ ${Number(series.rating).toFixed(1)}` : '';
  const trackGroups = movieDetailTrackGroups(series, {
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
  const heroBackdrop = heroBackdropSrcSet(series.backdrop || series.poster);

  const trailerSrc = useMemo(() => {
    if (!hasTrailer || !trailerReady || heroMode !== 'trailer' || trailerPaused) return '';
    if (trailerMuted) return trailerAutoplayEmbedUrl(series);
    const base = trailerEmbedUrl(series);
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
  }, [hasTrailer, trailerReady, heroMode, series, trailerMuted, trailerPaused]);

  useEffect(() => {
    const update = () => setReduceMotion(prefersReducedMotion());
    update();
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    // Series trailer is button-only — never auto-transition.
    setHeroMode('backdrop');
    setTrailerMuted(true);
    setTrailerPaused(false);
    setTrailerReady(false);
    setOverviewExpanded(false);
  }, [series.id]);

  const goEpisode = (ep: { id: number; season: number }, startOver = false) => {
    navigate(episodePlayerPath(series.id, ep.id, ep.season), {
      state: { autoplay: true, startOver },
    });
  };

  const startTrailer = () => {
    if (!hasTrailer || reduceMotion) return;
    setTrailerReady(true);
    setHeroMode('trailer');
    setTrailerPaused(false);
  };

  const returnToBackdrop = () => {
    setHeroMode('backdrop');
    setTrailerPaused(false);
  };

  const progressPercent = heroCta.kind === 'continue' ? heroCta.progressPercent : null;
  const recs = recommended.filter((item) => item.id !== series.id);

  const episodeLabels = {
    play: t.series.play,
    resume: t.series.resume,
    watchAgain: t.series.watchAgain,
    min: t.common.min,
    unavailable: t.series.unavailable,
    audio: t.movie.audio,
    subtitles: t.movie.subtitles,
    dubbed: t.movie.dubbed,
    subtitled: t.nav.subtitled,
    english: t.player.english,
    persian: t.player.persian === 'Persian' ? 'فارسی' : t.player.persian,
    pashto: t.player.pashto === 'Pashto' ? 'پښتو' : t.player.pashto,
    persianDubbed: t.player.persianDub,
    pashtoDubbed: t.player.pashtoDub,
  };

  void catalogEpisodesForCta;

  return (
    <div className="min-h-screen bg-background" data-testid="series-detail" dir={dir}>
      <section
        className={cn(heroSizing.section, 'md:min-h-[560px]')}
        data-testid="series-hero"
        data-hero-mode={heroMode}
        data-trailer-policy="button-only"
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
              data-testid="series-hero-backdrop"
              {...({ fetchpriority: 'high' } as object)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-secondary to-background" />
          )}
          {heroMode === 'trailer' && trailerSrc ? (
            <iframe
              key={`${trailerSrc}-${trailerMuted ? 'm' : 'u'}`}
              src={trailerSrc}
              title={`${series.title} trailer`}
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
                      alt={series.title}
                      className="max-h-14 w-auto max-w-[min(100%,360px)] object-contain drop-shadow-lg md:max-h-24"
                      data-testid="series-title-logo"
                    />
                    <p className="sr-only">{series.title}</p>
                  </>
                ) : (
                  <h1
                    className={cn(typography.displayTitle, 'max-w-[16ch] text-foreground drop-shadow-lg')}
                    data-testid="series-title-text"
                  >
                    {series.title}
                  </h1>
                )}

                <div className="flex flex-col gap-3">
                  <div
                    className="order-1 flex flex-wrap items-center gap-2 sm:gap-3"
                    aria-label="Series actions"
                    data-testid="series-actions"
                  >
                    {heroCta.kind === 'continue' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goEpisode(heroCta.episode, false)}
                        aria-label={`${t.series.continueWatching} ${heroCta.code}`}
                        data-testid="series-continue-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        {t.series.continueWatching} {heroCta.code}
                        {progressPercent != null ? (
                          <span className="ms-1 text-xs font-semibold opacity-80">{progressPercent}%</span>
                        ) : null}
                      </Button>
                    ) : null}
                    {heroCta.kind === 'next' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goEpisode(heroCta.episode, false)}
                        aria-label={`${t.series.nextEpisode} ${heroCta.code}`}
                        data-testid="series-next-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        {t.series.nextEpisode} {heroCta.code}
                      </Button>
                    ) : null}
                    {heroCta.kind === 'watch_again' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goEpisode(heroCta.episode, true)}
                        aria-label={`${t.series.watchAgain} ${heroCta.code}`}
                        data-testid="series-watch-again-button"
                      >
                        <RotateCcw className="h-5 w-5" />
                        {t.series.watchAgain}
                      </Button>
                    ) : null}
                    {heroCta.kind === 'play' ? (
                      <Button
                        size="xl"
                        variant="play"
                        className="gap-2"
                        onClick={() => goEpisode(heroCta.episode, false)}
                        aria-label={`${t.series.play} ${series.title}`}
                        data-testid="series-play-button"
                      >
                        <Play className="h-5 w-5 fill-current" />
                        {t.series.play}
                      </Button>
                    ) : null}
                    {heroCta.kind === 'unavailable' ? (
                      <span data-testid="series-unavailable">
                        <MetaChip>{t.series.unavailable}</MetaChip>
                      </span>
                    ) : null}

                    <WatchlistButton seriesId={series.id} />
                    {hasTrailer ? (
                      <Button
                        size="lg"
                        variant="glass"
                        className="gap-2"
                        onClick={startTrailer}
                        aria-label={`${t.series.trailer} ${series.title}`}
                        data-testid="series-trailer-button"
                      >
                        <Clapperboard className="h-5 w-5" />
                        {t.series.trailer}
                      </Button>
                    ) : null}
                  </div>

                  <div className="order-2 space-y-2" data-testid="series-hero-meta">
                    <MetaRow
                      asChips
                      items={[
                        yearLabel,
                        seasonsLabel,
                        ratingLabel,
                        ...series.genres.slice(0, 3),
                        series.ageRating,
                      ].filter(Boolean)}
                    />
                    {(trackGroups.audio.length > 0 || trackGroups.subtitles.length > 0) && (
                      <div
                        className="flex flex-col gap-1.5 text-sm text-foreground/90"
                        data-testid="series-track-meta"
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
                    {heroCta.kind === 'continue' && progressPercent != null ? (
                      <div
                        className="h-1 max-w-xs overflow-hidden rounded-full bg-white/15"
                        data-testid="series-continue-progress"
                        aria-hidden="true"
                      >
                        <div className="h-full bg-primary" style={{ width: `${progressPercent}%` }} />
                      </div>
                    ) : null}
                  </div>
                </div>

                {series.description ? (
                  <div className="hidden md:block" data-testid="series-hero-overview">
                    <p className={cn(typography.bodySm, 'max-w-xl', !overviewExpanded && 'line-clamp-3')}>
                      {series.description}
                    </p>
                    {series.description.length > 160 ? (
                      <button
                        type="button"
                        className="mt-1 text-sm font-medium text-primary"
                        onClick={() => setOverviewExpanded((v) => !v)}
                      >
                        {overviewExpanded ? t.series.showLess : t.series.more}
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {heroMode === 'trailer' && hasTrailer ? (
                  <div
                    className="flex flex-wrap items-center gap-2"
                    data-testid="series-trailer-controls"
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
                      {trailerMuted ? t.series.unmute : t.series.mute}
                    </Button>
                    <Button
                      size="sm"
                      variant="glass"
                      className="gap-2"
                      onClick={() => setTrailerPaused((v) => !v)}
                      data-testid="trailer-pause-toggle"
                    >
                      <Pause className="h-4 w-4" />
                      {trailerPaused ? t.series.resumeTrailer : t.series.pause}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-2"
                      onClick={returnToBackdrop}
                      data-testid="trailer-return-backdrop"
                    >
                      <ImageIcon className="h-4 w-4" />
                      {t.series.showBackdrop}
                    </Button>
                  </div>
                ) : null}

                {isDemo ? (
                  <p className="text-xs text-muted-foreground">
                    Demo catalog item: trailer and demo clip access do not indicate full series
                    availability.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="relative z-10 space-y-10 pb-20 pt-2 md:space-y-14">
        {series.description ? (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 md:hidden"
            data-testid="series-about"
          >
            <SectionHeader title={t.series.overview} className="mb-3 px-0" />
            <p
              className={cn(
                typography.body,
                'max-w-3xl text-foreground/90',
                !overviewExpanded && 'line-clamp-5'
              )}
            >
              {series.description}
            </p>
            {series.description.length > 160 ? (
              <button
                type="button"
                className="mt-2 text-sm font-medium text-primary"
                onClick={() => setOverviewExpanded((v) => !v)}
              >
                {overviewExpanded ? t.series.showLess : t.series.more}
              </button>
            ) : null}
          </section>
        ) : null}

        <section
          className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
          data-testid="series-episodes"
          aria-labelledby="episodes-heading"
        >
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <h2 id="episodes-heading" className={typography.sectionTitle}>
              {t.series.episodes}
            </h2>

            {seasons.length > 0 ? (
              <>
                <div className="hidden sm:block" data-testid="season-select-desktop">
                  <Select
                    value={String(selectedSeason)}
                    onValueChange={(v) => onSeasonChange(Number(v))}
                  >
                    <SelectTrigger className="w-[220px] bg-card/80 border-border" aria-label={t.series.selectSeason}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {seasons.map((s) => (
                        <SelectItem key={s.number} value={String(s.number)}>
                          {seasonLabel(t.series, s.number, s.episodeCount)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <Button
                  type="button"
                  variant="secondary"
                  className="gap-2 sm:hidden"
                  onClick={() => setSeasonSheetOpen(true)}
                  data-testid="season-select-mobile"
                  aria-haspopup="dialog"
                  aria-expanded={seasonSheetOpen}
                >
                  {seasonLabel(t.series, selectedSeason, seasons.find((s) => s.number === selectedSeason)?.episodeCount)}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </>
            ) : null}
          </div>

          {!seasons.length ? (
            <p className="py-8 text-center text-muted-foreground" data-testid="series-no-seasons">
              {t.series.noSeasons}
            </p>
          ) : seasonLoading ? (
            <div className="space-y-4" data-testid="episodes-loading">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="grid grid-cols-[120px_1fr] gap-3 sm:grid-cols-[168px_1fr]">
                  <Skeleton className="aspect-video w-full rounded-lg" />
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-3 w-1/3" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : episodes.length ? (
            <div className="divide-y-0">
              {episodes.map((ep) => (
                <EpisodeRow
                  key={ep.id}
                  episode={ep}
                  seriesId={series.id}
                  seriesPoster={series.poster}
                  progress={progressByEpisode.get(ep.id)}
                  onPlay={goEpisode}
                  labels={episodeLabels}
                />
              ))}
            </div>
          ) : (
            <p className="py-6 text-sm text-muted-foreground" data-testid="series-no-episodes">
              {t.series.noEpisodes}
            </p>
          )}
        </section>

        <CastRail
          credits={credits}
          dir={dir}
          headingId="series-cast-heading"
          title={t.series.cast}
          titleClassName={typography.sectionTitle}
          testId="series-cast"
          railTestId="series-cast-rail"
        />

        {recs.length > 0 ? (
          <div data-testid="series-recommendations">
            <ContentShelf title={t.series.moreLikeThis}>
              {recs.map((item) => (
                <MediaCard
                  key={item.id}
                  title={item.title}
                  imageUrl={item.poster}
                  year={item.year}
                  rating={item.rating}
                  showDemo={hasDemoClip(item)}
                  playable
                  onActivate={() => navigate(`/series/${item.id}`)}
                />
              ))}
            </ContentShelf>
          </div>
        ) : null}
      </div>

      <Sheet open={seasonSheetOpen} onOpenChange={setSeasonSheetOpen}>
        <SheetContent
          side="bottom"
          className="rounded-t-2xl pb-[max(1.5rem,env(safe-area-inset-bottom))]"
          data-testid="season-sheet"
        >
          <SheetHeader className="text-start">
            <SheetTitle>{t.series.selectSeason}</SheetTitle>
            <SheetDescription className="sr-only">{t.series.selectSeason}</SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-1" role="listbox" aria-label={t.series.selectSeason}>
            {seasons.map((s) => {
              const selected = s.number === selectedSeason;
              return (
                <button
                  key={s.number}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 rounded-lg px-3 py-3 text-start text-sm transition-colors',
                    selected ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:bg-muted/40'
                  )}
                  onClick={() => {
                    onSeasonChange(s.number);
                    setSeasonSheetOpen(false);
                  }}
                  data-testid={`season-option-${s.number}`}
                >
                  <span className="flex items-center gap-2">
                    <span
                      className={cn(
                        'inline-block h-2.5 w-2.5 rounded-full',
                        selected ? 'bg-primary' : 'bg-transparent ring-1 ring-border'
                      )}
                      aria-hidden="true"
                    />
                    {seasonLabel(t.series, s.number, s.episodeCount)}
                  </span>
                  {selected ? <Check className="h-4 w-4 text-primary" /> : null}
                </button>
              );
            })}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export { buildEpisodeProgressMap };
