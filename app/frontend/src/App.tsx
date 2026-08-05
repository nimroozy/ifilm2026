import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom';
import CustomerLayout, { LangProvider, AuthProvider } from '@/components/CustomerLayout';
import DocumentLangSync from '@/components/DocumentLangSync';
import ErrorBoundary from '@/components/ErrorBoundary';
import Index from '@/pages/Index';
import {
  MoviesPage,
  ChildrenPage,
  SeriesPage,
  MovieDetailsPage,
  SeriesDetailsPage,
  SearchPage,
} from '@/pages/Browse';
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
import SystemUpdatesPage from '@/pages/admin/SystemUpdatesPage';
import TmdbToolsPage from '@/pages/admin/TmdbToolsPage';
import AdminPlaceholderPage from '@/pages/admin/AdminPlaceholderPage';
import AboutPage from '@/pages/AboutPage';

const queryClient = new QueryClient();

function CustomerRoute({ children }: { children: React.ReactNode }) {
  return <CustomerLayout>{children}</CustomerLayout>;
}

function RootLayout() {
  return (
    <>
      <DocumentLangSync />
      <Outlet />
    </>
  );
}

/** Data router required for useBlocker (unsaved-change guard on MovieFormPage). */
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <CustomerRoute><Index /></CustomerRoute> },
      { path: '/movies', element: <CustomerRoute><MoviesPage /></CustomerRoute> },
      { path: '/series', element: <CustomerRoute><SeriesPage /></CustomerRoute> },
      { path: '/children', element: <CustomerRoute><ChildrenPage /></CustomerRoute> },
      { path: '/movie/:id', element: <CustomerRoute><MovieDetailsPage /></CustomerRoute> },
      { path: '/series/:id', element: <CustomerRoute><SeriesDetailsPage /></CustomerRoute> },
      { path: '/search', element: <CustomerRoute><SearchPage /></CustomerRoute> },
      { path: '/about', element: <CustomerRoute><AboutPage /></CustomerRoute> },
      { path: '/credits', element: <CustomerRoute><AboutPage /></CustomerRoute> },
      { path: '/login', element: <LoginPage /> },
      { path: '/profile', element: <CustomerRoute><ProfilePage /></CustomerRoute> },
      { path: '/devices', element: <CustomerRoute><DevicesPage /></CustomerRoute> },
      { path: '/watchlist', element: <CustomerRoute><WatchlistPage /></CustomerRoute> },
      { path: '/history', element: <CustomerRoute><HistoryPage /></CustomerRoute> },
      { path: '/player/movie/:id', element: <PlayerPage /> },
      { path: '/player/episode/:id', element: <PlayerPage /> },
      { path: '/player/asset/:assetId', element: <PlayerPage /> },
      { path: '/player/:id', element: <PlayerPage /> },
      { path: '/admin/login', element: <AdminLoginPage /> },
      {
        path: '/admin',
        element: (
          <RequireAdmin>
            <AdminLayout />
          </RequireAdmin>
        ),
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'movies', element: <MoviesListPage /> },
          { path: 'movies/new', element: <MovieFormPage /> },
          { path: 'movies/:id/edit', element: <MovieFormPage /> },
          { path: 'series', element: <SeriesListPage /> },
          { path: 'series/new', element: <SeriesFormPage /> },
          { path: 'series/:id/edit', element: <SeriesFormPage /> },
          { path: 'series/:id/seasons', element: <SeasonsPage /> },
          { path: 'seasons/:id/edit', element: <SeasonFormPage /> },
          { path: 'seasons/:id/episodes', element: <EpisodesPage /> },
          { path: 'episodes/:id/edit', element: <EpisodeFormPage /> },
          { path: 'genres', element: <GenresPage /> },
          { path: 'tools/upload', element: <MediaUploadPage /> },
          { path: 'tools/tmdb', element: <TmdbToolsPage /> },
          { path: 'media/processing', element: <MediaProcessingJobsPage /> },
          { path: 'media/playback-sessions', element: <PlaybackSessionsPage /> },
          { path: 'media/:assetId', element: <MediaAssetDetailPage /> },
          { path: 'system/updates', element: <SystemUpdatesPage /> },
          { path: 'tools/encoding', element: <AdminPlaceholderPage section="encoding" /> },
          { path: 'tools/cdn', element: <AdminPlaceholderPage section="cdn" /> },
          { path: 'tools/users', element: <AdminPlaceholderPage section="users" /> },
        ],
      },
    ],
  },
]);

const App = () => (
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        <AuthProvider>
          <TooltipProvider>
            <Toaster />
            <RouterProvider router={router} />
          </TooltipProvider>
        </AuthProvider>
      </LangProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

export default App;
