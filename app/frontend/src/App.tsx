import { lazy, Suspense, type ReactNode } from 'react';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider, Outlet, Navigate } from 'react-router-dom';
import CustomerLayout, { LangProvider, AuthProvider } from '@/components/CustomerLayout';
import DocumentLangSync from '@/components/DocumentLangSync';
import CustomerDocumentTitle from '@/components/customer/CustomerDocumentTitle';
import ErrorBoundary from '@/components/ErrorBoundary';
import Index from '@/pages/Index';

/** Customer shell + home stay eager; everything else is route-split. */
const MoviesPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.MoviesPage }))
);
const ChildrenPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.ChildrenPage }))
);
const SeriesPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.SeriesPage }))
);
const MovieDetailsPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.MovieDetailsPage }))
);
const SeriesDetailsPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.SeriesDetailsPage }))
);
const SearchPage = lazy(() =>
  import('@/pages/Browse').then((m) => ({ default: m.SearchPage }))
);
const CollectionsIndexPage = lazy(() =>
  import('@/pages/CollectionsPages').then((m) => ({ default: m.CollectionsIndexPage }))
);
const CollectionDetailPage = lazy(() =>
  import('@/pages/CollectionsPages').then((m) => ({ default: m.CollectionDetailPage }))
);
const LoginPage = lazy(() =>
  import('@/pages/Account').then((m) => ({ default: m.LoginPage }))
);
const ProfilePage = lazy(() =>
  import('@/pages/Account').then((m) => ({ default: m.ProfilePage }))
);
const DevicesPage = lazy(() =>
  import('@/pages/Account').then((m) => ({ default: m.DevicesPage }))
);
const WatchlistPage = lazy(() =>
  import('@/pages/Account').then((m) => ({ default: m.WatchlistPage }))
);
const HistoryPage = lazy(() =>
  import('@/pages/Account').then((m) => ({ default: m.HistoryPage }))
);
const GenresBrowsePage = lazy(() =>
  import('@/pages/CatalogBrowsePages').then((m) => ({ default: m.GenresBrowsePage }))
);
const DubbedPage = lazy(() =>
  import('@/pages/CatalogBrowsePages').then((m) => ({ default: m.DubbedPage }))
);
const SubtitledPage = lazy(() =>
  import('@/pages/CatalogBrowsePages').then((m) => ({ default: m.SubtitledPage }))
);
const NewReleasesPage = lazy(() =>
  import('@/pages/CatalogBrowsePages').then((m) => ({ default: m.NewReleasesPage }))
);
const AboutPage = lazy(() => import('@/pages/LegalPages'));
const ContactPage = lazy(() =>
  import('@/pages/LegalPages').then((m) => ({ default: m.ContactPage }))
);
const HelpPage = lazy(() =>
  import('@/pages/LegalPages').then((m) => ({ default: m.HelpPage }))
);
const PrivacyPage = lazy(() =>
  import('@/pages/LegalPages').then((m) => ({ default: m.PrivacyPage }))
);
const TermsPage = lazy(() =>
  import('@/pages/LegalPages').then((m) => ({ default: m.TermsPage }))
);
const CopyrightPage = lazy(() =>
  import('@/pages/LegalPages').then((m) => ({ default: m.CopyrightPage }))
);
const WhatToWatchPage = lazy(() => import('@/pages/WhatToWatchPage'));
const PlayerPage = lazy(() => import('@/pages/PlayerPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));

const RequireAdmin = lazy(() => import('@/pages/admin/RequireAdmin'));
const AdminLayout = lazy(() => import('@/pages/admin/AdminLayout'));
const AdminLoginPage = lazy(() => import('@/pages/admin/AdminLoginPage'));
const DashboardPage = lazy(() => import('@/pages/admin/DashboardPage'));
const MoviesListPage = lazy(() => import('@/pages/admin/MoviesListPage'));
const MovieFormPage = lazy(() => import('@/pages/admin/MovieFormPage'));
const SeriesListPage = lazy(() => import('@/pages/admin/SeriesListPage'));
const SeriesFormPage = lazy(() => import('@/pages/admin/SeriesFormPage'));
const SeasonsPage = lazy(() => import('@/pages/admin/SeasonsPage'));
const SeasonFormPage = lazy(() => import('@/pages/admin/SeasonFormPage'));
const EpisodesPage = lazy(() => import('@/pages/admin/EpisodesPage'));
const EpisodeFormPage = lazy(() => import('@/pages/admin/EpisodeFormPage'));
const GenresPage = lazy(() => import('@/pages/admin/GenresPage'));
const CollectionsListPage = lazy(() => import('@/pages/admin/CollectionsListPage'));
const CollectionFormPage = lazy(() => import('@/pages/admin/CollectionFormPage'));
const MediaUploadPage = lazy(() => import('@/pages/admin/MediaUploadPage'));
const MediaAssetDetailPage = lazy(() => import('@/pages/admin/MediaAssetDetailPage'));
const MediaStorageHealthPage = lazy(() => import('@/pages/admin/MediaStorageHealthPage'));
const MediaProcessingJobsPage = lazy(() => import('@/pages/admin/MediaProcessingJobsPage'));
const PlaybackSessionsPage = lazy(() => import('@/pages/admin/PlaybackSessionsPage'));
const SystemUpdatesPage = lazy(() => import('@/pages/admin/SystemUpdatesPage'));
const TmdbToolsPage = lazy(() => import('@/pages/admin/TmdbToolsPage'));
const AdminPlaceholderPage = lazy(() => import('@/pages/admin/AdminPlaceholderPage'));
const RecommendationsInspectPage = lazy(() =>
  import('@/pages/admin/RecommendationsInspectPage')
);

const queryClient = new QueryClient();

function CustomerRoute({ children }: { children: ReactNode }) {
  return <CustomerLayout>{children}</CustomerLayout>;
}

function LazyPage({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-[40vh]" data-testid="route-loading" />}>
      {children}
    </Suspense>
  );
}

function AdminGate({ children }: { children: ReactNode }) {
  return (
    <LazyPage>
      <RequireAdmin>
        <Suspense fallback={<div className="min-h-[40vh]" data-testid="route-loading" />}>
          {children}
        </Suspense>
      </RequireAdmin>
    </LazyPage>
  );
}

function RootLayout() {
  return (
    <>
      <DocumentLangSync />
      <CustomerDocumentTitle />
      <Outlet />
    </>
  );
}

function customerLazy(element: ReactNode) {
  return (
    <CustomerRoute>
      <LazyPage>{element}</LazyPage>
    </CustomerRoute>
  );
}

/** Data router required for useBlocker (unsaved-change guard on MovieFormPage). */
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <CustomerRoute><Index /></CustomerRoute> },
      { path: '/movies', element: customerLazy(<MoviesPage />) },
      { path: '/series', element: customerLazy(<SeriesPage />) },
      { path: '/children', element: customerLazy(<ChildrenPage />) },
      { path: '/kids', element: <Navigate to="/children" replace /> },
      { path: '/genres', element: customerLazy(<GenresBrowsePage />) },
      { path: '/collections', element: customerLazy(<CollectionsIndexPage />) },
      { path: '/collections/:slug', element: customerLazy(<CollectionDetailPage />) },
      { path: '/dubbed', element: customerLazy(<DubbedPage />) },
      { path: '/subtitled', element: customerLazy(<SubtitledPage />) },
      { path: '/new-releases', element: customerLazy(<NewReleasesPage />) },
      { path: '/what-to-watch', element: customerLazy(<WhatToWatchPage />) },
      { path: '/movie/:id', element: customerLazy(<MovieDetailsPage />) },
      { path: '/series/:id', element: customerLazy(<SeriesDetailsPage />) },
      { path: '/search', element: customerLazy(<SearchPage />) },
      { path: '/about', element: customerLazy(<AboutPage />) },
      { path: '/credits', element: customerLazy(<AboutPage />) },
      { path: '/contact', element: customerLazy(<ContactPage />) },
      { path: '/help', element: customerLazy(<HelpPage />) },
      { path: '/privacy', element: customerLazy(<PrivacyPage />) },
      { path: '/terms', element: customerLazy(<TermsPage />) },
      { path: '/copyright', element: customerLazy(<CopyrightPage />) },
      {
        path: '/login',
        element: (
          <LazyPage>
            <LoginPage />
          </LazyPage>
        ),
      },
      { path: '/profile', element: customerLazy(<ProfilePage />) },
      { path: '/devices', element: customerLazy(<DevicesPage />) },
      { path: '/watchlist', element: customerLazy(<WatchlistPage />) },
      { path: '/history', element: customerLazy(<HistoryPage />) },
      {
        path: '/player/movie/:id',
        element: (
          <LazyPage>
            <PlayerPage />
          </LazyPage>
        ),
      },
      {
        path: '/player/episode/:id',
        element: (
          <LazyPage>
            <PlayerPage />
          </LazyPage>
        ),
      },
      {
        path: '/player/asset/:assetId',
        element: (
          <LazyPage>
            <PlayerPage />
          </LazyPage>
        ),
      },
      {
        path: '/player/:id',
        element: (
          <LazyPage>
            <PlayerPage />
          </LazyPage>
        ),
      },
      {
        path: '/admin/login',
        element: (
          <LazyPage>
            <AdminLoginPage />
          </LazyPage>
        ),
      },
      {
        path: '/admin',
        element: (
          <AdminGate>
            <AdminLayout />
          </AdminGate>
        ),
        children: [
          { index: true, element: <LazyPage><DashboardPage /></LazyPage> },
          { path: 'movies', element: <LazyPage><MoviesListPage /></LazyPage> },
          { path: 'movies/new', element: <LazyPage><MovieFormPage /></LazyPage> },
          { path: 'movies/:id/edit', element: <LazyPage><MovieFormPage /></LazyPage> },
          { path: 'series', element: <LazyPage><SeriesListPage /></LazyPage> },
          { path: 'series/new', element: <LazyPage><SeriesFormPage /></LazyPage> },
          { path: 'series/:id/edit', element: <LazyPage><SeriesFormPage /></LazyPage> },
          { path: 'series/:id/seasons', element: <LazyPage><SeasonsPage /></LazyPage> },
          { path: 'seasons/:id/edit', element: <LazyPage><SeasonFormPage /></LazyPage> },
          { path: 'seasons/:id/episodes', element: <LazyPage><EpisodesPage /></LazyPage> },
          { path: 'episodes/:id/edit', element: <LazyPage><EpisodeFormPage /></LazyPage> },
          { path: 'genres', element: <LazyPage><GenresPage /></LazyPage> },
          { path: 'collections', element: <LazyPage><CollectionsListPage /></LazyPage> },
          { path: 'collections/new', element: <LazyPage><CollectionFormPage /></LazyPage> },
          { path: 'collections/:id/edit', element: <LazyPage><CollectionFormPage /></LazyPage> },
          { path: 'tools/upload', element: <LazyPage><MediaUploadPage /></LazyPage> },
          { path: 'tools/tmdb', element: <LazyPage><TmdbToolsPage /></LazyPage> },
          { path: 'tools/recommendations', element: <LazyPage><RecommendationsInspectPage /></LazyPage> },
          { path: 'media/storage-health', element: <LazyPage><MediaStorageHealthPage /></LazyPage> },
          { path: 'media/processing', element: <LazyPage><MediaProcessingJobsPage /></LazyPage> },
          { path: 'media/playback-sessions', element: <LazyPage><PlaybackSessionsPage /></LazyPage> },
          { path: 'media/:assetId', element: <LazyPage><MediaAssetDetailPage /></LazyPage> },
          { path: 'system/updates', element: <LazyPage><SystemUpdatesPage /></LazyPage> },
          { path: 'tools/encoding', element: <LazyPage><AdminPlaceholderPage section="encoding" /></LazyPage> },
          { path: 'tools/cdn', element: <LazyPage><AdminPlaceholderPage section="cdn" /></LazyPage> },
          { path: 'tools/users', element: <LazyPage><AdminPlaceholderPage section="users" /></LazyPage> },
        ],
      },
      { path: '*', element: customerLazy(<NotFoundPage />) },
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
