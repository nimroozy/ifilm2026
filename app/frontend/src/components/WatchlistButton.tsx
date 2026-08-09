import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth, useLang } from '@/components/CustomerLayout';
import { api, ApiError, tokenStore } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import { toast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

type Props = {
  movieId?: number;
  seriesId?: number;
  className?: string;
  /** Compact icon-only control (e.g. mobile hero CTA row). */
  iconOnly?: boolean;
};

export function WatchlistButton({ movieId, seriesId, className, iconOnly = false }: Props) {
  const { t } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const mockMode = isMockMode();
  const [inList, setInList] = useState(false);
  const [itemId, setItemId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mockMode || !isLoggedIn || !tokenStore.get()) {
      setInList(false);
      setItemId(null);
      return;
    }
    if ((movieId == null) === (seriesId == null)) return;
    let cancelled = false;
    void api
      .getWatchlistMembership(movieId != null ? { movie_id: movieId } : { series_id: seriesId! })
      .then((res) => {
        if (cancelled) return;
        setInList(res.in_watchlist);
        setItemId(res.item_id);
      })
      .catch(() => {
        if (!cancelled) {
          setInList(false);
          setItemId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isLoggedIn, mockMode, movieId, seriesId]);

  const onToggle = async () => {
    if (mockMode) {
      toast({ title: t.profile.watchlist, description: 'Sign in with API mode to sync your watchlist.' });
      return;
    }
    if (!isLoggedIn || !tokenStore.get()) {
      navigate('/login');
      return;
    }
    if ((movieId == null) === (seriesId == null)) return;
    setBusy(true);
    try {
      if (inList) {
        if (itemId != null) {
          await api.deleteWatchlistItem(itemId);
        } else {
          await api.removeWatchlistByContent(
            movieId != null ? { movie_id: movieId } : { series_id: seriesId! }
          );
        }
        setInList(false);
        setItemId(null);
        toast({ title: t.profile.watchlist, description: 'Removed from watchlist' });
      } else {
        const created = await api.addWatchlistItem(
          movieId != null ? { movie_id: movieId } : { series_id: seriesId! }
        );
        setInList(true);
        setItemId(created.id);
        toast({ title: t.profile.watchlist, description: 'Added to watchlist' });
      }
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Watchlist update failed';
      toast({ title: t.profile.watchlist, description: message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const label = inList ? t.profile.watchlist : t.movie.watchlist;

  return (
    <Button
      size={iconOnly ? 'icon' : 'lg'}
      variant={inList ? 'secondary' : 'outline'}
      className={cn(iconOnly ? 'h-11 w-11 shrink-0' : 'gap-2', className)}
      disabled={busy}
      onClick={() => void onToggle()}
      data-testid="watchlist-toggle"
      aria-pressed={inList}
      aria-label={label}
      title={label}
    >
      {inList ? <Check className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
      {iconOnly ? null : <span>{label}</span>}
    </Button>
  );
}
