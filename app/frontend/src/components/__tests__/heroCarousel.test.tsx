import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HeroCarousel } from '@/components/HeroCarousel';
import { AuthProvider, LangProvider } from '@/components/CustomerLayout';
import type { CatalogMovie } from '@/lib/catalogData';

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => true,
  isApiMode: () => false,
}));

function movie(partial: Partial<CatalogMovie> & { id: number; title: string }): CatalogMovie {
  return {
    type: 'movie',
    slug: partial.title.toLowerCase(),
    description: 'Overview text for hero.',
    year: 2024,
    rating: 8.1,
    duration: 120,
    genres: ['Action', 'Drama'],
    poster: '/poster.jpg',
    backdrop: '/backdrop.jpg',
    logoUrl: '',
    playable: true,
    hasPlayablePackage: true,
    ...partial,
  } as CatalogMovie;
}

function renderHero(featured: CatalogMovie[]) {
  return render(
    <LangProvider>
      <AuthProvider>
        <MemoryRouter>
          <HeroCarousel featured={featured} />
        </MemoryRouter>
      </AuthProvider>
    </LangProvider>
  );
}

describe('HeroCarousel G1 manual navigation', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.setItem('ifilm.locale', 'en');
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    window.localStorage.setItem('ifilm.locale', 'en');
  });

  it('does not auto-advance slides (no timer)', () => {
    const featured = [
      movie({ id: 1, title: 'Alpha' }),
      movie({ id: 2, title: 'Beta' }),
    ];
    renderHero(featured);
    expect(screen.getByTestId('hero-carousel')).toHaveAttribute('data-autoplay', 'false');
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Alpha');
    vi.advanceTimersByTime(30_000);
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Alpha');
  });

  it('supports manual next/prev and dots', () => {
    const featured = [
      movie({ id: 1, title: 'Alpha' }),
      movie({ id: 2, title: 'Beta' }),
      movie({ id: 3, title: 'Gamma' }),
    ];
    renderHero(featured);
    fireEvent.click(screen.getByTestId('hero-next'));
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Beta');
    fireEvent.click(screen.getByTestId('hero-prev'));
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Alpha');
    fireEvent.click(screen.getByRole('tab', { name: 'Show Gamma' }));
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Gamma');
  });

  it('uses title logo when logoUrl is present, otherwise text', () => {
    const { rerender } = renderHero([
      movie({ id: 1, title: 'Logo Film', logoUrl: '/logo.png' }),
    ]);
    expect(screen.getByTestId('hero-title-logo')).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: 'Logo Film' })).toBeTruthy();
    expect(screen.getByTestId('hero-title-logo')).toHaveAttribute('alt', '');
    expect(screen.queryByTestId('hero-title-text')).toBeNull();

    rerender(
      <LangProvider>
        <AuthProvider>
          <MemoryRouter>
            <HeroCarousel featured={[movie({ id: 2, title: 'Text Film', logoUrl: '' })]} />
          </MemoryRouter>
        </AuthProvider>
      </LangProvider>
    );
    expect(screen.getByTestId('hero-title-text')).toHaveTextContent('Text Film');
    expect(screen.queryByTestId('hero-title-logo')).toBeNull();
  });

  it('gives every slide selector a mobile-sized touch target', () => {
    renderHero([
      movie({ id: 1, title: 'Alpha' }),
      movie({ id: 2, title: 'Beta' }),
    ]);
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveClass('h-11', 'w-11');
    }
  });

  it('shows My List control (watchlist when authenticated in mock mode)', () => {
    renderHero([movie({ id: 1, title: 'Alpha' })]);
    expect(screen.getAllByTestId('watchlist-toggle').length).toBeGreaterThan(0);
  });

  it('keeps hero actions wrappable so mobile RTL labels are not truncated', () => {
    renderHero([movie({ id: 1, title: 'Alpha' }), movie({ id: 2, title: 'Beta' })]);
    const actions = screen.getByTestId('hero-actions');
    expect(actions.className).toMatch(/flex-wrap/);
    expect(screen.getByTestId('hero-play').querySelector('span')?.className || '').not.toMatch(
      /\btruncate\b/
    );
    expect(screen.getByTestId('hero-more-info').querySelector('span')?.className || '').not.toMatch(
      /\btruncate\b/
    );
  });

  it('keeps synopsis block aligned to UI direction while isolating mixed-script text', () => {
    window.localStorage.setItem('ifilm.locale', 'fa');
    renderHero([movie({ id: 1, title: 'Alpha', description: 'English synopsis with فارسی' })]);
    const synopsis = screen.getByTestId('hero-synopsis');
    expect(synopsis).not.toHaveAttribute('dir', 'auto');
    expect(synopsis.className).toMatch(/text-start/);
    const isolated = synopsis.querySelector('[dir="auto"]');
    expect(isolated).toBeTruthy();
    expect(isolated).toHaveTextContent('English synopsis with فارسی');
  });

  it('localizes demo-clip CTA label', () => {
    window.localStorage.setItem('ifilm.locale', 'fa');
    renderHero([
      movie({
        id: 1,
        title: 'Demo Film',
        playable: false,
        hasPlayablePackage: false,
        hasDemoClip: true,
      }),
    ]);
    expect(screen.getByTestId('hero-play')).toHaveTextContent('پخش کلیپ دمو');
  });

  it('localizes Coming Soon availability for FA and PS', () => {
    window.localStorage.setItem('ifilm.locale', 'fa');
    const { unmount } = renderHero([
      movie({
        id: 1,
        title: 'Soon Film',
        playable: false,
        hasPlayablePackage: false,
        hasDemoClip: false,
      }),
    ]);
    expect(screen.getByTestId('hero-unavailable')).toHaveTextContent('به‌زودی');
    unmount();

    window.localStorage.setItem('ifilm.locale', 'ps');
    renderHero([
      movie({
        id: 2,
        title: 'Soon Film PS',
        playable: false,
        hasPlayablePackage: false,
        hasDemoClip: false,
      }),
    ]);
    expect(screen.getByTestId('hero-unavailable')).toHaveTextContent('ژر راځي');
  });
});
