import { describe, expect, it } from 'vitest';
import { claimShelfTitle, shelfTitleKey } from '@/lib/homeShelves';

describe('claimShelfTitle', () => {
  it('returns the trimmed title the first time a label is claimed', () => {
    const claimed = new Set<string>();
    expect(claimShelfTitle('  Top Rated  ', claimed)).toBe('Top Rated');
    expect(claimed.has(shelfTitleKey('Top Rated'))).toBe(true);
  });

  it('rejects a later rail with the same visible label', () => {
    const claimed = new Set<string>();
    expect(claimShelfTitle('Top Rated', claimed)).toBe('Top Rated');
    expect(claimShelfTitle(' top rated ', claimed)).toBeNull();
    expect(claimShelfTitle('TOP RATED', claimed)).toBeNull();
  });

  it('allows a different title to render', () => {
    const claimed = new Set<string>();
    expect(claimShelfTitle('New Releases', claimed)).toBe('New Releases');
    expect(claimShelfTitle('Recently Added', claimed)).toBe('Recently Added');
  });

  it('does not reserve an empty title', () => {
    const claimed = new Set<string>();
    expect(claimShelfTitle('   ', claimed)).toBeNull();
    expect(claimed.size).toBe(0);
    expect(claimShelfTitle('Popular Now', claimed)).toBe('Popular Now');
  });
});
