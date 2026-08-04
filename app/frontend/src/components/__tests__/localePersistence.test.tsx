import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DocumentLangSync from '@/components/DocumentLangSync';
import { LangProvider, useLang } from '@/components/CustomerLayout';
import { LOCALE_STORAGE_KEY } from '@/lib/locale';
import AdminLayout from '@/pages/admin/AdminLayout';
import { tokenStore } from '@/lib/api';
import { vi } from 'vitest';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      me: vi.fn().mockResolvedValue({
        id: 1,
        username: 'admin',
        full_name: 'Admin User',
        role_name: 'Super Admin',
        permissions: [],
      }),
      getSystemVersion: vi.fn(),
    },
  };
});

function PublicProbe() {
  const { dir, lang, setLang, t } = useLang();
  return (
    <div data-testid="public-probe">
      <span data-testid="public-dir">{dir}</span>
      <span data-testid="public-lang">{lang}</span>
      <span data-testid="public-home-label">{t.nav.home}</span>
      <button type="button" onClick={() => setLang('fa')}>
        Set FA
      </button>
      <button type="button" onClick={() => setLang('en')}>
        Set EN
      </button>
      <button type="button" onClick={() => setLang('ps')}>
        Set PS
      </button>
    </div>
  );
}

function renderPublic(initial = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter initialEntries={[initial]}>
          <DocumentLangSync />
          <Routes>
            <Route path="/" element={<PublicProbe />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<div data-testid="admin-page">Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('public locale persistence', () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = `${LOCALE_STORAGE_KEY}=; path=/; max-age=0`;
    document.documentElement.setAttribute('lang', 'en');
    document.documentElement.setAttribute('dir', 'ltr');
    tokenStore.clearAdmin();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('first visit with no saved locale defaults to English LTR', async () => {
    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('en');
    expect(screen.getByTestId('public-dir').textContent).toBe('ltr');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('lang')).toBe('en');
      expect(document.documentElement.getAttribute('dir')).toBe('ltr');
    });
  });

  it('persists English → Persian across remount (refresh)', async () => {
    renderPublic();
    fireEvent.click(screen.getByText('Set FA'));
    await waitFor(() => {
      expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('fa');
      expect(document.documentElement.getAttribute('lang')).toBe('fa');
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    });
    cleanup();

    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('fa');
    expect(screen.getByTestId('public-dir').textContent).toBe('rtl');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('lang')).toBe('fa');
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    });
  });

  it('persists Persian → English across remount', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'fa');
    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('fa');
    fireEvent.click(screen.getByText('Set EN'));
    await waitFor(() => {
      expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    });
    cleanup();

    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('en');
    expect(screen.getByTestId('public-dir').textContent).toBe('ltr');
  });

  it('invalid stored value falls back to English', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'Persian');
    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('en');
    expect(screen.getByTestId('public-dir').textContent).toBe('ltr');
  });

  it('admin stays English/LTR while public preference remains Persian', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'fa');
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LangProvider>
          <MemoryRouter initialEntries={['/admin']}>
            <DocumentLangSync />
            <Routes>
              <Route path="/" element={<PublicProbe />} />
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<div>Dashboard</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </LangProvider>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(document.documentElement.getAttribute('lang')).toBe('en');
      expect(document.documentElement.getAttribute('dir')).toBe('ltr');
    });
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('fa');
  });

  it('returning from admin restores saved public locale', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'fa');
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function NavApp() {
      return (
        <QueryClientProvider client={client}>
          <LangProvider>
            <MemoryRouter initialEntries={['/admin']}>
              <DocumentLangSync />
              <Routes>
                <Route path="/" element={<PublicProbe />} />
                <Route path="/admin" element={<AdminLayout />}>
                  <Route
                    index
                    element={
                      <a href="/" data-testid="back-public">
                        Public
                      </a>
                    }
                  />
                </Route>
              </Routes>
            </MemoryRouter>
          </LangProvider>
        </QueryClientProvider>
      );
    }
    render(<NavApp />);
    await waitFor(() => {
      expect(document.documentElement.getAttribute('lang')).toBe('en');
    });
    cleanup();

    // Simulate leaving admin back to public (new navigation / remount).
    renderPublic('/');
    expect(screen.getByTestId('public-lang').textContent).toBe('fa');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('lang')).toBe('fa');
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    });
  });

  it('logout token clear does not erase locale preference', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'ps');
    tokenStore.clear();
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('ps');
    renderPublic();
    expect(screen.getByTestId('public-lang').textContent).toBe('ps');
  });
});
