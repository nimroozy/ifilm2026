import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MediaCard } from '@/design-system/MediaCard';
import { LangProvider } from '@/components/CustomerLayout';

describe('MediaCard localized a11y and touch targets', () => {
  beforeEach(() => {
    window.localStorage.setItem('ifilm.locale', 'fa');
  });

  it('uses Persian aria-labels and at least 44px control targets', () => {
    render(
      <LangProvider>
        <MediaCard
          title="فیلم نمونه"
          playable
          onActivate={() => undefined}
          onMyList={() => undefined}
        />
      </LangProvider>
    );

    const play = screen.getByTestId('media-card-play');
    const myList = screen.getByTestId('media-card-mylist');
    const details = screen.getByTestId('media-card-details');

    expect(play).toHaveAttribute('aria-label', 'پخش فیلم نمونه');
    expect(myList).toHaveAttribute('aria-label', 'لیست من فیلم نمونه');
    expect(details).toHaveAttribute('aria-label', 'جزئیات فیلم نمونه');

    for (const el of [play, myList, details]) {
      expect(el.className).toMatch(/min-h-11/);
      expect(el.className).toMatch(/min-w-11/);
    }
  });
});
