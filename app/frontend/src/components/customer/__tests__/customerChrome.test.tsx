import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, cleanup, within, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CustomerLayout, { LangProvider, AuthProvider } from '@/components/CustomerLayout';

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => true,
  isApiMode: () => false,
}));

function wrap(ui: ReactNode, path = '/') {
  return render(
    <LangProvider>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="*" element={<CustomerLayout>{ui}</CustomerLayout>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </LangProvider>
  );
}

describe('customer navigation and footer chrome', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: String(query).includes('1536'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => cleanup());

  it('renders desktop nav destinations including Phase 3 links', () => {
    wrap(<div>home</div>, '/');
    const nav = screen.getByTestId('desktop-nav');
    expect(within(nav).getByTestId('desktop-nav-home')).toBeTruthy();
    expect(within(nav).getByTestId('desktop-nav-genres')).toBeTruthy();
    expect(within(nav).getByTestId('desktop-nav-dubbed')).toBeTruthy();
    expect(within(nav).getByTestId('desktop-nav-subtitled')).toBeTruthy();
    expect(within(nav).getByTestId('desktop-nav-newReleases')).toBeTruthy();
    expect(within(nav).getByTestId('desktop-nav-collections')).toBeTruthy();
  });

  it('marks active route for nested movie detail', () => {
    wrap(<div>detail</div>, '/movie/42');
    expect(screen.getByTestId('desktop-nav-movies')).toHaveAttribute('data-active', 'true');
    expect(screen.getByTestId('desktop-nav-home')).toHaveAttribute('data-active', 'false');
  });

  it('renders complete footer links, TMDB attribution, and real social only', () => {
    wrap(<div>home</div>, '/');
    expect(screen.getByTestId('customer-footer')).toBeTruthy();
    expect(screen.getByTestId('footer-link-about')).toBeTruthy();
    expect(screen.getByTestId('footer-link-contact')).toBeTruthy();
    expect(screen.getByTestId('footer-link-help')).toBeTruthy();
    expect(screen.getByTestId('footer-link-privacy')).toBeTruthy();
    expect(screen.getByTestId('footer-link-terms')).toBeTruthy();
    expect(screen.getByTestId('footer-link-copyright')).toBeTruthy();
    expect(screen.getByTestId('footer-tmdb')).toHaveTextContent(/TMDB/i);
    expect(screen.getByTestId('footer-social-website')).toHaveAttribute(
      'href',
      'https://mobinnet.af/'
    );
    expect(screen.getByTestId('footer-social-facebook')).toHaveAttribute(
      'href',
      'https://www.facebook.com/mobinnetict'
    );
    expect(screen.queryByText(/app store|google play/i)).toBeNull();
  });

  it('opens mobile sheet with catalog and legal destinations', async () => {
    wrap(<div>home</div>, '/');
    fireEvent.click(screen.getByTestId('mobile-nav-trigger'));
    expect(await screen.findByTestId('mobile-nav-sheet')).toBeTruthy();
    expect(screen.getByTestId('mobile-nav-genres')).toBeTruthy();
    expect(screen.getByTestId('mobile-footer-privacy')).toBeTruthy();
  });

  it('collapses secondary desktop destinations into More below xl', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    wrap(<div>home</div>, '/dubbed');
    const more = screen.getByTestId('desktop-nav-more');
    expect(more).toBeTruthy();
    expect(more).toHaveAttribute('aria-haspopup', 'menu');
    // Secondary destinations leave the inline row; More reflects active overflow route.
    expect(screen.queryByTestId('desktop-nav-dubbed')).toBeNull();
    expect(more.className).toMatch(/text-primary/);
  });
});
