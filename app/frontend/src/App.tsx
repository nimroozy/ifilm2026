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
import {
  MoviesPage,
  ChildrenPage,
  SeriesPage,
  MovieDetailsPage,
  SeriesDetailsPage,
  SearchPage,
} from '@/pages/Browse';
import { CollectionsIndexPage, CollectionDetailPage } from '@/pages/CollectionsPages';
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
import CollectionsListPage from '@/pages/admin/CollectionsListPage';
import CollectionFormPage from '@/pages/admin/CollectionFormPage';
import MediaUploadPage from '@/pages/admin/MediaUploadPage';
import MediaAssetDetailPage from '@/pages/admin/MediaAssetDetailPage';
import MediaStorageHealthPage from '@/pages/admin/MediaStorageHealthPage';
import MediaProcessingJobsPage from '@/pages/admin/MediaProcessingJobsPage';
import PlaybackSessionsPage from '@/pages/admin/PlaybackSessionsPage';
import SystemUpdatesPage from '@/pages/admin/SystemUpdatesPage';
import TmdbToolsPage from '@/pages/admin/TmdbToolsPage';
import AdminPlaceholderPage from '@/pages/admin/AdminPlaceholderPage';
import {
  GenresBrowsePage,
  DubbedPage,
  SubtitledPage,
  NewReleasesPage,
} from '@/pages/CatalogBrowsePages';
import WhatToWatchPage from '@/pages/WhatToWatchPage';
import RecommendationsInspectPage from '@/pages/admin/RecommendationsInspectPage';
import NotFoundPage from '@/pages/NotFoundPage';

const AboutPage = lazy(() => import('@/pages/LegalPages'));
const ContactPage = lazy(() => import('@/pages/LegalPages').then((m) => ({ default: m.ContactPage })));
const HelpPage = lazy(() => import('@/pages/LegalPages').then((m) => ({ default: m.HelpPage })));
const PrivacyPage = lazy(() => import('@/pages/LegalPages').then((m) => ({ default: m.PrivacyPage })));
const TermsPage = lazy(() => import('@/pages/LegalPages').then((m) => ({ default: m.TermsPage })));
const CopyrightPage = lazy(() => import('@/pages/LegalPages').then((m) => ({ default: m.CopyrightPage })));

const queryClient = new QueryClient();

function CustomerRoute({ children }: { children: ReactNode }) {
  return <CustomerLayout>{children}</CustomerLayout>;
}

function LazyPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="min-h-[40vh]" data-testid="route-loading" />}>{children}</Suspense>;
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

/** Data router required for useBlocker (unsaved-change guard on MovieFormPage). */
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <CustomerRoute><Index /></CustomerRoute> },
      { path: '/movies', element: <CustomerRoute><MoviesPage /></CustomerRoute> },
      { path: '/series', element: <CustomerRoute><SeriesPage /></CustomerRoute> },
      { path: '/children', element: <CustomerRoute><ChildrenPage /></CustomerRoute> },
      { path: '/kids', element: <Navigate to="/children" replace /> },
      { path: '/genres', element: <CustomerRoute><GenresBrowsePage /></CustomerRoute> },
      { path: '/collections', element: <CustomerRoute><CollectionsIndexPage /></CustomerRoute> },
      { path: '/collections/:slug', element: <CustomerRoute><CollectionDetailPage /></CustomerRoute> },
      { path: '/dubbed', element: <CustomerRoute><DubbedPage /></CustomerRoute> },
      { path: '/subtitled', element: <CustomerRoute><SubtitledPage /></CustomerRoute> },
      { path: '/new-releases', element: <CustomerRoute><NewReleasesPage /></CustomerRoute> },
      { path: '/what-to-watch', element: <CustomerRoute><WhatToWatchPage /></CustomerRoute> },
      { path: '/movie/:id', element: <CustomerRoute><MovieDetailsPage /></CustomerRoute> },
      { path: '/series/:id', element: <CustomerRoute><SeriesDetailsPage /></CustomerRoute> },
      { path: '/search', element: <CustomerRoute><SearchPage /></CustomerRoute> },
      {
        path: '/about',
        element: (
          <CustomerRoute>
            <LazyPage>
              <AboutPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/credits',
        element: (
          <CustomerRoute>
            <LazyPage>
              <AboutPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/contact',
        element: (
          <CustomerRoute>
            <LazyPage>
              <ContactPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/help',
        element: (
          <CustomerRoute>
            <LazyPage>
              <HelpPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/privacy',
        element: (
          <CustomerRoute>
            <LazyPage>
              <PrivacyPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/terms',
        element: (
          <CustomerRoute>
            <LazyPage>
              <TermsPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
      {
        path: '/copyright',
        element: (
          <CustomerRoute>
            <LazyPage>
              <CopyrightPage />
            </LazyPage>
          </CustomerRoute>
        ),
      },
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
          { path: 'collections', element: <CollectionsListPage /> },
          { path: 'collections/new', element: <CollectionFormPage /> },
          { path: 'collections/:id/edit', element: <CollectionFormPage /> },
          { path: 'tools/upload', element: <MediaUploadPage /> },
          { path: 'tools/tmdb', element: <TmdbToolsPage /> },
          { path: 'tools/recommendations', element: <RecommendationsInspectPage /> },
          { path: 'media/storage-health', element: <MediaStorageHealthPage /> },
          { path: 'media/processing', element: <MediaProcessingJobsPage /> },
          { path: 'media/playback-sessions', element: <PlaybackSessionsPage /> },
          { path: 'media/:assetId', element: <MediaAssetDetailPage /> },
          { path: 'system/updates', element: <SystemUpdatesPage /> },
          { path: 'tools/encoding', element: <AdminPlaceholderPage section="encoding" /> },
          { path: 'tools/cdn', element: <AdminPlaceholderPage section="cdn" /> },
          { path: 'tools/users', element: <AdminPlaceholderPage section="users" /> },
        ],
      },
      { path: '*', element: <CustomerRoute><NotFoundPage /></CustomerRoute> },
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
