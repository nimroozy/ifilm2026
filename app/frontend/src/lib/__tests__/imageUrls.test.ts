import { describe, expect, it } from 'vitest';
import { heroBackdropSrcSet, sizedArtworkUrl } from '@/lib/imageUrls';

describe('sizedArtworkUrl', () => {
  it('rewrites TMDB poster sizes for cards', () => {
    const src = 'https://image.tmdb.org/t/p/original/abc.jpg';
    expect(sizedArtworkUrl(src, 'poster', 'card')).toBe(
      'https://image.tmdb.org/t/p/w342/abc.jpg'
    );
  });

  it('rewrites TMDB backdrop sizes for hero', () => {
    const src = 'https://image.tmdb.org/t/p/original/bg.jpg';
    expect(sizedArtworkUrl(src, 'backdrop', 'hero')).toBe(
      'https://image.tmdb.org/t/p/w1280/bg.jpg'
    );
  });

  it('leaves local artwork unchanged', () => {
    const src = '/media/artwork/poster.jpg';
    expect(sizedArtworkUrl(src, 'poster', 'card')).toBe(src);
  });
});

describe('heroBackdropSrcSet', () => {
  it('provides w780 default and w1280 candidate (never original)', () => {
    const src = 'https://image.tmdb.org/t/p/original/bg.jpg';
    const out = heroBackdropSrcSet(src);
    expect(out.src).toBe('https://image.tmdb.org/t/p/w780/bg.jpg');
    expect(out.srcSet).toContain('w780');
    expect(out.srcSet).toContain('w1280');
    expect(out.src).not.toContain('/original/');
    expect(out.srcSet).not.toContain('/original/');
  });
});
