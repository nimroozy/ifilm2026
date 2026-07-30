import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import CustomerLayout, { LangProvider, AuthProvider } from '@/components/CustomerLayout';
import Index from '@/pages/Index';
import { MoviesPage, SeriesPage, MovieDetailsPage, SeriesDetailsPage, PlayerPage, SearchPage } from '@/pages/Browse';
import { LoginPage, ProfilePage, DevicesPage, WatchlistPage, HistoryPage } from '@/pages/Account';
import AdminPage from '@/pages/Admin';

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
    <Route path="/player/:id" element={<PlayerPage />} />
    {/* Admin */}
    <Route path="/admin" element={<AdminPage />} />
  </Routes>
);

const App = () => (
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
);

export default App;
export { AppRoutes };