import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Film, Tv, Layers, Clapperboard, Tags, FileText, CheckCircle, Plus, Database } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { adminApi, ApiError, type DashboardStatsDto } from '@/lib/api';
import { ErrorState, LoadingBlock, PageHeader } from './adminShared';

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStatsDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.dashboardStats();
      setStats(data);
    } catch (err) {
      setStats(null);
      setError(err instanceof ApiError ? err.message : 'Failed to load dashboard stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingBlock rows={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!stats) return <ErrorState message="No stats available" onRetry={load} />;

  const cards = [
    { label: 'Total Movies', value: stats.total_movies, icon: Film, color: 'text-blue-500' },
    { label: 'Published Movies', value: stats.published_movies, icon: CheckCircle, color: 'text-green-500' },
    { label: 'Draft Movies', value: stats.draft_movies, icon: FileText, color: 'text-yellow-500' },
    { label: 'Total Series', value: stats.total_series, icon: Tv, color: 'text-purple-500' },
    { label: 'Published Series', value: stats.published_series, icon: CheckCircle, color: 'text-emerald-500' },
    { label: 'Seasons', value: stats.total_seasons, icon: Layers, color: 'text-cyan-500' },
    { label: 'Episodes', value: stats.total_episodes, icon: Clapperboard, color: 'text-orange-500' },
    { label: 'Genres', value: stats.total_genres, icon: Tags, color: 'text-primary' },
  ];

  return (
    <div className="min-w-0 max-w-full space-y-6" data-testid="dashboard-page">
      <PageHeader
        title="Dashboard"
        description="Catalog counts from the live admin API."
        actions={
          <>
            <Button asChild className="gap-2 shrink-0">
              <Link to="/admin/movies/new">
                <Plus className="h-4 w-4" />
                New Movie
              </Link>
            </Button>
            <Button asChild className="gap-2 shrink-0">
              <Link to="/admin/series/new">
                <Plus className="h-4 w-4" />
                New Series
              </Link>
            </Button>
            <Button asChild variant="outline" className="gap-2 shrink-0">
              <Link to="/admin/tools/tmdb">
                <Database className="h-4 w-4" />
                Import TMDB
              </Link>
            </Button>
          </>
        }
      />
      <div
        className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4"
        data-testid="dashboard-stats"
      >
        {cards.map((stat) => (
          <Card
            key={stat.label}
            className="min-w-0 border-border/80 bg-card/80 shadow-sm transition-shadow hover:shadow-md"
          >
            <CardContent className="pb-3 pt-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted/80">
                  <stat.icon className={`h-4 w-4 ${stat.color}`} />
                </div>
                <span className="font-display text-2xl font-bold tabular-nums text-foreground">
                  {stat.value}
                </span>
              </div>
              <p className="mt-3 truncate text-xs font-medium text-muted-foreground">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="border-border/80 bg-card/80 shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Operations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground" data-testid="dashboard-ops-deferred">
          <p>
            Use Catalog for metadata, Media → Upload/Processing for packaging, and Publishing readiness on each
            movie/episode edit page before publish.
          </p>
          <p>
            Live Radius remains disabled. CDN and DRM are deferred. Link media from the Media card on movie and
            episode edit pages.
          </p>
          <p>
            Full operational metrics (failed uploads/probes/encodes, active packages, worker health) are deferred to a
            separate issue. This dashboard shows catalog counts from the live admin API only — no decorative charts.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
