import { useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Play, Info, Star, Clock, ChevronLeft, ChevronRight, Heart, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useLang } from '@/components/CustomerLayout';
import { movies, series, watchHistory } from '@/data/mockData';

// ============ HERO BANNER ============
function HeroBanner() {
  const { t } = useLang();
  const navigate = useNavigate();
  const featured = movies.filter(m => m.featured);
  const [current, setCurrent] = useState(0);
  const movie = featured[current] || featured[0];

  return (
    <section className="relative h-[70vh] md:h-[85vh] w-full overflow-hidden -mt-16 md:-mt-20">
      {/* Backdrop with fallback gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-[hsl(28,24%,8%)] via-[hsl(30,20%,12%)] to-[hsl(28,24%,6%)]">
        <img src={movie.backdrop} alt={movie.title} className="w-full h-full object-cover opacity-60" loading="eager" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-background/20" />
        <div className="absolute inset-0 bg-gradient-to-r from-background/90 via-background/40 to-transparent" />
      </div>

      {/* Content */}
      <div className="relative h-full flex items-end pb-16 md:pb-24">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 max-w-4xl">
          <div className="space-y-4 animate-fade-in">
            <h1 className="text-3xl md:text-5xl lg:text-6xl font-serif font-bold text-foreground leading-tight drop-shadow-lg">
              {movie.title}
            </h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="outline" className="border-primary/50 text-primary">{movie.ageRating}</Badge>
              <span>{movie.year}</span>
              <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{movie.duration} {t.common.min}</span>
              <span className="flex items-center gap-1"><Star className="h-3.5 w-3.5 text-primary fill-primary" />{movie.rating}</span>
              {movie.genres.slice(0, 3).map(g => <Badge key={g} variant="secondary" className="text-xs">{g}</Badge>)}
            </div>
            <p className="text-sm md:text-base text-foreground/80 max-w-2xl line-clamp-3">
              {movie.description}
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{t.movie.audio}: {movie.audio.join(', ')}</span>
              <span className="mx-1">•</span>
              <span>{t.movie.subtitles}: {movie.subtitles.join(', ')}</span>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Button size="lg" onClick={() => navigate(`/player/${movie.id}`)} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2 font-semibold shadow-lg">
                <Play className="h-5 w-5 fill-current" />
                {t.hero.play}
              </Button>
              <Button size="lg" variant="secondary" onClick={() => navigate(`/movie/${movie.id}`)} className="gap-2 shadow-md">
                <Info className="h-5 w-5" />
                {t.hero.moreInfo}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Hero Dots */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2">
        {featured.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`w-2 h-2 rounded-full transition-all ${i === current ? 'bg-primary w-6' : 'bg-foreground/30'}`}
          />
        ))}
      </div>
    </section>
  );
}

// ============ CONTENT ROW ============
function ContentRow({ title, items, type = 'movie' }: { title: string; items: any[]; type?: 'movie' | 'series' }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const scroll = (dir: 'left' | 'right') => {
    if (scrollRef.current) {
      const amount = dir === 'left' ? -400 : 400;
      scrollRef.current.scrollBy({ left: amount, behavior: 'smooth' });
    }
  };

  if (!items.length) return null;

  return (
    <section className="py-4 md:py-6">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-lg md:text-xl font-serif font-bold text-foreground mb-3">{title}</h2>
      </div>
      <div className="relative group">
        <button onClick={() => scroll('left')} className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-background/80 backdrop-blur-sm p-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hidden md:flex">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <div ref={scrollRef} className="flex gap-3 overflow-x-auto hide-scrollbar px-4 sm:px-6 lg:px-8 scroll-smooth">
          {items.map((item) => (
            <div
              key={item.id}
              onClick={() => navigate(type === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)}
              className="flex-shrink-0 w-[140px] md:w-[180px] cursor-pointer group/card"
            >
              <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                <img src={item.poster} alt={item.title} className="w-full h-full object-cover transition-transform duration-300 group-hover/card:scale-105" />
                <div className="absolute inset-0 bg-black/0 group-hover/card:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover/card:opacity-100">
                  <Play className="h-10 w-10 text-white fill-white" />
                </div>
                {/* Badges */}
                <div className="absolute top-2 left-2 right-2 flex justify-between">
                  <Badge className="bg-primary/90 text-primary-foreground text-[10px] px-1.5 py-0.5">
                    {item.qualities?.[0] || '720p'}
                  </Badge>
                  {item.type === 'series' && item.newEpisode && (
                    <Badge className="bg-destructive text-destructive-foreground text-[10px] px-1.5 py-0.5">NEW</Badge>
                  )}
                </div>
                {item.progress && item.progress < 100 && (
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted">
                    <div className="h-full bg-primary" style={{ width: `${item.progress}%` }} />
                  </div>
                )}
              </div>
              <h3 className="text-xs md:text-sm font-medium text-foreground truncate">{item.title}</h3>
              <div className="flex items-center gap-1.5 text-[10px] md:text-xs text-muted-foreground">
                <span>{item.year}</span>
                <span>•</span>
                <span className="flex items-center gap-0.5"><Star className="h-3 w-3 text-primary fill-primary" />{item.rating}</span>
              </div>
            </div>
          ))}
        </div>
        <button onClick={() => scroll('right')} className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-background/80 backdrop-blur-sm p-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hidden md:flex">
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </section>
  );
}

// ============ CONTINUE WATCHING ROW ============
function ContinueWatchingRow() {
  const { t } = useLang();
  const navigate = useNavigate();
  const items = watchHistory.filter(h => h.progress < 100);

  if (!items.length) return null;

  return (
    <section className="py-4 md:py-6">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-lg md:text-xl font-serif font-bold text-foreground mb-3">{t.sections.continueWatching}</h2>
      </div>
      <div className="flex gap-3 overflow-x-auto hide-scrollbar px-4 sm:px-6 lg:px-8">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => navigate(item.type === 'series' ? `/series/${item.contentId}` : `/player/${item.contentId}`)}
            className="flex-shrink-0 w-[200px] md:w-[280px] cursor-pointer group/card"
          >
            <div className="relative aspect-video rounded-lg overflow-hidden bg-muted mb-2">
              <img src={item.poster} alt={item.title} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-black/0 group-hover/card:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover/card:opacity-100">
                <Play className="h-10 w-10 text-white fill-white" />
              </div>
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted/50">
                <div className="h-full bg-primary" style={{ width: `${item.progress}%` }} />
              </div>
            </div>
            <h3 className="text-xs md:text-sm font-medium text-foreground truncate">{item.title}</h3>
            {item.episode && <p className="text-[10px] text-muted-foreground">{item.episode}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

// ============ HOME PAGE ============
export default function HomePage() {
  const { t } = useLang();

  const trending = [...movies].sort((a, b) => b.views - a.views).slice(0, 12);
  const recentlyAdded = [...movies].sort((a, b) => b.year - a.year || b.id - a.id).slice(0, 12);
  const popular = movies.filter(m => m.rating >= 8.0).slice(0, 12);
  const afghanMovies = movies.filter(m => m.country === 'Afghanistan').slice(0, 12);
  const persianDubbed = movies.filter(m => m.dubbed.includes('Persian')).slice(0, 12);
  const pashtoDubbed = movies.filter(m => m.dubbed.includes('Pashto')).slice(0, 12);
  const actionMovies = movies.filter(m => m.genres.includes('Action')).slice(0, 12);
  const comedyMovies = movies.filter(m => m.genres.includes('Comedy')).slice(0, 12);
  const familyMovies = movies.filter(m => m.genres.includes('Family') || m.genres.includes('Animation')).slice(0, 12);
  const popularSeries = [...series].sort((a, b) => b.views - a.views).slice(0, 12);

  return (
    <div>
      <HeroBanner />
      <div className="space-y-2 -mt-8 relative z-10">
        <ContinueWatchingRow />
        <ContentRow title={t.sections.trending} items={trending} />
        <ContentRow title={t.sections.popularSeries} items={popularSeries} type="series" />
        <ContentRow title={t.sections.recentlyAdded} items={recentlyAdded} />
        <ContentRow title={t.sections.popularMovies} items={popular} />
        <ContentRow title={t.sections.afghanMovies} items={afghanMovies} />
        <ContentRow title={t.sections.persianDubbed} items={persianDubbed} />
        <ContentRow title={t.sections.pashtoDubbed} items={pashtoDubbed} />
        <ContentRow title={t.sections.action} items={actionMovies} />
        <ContentRow title={t.sections.comedy} items={comedyMovies} />
        <ContentRow title={t.sections.family} items={familyMovies} />
      </div>
    </div>
  );
}