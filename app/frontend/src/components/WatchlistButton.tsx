import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth, useLang } from '@/components/CustomerLayout';
import { api, ApiError, tokenStore } from '@/lib/api';
import { isMockMode } from '@/lib/dataMode';
import { toast } from '@/hooks/use-toast';

type Props = {
  movieId?: number;
  seriesId?: number;
  className?: string;
};

export function WatchlistButton({ movieId, seriesId, className }: Props) {
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

  return (
    <Button
      size="lg"
      variant={inList ? 'secondary' : 'outline'}
      className={className ?? 'gap-2'}
      disabled={busy}
      onClick={() => void onToggle()}
      data-testid="watchlist-toggle"
      aria-pressed={inList}
    >
      {inList ? <Check className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
      {inList ? t.profile.watchlist : t.movie.watchlist}
    </Button>
  );
}
