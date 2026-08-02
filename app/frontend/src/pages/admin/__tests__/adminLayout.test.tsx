import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';
import AdminLayout from '../AdminLayout';
import DocumentLangSync from '@/components/DocumentLangSync';
import { LangProvider, useLang } from '@/components/CustomerLayout';
import { tokenStore } from '@/lib/api';

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

function PublicRtlProbe() {
  const { dir, lang, setLang } = useLang();
  return (
    <div data-testid="public-probe">
      <span data-testid="public-dir">{dir}</span>
      <span data-testid="public-lang">{lang}</span>
      <button type="button" onClick={() => setLang('fa')}>
        Set FA
      </button>
      <button type="button" onClick={() => setLang('en')}>
        Set EN
      </button>
    </div>
  );
}

function renderAt(initial: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter initialEntries={[initial]}>
          <DocumentLangSync />
          <Routes>
            <Route path="/" element={<PublicRtlProbe />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<div data-testid="admin-page">Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('admin LTR layout', () => {
  beforeEach(() => {
    tokenStore.clearAdmin();
    document.documentElement.setAttribute('dir', 'rtl');
    document.documentElement.setAttribute('lang', 'fa');
  });

  afterEach(() => {
    cleanup();
  });

  it('admin root has dir=ltr and lang=en', async () => {
    renderAt('/admin');
    const root = await screen.findByTestId('admin-layout-root');
    expect(root.getAttribute('dir')).toBe('ltr');
    expect(root.getAttribute('lang')).toBe('en');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('ltr');
      expect(document.documentElement.getAttribute('lang')).toBe('en');
    });
  });

  it('desktop sidebar uses left positioning and content uses lg:ml-64', async () => {
    renderAt('/admin');
    const sidebar = await screen.findByTestId('admin-desktop-sidebar');
    expect(sidebar.className).toContain('fixed');
    expect(sidebar.className).toContain('left-0');
    expect(sidebar.className).toContain('top-0');
    expect(sidebar.className).toContain('h-screen');
    expect(sidebar.className).toContain('w-64');
    expect(sidebar.className).toContain('border-r');
    expect(sidebar.className).not.toContain('right-0');

    const content = screen.getByTestId('admin-content-wrapper');
    expect(content.className).toContain('lg:ml-64');
    expect(content.className).not.toContain('lg:mr-64');
  });

  it('sidebar stays left when public locale is Persian/Dari', async () => {
    // Start on a public RTL page, then navigate into admin via remount with shared provider state.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LangProvider>
          <MemoryRouter initialEntries={['/']}>
            <DocumentLangSync />
            <Routes>
              <Route path="/" element={<PublicRtlProbe />} />
              <Route path="/admin" element={<AdminLayout />}>
                <Route index element={<div>Dashboard</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </LangProvider>
      </QueryClientProvider>
    );
    expect(screen.getByTestId('public-dir').textContent).toBe('rtl');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    });
    cleanup();

    // Public lang context defaults to fa; admin must still force LTR left sidebar.
    renderAt('/admin');
    const sidebar = await screen.findByTestId('admin-desktop-sidebar');
    expect(sidebar.className).toContain('left-0');
    expect(sidebar.className).not.toContain('right-0');
    expect(screen.getByTestId('admin-layout-root').getAttribute('dir')).toBe('ltr');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('ltr');
      expect(document.documentElement.getAttribute('lang')).toBe('en');
    });
  });

  it('mobile drawer opens from the left', async () => {
    renderAt('/admin');
    fireEvent.click(await screen.findByTestId('admin-mobile-menu-button'));
    const drawer = await screen.findByTestId('admin-mobile-drawer');
    expect(drawer.getAttribute('dir')).toBe('ltr');
    expect(drawer.className).toMatch(/left-0|slide-in-from-left/);
    // Sheet variant for side=left includes physical left-0.
    expect(drawer.className).toContain('left-0');
    expect(drawer.className).not.toContain('right-0');
  });

  it('public application still supports RTL', async () => {
    renderAt('/');
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
      expect(document.documentElement.getAttribute('lang')).toBe('fa');
    });
    expect(screen.getByTestId('public-dir').textContent).toBe('rtl');
    fireEvent.click(screen.getByText('Set EN'));
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('ltr');
      expect(document.documentElement.getAttribute('lang')).toBe('en');
    });
    fireEvent.click(screen.getByText('Set FA'));
    await waitFor(() => {
      expect(document.documentElement.getAttribute('dir')).toBe('rtl');
      expect(document.documentElement.getAttribute('lang')).toBe('fa');
    });
  });
});

describe('production metadata cleanup', () => {
  it('index.html has iFilm Admin metadata and local favicon', () => {
    const htmlPath = path.resolve(__dirname, '../../../../index.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    expect(html).toContain('<title>iFilm Admin</title>');
    expect(html).toContain('content="iFilm media and catalog administration"');
    expect(html).toContain('href="/favicon.svg"');
    expect(html).not.toContain('Atoms Generated Project');
    expect(html).not.toContain('metadl.com');
    expect(html).not.toContain('favicon_atoms');
    expect(html).not.toContain('data-mgx-overview');
  });

  it('local favicon exists and vite defaults are not MGX', () => {
    const faviconPath = path.resolve(__dirname, '../../../../public/favicon.svg');
    expect(fs.existsSync(faviconPath)).toBe(true);
    const viteConfig = fs.readFileSync(
      path.resolve(__dirname, '../../../../vite.config.ts'),
      'utf8'
    );
    expect(viteConfig).toContain("'iFilm Admin'");
    expect(viteConfig).toContain('iFilm media and catalog administration');
    expect(viteConfig).toContain("'/favicon.svg'");
    expect(viteConfig).not.toContain('Atoms Generated Project');
    expect(viteConfig).not.toContain('metadl.com');
  });
});
