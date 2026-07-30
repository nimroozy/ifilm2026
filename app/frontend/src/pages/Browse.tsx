import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Play, Star, Clock, Heart, Plus, Share2, ChevronDown, Filter, Grid, List, Search as SearchIcon, X, Volume2, Maximize, SkipForward, SkipBack, Settings, Pause, Wifi, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { useLang } from '@/components/CustomerLayout';
import { movies, series, episodes, genres, type Movie, type Series as SeriesType } from '@/data/mockData';

// ============ MOVIES PAGE ============
export function MoviesPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');
  const [sort, setSort] = useState('newest');
  const [view, setView] = useState<'grid' | 'list'>('grid');

  const filtered = useMemo(() => {
    let result = [...movies];
    if (search) result = result.filter(m => m.title.toLowerCase().includes(search.toLowerCase()) || m.originalTitle.includes(search));
    if (genre !== 'all') result = result.filter(m => m.genres.includes(genre));
    if (sort === 'newest') result.sort((a, b) => b.year - a.year);
    else if (sort === 'rating') result.sort((a, b) => b.rating - a.rating);
    else if (sort === 'popular') result.sort((a, b) => b.views - a.views);
    else if (sort === 'title') result.sort((a, b) => a.title.localeCompare(b.title));
    return result;
  }, [search, genre, sort]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.nav.movies}</h1>
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder={t.search.placeholder} value={search} onChange={e => setSearch(e.target.value)} className="pl-9 bg-card border-border" />
          </div>
          <Select value={genre} onValueChange={setGenre}>
            <SelectTrigger className="w-[140px] bg-card border-border"><SelectValue placeholder={t.common.filter} /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t.common.all}</SelectItem>
              {genres.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="w-[140px] bg-card border-border"><SelectValue placeholder={t.common.sort} /></SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest</SelectItem>
              <SelectItem value="rating">Rating</SelectItem>
              <SelectItem value="popular">Popular</SelectItem>
              <SelectItem value="title">Title</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex gap-1">
            <Button variant={view === 'grid' ? 'default' : 'outline'} size="icon" onClick={() => setView('grid')}><Grid className="h-4 w-4" /></Button>
            <Button variant={view === 'list' ? 'default' : 'outline'} size="icon" onClick={() => setView('list')}><List className="h-4 w-4" /></Button>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground"><p className="text-lg">{t.search.noResults}</p></div>
        ) : view === 'grid' ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {filtered.map(movie => (
              <div key={movie.id} onClick={() => navigate(`/movie/${movie.id}`)} className="cursor-pointer group">
                <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                  <img src={movie.poster} alt={movie.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                    <Play className="h-10 w-10 text-white fill-white" />
                  </div>
                  <Badge className="absolute top-2 left-2 bg-primary/90 text-primary-foreground text-[10px]">{movie.qualities[0]}</Badge>
                </div>
                <h3 className="text-sm font-medium text-foreground truncate">{movie.title}</h3>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{movie.year}</span><span>•</span><Star className="h-3 w-3 text-primary fill-primary" /><span>{movie.rating}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(movie => (
              <div key={movie.id} onClick={() => navigate(`/movie/${movie.id}`)} className="flex gap-4 p-3 rounded-lg bg-card hover:bg-card/80 cursor-pointer transition-colors">
                <img src={movie.poster} alt={movie.title} className="w-16 h-24 rounded object-cover flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-foreground">{movie.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{movie.genres.join(', ')}</p>
                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                    <span>{movie.year}</span><span>{movie.duration} min</span><Star className="h-3 w-3 text-primary fill-primary" /><span>{movie.rating}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ SERIES PAGE ============
export function SeriesPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('all');

  const filtered = useMemo(() => {
    let result = [...series];
    if (search) result = result.filter(s => s.title.toLowerCase().includes(search.toLowerCase()));
    if (genre !== 'all') result = result.filter(s => s.genres.includes(genre));
    return result.sort((a, b) => b.views - a.views);
  }, [search, genre]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground mb-6">{t.nav.series}</h1>
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder={t.search.placeholder} value={search} onChange={e => setSearch(e.target.value)} className="pl-9 bg-card border-border" />
          </div>
          <Select value={genre} onValueChange={setGenre}>
            <SelectTrigger className="w-[140px] bg-card border-border"><SelectValue placeholder={t.common.filter} /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t.common.all}</SelectItem>
              {genres.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {filtered.map(s => (
            <div key={s.id} onClick={() => navigate(`/series/${s.id}`)} className="cursor-pointer group">
              <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                <img src={s.poster} alt={s.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center opacity-0 group-hover:opacity-100">
                  <Play className="h-10 w-10 text-white fill-white" />
                </div>
                {s.newEpisode && <Badge className="absolute top-2 right-2 bg-destructive text-destructive-foreground text-[10px]">NEW</Badge>}
                <Badge className="absolute bottom-2 left-2 bg-background/80 text-foreground text-[10px]">{s.seasons}S • {s.episodes}E</Badge>
              </div>
              <h3 className="text-sm font-medium text-foreground truncate">{s.title}</h3>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>{s.year}</span><span>•</span><Star className="h-3 w-3 text-primary fill-primary" /><span>{s.rating}</span>
                <span>•</span><span>{s.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============ MOVIE DETAILS PAGE ============
export function MovieDetailsPage() {
  const { id } = useParams();
  const { t } = useLang();
  const navigate = useNavigate();
  const movie = movies.find(m => m.id === Number(id));
  const [inWatchlist, setInWatchlist] = useState(false);
  const [liked, setLiked] = useState(false);

  if (!movie) return <div className="min-h-screen flex items-center justify-center text-foreground">Movie not found</div>;

  const related = movies.filter(m => m.id !== movie.id && m.genres.some(g => movie.genres.includes(g))).slice(0, 6);

  return (
    <div className="min-h-screen">
      {/* Backdrop */}
      <div className="relative h-[50vh] md:h-[60vh]">
        <img src={movie.backdrop} alt={movie.title} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 -mt-32 relative z-10 pb-12">
        <div className="flex flex-col md:flex-row gap-6 md:gap-8">
          {/* Poster */}
          <div className="flex-shrink-0 w-[180px] md:w-[220px] mx-auto md:mx-0">
            <img src={movie.poster} alt={movie.title} className="w-full rounded-lg shadow-xl" />
          </div>

          {/* Info */}
          <div className="flex-1 space-y-4">
            <h1 className="text-2xl md:text-4xl font-serif font-bold text-foreground">{movie.title}</h1>
            <p className="text-sm text-muted-foreground">{movie.originalTitle}</p>

            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="outline" className="border-primary/50 text-primary">{movie.ageRating}</Badge>
              <span>{movie.year}</span>
              <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{movie.duration} {t.common.min}</span>
              <span className="flex items-center gap-1"><Star className="h-4 w-4 text-primary fill-primary" />{movie.rating}/10</span>
              <span>{movie.country}</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {movie.genres.map(g => <Badge key={g} variant="secondary">{g}</Badge>)}
            </div>

            <p className="text-sm md:text-base text-foreground/80 leading-relaxed">{movie.description}</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div><span className="text-muted-foreground">{t.movie.director}:</span> <span className="text-foreground">{movie.director}</span></div>
              <div><span className="text-muted-foreground">{t.movie.cast}:</span> <span className="text-foreground">{movie.cast.join(', ')}</span></div>
              <div><span className="text-muted-foreground">{t.movie.audio}:</span> <span className="text-foreground">{movie.audio.join(', ')}</span></div>
              <div><span className="text-muted-foreground">{t.movie.subtitles}:</span> <span className="text-foreground">{movie.subtitles.join(', ')}</span></div>
              <div><span className="text-muted-foreground">{t.movie.quality}:</span> <span className="text-foreground">{movie.qualities.join(', ')}</span></div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Button size="lg" onClick={() => navigate(`/player/${movie.id}`)} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2 font-semibold">
                <Play className="h-5 w-5 fill-current" />{t.movie.play}
              </Button>
              <Button variant="outline" size="lg" onClick={() => setInWatchlist(!inWatchlist)} className={`gap-2 ${inWatchlist ? 'border-primary text-primary' : ''}`}>
                <Plus className="h-5 w-5" />{t.movie.watchlist}
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setLiked(!liked)} className={liked ? 'text-destructive' : ''}>
                <Heart className={`h-5 w-5 ${liked ? 'fill-current' : ''}`} />
              </Button>
              <Button variant="ghost" size="icon"><Share2 className="h-5 w-5" /></Button>
            </div>
          </div>
        </div>

        {/* Related */}
        {related.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-serif font-bold text-foreground mb-4">{t.movie.related}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {related.map(m => (
                <div key={m.id} onClick={() => navigate(`/movie/${m.id}`)} className="cursor-pointer group">
                  <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                    <img src={m.poster} alt={m.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                  </div>
                  <h3 className="text-xs font-medium text-foreground truncate">{m.title}</h3>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============ SERIES DETAILS PAGE ============
export function SeriesDetailsPage() {
  const { id } = useParams();
  const { t } = useLang();
  const navigate = useNavigate();
  const show = series.find(s => s.id === Number(id));
  const [selectedSeason, setSelectedSeason] = useState(1);

  if (!show) return <div className="min-h-screen flex items-center justify-center text-foreground">Series not found</div>;

  const showEpisodes = episodes.filter(e => e.seriesId === show.id && e.season === selectedSeason);

  return (
    <div className="min-h-screen">
      <div className="relative h-[40vh] md:h-[50vh]">
        <img src={show.backdrop} alt={show.title} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 -mt-24 relative z-10 pb-12">
        <div className="flex flex-col md:flex-row gap-6">
          <div className="flex-shrink-0 w-[160px] md:w-[200px] mx-auto md:mx-0">
            <img src={show.poster} alt={show.title} className="w-full rounded-lg shadow-xl" />
          </div>
          <div className="flex-1 space-y-3">
            <h1 className="text-2xl md:text-3xl font-serif font-bold text-foreground">{show.title}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="outline" className="border-primary/50 text-primary">{show.ageRating}</Badge>
              <span>{show.year}</span>
              <span>{show.seasons} {t.common.season}s</span>
              <span>{show.episodes} {t.common.episode}s</span>
              <Badge variant={show.status === 'Ongoing' ? 'default' : 'secondary'}>{show.status}</Badge>
              <Star className="h-4 w-4 text-primary fill-primary" /><span>{show.rating}</span>
            </div>
            <p className="text-sm text-foreground/80">{show.description}</p>
            <div className="flex flex-wrap gap-2">{show.genres.map(g => <Badge key={g} variant="secondary">{g}</Badge>)}</div>
            <Button size="lg" onClick={() => navigate(`/player/${show.id}`)} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
              <Play className="h-5 w-5 fill-current" />{t.movie.play}
            </Button>
          </div>
        </div>

        {/* Season Selector & Episodes */}
        <div className="mt-8">
          <div className="flex items-center gap-4 mb-4">
            <Select value={String(selectedSeason)} onValueChange={v => setSelectedSeason(Number(v))}>
              <SelectTrigger className="w-[160px] bg-card border-border"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Array.from({ length: show.seasons }, (_, i) => (
                  <SelectItem key={i + 1} value={String(i + 1)}>{t.common.season} {i + 1}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-3">
            {showEpisodes.length > 0 ? showEpisodes.map(ep => (
              <div key={ep.id} onClick={() => navigate(`/player/${show.id}?ep=${ep.id}`)} className="flex gap-4 p-3 rounded-lg bg-card hover:bg-card/80 cursor-pointer transition-colors">
                <div className="relative w-[120px] md:w-[160px] flex-shrink-0">
                  <img src={ep.thumbnail} alt={ep.title} className="w-full aspect-video rounded object-cover" />
                  {ep.progress && ep.progress < 100 && (
                    <div className="absolute bottom-0 left-0 right-0 h-1 bg-muted"><div className="h-full bg-primary" style={{ width: `${ep.progress}%` }} /></div>
                  )}
                  {ep.watched && <Badge className="absolute top-1 right-1 bg-primary/80 text-[9px]">✓</Badge>}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-foreground text-sm">E{ep.episode} - {ep.title}</h4>
                  <p className="text-xs text-muted-foreground mt-1">{ep.duration} {t.common.min}</p>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{ep.description}</p>
                </div>
              </div>
            )) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No episodes available for this season yet.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ VIDEO PLAYER PAGE ============
export function PlayerPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useLang();
  const [isPlaying, setIsPlaying] = useState(true);
  const [progress, setProgress] = useState([32]);
  const [volume, setVolume] = useState([80]);
  const [showControls, setShowControls] = useState(true);
  const [quality, setQuality] = useState('1080p');
  const [showSkipIntro, setShowSkipIntro] = useState(true);

  const movie = movies.find(m => m.id === Number(id)) || movies[0];
  const cdnNode = 'Kabul CDN';

  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col" onMouseMove={() => setShowControls(true)}>
      {/* Video Area */}
      <div className="flex-1 relative flex items-center justify-center bg-gradient-to-br from-black via-gray-900 to-black">
        <img src={movie.backdrop} alt={movie.title} className="absolute inset-0 w-full h-full object-cover opacity-30" />
        <div className="absolute inset-0 flex items-center justify-center">
          <Button variant="ghost" size="icon" onClick={() => setIsPlaying(!isPlaying)} className="h-20 w-20 rounded-full bg-black/40 hover:bg-black/60 text-white">
            {isPlaying ? <Pause className="h-10 w-10" /> : <Play className="h-10 w-10 fill-white" />}
          </Button>
        </div>

        {/* Skip Intro */}
        {showSkipIntro && (
          <Button onClick={() => setShowSkipIntro(false)} className="absolute bottom-24 right-6 bg-foreground/20 backdrop-blur-sm text-white border border-white/30 hover:bg-foreground/30">
            Skip Intro →
          </Button>
        )}

        {/* Top Bar */}
        <div className={`absolute top-0 left-0 right-0 p-4 flex items-center justify-between bg-gradient-to-b from-black/60 to-transparent transition-opacity ${showControls ? 'opacity-100' : 'opacity-0'}`}>
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="text-white hover:bg-white/10">
            <X className="h-6 w-6" />
          </Button>
          <div className="text-center">
            <h3 className="text-white font-medium text-sm">{movie.title}</h3>
          </div>
          <div className="flex items-center gap-1 text-xs text-white/70">
            <Wifi className="h-3.5 w-3.5 text-green-400" />
            <span>{cdnNode}</span>
          </div>
        </div>

        {/* Bottom Controls */}
        <div className={`absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent transition-opacity ${showControls ? 'opacity-100' : 'opacity-0'}`}>
          {/* Progress Bar */}
          <div className="mb-3">
            <Slider value={progress} onValueChange={setProgress} max={100} step={1} className="w-full [&_[role=slider]]:bg-primary [&_[role=slider]]:border-primary" />
            <div className="flex justify-between text-xs text-white/70 mt-1">
              <span>0:41:12</span>
              <span>2:08:00</span>
            </div>
          </div>

          {/* Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/10"><SkipBack className="h-5 w-5" /></Button>
              <Button variant="ghost" size="icon" onClick={() => setIsPlaying(!isPlaying)} className="text-white hover:bg-white/10">
                {isPlaying ? <Pause className="h-6 w-6" /> : <Play className="h-6 w-6 fill-white" />}
              </Button>
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/10"><SkipForward className="h-5 w-5" /></Button>
              <div className="flex items-center gap-1 ml-2 w-24">
                <Volume2 className="h-4 w-4 text-white" />
                <Slider value={volume} onValueChange={setVolume} max={100} step={1} className="[&_[role=slider]]:bg-white [&_[role=slider]]:border-white" />
              </div>
            </div>

            <div className="flex items-center gap-1">
              <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-[10px]">{quality}</Badge>
              <Select value={quality} onValueChange={setQuality}>
                <SelectTrigger className="w-auto h-8 bg-transparent border-none text-white text-xs gap-1 px-2"><Settings className="h-4 w-4" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto</SelectItem>
                  <SelectItem value="1080p">1080p</SelectItem>
                  <SelectItem value="720p">720p</SelectItem>
                  <SelectItem value="480p">480p</SelectItem>
                  <SelectItem value="360p">360p</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/10"><Monitor className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/10"><Maximize className="h-5 w-5" /></Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ SEARCH PAGE ============
export function SearchPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  const popularSearches = ['Action', 'Comedy', 'Afghan Movies', 'New Releases', 'Dubbed', 'Drama'];

  const results = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    const movieResults = movies.filter(m => m.title.toLowerCase().includes(q) || m.originalTitle.includes(query) || m.cast.some(c => c.toLowerCase().includes(q)) || m.director.toLowerCase().includes(q));
    const seriesResults = series.filter(s => s.title.toLowerCase().includes(q) || s.originalTitle.includes(query));
    return [...movieResults.map(m => ({ ...m, resultType: 'movie' as const })), ...seriesResults.map(s => ({ ...s, resultType: 'series' as const }))];
  }, [query]);

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        {/* Search Input */}
        <div className="relative max-w-2xl mx-auto mb-8">
          <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
          <Input
            placeholder={t.search.placeholder}
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="pl-12 h-14 text-lg bg-card border-border rounded-xl"
            autoFocus
          />
          {query && (
            <Button variant="ghost" size="icon" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
              <X className="h-5 w-5" />
            </Button>
          )}
        </div>

        {!query ? (
          <div className="max-w-2xl mx-auto">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">{t.search.popular}</h3>
            <div className="flex flex-wrap gap-2">
              {popularSearches.map(s => (
                <Button key={s} variant="secondary" size="sm" onClick={() => setQuery(s)} className="rounded-full">{s}</Button>
              ))}
            </div>
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground"><p className="text-lg">{t.search.noResults}</p></div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {results.map(item => (
              <div key={`${item.resultType}-${item.id}`} onClick={() => navigate(item.resultType === 'series' ? `/series/${item.id}` : `/movie/${item.id}`)} className="cursor-pointer group">
                <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-muted mb-2">
                  <img src={item.poster} alt={item.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                  <Badge className="absolute top-2 left-2 bg-primary/90 text-primary-foreground text-[10px]">{item.resultType === 'series' ? 'Series' : 'Movie'}</Badge>
                </div>
                <h3 className="text-sm font-medium text-foreground truncate">{item.title}</h3>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>{item.year}</span><span>•</span><Star className="h-3 w-3 text-primary fill-primary" /><span>{item.rating}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}