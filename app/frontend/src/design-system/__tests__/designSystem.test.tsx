import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ContentShelf, MediaCard, MetaRow, RatingBadge, StatusChip } from '@/design-system';

describe('design system', () => {
  it('renders MediaCard with rating, demo, quality, and progress', () => {
    const onActivate = vi.fn();
    render(
      <MediaCard
        title="Sample Film"
        imageUrl="/poster.jpg"
        year={2024}
        rating={8.4}
        quality="1080p"
        showDemo
        playable
        progress={42}
        onActivate={onActivate}
      />
    );
    expect(screen.getByTestId('media-card')).toBeInTheDocument();
    expect(screen.getByText('Sample Film')).toBeInTheDocument();
    expect(screen.getByTestId('rating-badge')).toHaveTextContent('8.4');
    expect(screen.getByTestId('demo-clip-badge')).toBeInTheDocument();
    expect(screen.getByTestId('quality-badge')).toHaveTextContent('1080p');
    expect(screen.getByTestId('media-card-progress')).toHaveStyle({ width: '42%' });
    expect(screen.getByTestId('media-card-play')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('media-card'));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('hides Play overlay unless content is playable', () => {
    const { rerender } = render(<MediaCard title="Unavailable Film" />);
    expect(screen.queryByTestId('media-card-play')).not.toBeInTheDocument();
    rerender(<MediaCard title="Playable Film" playable />);
    expect(screen.getByTestId('media-card-play')).toBeInTheDocument();
  });

  it('supports keyboard activation on MediaCard', () => {
    const onActivate = vi.fn();
    render(<MediaCard title="Key Film" onActivate={onActivate} />);
    const card = screen.getByTestId('media-card');
    fireEvent.keyDown(card, { key: 'Enter' });
    fireEvent.keyDown(card, { key: ' ' });
    expect(onActivate).toHaveBeenCalledTimes(2);
  });

  it('renders ContentShelf title and children', () => {
    render(
      <ContentShelf title="Trending">
        <MediaCard title="Alpha Title" imageUrl="/a.jpg" />
        <MediaCard title="Beta Title" imageUrl="/b.jpg" />
      </ContentShelf>
    );
    expect(screen.getByTestId('content-shelf')).toBeInTheDocument();
    expect(screen.getByText('Trending')).toBeInTheDocument();
    expect(screen.getByText('Alpha Title')).toBeInTheDocument();
    expect(screen.getByText('Beta Title')).toBeInTheDocument();
    expect(screen.getAllByTestId('media-card')).toHaveLength(2);
  });

  it('exposes motion presets', async () => {
    const { motionClass, motionPresets } = await import('@/design-system');
    expect(motionPresets.fadeIn).toContain('fade-in');
    expect(motionClass('fadeIn', 'hoverLift')).toContain('animate-fade-in');
  });
});
