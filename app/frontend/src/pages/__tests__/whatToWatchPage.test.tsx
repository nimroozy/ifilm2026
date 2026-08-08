import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import WhatToWatchPage from '@/pages/WhatToWatchPage';

const whatToWatch = vi.fn();

vi.mock('@/lib/api', () => ({
  api: {
    whatToWatch: (...args: unknown[]) => whatToWatch(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 400) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock('@/components/CustomerLayout', () => ({
  useLang: () => ({
    t: {
      whatToWatch: {
        eyebrow: 'Guided discovery',
        title: 'What to Watch',
        subtitle: 'Answer a few quick questions.',
        step: 'Step',
        results: 'Results',
        askType: 'What are you in the mood to watch?',
        askGenre: 'Any genre preference?',
        askMood: 'Pick a mood',
        askDuration: 'How long do you have?',
        askLanguage: 'Language preference?',
        askSubtitles: 'Do you need subtitles?',
        askPeriod: 'Release period?',
        typeMovie: 'Movie',
        typeSeries: 'Series',
        typeEither: 'Either',
        any: 'Any',
        genreAction: 'Action',
        genreComedy: 'Comedy',
        genreDrama: 'Drama',
        genreSciFi: 'Sci-Fi',
        genreFamily: 'Family',
        genreThriller: 'Thriller',
        moodExciting: 'Exciting',
        moodFunny: 'Funny',
        moodEmotional: 'Emotional',
        moodRelaxing: 'Relaxing',
        moodSuspenseful: 'Suspenseful',
        moodFamily: 'Family',
        durationShort: 'Under 90 min',
        durationMedium: '90–120 min',
        durationLong: 'Over 120 min',
        langOriginal: 'Original',
        langPersian: 'Persian / Dari dub',
        langPashto: 'Pashto dub',
        subsOptional: 'Optional',
        subsRequired: 'Required',
        periodNew: 'New',
        periodModern: 'Modern',
        periodClassic: 'Classic',
        resultsTitle: 'Your matches',
        empty: 'No matches',
        error: 'Unable to load',
        reset: 'Reset',
        tryAgain: 'Try Again',
        back: 'Back',
      },
    },
  }),
}));

describe('WhatToWatchPage', () => {
  beforeEach(() => {
    whatToWatch.mockReset();
  });

  it('walks steps and shows explained results', async () => {
    whatToWatch.mockResolvedValue({
      mode: 'what_to_watch',
      ai: false,
      filters: {},
      count: 1,
      items: [
        {
          content_type: 'movie',
          id: 7,
          slug: 'paddington',
          title: 'Paddington',
          poster_url: 'https://example.test/p.jpg',
          score: 0.7,
          reasons: ['Fits Funny (Comedy)'],
          explanation: 'Fits Funny (Comedy)',
          detail_path: '/movie/paddington',
          playable: true,
        },
      ],
    });

    render(
      <MemoryRouter>
        <WhatToWatchPage />
      </MemoryRouter>
    );

    expect(screen.getByTestId('what-to-watch-page')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('wtw-type-movie'));
    fireEvent.click(screen.getByTestId('wtw-genre-Comedy'));
    fireEvent.click(screen.getByTestId('wtw-mood-funny'));
    fireEvent.click(screen.getByTestId('wtw-duration-any'));
    fireEvent.click(screen.getByTestId('wtw-language-any'));
    fireEvent.click(screen.getByTestId('wtw-subtitles-optional'));
    fireEvent.click(screen.getByTestId('wtw-period-any'));

    await waitFor(() => {
      expect(screen.getByTestId('wtw-results')).toBeInTheDocument();
    });
    expect(whatToWatch).toHaveBeenCalled();
    expect(screen.getByText('Paddington')).toBeInTheDocument();
    expect(screen.getByText('Fits Funny (Comedy)')).toBeInTheDocument();
    expect(screen.getByTestId('wtw-reset')).toBeInTheDocument();
    expect(screen.getByTestId('wtw-try-again')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    whatToWatch.mockResolvedValue({
      mode: 'what_to_watch',
      ai: false,
      filters: {},
      count: 0,
      items: [],
    });

    render(
      <MemoryRouter>
        <WhatToWatchPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTestId('wtw-type-either'));
    fireEvent.click(screen.getByTestId('wtw-genre-any'));
    fireEvent.click(screen.getByTestId('wtw-mood-any'));
    fireEvent.click(screen.getByTestId('wtw-duration-any'));
    fireEvent.click(screen.getByTestId('wtw-language-any'));
    fireEvent.click(screen.getByTestId('wtw-subtitles-any'));
    fireEvent.click(screen.getByTestId('wtw-period-any'));

    await waitFor(() => {
      expect(screen.getByTestId('wtw-empty')).toBeInTheDocument();
    });
  });
});
