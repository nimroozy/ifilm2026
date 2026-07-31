import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import CustomerLayout, { LangProvider, AuthProvider } from '@/components/CustomerLayout';
import ErrorBoundary from '@/components/ErrorBoundary';
import Index from '@/pages/Index';
import { MoviesPage, SeriesPage, MovieDetailsPage, SeriesDetailsPage, SearchPage } from '@/pages/Browse';
import PlayerPage from '@/pages/PlayerPage';
import { LoginPage, ProfilePage, DevicesPage, WatchlistPage, HistoryPage } from '@/pages/Account';
import RequireAdmin from '@/pages/admin/RequireAdmin';
import AdminLayout from '@/pages/admin/AdminLayout';
import AdminLoginPage from '@/pages/admin/AdminLoginPage';
import DashboardPage from '@/pages/admin/DashboardPage';
import MoviesListPage from '@/pages/admin/MoviesListPage';
import MovieFormPage from '@/pages/admin/MovieFormPage';
import SeriesListPage from '@/pages/admin/SeriesListPage';
import SeriesFormPage from '@/pages/admin/SeriesFormPage';
import SeasonsPage from '@/pages/admin/SeasonsPage';
import SeasonFormPage from '@/pages/admin/SeasonFormPage';
import EpisodesPage from '@/pages/admin/EpisodesPage';
import EpisodeFormPage from '@/pages/admin/EpisodeFormPage';
import GenresPage from '@/pages/admin/GenresPage';
import MediaUploadPage from '@/pages/admin/MediaUploadPage';
import MediaAssetDetailPage from '@/pages/admin/MediaAssetDetailPage';
import MediaProcessingJobsPage from '@/pages/admin/MediaProcessingJobsPage';
import PlaybackSessionsPage from '@/pages/admin/PlaybackSessionsPage';
import AdminPlaceholderPage from '@/pages/admin/AdminPlaceholderPage';

const queryClient = new QueryClient();

function CustomerRoute({ children }: { children: React.ReactNode }) {
  return <CustomerLayout>{children}</CustomerLayout>;
}

const AppRoutes = () => (
  <Routes>
    {/* Customer Routes */}
    <Route path="/" element={<CustomerRoute><Index /></CustomerRoute>} />
    <Route path="/movies" element={<CustomerRoute><MoviesPage /></CustomerRoute>} />
    <Route path="/series" element={<CustomerRoute><SeriesPage /></CustomerRoute>} />
    <Route path="/children" element={<CustomerRoute><MoviesPage /></CustomerRoute>} />
    <Route path="/movie/:id" element={<CustomerRoute><MovieDetailsPage /></CustomerRoute>} />
    <Route path="/series/:id" element={<CustomerRoute><SeriesDetailsPage /></CustomerRoute>} />
    <Route path="/search" element={<CustomerRoute><SearchPage /></CustomerRoute>} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/profile" element={<CustomerRoute><ProfilePage /></CustomerRoute>} />
    <Route path="/devices" element={<CustomerRoute><DevicesPage /></CustomerRoute>} />
    <Route path="/watchlist" element={<CustomerRoute><WatchlistPage /></CustomerRoute>} />
    <Route path="/history" element={<CustomerRoute><HistoryPage /></CustomerRoute>} />
    {/* Player - fullscreen, no layout */}
    <Route path="/player/movie/:id" element={<PlayerPage />} />
    <Route path="/player/episode/:id" element={<PlayerPage />} />
    <Route path="/player/asset/:assetId" element={<PlayerPage />} />
    <Route path="/player/:id" element={<PlayerPage />} />

    {/* Admin */}
    <Route path="/admin/login" element={<AdminLoginPage />} />
    <Route
      path="/admin"
      element={
        <RequireAdmin>
          <AdminLayout />
        </RequireAdmin>
      }
    >
      <Route index element={<DashboardPage />} />
      <Route path="movies" element={<MoviesListPage />} />
      <Route path="movies/new" element={<MovieFormPage />} />
      <Route path="movies/:id/edit" element={<MovieFormPage />} />
      <Route path="series" element={<SeriesListPage />} />
      <Route path="series/new" element={<SeriesFormPage />} />
      <Route path="series/:id/edit" element={<SeriesFormPage />} />
      <Route path="series/:id/seasons" element={<SeasonsPage />} />
      <Route path="seasons/:id/edit" element={<SeasonFormPage />} />
      <Route path="seasons/:id/episodes" element={<EpisodesPage />} />
      <Route path="episodes/:id/edit" element={<EpisodeFormPage />} />
      <Route path="genres" element={<GenresPage />} />
      <Route path="tools/upload" element={<MediaUploadPage />} />
      <Route path="media/processing" element={<MediaProcessingJobsPage />} />
      <Route path="media/playback-sessions" element={<PlaybackSessionsPage />} />
      <Route path="media/:assetId" element={<MediaAssetDetailPage />} />
      <Route path="tools/encoding" element={<AdminPlaceholderPage section="encoding" />} />
      <Route path="tools/cdn" element={<AdminPlaceholderPage section="cdn" />} />
      <Route path="tools/users" element={<AdminPlaceholderPage section="users" />} />
    </Route>
  </Routes>
);

const App = () => (
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        <AuthProvider>
          <TooltipProvider>
            <Toaster />
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </TooltipProvider>
        </AuthProvider>
      </LangProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

export default App;
export { AppRoutes };
