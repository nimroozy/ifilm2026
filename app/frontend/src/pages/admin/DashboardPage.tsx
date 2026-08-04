import { useCallback, useEffect, useState } from 'react';
import { Film, Tv, Layers, Clapperboard, Tags, FileText, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { adminApi, ApiError, type DashboardStatsDto } from '@/lib/api';
import { ErrorState, LoadingBlock } from './adminShared';

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
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-foreground">Dashboard</h2>
        <p className="text-sm text-muted-foreground mt-1">Catalog counts from the live admin API.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="dashboard-stats">
        {cards.map((stat) => (
          <Card key={stat.label} className="bg-card border-border">
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
                <span className="text-2xl font-bold text-foreground">{stat.value}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-2">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="bg-card border-border">
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
