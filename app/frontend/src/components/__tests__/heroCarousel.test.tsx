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
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
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

  it('shows My List control (watchlist when authenticated in mock mode)', () => {
    renderHero([movie({ id: 1, title: 'Alpha' })]);
    expect(
      screen.queryByTestId('watchlist-toggle') || screen.queryByTestId('hero-my-list-signin')
    ).toBeTruthy();
  });
});
