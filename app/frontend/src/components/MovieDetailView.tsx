import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play,
  Plus,
  Share2,
  Check,
  Clapperboard,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ContentShelf, MediaCard, MetaChip, MetaRow, SectionHeader, typography } from '@/design-system';
import { useLang } from '@/components/CustomerLayout';
import type { CatalogMovie } from '@/lib/catalogData';
import { canPlayFullMovie, fullMovieUnavailableLabel, hasDemoClip, isDemoCatalogItem } from '@/lib/catalogPresentation';
import { trailerEmbedUrl } from '@/lib/trailers';
import { cn } from '@/lib/utils';

function CastAvatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return (
    <div className="flex w-[88px] shrink-0 flex-col items-center gap-2 text-center sm:w-[100px]">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary/30 to-secondary text-sm font-semibold text-foreground ring-1 ring-white/10 sm:h-20 sm:w-20 sm:text-base">
        {initials || '?'}
      </div>
      <p className="line-clamp-2 text-xs font-medium text-foreground sm:text-sm">{name}</p>
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

export function MovieDetailView({
  movie,
  related,
}: {
  movie: CatalogMovie;
  related: CatalogMovie[];
}) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [shared, setShared] = useState(false);
  const trailer = trailerEmbedUrl(movie);
  const playable = canPlayFullMovie(movie);
  const demo = hasDemoClip(movie);
  const isDemo = isDemoCatalogItem(movie);
  const logoUrl = 'logoUrl' in movie && typeof movie.logoUrl === 'string' ? movie.logoUrl : '';
  const tmdbId = 'tmdbId' in movie ? movie.tmdbId : null;
  const runtimeLabel = movie.duration ? `${movie.duration} ${t.common.min}` : '';
  const imdbLabel = movie.rating ? `IMDb ${Number(movie.rating).toFixed(1)}` : '';

  const onShare = async () => {
    const ok = await shareTitle(movie.title, window.location.href);
    if (ok) {
      setShared(true);
      window.setTimeout(() => setShared(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-background" data-testid="movie-detail">
      {/* Cinematic hero */}
      <section className="relative -mt-16 min-h-[78vh] w-full overflow-hidden md:-mt-20 md:min-h-[88vh]">
        <div className="absolute inset-0 bg-[hsl(222,28%,5%)]">
          {movie.backdrop ? (
            <img
              src={movie.backdrop}
              alt=""
              className="h-full w-full object-cover object-top opacity-70"
              loading="eager"
              decoding="async"
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-background/10" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/50 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-transparent" />
        </div>

        <div className="relative z-10 flex min-h-[78vh] items-end pb-10 pt-28 md:min-h-[88vh] md:pb-16 md:pt-32">
          <div className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <div className="grid items-end gap-8 lg:grid-cols-[220px_1fr]">
              <div className="mx-auto hidden w-[200px] shrink-0 md:mx-0 md:block lg:w-[220px]">
                <img
                  src={movie.poster}
                  alt=""
                  className="aspect-[2/3] w-full rounded-xl object-cover shadow-2xl ring-1 ring-white/10"
                />
              </div>

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
                {logoUrl ? (
                  <p className="sr-only">{movie.title}</p>
                ) : null}
                {movie.originalTitle && movie.originalTitle !== movie.title ? (
                  <p className="text-sm text-muted-foreground md:text-base">{movie.originalTitle}</p>
                ) : null}

                <MetaRow
                  asChips
                  items={[
                    movie.ageRating,
                    movie.year,
                    runtimeLabel,
                    movie.country,
                    movie.language,
                    imdbLabel,
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

                {movie.director ? (
                  <p className="text-sm text-foreground/90">
                    <span className="text-muted-foreground">{t.movie.director}: </span>
                    <span className="font-medium">{movie.director}</span>
                  </p>
                ) : null}

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
                      Play
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
                  {trailer ? (
                    <Button size="lg" variant="glass" asChild className="gap-2" data-testid="movie-trailer-button">
                      <a
                        href={trailer}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Watch trailer for ${movie.title}`}
                      >
                        <Clapperboard className="h-5 w-5" />
                        Watch Trailer
                      </a>
                    </Button>
                  ) : null}
                  {!playable && !demo ? (
                    <Badge
                      variant="secondary"
                      className="px-3 py-2 text-sm"
                      data-testid="full-movie-unavailable"
                    >
                      {fullMovieUnavailableLabel()}
                    </Badge>
                  ) : null}
                  <Button
                    size="lg"
                    variant="outline"
                    disabled
                    title="Watchlist sync is not available yet"
                    className="gap-2 opacity-70"
                    data-testid="watchlist-deferred"
                  >
                    <Plus className="h-5 w-5" />
                    Add Watchlist
                  </Button>
                  <Button size="lg" variant="ghost" className="gap-2" onClick={() => void onShare()}>
                    {shared ? <Check className="h-5 w-5 text-success" /> : <Share2 className="h-5 w-5" />}
                    {shared ? 'Copied' : 'Share'}
                  </Button>
                </div>

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

      <div className="relative z-10 space-y-12 pb-16 pt-2 md:space-y-16">
        {/* Overview + technical */}
        {(movie.description ||
          movie.director ||
          movie.audio?.length ||
          movie.subtitles?.length ||
          movie.qualities?.length ||
          movie.country ||
          movie.language ||
          runtimeLabel ||
          imdbLabel) ? (
        <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-10 lg:grid-cols-[1.4fr_1fr]">
            {movie.description ? (
            <div>
              <SectionHeader title="Overview" className="mb-4 px-0" />
              <p className={cn(typography.body, 'text-foreground/90')}>{movie.description}</p>
            </div>
            ) : <div />}
            <div className="rounded-2xl border border-white/8 bg-card/60 p-5 shadow-lg backdrop-blur-sm">
              <h2 className={cn(typography.sectionTitle, 'mb-4')}>Technical Details</h2>
              <dl className="space-y-3 text-sm">
                {[
                  [t.movie.director, movie.director],
                  [t.movie.audio, movie.audio?.join(', ')],
                  [t.movie.subtitles, movie.subtitles?.join(', ')],
                  [t.movie.quality, movie.qualities?.join(', ')],
                  ['Country', movie.country],
                  ['Language', movie.language],
                  ['Runtime', runtimeLabel],
                  ['IMDb', imdbLabel.replace(/^IMDb\s/, '')],
                ]
                  .filter(([, value]) => Boolean(value))
                  .map(([label, value]) => (
                    <div key={String(label)} className="flex justify-between gap-4 border-b border-white/5 pb-2 last:border-0">
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="text-right font-medium text-foreground">{value}</dd>
                    </div>
                  ))}
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                {(movie.qualities ?? []).map((q) => (
                  <MetaChip key={q}>{q}</MetaChip>
                ))}
              </div>
            </div>
          </div>
        </section>
        ) : null}

        {/* Cast */}
        {movie.cast?.length ? (
          <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8" aria-labelledby="cast-heading">
            <h2 id="cast-heading" className={cn(typography.sectionTitle, 'mb-5')}>
              {t.movie.cast}
            </h2>
            <div className="flex gap-4 overflow-x-auto pb-2 hide-scrollbar sm:gap-5">
              {movie.cast.map((person) => (
                <CastAvatar key={person} name={person} />
              ))}
            </div>
          </section>
        ) : null}

        {/* Gallery — only when artwork exists */}
        {movie.poster || movie.backdrop ? (
        <section className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8" aria-labelledby="gallery-heading">
          <h2 id="gallery-heading" className={cn(typography.sectionTitle, 'mb-5')}>
            Gallery
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {movie.poster ? (
              <figure className="overflow-hidden rounded-2xl bg-muted ring-1 ring-white/10">
                <img src={movie.poster} alt={`${movie.title} poster`} className="aspect-[2/3] w-full object-cover sm:aspect-[3/4]" />
              </figure>
            ) : null}
            {movie.backdrop ? (
              <figure className="overflow-hidden rounded-2xl bg-muted ring-1 ring-white/10">
                <img
                  src={movie.backdrop}
                  alt={`${movie.title} backdrop`}
                  className="aspect-video h-full w-full object-cover"
                />
              </figure>
            ) : null}
          </div>
        </section>
        ) : null}

        {/* Trailer */}
        {trailer ? (
          <section
            className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
            aria-labelledby="movie-trailer-heading"
          >
            <h2 id="movie-trailer-heading" className={cn(typography.sectionTitle, 'mb-5')}>
              Watch Trailer
            </h2>
            <div className="aspect-video overflow-hidden rounded-2xl border border-white/10 bg-black shadow-xl">
              <iframe
                src={trailer}
                title={`${movie.title} trailer`}
                className="h-full w-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                loading="lazy"
                data-testid="youtube-trailer-embed"
                referrerPolicy="strict-origin-when-cross-origin"
              />
            </div>
          </section>
        ) : null}

        {/* Similar */}
        {related.length > 0 ? (
          <ContentShelf title={t.movie.related}>
            {related.map((item) => (
              <MediaCard
                key={item.id}
                title={item.title}
                imageUrl={item.poster}
                year={item.year}
                rating={item.rating}
                showDemo={hasDemoClip(item)}
                playable={canPlayFullMovie(item) || hasDemoClip(item)}
                onActivate={() => navigate(`/movie/${item.id}`)}
              />
            ))}
          </ContentShelf>
        ) : null}
      </div>
    </div>
  );
}
