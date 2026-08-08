import { describe, expect, it } from 'vitest';
import { sizedArtworkUrl } from '@/lib/imageUrls';

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
